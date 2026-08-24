"""Club path from a Cartesian linear fit across pre-impact frames.

Club path is a direction of travel, so it needs samples over time. Fitting
Cartesian x/y (rather than the azimuth angle or its rate) means a constant
per-element phase error cancels out of the path — which matters because the
shipped array calibration was measured on a different board — and it means
the fit carries no bias from where in the window the samples happen to sit
(see openflight.iwr6843.club's module docstring for why).

Sign convention under test (TrackMan, right-handed): positive = in-to-out.
"""

import math

import numpy as np
import pytest

from openflight.iwr6843 import club, doa
from openflight.iwr6843.calibration import Calibration
from openflight.iwr6843.dump import SAMPLE_RANGE_FFT_IQ16, pack_dump
from openflight.iwr6843.shot import TX2_LOOP_PERIOD_S

FRAME_PERIOD_S = 4e-3


def _synth_club(path_deg, *, club_speed_ms=22.0, tee_range_m=1.372, n_samples=128):
    """A club head on a straight line through the tee at the moment of impact.

    Built in Cartesian space, not by asserting an azimuth rate directly:
    position(t) = tee_position + (t - t_impact) * velocity, where velocity
    has magnitude club_speed_ms and direction path_deg off the target line
    (the boresight / x-axis). Range and azimuth at each (frame, loop) are the
    exact polar coordinates of that position — range becomes the bin index,
    azimuth becomes the TX2-vs-(TX1,TX3) phase (phase = pi*sin(az)), which
    estimate_club_path inverts exactly with arcsin. The raw TX2/TX3 values
    also carry the TDM-Doppler phase that tx2_phase_at's own motion
    correction expects to remove (using this same target's true local radial
    speed), so the round trip is exact modulo the estimator's linear-fit
    approximation of a rate that is not actually constant along a straight
    line — that residual is the thing under test.

    Every TX block within a loop also carries the target's true round-trip
    phase 4*pi*range(t)/lambda. This is common to TX1/TX2/TX3 within one
    loop, so it exactly cancels in tx2_phase_at's conj(reference)*tx2
    difference and never touches the recovered azimuth. But it is NOT
    optional: without it, a slowly-walking target is nearly bit-for-bit
    identical across the loops of one burst, and burst-scope MTI (subtract
    each bin's mean over the burst's loops) fully cancels it — exactly the
    "static argmax never sees the ball" problem tracking.py's docstring
    describes, here hitting the azimuth channel instead of the range one.
    A real target survives MTI because it keeps moving sub-bin during the
    burst, which is precisely this phase term.

    impact happens at slot-order club.PRE_IMPACT_FRAMES (see
    club.pre_impact_window_s), i.e. t_impact = PRE_IMPACT_FRAMES *
    frame_period_s from the oldest retained frame.

    The dump MUST declare sample_fmt=SAMPLE_RANGE_FFT_IQ16. Writing an
    amplitude spike at a range bin produces range-domain data, and this
    firmware emits range snapshots in the field, so is_range_snapshot() must
    be True. Left as raw-ADC, mti_filter FFTs the spike a second time; a
    time-domain impulse has flat magnitude across every bin, so no range peak
    survives and the tracker finds nothing (SNR ~2.3 against snr_min 4.0).
    """
    n_frames, loops, n_rx, n_tx = 18, 12, 4, 3
    res = 6.0 / n_samples
    t_impact = club.PRE_IMPACT_FRAMES * FRAME_PERIOD_S
    path_rad = math.radians(path_deg)
    v_x = club_speed_ms * math.cos(path_rad)
    v_y = club_speed_ms * math.sin(path_rad)
    # TDM offset of each TX's chirp from TX1's, within one loop: TX1 is the
    # reference (offset 0), TX2 (the modulated element) trails by TDM_TAU_S,
    # TX3 trails by TX2_VERTICAL_TDM_TAU_S (see doa.tx2_phase_at). tdm_sign
    # is fixed at +1 to match every call in this module.
    tdm_offsets = (0.0, doa.TDM_TAU_S, doa.TX2_VERTICAL_TDM_TAU_S)
    cube = np.zeros((n_frames, loops * n_tx, n_rx, n_samples), dtype=complex)
    for frame in range(n_frames):
        for loop in range(loops):
            t = frame * FRAME_PERIOD_S + loop * TX2_LOOP_PERIOD_S
            s = t - t_impact
            x = tee_range_m + s * v_x
            y = s * v_y
            range_m = math.hypot(x, y)
            bin_at = int(range_m / res)
            if not 0 <= bin_at < n_samples:
                continue
            az_rad = math.atan2(y, x)
            phase_az = math.pi * math.sin(az_rad)
            v_r = (x * v_x + y * v_y) / range_m  # true local radial speed
            doppler_phase = 4.0 * math.pi * range_m / doa.LAM
            for tx in range(n_tx):
                amp = 1000.0
                az_factor = 1.0 if tx != 1 else np.exp(1j * phase_az)
                tdm_phase = 4.0 * np.pi * v_r * tdm_offsets[tx] / doa.LAM
                value = amp * az_factor * np.exp(1j * (tdm_phase + doppler_phase))
                cube[frame, loop * n_tx + tx, :, bin_at] = value
    return pack_dump(
        cube,
        n_tx=n_tx,
        version=3,
        frame_period_us=4000,
        trigger_frame=0,
        sample_fmt=SAMPLE_RANGE_FFT_IQ16,
    )


