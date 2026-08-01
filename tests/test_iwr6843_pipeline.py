"""End-to-end tests for the openflight.iwr6843 shot pipeline.

A synthetic moving ball is packed into the exact wire format (pack_dump is
the executable spec the firmware mirrors), then the full chain — parse, MTI,
track, TDM correction, MUSIC, trajectory fits — must recover the truth.
Conventions locked here: ImRe byte order, TDM phase sign, physical-orientation
flip, header-driven geometry and time order.
"""

from __future__ import annotations

import numpy as np
import pytest

from openflight.iwr6843 import Calibration, estimate_lcmf_v1, lcmf, process_dump
from openflight.iwr6843.dump import (
    HEADER,
    MAGIC,
    MAX_SUPPORTED_DUMP_VERSION,
    SAMPLE_RANGE_FFT_IQ16,
    SAMPLE_RANGE_FFT_IQ16_WINDOWED,
    TEMP_REPORT_KEYS,
    pack_dump,
    parse_dump,
    parse_header,
    payload_nbytes,
    project_tx_pair,
)
from openflight.iwr6843.lcmf import (
    ANGLE_CORRECTION_DEG,
    TX2_LOOP_PERIOD_S,
    TX2_VERTICAL_TDM_TAU_S,
    _tx2_horizontal_proxy,
)
from openflight.iwr6843.music import LAM, steer
from openflight.iwr6843.shot import ShotMeasurement, geometry_from_header
from openflight.iwr6843.tracking import LOOP_PRI_S, RANGE_SPAN_M, BallTrack

TAU_S = 45e-6
RADAR_HEIGHT_M = 0.152


def synth_shot(
    *,
    speed_ms=45.0,
    launch_deg=18.0,
    tee_m=1.5,
    tilt_deg=10.4,
    n_frames=12,
    n_loops=16,
    n_tx=2,
    n_samples=128,
    frame_period_us=6000,
    trigger_frame=3,
    amp=400.0,
    noise=6.0,
    image_gain=0.0,
    accel_ms2=0.0,
    seed=0,
    tx_order="normal",
):
    """Raw dump bytes for one synthetic ball flight (+ optional floor image).

    The cube is built in CHIP conventions (the reverse of physical element
    order; TX1 block carries the +Doppler TDM phase) so the pipeline's
    decode path is what's under test. ``accel_ms2`` makes the radial speed
    time-varying (Doppler phase follows the true displacement; the TDM
    phase follows the INSTANTANEOUS velocity).
    """
    rng = np.random.default_rng(seed)
    res = RANGE_SPAN_M / n_samples
    if n_tx not in (2, 3):
        raise ValueError(f"unsupported TX count: {n_tx}")
    cpf = n_tx * n_loops
    loop_period_s = LOOP_PRI_S if n_tx == 2 else TX2_LOOP_PERIOD_S
    tdm_tau_s = TAU_S if n_tx == 2 else TX2_VERTICAL_TDM_TAU_S
    cube = np.zeros((n_frames, cpf, 4, n_samples), dtype=complex)
    samples = np.arange(n_samples)
    tan_la = np.tan(np.radians(launch_deg))
    for slot in range(n_frames):
        t_slot = ((slot - trigger_frame) % n_frames) * frame_period_us / 1e6
        for loop in range(n_loops):
            t_s = t_slot + loop * loop_period_s
            disp = speed_ms * t_s + 0.5 * accel_ms2 * t_s * t_s
            v_inst = speed_ms + accel_ms2 * t_s
            x_m = tee_m + disp
            h_m = tan_la * (x_m - tee_m)  # height above radar plane
            theta = np.arctan2(h_m, x_m) - np.radians(tilt_deg)
            rbin = x_m / res
            if rbin >= n_samples - 2:
                continue
            tone = np.exp(2j * np.pi * rbin * samples / n_samples)
            phys = steer(theta, 8)
            if image_gain:
                theta_img = np.arctan2(-(h_m + 2 * RADAR_HEIGHT_M), x_m) - np.radians(tilt_deg)
                phys = phys + image_gain * steer(theta_img, 8)
            chip = phys[::-1].copy()  # physical -> chip order
            doppler = np.exp(1j * 4 * np.pi * disp / LAM)
            tdm = np.exp(1j * 4 * np.pi * v_inst * tdm_tau_s / LAM)
            if tx_order == "normal":
                chirp0, chirp1 = chip[:4], chip[4:] * tdm
            elif tx_order == "reversed":
                chirp0, chirp1 = chip[4:], chip[:4] * tdm
            else:
                raise ValueError(f"unsupported TX order: {tx_order}")
            for rx in range(4):
                chirp_base = n_tx * loop
                cube[slot, chirp_base, rx] = amp * doppler * chirp0[rx] * tone
                cube[slot, chirp_base + n_tx - 1, rx] = amp * doppler * chirp1[rx] * tone
    cube += rng.standard_normal(cube.shape) * noise + 1j * rng.standard_normal(cube.shape) * noise
    return pack_dump(
        cube, n_tx=n_tx, trigger_frame=trigger_frame, version=3, frame_period_us=frame_period_us
    )


