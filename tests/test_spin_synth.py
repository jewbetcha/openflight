"""Sanity checks for the synthetic seam-modulated I/Q generator."""

import numpy as np
from spin_synth import synth_capture


def _dominant_freq_hz(i_samples, q_samples, start, sample_rate=30000):
    i = np.array(i_samples[start : start + 1024]) - np.mean(i_samples[start : start + 1024])
    q = np.array(q_samples[start : start + 1024]) - np.mean(q_samples[start : start + 1024])
    spectrum = np.abs(np.fft.fft(i + 1j * q, 8192))
    peak_bin = int(np.argmax(spectrum[1:4096])) + 1
    return peak_bin * sample_rate / 8192


def test_tone_lands_at_ball_doppler():
    i_samples, q_samples = synth_capture(rpm=3000, ball_speed_mph=145.0, decel_mph_per_s=0.0)
    expected_hz = 2 * (145.0 / 2.23694) / 0.01243  # ~10430 Hz
    measured = _dominant_freq_hz(i_samples, q_samples, start=600)
    assert abs(measured - expected_hz) < 150


def test_silent_before_onset():
    i_samples, q_samples = synth_capture(rpm=3000, onset_ms=20.0, noise_rms=0.0)
    onset_sample = int(20.0 * 30000 / 1000)
    assert max(abs(v - 2048.0) for v in i_samples[: onset_sample - 1]) < 1e-9
    assert max(abs(v - 2048.0) for v in i_samples[onset_sample + 10 :]) > 1.0


def test_visible_ms_truncates_signal():
    i_samples, _ = synth_capture(rpm=3000, onset_ms=8.0, visible_ms=15.0, noise_rms=0.0)
    end_sample = int((8.0 + 15.0) * 30000 / 1000)
    assert max(abs(v - 2048.0) for v in i_samples[end_sample + 10 :]) < 1e-9