def _cal(tee_range_m=1.372):
    cal = Calibration.load("config/iwr6843_calibration_reference.json")
    cal.tee_range_m = tee_range_m
    return cal


@pytest.mark.parametrize("path_deg", [0.0, 4.0, -4.0, 8.0, -8.0, 12.0, -12.0])
def test_recovers_known_path(path_deg):
    """path_deg = atan2(v_y, v_x) is EXACT for straight-line motion at constant
    velocity -- x(t) and y(t) are each exactly linear in time, so a linear fit's
    slope carries no window-position bias (see club.py's module docstring). The
    tolerance here covers this fixture's own discretization (range-bin
    quantization, the RANSAC track's tol=1.2-bin inlier gate, the small-angle
    phase->azimuth inversion), not residual model bias: observed error grows
    from ~0.034 deg at 4 deg to ~0.30 deg at 12 deg, not the 1.2-3.5 deg
    scale error the earlier (angle-rate) formulation produced at the same
    angles.
    """
    result = club.estimate_club_path(
        _synth_club(path_deg), _cal(), ops_club_speed_mph=74.0, tdm_sign=1
    )
    assert result.status == "accepted", result.status
    assert result.path_deg == pytest.approx(path_deg, abs=0.4)


def test_sign_convention_is_in_to_out_positive():
    """A club moving rightward relative to the target line reads positive."""
    out_in = club.estimate_club_path(_synth_club(-6.0), _cal(), ops_club_speed_mph=74.0, tdm_sign=1)
    in_out = club.estimate_club_path(_synth_club(6.0), _cal(), ops_club_speed_mph=74.0, tdm_sign=1)
    assert in_out.path_deg > 0 > out_in.path_deg


def test_aim_offset_is_added():
    without = club.estimate_club_path(_synth_club(0.0), _cal(), ops_club_speed_mph=74.0, tdm_sign=1)
    with_offset = club.estimate_club_path(
        _synth_club(0.0), _cal(), ops_club_speed_mph=74.0, tdm_sign=1, aim_offset_deg=2.0
    )
    assert with_offset.path_deg == pytest.approx(without.path_deg + 2.0, abs=0.01)


def test_result_serialises():
    result = club.estimate_club_path(_synth_club(3.0), _cal(), ops_club_speed_mph=74.0, tdm_sign=1)
    payload = result.to_dict()
    assert payload["status"] == "accepted"
    assert set(payload) >= {
        "status",
        "path_deg",
        "confidence",
        "azimuth_rate_dps",
        "range_rate_ms",
        "club_range_m",
        "n_frames",
        "n_snapshots",
        "fit_residual_deg",
        "track_rms_bins",
        "track_inliers",
        "track_span_s",
    }


# --- Failure modes -----------------------------------------------------
#
# Every rejection below must leave path_deg at None without corrupting the
# evidence fields (range_rate_ms, track_inliers, n_snapshots, ...) that a
# caller or session log might still want to record.


def test_two_tx_dump_is_rejected():
    """Club path needs TX2; a 2-TX dump has no horizontal aperture."""
    cube = np.zeros((18, 24, 4, 128), dtype=complex)
    cube[:, :, :, 30] = 1000.0
    raw = pack_dump(cube, n_tx=2, version=3, frame_period_us=4000, sample_fmt=SAMPLE_RANGE_FFT_IQ16)
    result = club.estimate_club_path(raw, _cal(), ops_club_speed_mph=74.0)
    assert result.status == "rejected_requires_three_tx"
    assert result.path_deg is None


def test_empty_dump_reports_no_club_track():
    cube = np.zeros((18, 36, 4, 128), dtype=complex)
    raw = pack_dump(cube, n_tx=3, version=3, frame_period_us=4000, sample_fmt=SAMPLE_RANGE_FFT_IQ16)
    result = club.estimate_club_path(raw, _cal(), ops_club_speed_mph=74.0)
    assert result.status == "rejected_no_club_track"
    assert result.path_deg is None