def range_snapshot_dump(raw: bytes, *, start_bin: int = 20, n_bins: int = 80) -> bytes:
    """Convert a raw ADC dump into the HWA range-snapshot wire format."""
    meta, cube = parse_dump(raw)
    rfft = np.fft.fft(cube, axis=-1)
    return pack_dump(
        rfft[..., start_bin : start_bin + n_bins],
        n_tx=meta["n_tx"],
        trigger_frame=meta["trigger_frame"],
        version=meta["version"],
        frame_period_us=meta["frame_period_us"],
        sample_fmt=SAMPLE_RANGE_FFT_IQ16,
        range_bin_start=start_bin,
    )


def windowed_range_snapshot_dump(
    raw: bytes, *, starts_chronological: tuple[int, ...], n_bins: int = 53
) -> bytes:
    """Convert raw ADC into v4 per-frame range windows."""
    meta, cube = parse_dump(raw)
    rfft = np.fft.fft(cube, axis=-1)
    starts_memory = tuple(
        starts_chronological[(slot - meta["trigger_frame"]) % meta["n_frames"]]
        for slot in range(meta["n_frames"])
    )
    cropped = np.stack(
        [frame[..., start : start + n_bins] for frame, start in zip(rfft, starts_memory)]
    )
    return pack_dump(
        cropped,
        n_tx=meta["n_tx"],
        trigger_frame=meta["trigger_frame"],
        version=4,
        frame_period_us=meta["frame_period_us"],
        sample_fmt=SAMPLE_RANGE_FFT_IQ16_WINDOWED,
        range_bin_starts=starts_memory,
    )


@pytest.fixture(name="cal")
def _cal():
    cal = Calibration.identity()
    cal.tilt_rad = np.radians(10.4)
    cal.tee_range_m = 1.5
    # synthetic flights launch AT the radar plane -> ball height above the
    # floor equals the radar height (anchor h = 0 in radar-plane coords)
    cal.tee_ball_height_m = RADAR_HEIGHT_M
    cal.meta["radar_height_m"] = RADAR_HEIGHT_M
    return cal


def test_header_carries_period_and_trigger():
    raw = synth_shot(frame_period_us=6000, trigger_frame=5)
    meta = parse_header(raw)
    assert meta["frame_period_us"] == 6000
    assert meta["trigger_frame"] == 5
    geo = geometry_from_header(meta)
    assert geo.frame_period_s == pytest.approx(0.006)
    assert geo.n_loops == 16


def test_parse_header_rejects_future_dump_version():
    raw = synth_shot()
    future = bytearray(raw[:HEADER.size])
    future[4:6] = int(MAX_SUPPORTED_DUMP_VERSION + 1).to_bytes(2, "little")

    with pytest.raises(ValueError, match="unsupported dump version"):
        parse_header(bytes(future))


def test_parse_header_rejects_short_temperature_extension():
    raw = synth_shot()
    v5_header_only = bytearray(raw[:HEADER.size])
    v5_header_only[4:6] = int(MAX_SUPPORTED_DUMP_VERSION).to_bytes(2, "little")

    with pytest.raises(ValueError, match="short temperature report extension"):
        parse_header(bytes(v5_header_only))


def test_pack_dump_rejects_temperature_version_mismatches():
    cube = np.zeros((2, 4, 4, 8), dtype=complex)
    report = {key: index for index, key in enumerate(TEMP_REPORT_KEYS)}

    with pytest.raises(ValueError, match="temperature reports require dump version 5"):
        pack_dump(cube, n_tx=2, version=4, temperature_report=report)

    with pytest.raises(ValueError, match="dump version 5\\+ requires a temperature report"):
        pack_dump(cube, n_tx=2, version=5)


def test_parse_dump_rejects_short_window_table():
    header = HEADER.pack(
        MAGIC,
        4,
        4,
        6,
        3,
        4,
        53,
        SAMPLE_RANGE_FFT_IQ16_WINDOWED,
        0,
        0,
        4000,
    )

    with pytest.raises(ValueError, match="short per-frame range-window table"):
        parse_dump(header + b"\x14\x14")


def test_parse_dump_rejects_truncated_payload():
    raw = synth_shot()

    with pytest.raises(ValueError, match="short payload"):
        parse_dump(raw[:-1])


def test_recovers_speed_and_launch_angle(cal):
    truth_v, truth_la = 45.0, 18.0
    raw = synth_shot(speed_ms=truth_v, launch_deg=truth_la)
    shot = process_dump(raw, cal, coherent_loops=1, two_ray=False)
    assert shot.ball_found
    assert shot.track.speed_ms == pytest.approx(truth_v, rel=0.02)
    assert shot.fits["tee"].launch_angle_deg == pytest.approx(truth_la, abs=1.5)


