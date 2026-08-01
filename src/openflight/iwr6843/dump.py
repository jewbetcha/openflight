"""Decode IWR6843 rolling-ring captures on the Raspberry Pi.

Contract (firmware <-> Pi), little-endian:
  header (20 B): magic 'ILD1', u16 version, u16 n_frames, u16 chirps_per_frame,
                 u8 n_tx, u8 n_rx, u16 n_samples, u8 sample_fmt (0=int16 I/Q),
                 u8 pad, u16 trigger_frame, u16 pad2
  header extension (v5+ only, 24 B): device-time + temperature report
  payload: per frame, per chirp, per rx: n_samples x (int16 Q, int16 I)
  (TI ADCBUF native complex order is IMAG-first ["ImRe"] -- VERIFIED ON HW
  2026-07-12: parsing Re-first put the ceiling/hand at negative range bins)

Chirp order in a frame is TDM-interleaved: chirp c -> tx = c % n_tx,
loop = c // n_tx. The rotated-board elevation virtual array is
[tx0.rx0..rx(nrx-1), tx1.rx0..] = n_tx*n_rx lambda/2 elements.

Current firmware stores windowed complex range-FFT snapshots. Earlier dump
versions remain parseable so recorded sessions can still be replayed, and the
supported firmware may append a v5 temperature report after the fixed header.
"""

from __future__ import annotations

import struct

import numpy as np

from openflight.iwr6843.music import est_music_fbss, steer

MAGIC = b"ILD1"
HEADER = struct.Struct("<4sHHHBBHBBHH")
TEMP_REPORT = struct.Struct("<Ihhhhhhhhhh")
MAX_SUPPORTED_DUMP_VERSION = 5
# TI mmWaveLink rlRfTempData_t temperature fields are signed, 1 LSB = 1 deg C.
TEMP_REPORT_KEYS = (
    "device_time_ms",
    "rx0_c",
    "rx1_c",
    "rx2_c",
    "rx3_c",
    "tx0_c",
    "tx1_c",
    "tx2_c",
    "pm_c",
    "dig0_c",
    "dig1_c",
)
SAMPLE_INT16_IQ = 0
SAMPLE_RANGE_FFT_IQ16 = 1
SAMPLE_RANGE_FFT_IQ16_WINDOWED = 2


def pack_dump(
    cube: np.ndarray,
    *,
    n_tx: int,
    trigger_frame: int = 0,
    version: int = 1,
    frame_period_us: int = 0,
    sample_fmt: int = SAMPLE_INT16_IQ,
    range_bin_start: int = 0,
    range_bin_starts: tuple[int, ...] | list[int] | None = None,
    temperature_report: dict[str, int] | None = None,
) -> bytes:
    """Complex cube [n_frames, chirps_per_frame, n_rx, n_samples] -> dump bytes.

    Reference packer: this is the exact byte layout the firmware must emit, and
    the synthesis/test path uses it so the format has one executable definition.
    """
    n_frames, cpf, n_rx, n_samples = cube.shape
    if sample_fmt not in (
        SAMPLE_INT16_IQ,
        SAMPLE_RANGE_FFT_IQ16,
        SAMPLE_RANGE_FFT_IQ16_WINDOWED,
    ):
        raise ValueError(f"unsupported sample_fmt {sample_fmt}")
    temp_prefix = b""
    if temperature_report is not None:
        if version < 5:
            raise ValueError("temperature reports require dump version 5+")
        try:
            temp_values = tuple(int(temperature_report[key]) for key in TEMP_REPORT_KEYS)
        except KeyError as exc:  # pragma: no cover - defensive validation
            missing = exc.args[0]
            raise ValueError(f"temperature report missing {missing!r}") from exc
        temp_prefix = TEMP_REPORT.pack(*temp_values)
    elif version >= 5:
        raise ValueError("dump version 5+ requires a temperature report")
    frame_prefix = b""
    if sample_fmt == SAMPLE_RANGE_FFT_IQ16_WINDOWED:
        if version < 4:
            raise ValueError("windowed range snapshots require dump version 4+")
        if range_bin_starts is None or len(range_bin_starts) != n_frames:
            raise ValueError("windowed range snapshots require one start bin per frame")
        if any(start < 0 or start > 255 for start in range_bin_starts):
            raise ValueError("frame range-bin starts must fit in uint8")
        frame_prefix = bytes(range_bin_starts)
    pad = range_bin_start if sample_fmt == SAMPLE_RANGE_FFT_IQ16 else 0
    hdr = HEADER.pack(
        MAGIC,
        version,
        n_frames,
        cpf,
        n_tx,
        n_rx,
        n_samples,
        sample_fmt,
        pad,
        trigger_frame,
        frame_period_us,
    )
    flat = cube.reshape(-1)
    iq = np.empty(flat.size * 2, dtype="<i2")
    iq[0::2] = np.clip(np.round(flat.imag), -32768, 32767).astype("<i2")  # Im first (TI ImRe)
    iq[1::2] = np.clip(np.round(flat.real), -32768, 32767).astype("<i2")
    return hdr + temp_prefix + frame_prefix + iq.tobytes()


