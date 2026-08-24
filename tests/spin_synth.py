"""Synthetic seam-modulated Doppler I/Q generator for spin estimator tests.

Models the outbound golf-ball return: a Doppler tone at the ball speed with
linear deceleration, seam amplitude modulation (AM) at 1x spin rate, seam
frequency modulation (FM) at 1x spin rate, plus white ADC noise. Values are
centered at 2048 to mimic the OPS243's 12-bit ADC.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

WAVELENGTH_M = 0.01243
MPS_TO_MPH = 2.23694
ADC_CENTER = 2048.0


def _mph_to_hz(mph: float) -> float:
    return 2 * (mph / MPS_TO_MPH) / WAVELENGTH_M


def synth_capture(
    rpm: float,
    *,
    ball_speed_mph: float = 145.0,
    am_depth: float = 0.03,
    fm_dev_hz: float = 25.0,
    decel_mph_per_s: float = 60.0,
    onset_ms: float = 8.0,
    visible_ms: Optional[float] = None,
    amplitude: float = 40.0,
    noise_rms: float = 2.0,
    seed: int = 1,
    n_samples: int = 4096,
    sample_rate: int = 30000,
) -> tuple[list[float], list[float]]:
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples) / sample_rate
    onset_s = onset_ms / 1000.0
    seam_hz = rpm / 60.0

    time_since_onset = np.maximum(t - onset_s, 0.0)
    inst_freq = (
        _mph_to_hz(ball_speed_mph)
        - _mph_to_hz(decel_mph_per_s) * time_since_onset
        + fm_dev_hz * np.sin(2 * np.pi * seam_hz * time_since_onset)
    )
    phase = 2 * np.pi * np.cumsum(inst_freq) / sample_rate

    envelope = amplitude * (1.0 + am_depth * np.sin(2 * np.pi * seam_hz * time_since_onset + 0.7))
    active = t >= onset_s
    if visible_ms is not None:
        active &= t < onset_s + visible_ms / 1000.0

    signal = envelope * np.exp(1j * phase) * active
    i_samples = ADC_CENTER + signal.real + rng.normal(0.0, noise_rms, n_samples)
    q_samples = ADC_CENTER + signal.imag + rng.normal(0.0, noise_rms, n_samples)
    return i_samples.tolist(), q_samples.tolist()