def test_range_snapshot_recovers_speed_and_launch_angle(cal):
    """Snapshot dumps store selected FFT bins, not raw ADC fast-time samples."""
    truth_v, truth_la = 45.0, 18.0
    raw = range_snapshot_dump(
        synth_shot(speed_ms=truth_v, launch_deg=truth_la, n_loops=10),
        start_bin=20,
        n_bins=80,
    )

    shot = process_dump(raw, cal, coherent_loops=1, two_ray=False)

    assert shot.ball_found
    assert shot.track.speed_ms == pytest.approx(truth_v, rel=0.02)
    assert shot.fits["tee"].launch_angle_deg == pytest.approx(truth_la, abs=1.5)
    assert shot.to_dict()["geometry"]["range_bin_start"] == 20
    assert shot.to_dict()["geometry"]["range_fft_size"] == 128


def test_range_snapshot_tx_projection_preserves_absolute_bins():
    rng = np.random.default_rng(22)
    cube = rng.standard_normal((12, 30, 4, 128)) + 1j * rng.standard_normal((12, 30, 4, 128))
    raw = pack_dump(cube, n_tx=3, trigger_frame=4, version=3, frame_period_us=6000)
    snapshot = range_snapshot_dump(raw, start_bin=20, n_bins=80)

    projected = project_tx_pair(snapshot, (0, 2))
    meta, parsed = parse_dump(projected)
    geo = geometry_from_header(meta, loop_period_s=TX2_LOOP_PERIOD_S)

    assert meta["sample_fmt"] == SAMPLE_RANGE_FFT_IQ16
    assert meta["range_bin_start"] == 20
    assert parsed.shape == (12, 20, 4, 80)
    assert geo.range_res_m == pytest.approx(RANGE_SPAN_M / 128)
    assert geo.local_bin(34) == 14
    assert geo.contains_bin(34)
    assert not geo.contains_bin(110)


def test_windowed_snapshot_round_trip_and_size():
    raw = synth_shot(n_loops=10, trigger_frame=3)
    starts = (20,) * 4 + (32,) * 4 + (47,) * 4
    snapshot = windowed_range_snapshot_dump(raw, starts_chronological=starts)

    header = parse_header(snapshot)
    meta, cube = parse_dump(snapshot)

    assert header["version"] == 4
    assert header["sample_fmt"] == SAMPLE_RANGE_FFT_IQ16_WINDOWED
    assert header["frame_metadata_nbytes"] == 12
    assert len(snapshot) == HEADER.size + payload_nbytes(header)
    assert cube.shape == (12, 20, 4, 53)
    assert tuple(meta["range_bin_starts"][(3 + index) % 12] for index in range(12)) == starts


def test_windowed_snapshot_temperature_report_round_trip_and_projection():
    rng = np.random.default_rng(24)
    starts = (20, 20, 32, 32)
    cube = rng.standard_normal((4, 6, 4, 53)) + 1j * rng.standard_normal((4, 6, 4, 53))
    report = {key: index + 100 for index, key in enumerate(TEMP_REPORT_KEYS)}
    raw = pack_dump(
        cube,
        n_tx=3,
        trigger_frame=1,
        version=5,
        frame_period_us=4000,
        sample_fmt=SAMPLE_RANGE_FFT_IQ16_WINDOWED,
        range_bin_starts=starts,
        temperature_report=report,
    )

    header = parse_header(raw)
    meta, parsed = parse_dump(raw)
    projected_meta, projected = parse_dump(project_tx_pair(raw, (0, 2)))

    assert header["temperature_report"] == report
    assert header["header_nbytes"] == HEADER.size + 24
    assert meta["range_bin_starts"] == starts
    assert parsed.shape == cube.shape
    assert projected_meta["temperature_report"] == report
    assert projected_meta["range_bin_starts"] == starts
    assert projected.shape == (4, 4, 4, 53)


def test_windowed_snapshot_recovers_speed_and_launch_angle(cal):
    truth_v, truth_la = 45.0, 18.0
    starts = (20,) * 4 + (32,) * 4 + (47,) * 4
    raw = windowed_range_snapshot_dump(
        synth_shot(
            speed_ms=truth_v,
            launch_deg=truth_la,
            n_loops=10,
            trigger_frame=3,
        ),
        starts_chronological=starts,
    )

    shot = process_dump(raw, cal, coherent_loops=1, two_ray=False)

    assert shot.ball_found
    assert shot.track.speed_ms == pytest.approx(truth_v, rel=0.02)
    assert shot.fits["tee"].launch_angle_deg == pytest.approx(truth_la, abs=1.5)
    assert shot.geometry.range_bin_starts is not None