def parse_header(raw: bytes) -> dict:
    """Unpack the fixed header and optional v5 temperature extension.

    Lets the runtime size the burst before the full payload has arrived.
    """
    if len(raw) < HEADER.size:
        raise ValueError(f"short header: {len(raw)} bytes < {HEADER.size} needed")
    (magic, ver, nf, cpf, ntx, nrx, ns, fmt, _pad, trig, period_us) = HEADER.unpack_from(raw, 0)
    if magic != MAGIC:
        raise ValueError(f"bad magic {magic!r} (expected {MAGIC!r})")
    if ver > MAX_SUPPORTED_DUMP_VERSION:
        raise ValueError(
            f"unsupported dump version {ver}; max supported is {MAX_SUPPORTED_DUMP_VERSION}"
        )
    if fmt not in (
        SAMPLE_INT16_IQ,
        SAMPLE_RANGE_FFT_IQ16,
        SAMPLE_RANGE_FFT_IQ16_WINDOWED,
    ):
        raise ValueError(f"unsupported sample_fmt {fmt}")
    header_nbytes = HEADER.size
    temperature_report = None
    if ver >= 5:
        if len(raw) < HEADER.size + TEMP_REPORT.size:
            raise ValueError("short temperature report extension")
        temp = TEMP_REPORT.unpack_from(raw, HEADER.size)
        temperature_report = dict(zip(TEMP_REPORT_KEYS, temp, strict=True))
        header_nbytes += TEMP_REPORT.size
    return dict(
        version=ver,
        n_frames=nf,
        chirps_per_frame=cpf,
        n_tx=ntx,
        n_rx=nrx,
        n_samples=ns,
        trigger_frame=trig,
        frame_period_us=period_us,
        sample_fmt=fmt,
        range_bin_start=_pad if fmt == SAMPLE_RANGE_FFT_IQ16 else 0,
        frame_metadata_nbytes=nf if fmt == SAMPLE_RANGE_FFT_IQ16_WINDOWED else 0,
        header_nbytes=header_nbytes,
        temperature_report=temperature_report,
    )


def payload_nbytes(meta: dict) -> int:
    """Bytes of int16-I/Q ADC payload following the header."""
    iq_nbytes = meta["n_frames"] * meta["chirps_per_frame"] * meta["n_rx"] * meta["n_samples"] * 4
    return meta.get("frame_metadata_nbytes", 0) + iq_nbytes


def parse_dump(raw: bytes):
    """Dump bytes -> (meta dict, complex cube [n_frames, cpf, n_rx, n_samples])."""
    meta = parse_header(raw)
    nf, cpf, nrx, ns = (meta["n_frames"], meta["chirps_per_frame"], meta["n_rx"], meta["n_samples"])
    payload_offset = meta["header_nbytes"] + meta.get("frame_metadata_nbytes", 0)
    if meta["sample_fmt"] == SAMPLE_RANGE_FFT_IQ16_WINDOWED:
        if len(raw) < payload_offset:
            raise ValueError("short per-frame range-window table")
        meta["range_bin_starts"] = tuple(raw[meta["header_nbytes"] : payload_offset])
    n = nf * cpf * nrx * ns
    expected_payload_nbytes = n * 4
    actual_payload_nbytes = len(raw) - payload_offset
    if actual_payload_nbytes < expected_payload_nbytes:
        raise ValueError(
            f"short payload: {actual_payload_nbytes} bytes < {expected_payload_nbytes} needed"
        )
    body = np.frombuffer(raw, dtype="<i2", offset=payload_offset, count=2 * n)
    if body.size < 2 * n:
        raise ValueError(f"short payload: {body.size} i16 < {2 * n} needed")
    iq = body.astype(np.float64)
    cube = (iq[1::2] + 1j * iq[0::2]).reshape(nf, cpf, nrx, ns)  # ImRe: Q,I pairs
    return meta, cube


def is_range_snapshot(meta: dict) -> bool:
    """True when payload already contains selected range-FFT bins."""
    return meta.get("sample_fmt", SAMPLE_INT16_IQ) in (
        SAMPLE_RANGE_FFT_IQ16,
        SAMPLE_RANGE_FFT_IQ16_WINDOWED,
    )


