"""Tests for K-LD7 raw ADC processing library."""

import sys
from pathlib import Path

import numpy as np
import pytest

# Functions available in the package — prefer importing from there
try:
    from openflight.kld7.radc import (
        CFARDetection,
        bin_to_velocity_kmh,
        cfar_detect,
        compute_spectrum,
        parse_radc_payload,
        to_complex_iq,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "analysis"))
    from kld7_radc_lib import (
        CFARDetection,
        bin_to_velocity_kmh,
        cfar_detect,
        compute_spectrum,
        parse_radc_payload,
        to_complex_iq,
    )

# Functions that remain in scripts only
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "analysis"))
from kld7_radc_lib import (
    ADC_MIDPOINT,
    RADCDetection,
    compare_radc_vs_pdat,
    estimate_angle_from_phase,
    process_radc_frame,
)


class TestParseRadcPayload:
    def test_parses_3072_bytes_into_six_channels(self):
        """RADC payload should split into 6 arrays of 256 uint16 samples."""
        # Create synthetic 3072-byte payload: 6 segments of 256 uint16 values
        payload = b""
        for seg in range(6):
            payload += np.arange(seg * 256, (seg + 1) * 256, dtype=np.uint16).tobytes()

        result = parse_radc_payload(payload)

        assert result["f1a_i"].shape == (256,)
        assert result["f1a_q"].shape == (256,)
        assert result["f2a_i"].shape == (256,)
        assert result["f2a_q"].shape == (256,)
        assert result["f1b_i"].shape == (256,)
        assert result["f1b_q"].shape == (256,)
        assert result["f1a_i"].dtype == np.uint16
        # Verify first segment starts at 0
        assert result["f1a_i"][0] == 0
        assert result["f1a_i"][255] == 255
        # Verify second segment starts at 256
        assert result["f1a_q"][0] == 256

    def test_rejects_wrong_payload_size(self):
        """Payloads that aren't 3072 bytes should raise ValueError."""
        with pytest.raises(ValueError, match="3072"):
            parse_radc_payload(b"\x00" * 1024)

    def test_to_complex_iq(self):
        """Should convert uint16 I/Q pairs to complex float with mean removal."""
        # Create I channel with a signal: ramp from 32768 to 32768+255
        i_vals = np.arange(32768, 32768 + 256, dtype=np.uint16)
        # Q channel constant
        q_vals = np.full(256, 33000, dtype=np.uint16)

        f1a = to_complex_iq(i_vals, q_vals)

        assert f1a.dtype == np.complex128
        assert f1a.shape == (256,)
        # Mean-removed: I should center around 0 with spread ~±128
        assert np.abs(np.mean(f1a.real)) < 1.0  # mean is ~0 after removal
        # Q is constant, so mean removal makes all values ~0
        assert np.abs(f1a[0].imag) < 1.0


class TestComputeSpectrum:
    def test_returns_magnitude_spectrum_of_correct_size(self):
        """FFT should produce magnitude spectrum with fft_size bins."""
        iq = np.random.randn(256) + 1j * np.random.randn(256)
        spectrum = compute_spectrum(iq, fft_size=2048)
        assert spectrum.shape == (2048,)
        assert spectrum.dtype == np.float64

    def test_detects_injected_tone(self):
        """A pure tone at a known bin should produce a clear peak."""
        n = 256
        fft_size = 2048
        bin_target = 100  # put energy at bin 100
        freq = bin_target / fft_size
        t = np.arange(n)
        iq = np.exp(2j * np.pi * freq * t)

        spectrum = compute_spectrum(iq, fft_size=fft_size)

        peak_bin = np.argmax(spectrum)
        # Peak should be at or very near the target bin
        assert abs(peak_bin - bin_target) <= 1

    def test_zero_padding_increases_resolution(self):
        """Larger FFT size should produce more bins."""
        iq = np.random.randn(256) + 1j * np.random.randn(256)
        spec_small = compute_spectrum(iq, fft_size=512)
        spec_large = compute_spectrum(iq, fft_size=4096)
        assert spec_small.shape == (512,)
        assert spec_large.shape == (4096,)


class TestCFARDetect:
    def test_detects_tone_above_noise(self):
        """A clear tone in noise should produce exactly one detection."""
        fft_size = 2048
        # Noise floor
        spectrum = np.random.exponential(1.0, size=fft_size)
        # Inject a strong tone at bin 500
        spectrum[500] = 200.0

        detections = cfar_detect(spectrum, guard_cells=4, training_cells=16, threshold_factor=8.0)

        assert len(detections) >= 1
        bins = [d.bin_index for d in detections]
        assert 500 in bins

    def test_no_detections_in_pure_noise(self):
        """Uniform noise should produce very few or zero false detections."""
        fft_size = 2048
        np.random.seed(42)
        spectrum = np.random.exponential(1.0, size=fft_size)

        detections = cfar_detect(spectrum, guard_cells=4, training_cells=16, threshold_factor=12.0)

        # With high threshold, noise should produce very few false alarms
        assert len(detections) <= 5

    def test_detection_has_required_fields(self):
        """Each detection should carry bin index, magnitude, and SNR."""
        spectrum = np.ones(2048)
        spectrum[300] = 100.0

        detections = cfar_detect(spectrum, guard_cells=4, training_cells=16, threshold_factor=8.0)

        assert len(detections) >= 1
        d = detections[0]
        assert hasattr(d, "bin_index")
        assert hasattr(d, "magnitude")
        assert hasattr(d, "snr_db")
        assert d.snr_db > 0