def test_windowed_12_loop_18_frame_server_geometry(cal):
    """The TrackMan test firmware is decoded entirely from its v4 header."""
    truth_v, truth_la = 45.0, 18.0
    raw_3tx = synth_shot(
        speed_ms=truth_v,
        launch_deg=truth_la,
        n_frames=18,
        n_loops=12,
        n_tx=3,
        frame_period_us=4000,
        trigger_frame=6,
    )
    starts = (20,) * 6 + (32,) * 6 + (47,) * 6
    raw = windowed_range_snapshot_dump(raw_3tx, starts_chronological=starts)

    shot = process_dump(raw, cal, coherent_loops=1, two_ray=False)

    assert shot.ball_found
    assert shot.geometry.n_frames == 18
    assert shot.geometry.n_loops == 12
    assert shot.geometry.frame_period_s == pytest.approx(0.004)
    assert len(shot.geometry.range_bin_starts or ()) == 18
    assert shot.track.speed_ms == pytest.approx(truth_v, rel=0.02)
    assert shot.fits["tee"].launch_angle_deg == pytest.approx(truth_la, abs=1.5)


def test_windowed_snapshot_tx_projection_preserves_frame_starts():
    rng = np.random.default_rng(23)
    starts = (20, 20, 20, 20, 32, 32, 32, 32, 47, 47, 47, 47)
    cube = rng.standard_normal((12, 30, 4, 53)) + 1j * rng.standard_normal((12, 30, 4, 53))
    raw = pack_dump(
        cube,
        n_tx=3,
        trigger_frame=4,
        version=4,
        frame_period_us=6000,
        sample_fmt=SAMPLE_RANGE_FFT_IQ16_WINDOWED,
        range_bin_starts=starts,
    )

    projected = project_tx_pair(raw, (0, 2))
    meta, parsed = parse_dump(projected)
    geo = geometry_from_header(meta, loop_period_s=TX2_LOOP_PERIOD_S)

    assert parsed.shape == (12, 20, 4, 53)
    assert meta["range_bin_starts"] == starts
    assert geo.local_bin(52, frame=8) == 5
    assert geo.contains_bin(52, margin=1, frame=8)
    assert not geo.contains_bin(40, frame=8)


def test_reversed_tx_order_recovers_same_speed_and_angle(cal):
    normal = process_dump(
        synth_shot(launch_deg=18.0, tx_order="normal"),
        cal,
        club="9i",
        tx_order="normal",
    )
    reversed_order = process_dump(
        synth_shot(launch_deg=18.0, tx_order="reversed"),
        cal,
        club="9i",
        tx_order="reversed",
    )

    assert reversed_order.ball_speed_mph == pytest.approx(normal.ball_speed_mph, abs=0.1)
    assert reversed_order.launch_angle_deg == pytest.approx(18.0, abs=1.5)


def test_tx_orders_canonicalize_to_same_physical_array():
    from openflight.iwr6843.doa import canonicalize_tx_blocks

    physical_chip_order = np.arange(8, dtype=complex)
    phase = 0.37
    normal = canonicalize_tx_blocks(
        physical_chip_order[:4],
        physical_chip_order[4:] * np.exp(1j * phase),
        tdm_phase=phase,
        tx_order="normal",
    )
    reversed_order = canonicalize_tx_blocks(
        physical_chip_order[4:],
        physical_chip_order[:4] * np.exp(1j * phase),
        tdm_phase=phase,
        tx_order="reversed",
    )

    np.testing.assert_allclose(normal, physical_chip_order[::-1])
    np.testing.assert_allclose(reversed_order, physical_chip_order[::-1])


def test_production_config_uses_normal_three_tx_order():
    from openflight.iwr6843.monitor import tx_order_from_config

    assert tx_order_from_config("config/iwr6843_l3dump_vTX2_window53_12l18f.cfg") == "normal"


def test_invalid_tx_order_is_rejected_before_processing(cal):
    with pytest.raises(ValueError, match="tx_order"):
        process_dump(synth_shot(), cal, tx_order="unknown")


def test_tdm_sign_policy_is_resolved_once_and_logged(cal, monkeypatch):
    """One shot must use one Doppler sign across every angle estimator."""
    from openflight.iwr6843 import doa

    calls = 0
    original = doa.measure_tdm_sign

    def counted_measure(mti, track, geo):
        nonlocal calls
        calls += 1
        return original(mti, track, geo)

    monkeypatch.setattr(doa, "measure_tdm_sign", counted_measure)
    shot = process_dump(synth_shot(), cal, tdm_sign_policy="auto")

    assert calls == 1
    assert shot.tdm_sign_policy == "auto"
    assert shot.tdm_sign_used == 1
    assert shot.to_dict()["tdm_sign_policy"] == "auto"
    assert shot.to_dict()["tdm_sign_used"] == 1

    calls = 0
    fixed = process_dump(synth_shot(), cal, tdm_sign_policy="positive")
    assert calls == 0
    assert fixed.tdm_sign_policy == "positive"
    assert fixed.tdm_sign_used == 1
    assert fixed.launch_angle_deg == pytest.approx(18.0, abs=2.0)