def test_club_speed_mismatch_is_rejected():
    """A 22 m/s radial track cannot belong to a 20 mph club."""
    result = club.estimate_club_path(_synth_club(0.0), _cal(), ops_club_speed_mph=20.0, tdm_sign=1)
    assert result.status == "rejected_club_speed_mismatch"
    assert result.path_deg is None
    assert result.range_rate_ms is not None, "evidence must survive the rejection"


def test_rejections_carry_their_evidence():
    """A threshold that rejects a value must record the value it rejected."""
    result = club.estimate_club_path(_synth_club(0.0), _cal(), ops_club_speed_mph=20.0, tdm_sign=1)
    payload = result.to_dict()
    assert payload["range_rate_ms"] is not None
    assert payload["track_inliers"] is not None


def test_short_ring_reports_no_pre_impact_frames():
    """A ring with no pre-impact window cannot produce club path."""
    cube = np.zeros((4, 36, 4, 128), dtype=complex)
    cube[:, :, :, 30] = 1000.0
    raw = pack_dump(cube, n_tx=3, version=3, frame_period_us=4000, sample_fmt=SAMPLE_RANGE_FFT_IQ16)
    result = club.estimate_club_path(raw, _cal(), ops_club_speed_mph=74.0)
    assert result.status == "rejected_no_pre_impact_frames"


def test_insufficient_snapshots_is_rejected(monkeypatch):
    monkeypatch.setattr(club, "CLUB_MIN_SNAPSHOTS", 10_000)
    result = club.estimate_club_path(_synth_club(0.0), _cal(), ops_club_speed_mph=74.0, tdm_sign=1)
    assert result.status == "rejected_insufficient_snapshots"
    assert result.n_snapshots > 0, "the count that failed must be recorded"


def test_azimuth_fit_residual_is_rejected(monkeypatch):
    monkeypatch.setattr(club, "CLUB_MAX_AZIMUTH_FIT_RESIDUAL_DEG", 1e-9)
    result = club.estimate_club_path(_synth_club(4.0), _cal(), ops_club_speed_mph=74.0, tdm_sign=1)
    assert result.status == "rejected_azimuth_fit"
    assert result.fit_residual_deg is not None


def test_phase_wrap_is_rejected(monkeypatch):
    """The true azimuth swing is ~0.04 rad; anything near a wrap is a bad track."""
    monkeypatch.setattr(club, "CLUB_MAX_PHASE_SWING_RAD", 1e-6)
    result = club.estimate_club_path(_synth_club(4.0), _cal(), ops_club_speed_mph=74.0, tdm_sign=1)
    assert result.status == "rejected_phase_wrap"


def test_club_search_does_not_fit_the_ball(monkeypatch):
    """A fast late mover must not be reported as club path.

    The ball's radial speed (40 m/s) sits inside CLUB_SPEED_BOUNDS_MS, so
    only the pre-impact time window separates it from a real club track.
    """
    n_frames, loops, n_rx, n_tx, n_samples = 18, 12, 4, 3, 128
    res = 6.0 / n_samples
    cube = np.zeros((n_frames, loops * n_tx, n_rx, n_samples), dtype=complex)
    for frame in range(n_frames):
        for loop in range(loops):
            t = frame * 4e-3 + loop * 90e-6
            if t < 0.030:  # nothing before the ball launches
                continue
            bin_at = int((1.5 + 40.0 * (t - 0.030)) / res)
            if 0 <= bin_at < n_samples:
                cube[frame, loop * n_tx : (loop + 1) * n_tx, :, bin_at] = 1000.0
    raw = pack_dump(
        cube,
        n_tx=n_tx,
        version=3,
        frame_period_us=4000,
        trigger_frame=0,
        sample_fmt=SAMPLE_RANGE_FFT_IQ16,
    )
    result = club.estimate_club_path(raw, _cal(), ops_club_speed_mph=74.0, tdm_sign=1)
    assert result.status != "accepted", (
        f"fitted a post-impact mover as club path: {result.to_dict()}"
    )
    assert result.status == "rejected_no_club_track", (
        "the narrow pre-impact window should see no signal at all (the ball "
        f"only appears after it), got {result.status}: {result.to_dict()}"
    )

    # Prove it's the time window doing the excluding, not a broken fixture:
    # widen the pre-impact window far enough to cover the ball's launch and
    # confirm this exact mover IS findable once the window permits it.
    monkeypatch.setattr(club, "PRE_IMPACT_FRAMES", n_frames - 2)
    widened = club.estimate_club_path(raw, _cal(), ops_club_speed_mph=74.0, tdm_sign=1)
    assert widened.range_rate_ms is not None, (
        "the ball's mover should be findable once the window covers its "
        f"launch time, proving the window (not the fixture) excludes it; "
        f"got {widened.to_dict()}"
    )