class TestBinToPhysical:
    def test_zero_bin_is_zero_velocity(self):
        """DC bin should map to zero velocity."""
        v = bin_to_velocity_kmh(0, fft_size=2048, max_speed_kmh=100.0)
        assert v == pytest.approx(0.0, abs=0.1)

    def test_velocity_scales_linearly(self):
        """Bins should map linearly to velocity up to max_speed."""
        fft_size = 2048
        max_speed = 100.0
        v_quarter = bin_to_velocity_kmh(fft_size // 4, fft_size=fft_size, max_speed_kmh=max_speed)
        v_half = bin_to_velocity_kmh(fft_size // 2, fft_size=fft_size, max_speed_kmh=max_speed)
        # fft_size//4 is half of fft_size//2 (the Nyquist bin), so maps to max_speed/2
        assert v_quarter == pytest.approx(max_speed / 2, abs=1.0)
        assert v_half == pytest.approx(max_speed, abs=1.0)

    def test_negative_velocity_for_upper_bins(self):
        """Upper half of FFT bins represent negative (inbound) velocity."""
        fft_size = 2048
        max_speed = 100.0
        v = bin_to_velocity_kmh(fft_size - 10, fft_size=fft_size, max_speed_kmh=max_speed)
        assert v < 0


class TestAngleEstimation:
    def test_zero_phase_difference_gives_zero_angle(self):
        """Identical signals on both channels should give ~0 degrees."""
        n = 256
        signal = np.exp(2j * np.pi * 0.1 * np.arange(n))
        angle = estimate_angle_from_phase(signal, signal)
        assert abs(angle) < 2.0

    def test_known_phase_offset_gives_nonzero_angle(self):
        """A deliberate phase shift between channels should produce a measurable angle."""
        n = 256
        signal = np.exp(2j * np.pi * 0.1 * np.arange(n))
        shifted = signal * np.exp(1j * np.pi / 6)  # 30 degree phase shift
        angle = estimate_angle_from_phase(signal, shifted)
        assert abs(angle) > 5.0


class TestProcessRadcFrame:
    def _make_frame(self, tone_bin=100):
        """Create a synthetic RADC frame with a tone at a known bin."""
        n = 256
        fft_size = 2048
        freq = tone_bin / fft_size
        t = np.arange(n)
        signal = 5000.0 * np.exp(2j * np.pi * freq * t)
        noise = np.random.randn(n) + 1j * np.random.randn(n)
        iq = signal + noise

        i_vals = (iq.real + ADC_MIDPOINT).astype(np.uint16)
        q_vals = (iq.imag + ADC_MIDPOINT).astype(np.uint16)
        # Pack into 3072-byte payload (put signal in F1A, zeros elsewhere)
        payload = bytearray(3072)
        payload[0:512] = i_vals.tobytes()
        payload[512:1024] = q_vals.tobytes()

        return {
            "timestamp": 1000.0,
            "radc": bytes(payload),
            "tdat": None,
            "pdat": [],
        }

    def test_returns_detections_for_frame_with_tone(self):
        """A frame with an injected tone should produce at least one detection."""
        frame = self._make_frame(tone_bin=100)
        detections = process_radc_frame(
            frame, frame_index=0, fft_size=2048, max_speed_kmh=100.0,
            cfar_guard=32, cfar_training=32,
        )
        assert len(detections) >= 1
        assert all(isinstance(d, RADCDetection) for d in detections)

    def test_returns_empty_for_noise_only_frame(self):
        """A frame with only noise should produce few or no detections."""
        np.random.seed(42)
        noise_i = np.random.randint(30000, 35000, size=256, dtype=np.uint16)
        noise_q = np.random.randint(30000, 35000, size=256, dtype=np.uint16)
        payload = bytearray(3072)
        payload[0:512] = noise_i.tobytes()
        payload[512:1024] = noise_q.tobytes()
        frame = {"timestamp": 1000.0, "radc": bytes(payload), "tdat": None, "pdat": []}
        detections = process_radc_frame(
            frame, frame_index=0, fft_size=2048, max_speed_kmh=100.0,
            cfar_threshold=12.0,
        )
        assert len(detections) <= 3


class TestCompareRadcVsPdat:
    def test_counts_radc_and_pdat_detections(self):
        """Comparison should report counts from both sources."""
        radc_detections = [
            RADCDetection(0, 1.0, 0.0, 50.0, 10.0, 100.0, 15.0, 500),
            RADCDetection(0, 1.0, 0.0, 30.0, 8.0, 80.0, 12.0, 300),
        ]
        pdat = [
            {"distance": 4.2, "speed": 25.0, "angle": 10.0, "magnitude": 2500},
        ]

        result = compare_radc_vs_pdat(radc_detections, pdat)

        assert result["radc_count"] == 2
        assert result["pdat_count"] == 1

    def test_handles_empty_inputs(self):
        """Should handle cases where one or both sources have no detections."""
        result = compare_radc_vs_pdat([], [])
        assert result["radc_count"] == 0
        assert result["pdat_count"] == 0