def test_invalid_tdm_sign_policy_is_rejected_before_parsing(cal):
    with pytest.raises(ValueError, match="tdm_sign_policy"):
        process_dump(b"not a dump", cal, tdm_sign_policy="guess")


def test_time_order_uses_header_rotation(cal):
    for trig in (0, 4, 9):
        raw = synth_shot(trigger_frame=trig)
        shot = process_dump(raw, cal, coherent_loops=1, two_ray=False)
        assert shot.ball_found, f"trigger_frame={trig}"
        assert shot.track.speed_ms == pytest.approx(45.0, rel=0.03)


def test_coherent_integration_raises_snr(cal):
    raw = synth_shot(noise=25.0)
    shot_k1 = process_dump(raw, cal, coherent_loops=1, two_ray=False)
    shot_k4 = process_dump(raw, cal, coherent_loops=4, two_ray=False)
    assert shot_k4.ball_found
    # K=4 sums 4 loops coherently: fewer points, each ~4x the energy
    assert 0 < shot_k4.n_angle_points <= shot_k1.n_angle_points
    assert shot_k4.fits["free"].launch_angle_deg == pytest.approx(18.0, abs=2.0)


def test_two_ray_recovers_angle_under_multipath(cal):
    """With a strong floor image the plain fits bend; two-ray should not."""
    raw = synth_shot(image_gain=0.6, noise=4.0)
    shot = process_dump(raw, cal, coherent_loops=2, two_ray=True)
    assert shot.ball_found
    assert "two_ray" in shot.fits
    assert shot.fits["two_ray"].launch_angle_deg == pytest.approx(18.0, abs=2.0)


def test_no_ball_in_empty_scene(cal):
    rng = np.random.default_rng(1)
    cube = (
        rng.standard_normal((12, 32, 4, 128)) + 1j * rng.standard_normal((12, 32, 4, 128))
    ) * 8.0
    raw = pack_dump(cube, n_tx=2, version=3, frame_period_us=6000)
    shot = process_dump(raw, Calibration.identity())
    assert not shot.ball_found
    assert shot.summary() == "no ball detected"


def _two_streak_cube(*, slow_ms=24.0, fast_ms=60.0, n_frames=12, n_loops=16, n_samples=128, seed=3):
    """A lingering slow object (whole window) plus a faster, shorter ball."""
    rng = np.random.default_rng(seed)
    res = RANGE_SPAN_M / n_samples
    cube = np.zeros((n_frames, 2 * n_loops, 4, n_samples), dtype=complex)
    samples = np.arange(n_samples)
    for slot in range(n_frames):
        for loop in range(n_loops):
            t_s = slot * 0.006 + loop * LOOP_PRI_S
            movers = [(1.00 + fast_ms * t_s, 400.0)]
            if t_s < 0.045:  # the flying tee lands mid-window
                movers.append((2.30 + slow_ms * t_s, 500.0))
            for x_m, amp in movers:
                rbin = x_m / res
                if rbin >= n_samples - 2:
                    continue
                tone = amp * np.exp(2j * np.pi * rbin * samples / n_samples)
                dopp = np.exp(1j * 4 * np.pi * (x_m - 1.0) / LAM)
                cube[slot, 2 * loop] += dopp * tone
                cube[slot, 2 * loop + 1] += dopp * tone
    cube += (rng.standard_normal(cube.shape) + 1j * rng.standard_normal(cube.shape)) * 6.0
    return pack_dump(cube, n_tx=2, version=3, frame_period_us=6000)


def test_fastest_credible_track_beats_slow_theft():
    """A slow lingering object must not steal the track from the ball.

    2026-07-14 live bug: the flying tee (~25 m/s) outlasted the ball in the
    gates and won most-inliers RANSAC on 5 driver + several SW shots.
    """
    from openflight.iwr6843.dump import parse_dump, parse_header
    from openflight.iwr6843.shot import geometry_from_header as gfh
    from openflight.iwr6843.tracking import find_ball, mti_filter

    raw = _two_streak_cube()
    meta, cube = parse_dump(raw)
    geo = gfh(parse_header(raw))
    track = find_ball(mti_filter(cube), geo)
    assert track is not None
    assert track.speed_ms == pytest.approx(60.0, abs=3.0)


def test_local_velocity_on_accelerating_ball(cal):
    """Quadratic refit exposes the instantaneous radial speed."""
    raw = synth_shot(speed_ms=40.0, accel_ms2=60.0, noise=4.0)
    shot = process_dump(raw, cal, two_ray=False)
    assert shot.ball_found and shot.track is not None
    trk = shot.track
    assert trk.quad_bins is not None
    res = RANGE_SPAN_M / 128
    v_first = trk.speed_ms_at(trk.t_first, res)
    v_last = trk.speed_ms_at(trk.t_last, res)
    assert v_first == pytest.approx(40.0 + 60.0 * trk.t_first, abs=2.0)
    assert v_last == pytest.approx(40.0 + 60.0 * trk.t_last, abs=2.0)
    assert v_last - v_first > 2.0