def project_tx_pair(raw: bytes, tx_indices: tuple[int, int] = (0, 1)) -> bytes:
    """Return a dump containing only the selected TX chirps from each TDM loop.

    The current vertical LCMF estimator consumes a 2TX virtual array. Experimental
    capture builds may store an extra TX for horizontal/aim work; this helper
    keeps the full raw dump on disk while letting the existing vertical pipeline
    operate on a deterministic TX pair.
    """
    meta, cube = parse_dump(raw)
    n_tx = meta["n_tx"]
    if n_tx == len(tx_indices) and tuple(tx_indices) == tuple(range(n_tx)):
        return raw
    if any(tx < 0 or tx >= n_tx for tx in tx_indices):
        raise ValueError(f"TX projection {tx_indices} invalid for {n_tx} TX dump")
    if meta["chirps_per_frame"] % n_tx:
        raise ValueError(
            f"chirps_per_frame {meta['chirps_per_frame']} is not divisible by n_tx {n_tx}"
        )
    n_frames, _cpf, n_rx, n_samples = cube.shape
    loops = meta["chirps_per_frame"] // n_tx
    tdm = cube.reshape(n_frames, loops, n_tx, n_rx, n_samples)
    projected = tdm[:, :, list(tx_indices), :, :].reshape(
        n_frames,
        loops * len(tx_indices),
        n_rx,
        n_samples,
    )
    return pack_dump(
        projected,
        n_tx=len(tx_indices),
        trigger_frame=meta["trigger_frame"],
        version=meta["version"],
        frame_period_us=meta.get("frame_period_us", 0),
        sample_fmt=meta.get("sample_fmt", SAMPLE_INT16_IQ),
        range_bin_start=meta.get("range_bin_start", 0),
        range_bin_starts=meta.get("range_bin_starts"),
        temperature_report=meta.get("temperature_report"),
    )


def range_fft(cube: np.ndarray, n_fft: int | None = None) -> np.ndarray:
    """FFT over the ADC-sample axis -> [n_frames, cpf, n_rx, n_range]."""
    n_fft = n_fft or cube.shape[-1]
    return np.fft.fft(cube, n=n_fft, axis=-1)


def range_data(meta: dict, cube: np.ndarray, n_fft: int | None = None) -> np.ndarray:
    """Return range-domain data for either raw ADC or range-snapshot dumps."""
    if is_range_snapshot(meta):
        return cube
    return range_fft(cube, n_fft=n_fft)


def ball_range_bin(
    rfft: np.ndarray, frame: int, *, lo_bin: int = 1, hi_bin: int | None = None
) -> int:
    """Strongest range bin in a gate (power summed over all chirps + RX)."""
    hi_bin = hi_bin or rfft.shape[-1] // 2
    power = np.sum(np.abs(rfft[frame, :, :, lo_bin:hi_bin]) ** 2, axis=(0, 1))
    return lo_bin + int(np.argmax(power))


def virtual_snapshot(
    rfft: np.ndarray, frame: int, range_bin: int, n_tx: int, n_rx: int, loop: int = 0
) -> np.ndarray:
    """n_tx*n_rx-element complex snapshot at (frame, range_bin) for one loop.

    Elements ordered [tx0.rx0.., tx1.rx0.., ...] = the rotated elevation ULA.
    """
    snap = np.empty(n_tx * n_rx, dtype=complex)
    for tx in range(n_tx):
        chirp = loop * n_tx + tx
        for rx in range(n_rx):
            snap[tx * n_rx + rx] = rfft[frame, chirp, rx, range_bin]
    return snap


def frame_elevation(
    rfft: np.ndarray,
    frame: int,
    *,
    n_tx: int,
    n_rx: int,
    noise_var: float = 1.0,
    lo_bin: int = 1,
    hi_bin: int | None = None,
):
    """Per-frame elevation (deg) at the frame's strongest range bin.

    Returns (elev_deg, range_bin). noise_var scales the MUSIC source-count
    threshold; pass an estimate of the per-element noise power.
    """
    rb = ball_range_bin(rfft, frame, lo_bin=lo_bin, hi_bin=hi_bin)
    snap = virtual_snapshot(rfft, frame, rb, n_tx, n_rx)
    theta = est_music_fbss(snap, noise_var)
    return float(np.degrees(theta)), rb


# --- synthesis (tests + executable spec of the firmware format) -------------
def synth_target(
    elev_deg: float,
    range_bin: int,
    *,
    n_frames: int = 1,
    n_tx: int = 2,
    n_rx: int = 4,
    n_samples: int = 128,
    amp: float = 1000.0,
    noise: float = 0.0,
    rng=None,
) -> np.ndarray:
    """Raw-ADC cube for ONE static point target at (elev_deg, range_bin).

    Beat tone exp(j*2pi*range_bin*n/n_samples) -> range-FFT peaks at range_bin;
    steer(theta, n_tx*n_rx) sets the elevation phase across the virtual array.
    Returns cube [n_frames, n_tx (=cpf, 1 loop), n_rx, n_samples].
    """
    rng = np.random.default_rng(0) if rng is None else rng
    n_el = n_tx * n_rx
    a = steer(np.radians(elev_deg), n_el)
    n = np.arange(n_samples)
    tone = np.exp(2j * np.pi * range_bin * n / n_samples)
    cube = np.zeros((n_frames, n_tx, n_rx, n_samples), dtype=complex)
    for f in range(n_frames):
        for tx in range(n_tx):
            for rx in range(n_rx):
                cube[f, tx, rx] = amp * a[tx * n_rx + rx] * tone
    if noise:
        cube += (rng.standard_normal(cube.shape) + 1j * rng.standard_normal(cube.shape)) * noise
    return cube