def test_tee_anchor_is_floor_referenced():
    """fit_tee anchors at ball-above-floor minus radar height.

    The old radar-plane anchor sat ~0.15 m high; on a short-lever wedge
    that was a ~-11 deg launch-angle bias.
    """
    from openflight.iwr6843.doa import AnglePoint
    from openflight.iwr6843.trajectory import fit_tee

    cal = Calibration.identity()
    cal.tee_range_m = 1.5
    cal.tee_ball_height_m = 0.04
    cal.meta["radar_height_m"] = 0.152
    truth = np.radians(15.0)
    h_anchor = 0.04 - 0.152
    points = []
    for x in np.linspace(2.4, 4.4, 12):
        h = h_anchor + np.tan(truth) * (x - 1.5)
        points.append(
            AnglePoint(
                t_s=0.0,
                range_m=float(np.hypot(x, h)),
                theta_rad=float(np.arctan2(h, x)),
                snr=30.0,
                n_summed=1,
            )
        )
    fit = fit_tee(points, cal)
    assert fit is not None
    assert fit.launch_angle_deg == pytest.approx(15.0, abs=0.1)
    # anchoring at the radar plane instead must visibly rotate the fit
    cal.tee_ball_height_m = 0.04 + 0.152
    fit_old = fit_tee(points, cal)
    assert fit_old.launch_angle_deg < fit.launch_angle_deg - 2.0


def test_two_ray_policy_anchored_gated_multipath(cal):
    """Mid-iron policy (tee anchor + angle gate) under a strong floor image."""
    raw = synth_shot(image_gain=0.6, noise=4.0)
    shot = process_dump(raw, cal, two_ray=True, club="9i")
    assert shot.ball_found
    assert "two_ray" in shot.fits
    assert shot.fits["two_ray"].launch_angle_deg == pytest.approx(18.0, abs=2.0)


def test_cosine_speed_factor_matches_kinematics():
    """Factor must equal (r2-r1)/path from direct kinematics."""
    from openflight.iwr6843.trajectory import cosine_speed_factor

    cal = Calibration.identity()
    cal.tee_range_m = 1.5
    cal.tee_ball_height_m = 0.152  # dz=0: x_tee == slant
    cal.meta["radar_height_m"] = 0.152
    la = np.radians(20.0)
    xs = np.linspace(1.5, 5.0, 400)
    zs = 0.152 + np.tan(la) * (xs - 1.5)
    rs = np.hypot(xs, zs - 0.152)
    r1, r2 = 2.0, 4.0
    i1, i2 = np.searchsorted(rs, r1), np.searchsorted(rs, r2)
    path = (xs[i2] - xs[i1]) / np.cos(la)
    expect = (rs[i2] - rs[i1]) / path
    got = cosine_speed_factor(20.0, r1, r2, cal)
    assert got == pytest.approx(expect, abs=0.005)
    assert got < 0.985  # meaningfully below 1 at LA 20


def test_thin_capture_rejected(cal):
    """Junk captures (few frames of ball) must be a no-read, not a number."""
    raw = synth_shot(n_frames=3, trigger_frame=0, tee_m=2.3)
    shot = process_dump(raw, cal)
    assert shot.ball_found
    assert shot.quality == "reject"
    assert shot.launch_angle_deg is None
    assert "rejected" in shot.summary()


def test_notch_speed_ball_recovered(cal):
    """A ball at 2 x 26.93 m/s is invisible to burst-MTI (loop phase ~ 0
    mod 2pi); the window-scope retry must recover track AND angle."""
    from openflight.iwr6843.dump import parse_dump
    from openflight.iwr6843.tracking import find_ball, mti_filter

    notch_v = 2 * 26.93
    raw = synth_shot(speed_ms=notch_v, noise=4.0)
    meta, cube = parse_dump(raw)
    geo = geometry_from_header(meta)
    burst_track = find_ball(mti_filter(cube), geo)
    shot = process_dump(raw, cal)
    assert shot.ball_found and shot.quality != "reject"
    assert shot.notch_recovered
    if burst_track is not None:  # burst track is visibly degraded
        assert shot.track.rms_bins < burst_track.rms_bins
    assert shot.track.speed_ms == pytest.approx(notch_v, rel=0.03)
    assert shot.policy == "far"  # notch-near -> no-anchor config
    assert shot.launch_angle_deg == pytest.approx(18.0, abs=2.5)


def test_policy_is_observable_keyed(cal):
    """Same club label, different speeds -> different policy."""
    slow = process_dump(synth_shot(speed_ms=45.0), cal, club="7Iron")
    fast = process_dump(synth_shot(speed_ms=60.0), cal, club="7Iron")
    assert slow.policy.startswith("anchored")
    assert fast.policy == "far"


def test_club_class_mapping():
    from openflight.iwr6843.shot import club_class

    assert club_class("SandWedge") == "wedge"
    assert club_class("PW") == "wedge"
    assert club_class("9i") == "mid_iron"
    assert club_class("7Iron") == "mid_iron"
    assert club_class("5Iron") == "long_iron"
    assert club_class("3 hybrid") == "long_iron"
    assert club_class("Driver") == "driver"
    assert club_class(None) == "default"
    assert club_class("putter") == "default"


def test_lcmf_v1_logs_five_components_but_fuses_only_the_two_channels(cal):
    """Production LCMF must expose its raw fusion without a global correction.

    All five components stay in the log -- they are useful in session replay
    -- but only the two channel models can be selected, so only they decide
    the angle. Averaging all five let a ``fast_*`` outlier both shift the
    answer and, once selection replaced averaging, widen the spread past
    CHANNEL_SPREAD_MAX_DEG and force a corroborated pair down to one channel.
    """
    raw = synth_shot(speed_ms=45.0, launch_deg=18.0, image_gain=0.35, noise=4.0)

    result = estimate_lcmf_v1(
        raw,
        cal,
        ball_speed_mph=45.0 * 2.23694,
        club="9i",
    )

    assert result.accepted
    channels = {"channel_two8_deg", "channel_four4_path_tdm_deg"}
    fast = {"fast_direct1_deg", "fast_two2_deg", "fast_four4_deg"}
    assert set(result.components_deg) == channels | fast
    channel_values = [result.components_deg[name] for name in channels]
    assert result.raw_angle_deg == pytest.approx(np.mean(channel_values))
    assert result.component_std_deg == pytest.approx(np.std(channel_values))
    assert result.single_channel is False
    assert set(result.channels_used) == channels
    assert ANGLE_CORRECTION_DEG == 0.0
    assert result.angle_deg == pytest.approx(result.raw_angle_deg + ANGLE_CORRECTION_DEG)
    assert result.n_snapshots <= 4 * result.n_frames
    assert result.n_frames >= 3
    assert result.to_dict()["angle_correction_deg"] == ANGLE_CORRECTION_DEG


def test_lcmf_v1_fuses_range_snapshot_channel_components(cal):
    """Range snapshots intentionally skip raw-ADC fast-time models."""
    raw = range_snapshot_dump(
        synth_shot(speed_ms=45.0, launch_deg=18.0, image_gain=0.35, noise=4.0, n_loops=10),
        start_bin=20,
        n_bins=80,
    )

    result = estimate_lcmf_v1(
        raw,
        cal,
        ball_speed_mph=45.0 * 2.23694,
        club="9i",
    )

    assert result.accepted
    assert set(result.components_deg) == {
        "channel_two8_deg",
        "channel_four4_path_tdm_deg",
    }
    assert result.raw_angle_deg == pytest.approx(np.mean(list(result.components_deg.values())))
    assert result.angle_deg == pytest.approx(result.raw_angle_deg + ANGLE_CORRECTION_DEG)
    assert result.n_snapshots <= 4 * result.n_frames
    assert result.n_frames >= 3


def _range_snapshot_shot() -> bytes:
    return range_snapshot_dump(
        synth_shot(speed_ms=45.0, launch_deg=18.0, image_gain=0.35, noise=4.0, n_loops=10),
        start_bin=20,
        n_bins=80,
    )


def test_lcmf_v1_rejects_when_every_channel_is_off_the_grid(cal, monkeypatch):
    """No channel measured anything, so there is no angle to report.

    An argmin pinned to a grid edge means the true minimum lies outside the
    searched range. When that is true of every channel the estimator knows
    nothing about this shot, and inventing an answer from a set of
    non-measurements is worse than admitting it.
    """
    monkeypatch.setattr(lcmf, "grid_curvature", lambda objective: None)

    result = estimate_lcmf_v1(
        _range_snapshot_shot(), cal, ball_speed_mph=45.0 * 2.23694, club="9i"
    )

    assert result.status == "rejected_no_conditioned_channel"
    assert result.angle_deg is None
    assert not result.accepted
    assert result.track_speed_mph is not None, "a rejection must keep its track evidence"


def test_lcmf_v1_rejects_disagreeing_channels_with_no_curvature_to_choose_on(
    cal, monkeypatch
):
    """A tie on evidence is not a licence to return whichever channel is first.

    ``max()`` yields the first key on a tie, and insertion order puts
    ``channel_two8_deg`` -- the channel that collapses on real shots -- at
    the front. Rejecting is the only defensible outcome when the channels
    disagree and nothing distinguishes them.
    """
    monkeypatch.setattr(lcmf, "grid_curvature", lambda objective: 0.0)
    monkeypatch.setattr(lcmf, "CHANNEL_SPREAD_MAX_DEG", 0.0)

    result = estimate_lcmf_v1(
        _range_snapshot_shot(), cal, ball_speed_mph=45.0 * 2.23694, club="9i"
    )

    assert result.status == "rejected_no_conditioned_channel"
    assert result.angle_deg is None


def test_lcmf_v1_rejects_a_grid_too_coarse_to_score_a_minimum(cal):
    """A caller-supplied grid with no interior points scores nothing.

    ``grid_step_deg`` is the caller's, and a large enough step leaves the
    -5..45 deg search with fewer than three points -- every index is then an
    edge, so no channel can be scored. Before selection required strictly
    positive evidence this resolved to whichever channel came first in the
    dict, which is ``channel_two8_deg``: a coarse grid silently produced the
    collapsed channel's angle. Not reachable from current call sites
    (``calibration_session`` passes 1.0), so this pins the protection rather
    than a live path.
    """
    grid = np.arange(-5.0, 45.0 + 50.0 / 2.0, 50.0)
    assert len(grid) < 3, "fixture assumes a grid with no interior point"

    result = estimate_lcmf_v1(
        _range_snapshot_shot(),
        cal,
        ball_speed_mph=45.0 * 2.23694,
        club="9i",
        grid_step_deg=50.0,
    )

    assert result.status == "rejected_no_conditioned_channel"
    assert result.angle_deg is None


def test_lcmf_v1_rejects_empty_capture_without_inventing_angle(cal):
    rng = np.random.default_rng(11)
    cube = (
        rng.standard_normal((12, 32, 4, 128)) + 1j * rng.standard_normal((12, 32, 4, 128))
    ) * 8.0
    raw = pack_dump(cube, n_tx=2, version=3, frame_period_us=6000)

    result = estimate_lcmf_v1(raw, cal, ball_speed_mph=100.0, club="9i")

    assert not result.accepted
    assert result.angle_deg is None
    assert result.status == "rejected_by_ball_tracker"


def test_lcmf_v1_reports_rejected_track_quality(cal):
    """A detected but thin track must not be mislabeled as a TDM-sign failure."""
    raw = synth_shot(n_frames=3, trigger_frame=0, tee_m=2.3)

    result = estimate_lcmf_v1(raw, cal, ball_speed_mph=100.0, club="9i")

    assert not result.accepted
    assert result.angle_deg is None
    assert result.track_inliers is not None
    assert result.tracker_quality == "reject"
    assert result.status == "rejected_track_quality"


def test_lcmf_v1_uses_tx2_effective_timing_on_three_tx_capture(cal):
    rng = np.random.default_rng(12)
    cube = (
        rng.standard_normal((12, 30, 4, 128)) + 1j * rng.standard_normal((12, 30, 4, 128))
    ) * 8.0
    raw = pack_dump(cube, n_tx=3, version=3, frame_period_us=6000)

    result = estimate_lcmf_v1(raw, cal, ball_speed_mph=100.0, club="9i")

    assert not result.accepted
    assert result.effective_tdm_tau_s == pytest.approx(TX2_VERTICAL_TDM_TAU_S)
    assert result.effective_loop_period_s == pytest.approx(TX2_LOOP_PERIOD_S)


def test_tx2_horizontal_uses_tail_of_ball_track_not_fixed_ring_tail():
    """Boundary-frozen blocks place impact anywhere, so physical slots 9-11 are not special."""
    n_frames, n_loops, n_tx, n_rx, n_bins = 12, 10, 3, 4, 80
    start_bin = 20
    cube = np.zeros((n_frames, n_loops * n_tx, n_rx, n_bins), dtype=complex)
    track = BallTrack(
        speed_ms=45.0,
        slope_bins=960.0,
        intercept_bins=31.0,
        rms_bins=0.2,
        n_inliers=40,
        t_first=0.012,
        t_last=0.031,
        low_confidence=False,
    )
    shot = ShotMeasurement(geometry=None, ball_found=True, track=track)

    for frame in range(n_frames):
        for loop in range(n_loops):
            time_s = frame * 0.006 + loop * TX2_LOOP_PERIOD_S
            if not track.t_first <= time_s <= track.t_last:
                continue
            local_bin = int(round(track.bin_at(time_s))) - start_bin
            common = np.exp(1j * 0.7 * loop)
            cube[frame, loop * n_tx, :, local_bin] = common
            cube[frame, loop * n_tx + 1, :, local_bin] = common * np.exp(0.25j)
            cube[frame, loop * n_tx + 2, :, local_bin] = common

    raw = pack_dump(
        cube,
        n_tx=3,
        version=3,
        frame_period_us=6000,
        sample_fmt=SAMPLE_RANGE_FFT_IQ16,
        range_bin_start=start_bin,
    )

    angle_deg, coherence, status = _tx2_horizontal_proxy(raw, shot, tdm_sign=1)

    assert angle_deg is not None
    assert coherence is not None and coherence > 0.25
    assert status == "hlcmf_v0_accepted"
