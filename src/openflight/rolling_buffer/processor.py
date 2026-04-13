"""
Rolling buffer signal processor.

Handles FFT processing of raw I/Q data to extract speed and spin information.
Based on OmniPreSense AN-027 Rolling Buffer application note.
"""

import json
import logging
from typing import List, Optional, Tuple

import numpy as np
from scipy.signal import butter, sosfiltfilt

from .types import (
    IQCapture,
    ProcessedCapture,
    SpeedReading,
    SpeedTimeline,
    SpinResult,
)

logger = logging.getLogger("openflight.rolling_buffer.processor")


class RollingBufferProcessor:
    """
    Processes raw I/Q data from rolling buffer mode into speed and spin data.

    The processor implements:
    1. Standard FFT processing (128-sample blocks, ~56 Hz equivalent)
    2. Overlapping FFT processing (32-sample steps, ~937 Hz)
    3. Secondary FFT for spin detection from speed oscillations

    Based on OmniPreSense documentation:
    - AN-027-A Rolling Buffer
    - Sports Ball Detection presentation
    """

    # Processing constants
    WINDOW_SIZE = 128  # Samples per FFT window
    FFT_SIZE = 4096  # Zero-padded FFT size
    STEP_SIZE_STANDARD = 128  # Non-overlapping step
    STEP_SIZE_OVERLAP = 32  # Overlapping step for high resolution
    SAMPLE_RATE = 30000  # 30 ksps

    # Speed conversion
    # Speed = bin_index * wavelength * sample_rate / (2 * fft_size)
    # For 24.125 GHz radar: wavelength = c / f = 0.01243 m
    # Simplified: bin * 0.0063 * (sample_rate / fft_size) gives m/s
    WAVELENGTH_M = 0.01243  # meters (24.125 GHz)
    MPS_TO_MPH = 2.23694

    # Signal processing
    ADC_RANGE = 4096  # 12-bit ADC
    VOLTAGE_REF = 3.3  # Reference voltage

    # Magnitude threshold for valid peaks. Low threshold lets weak signals
    # through; they get filtered later by the 15 mph speed check.
    MAGNITUDE_THRESHOLD = 3

    # Multi-peak extraction
    MIN_PEAK_SEPARATION_BINS = 50  # ~5 mph; rejects sidelobe duplicates
    MAX_PEAKS_PER_DIRECTION = 3

    # DC mask: skip first N bins in peak search to reject DC leakage,
    # body movement, and environmental noise. At 30kHz/4096-pt FFT,
    # each bin ≈ 0.1 mph, so 150 bins ≈ 15 mph exclusion zone.
    # Matches the streaming processor's dc_mask and the trigger's
    # 15 mph acceptance threshold — no useful signal lives below 15 mph.
    DC_MASK_BINS = 150

    # Spin detection via amplitude envelope demodulation.
    # The ball seam modulates the radar return at 2x spin rate.
    SPIN_BANDPASS_BW_HZ = 700       # ±700 Hz around ball Doppler (must cover max seam freq)
    SPIN_BANDPASS_ORDER = 4          # Butterworth filter order
    SPIN_ENVELOPE_FFT_SIZE = 8192   # Zero-padded FFT for envelope
    SPIN_MIN_SEAM_HZ = 33.0         # ~2000 RPM min (seam = 1x spin)
    SPIN_MAX_SEAM_HZ = 200.0        # 12000 RPM max
    SPIN_MIN_SAMPLES = 600           # ~20ms minimum ball signal
    SPIN_SNR_HIGH = 8.0              # High confidence threshold
    SPIN_SNR_MEDIUM = 5.0            # Medium confidence threshold
    SPIN_SNR_MIN = 3.0               # Minimum to report
    SPIN_AUTOCORR_MIN = 0.3          # Minimum normalized correlation
    SPIN_MIN_CYCLES = 2              # Minimum seam cycles to report

    def __init__(self, sample_rate: int = 30000):
        """Initialize processor with pre-computed window function.

        Args:
            sample_rate: Sample rate in Hz (default 30000). Lower rates
                extend the buffer duration at the cost of max detectable speed.
        """
        self.SAMPLE_RATE = sample_rate
        self.hanning_window = np.hanning(self.WINDOW_SIZE)

    def parse_capture(self, response: str) -> Optional[IQCapture]:
        """
        Parse S! command response into IQCapture object.

        The response consists of multiple JSON lines:
        {"sample_time": "964.003"}
        {"trigger_time": "964.105"}
        {"I": [4096 integers...]}
        {"Q": [4096 integers...]}

        Args:
            response: Raw response string from S! command

        Returns:
            IQCapture object or None if parsing fails
        """
        try:
            sample_time = None
            trigger_time = None
            i_samples = None
            q_samples = None

            for line in response.strip().split("\n"):
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue

                try:
                    data = json.loads(line)

                    if "sample_time" in data:
                        sample_time = float(data["sample_time"])
                    elif "trigger_time" in data:
                        trigger_time = float(data["trigger_time"])
                    elif "I" in data:
                        i_samples = data["I"]
                    elif "Q" in data:
                        q_samples = data["Q"]

                except json.JSONDecodeError:
                    continue

            if all(v is not None for v in [sample_time, trigger_time, i_samples, q_samples]):
                return IQCapture(
                    sample_time=sample_time,
                    trigger_time=trigger_time,
                    i_samples=i_samples,
                    q_samples=q_samples,
                )

            # Log what's missing
            missing = []
            if sample_time is None:
                missing.append("sample_time")
            if trigger_time is None:
                missing.append("trigger_time")
            if i_samples is None:
                missing.append("I")
            if q_samples is None:
                missing.append("Q")

            # Include response preview in warning for debugging
            if len(response) < 500:
                response_preview = repr(response)
            else:
                response_preview = repr(response[:500]) + "..."
            logger.warning(
                "[PROCESSOR] Incomplete capture (missing: %s). Response (%d bytes): %s",
                ", ".join(missing),
                len(response),
                response_preview,
            )
            return None

        except Exception as e:
            logger.error("[PROCESSOR] Failed to parse capture: %s", e, exc_info=True)
            return None

    def _find_peaks(
        self,
        magnitude: np.ndarray,
        start: int,
        end: int,
    ) -> List[Tuple[int, float]]:
        """
        Find local maxima in a magnitude spectrum region.

        Uses numpy-only local maxima detection with greedy separation
        filtering to reject sidelobe duplicates.

        Args:
            magnitude: Full FFT magnitude array
            start: First bin to search (inclusive)
            end: Last bin to search (exclusive)

        Returns:
            List of (bin_index, magnitude) sorted by magnitude descending,
            capped at MAX_PEAKS_PER_DIRECTION.
        """
        if start >= end or end - start < 3:
            return []

        region = magnitude[start:end]

        # Local maxima: bins where value > both neighbors
        local_max = (region[1:-1] > region[:-2]) & (region[1:-1] > region[2:])
        # Convert to absolute bin indices
        peak_indices = np.where(local_max)[0] + start + 1

        # Filter by magnitude threshold
        candidates = [
            (int(idx), float(magnitude[idx]))
            for idx in peak_indices
            if magnitude[idx] >= self.MAGNITUDE_THRESHOLD
        ]

        # Sort by magnitude descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Greedy selection with minimum separation
        selected: List[Tuple[int, float]] = []
        for bin_idx, mag in candidates:
            if len(selected) >= self.MAX_PEAKS_PER_DIRECTION:
                break
            too_close = any(
                abs(bin_idx - sel_bin) < self.MIN_PEAK_SEPARATION_BINS for sel_bin, _ in selected
            )
            if not too_close:
                selected.append((bin_idx, mag))

        return selected

    def _process_block(
        self,
        i_block: np.ndarray,
        q_block: np.ndarray,
    ) -> List[Tuple[float, float, str]]:
        """
        Process a single 128-sample block through FFT.

        Steps:
        1. Remove DC offset (subtract mean)
        2. Scale to voltage (multiply by 3.3/4096)
        3. Apply Hanning window
        4. Create complex signal (I + jQ)
        5. FFT with zero-padding
        6. Find peak in outbound and inbound independently
        7. Return all peaks exceeding MAGNITUDE_THRESHOLD

        Args:
            i_block: 128 I samples
            q_block: 128 Q samples

        Returns:
            List of (speed_mph, magnitude, direction) tuples for each
            peak exceeding MAGNITUDE_THRESHOLD. May contain 0, 1, or 2 entries.
        """
        # Remove DC offset
        i_centered = i_block - np.mean(i_block)
        q_centered = q_block - np.mean(q_block)

        # Scale to voltage
        i_scaled = i_centered * (self.VOLTAGE_REF / self.ADC_RANGE)
        q_scaled = q_centered * (self.VOLTAGE_REF / self.ADC_RANGE)

        # Apply Hanning window
        i_windowed = i_scaled * self.hanning_window
        q_windowed = q_scaled * self.hanning_window

        # Create complex signal (standard I + jQ)
        complex_signal = i_windowed + 1j * q_windowed

        # FFT
        fft_result = np.fft.fft(complex_signal, self.FFT_SIZE)
        magnitude = np.abs(fft_result)

        half = self.FFT_SIZE // 2
        dc_mask = self.DC_MASK_BINS

        results: List[Tuple[float, float, str]] = []

        # OPS243 I/Q convention (empirically determined from diagnostic data):
        # - Positive frequencies (bins 1 to half-1) = OUTBOUND (away from radar)
        # - Negative frequencies (bins half+1 to end) = INBOUND (toward radar)

        # Outbound peaks: search positive frequencies, skipping DC mask bins
        if dc_mask < half:
            for peak_bin, peak_mag in self._find_peaks(magnitude, dc_mask, half):
                freq_hz = peak_bin * self.SAMPLE_RATE / self.FFT_SIZE
                speed_mps = freq_hz * self.WAVELENGTH_M / 2
                speed_mph = speed_mps * self.MPS_TO_MPH
                results.append((speed_mph, float(peak_mag), "outbound"))

        # Inbound peaks: search negative frequencies, skipping DC mask bins
        # Negative frequencies are in bins [half+1, FFT_SIZE-1].
        # FFT layout: bin FFT_SIZE-1 is freq -1 (nearest DC),
        #             bin half+1 is freq -(half-1) (nearest Nyquist).
        # DC leakage lives at the END of the array (bins near FFT_SIZE-1),
        # so we exclude bins [FFT_SIZE - dc_mask, FFT_SIZE-1].
        neg_start = half + 1
        neg_end = self.FFT_SIZE - dc_mask
        if neg_start < neg_end:
            for neg_peak_bin, neg_peak_mag in self._find_peaks(magnitude, neg_start, neg_end):
                abs_bin = self.FFT_SIZE - neg_peak_bin
                freq_hz = abs_bin * self.SAMPLE_RATE / self.FFT_SIZE
                speed_mps = freq_hz * self.WAVELENGTH_M / 2
                speed_mph = speed_mps * self.MPS_TO_MPH
                results.append((speed_mph, float(neg_peak_mag), "inbound"))

        return results

    def _process_capture(self, capture: IQCapture, step_size: int) -> SpeedTimeline:
        """
        Process capture with given step size.

        Args:
            capture: Raw I/Q capture from radar
            step_size: Samples between FFT windows (128=standard, 32=overlapping)

        Returns:
            SpeedTimeline with extracted speed readings
        """
        i_data = np.array(capture.i_samples)
        q_data = np.array(capture.q_samples)

        readings = []
        start = 0

        while start + self.WINDOW_SIZE <= len(i_data):
            i_block = i_data[start : start + self.WINDOW_SIZE]
            q_block = q_data[start : start + self.WINDOW_SIZE]

            peaks = self._process_block(i_block, q_block)
            timestamp_ms = (start / self.SAMPLE_RATE) * 1000

            for speed_mph, magnitude, direction in peaks:
                readings.append(
                    SpeedReading(
                        speed_mph=speed_mph,
                        magnitude=magnitude,
                        timestamp_ms=timestamp_ms,
                        direction=direction,
                    )
                )

            start += step_size

        sample_rate_hz = self.SAMPLE_RATE / step_size

        return SpeedTimeline(
            readings=readings,
            sample_rate_hz=sample_rate_hz,
            capture=capture,
        )

    def process_standard(self, capture: IQCapture) -> SpeedTimeline:
        """
        Process capture with standard non-overlapping blocks (~56 Hz).

        Args:
            capture: Raw I/Q capture from radar

        Returns:
            SpeedTimeline with ~32 readings (one per 128-sample block)
        """
        return self._process_capture(capture, self.STEP_SIZE_STANDARD)

    def process_overlapping(self, capture: IQCapture) -> SpeedTimeline:
        """
        Process capture with overlapping blocks for high resolution (~937 Hz).

        This provides 4x the temporal resolution of standard processing,
        which is required for spin detection.

        Args:
            capture: Raw I/Q capture from radar

        Returns:
            SpeedTimeline with ~124 readings (32-sample stepping)
        """
        return self._process_capture(capture, self.STEP_SIZE_OVERLAP)

    def extract_ball_speeds(
        self,
        timeline: SpeedTimeline,
        ball_timestamp_ms: float,
        ball_speed_mph: float,
        window_ms: float = 50,
        speed_tolerance_mph: float = 5.0,
    ) -> List[float]:
        """
        Extract ball speed readings around impact for spin analysis.

        Uses the detected ball signal position rather than trigger offset,
        since with all-pre-trigger buffer configurations (e.g. S#32) the
        trigger fires at the end of the buffer while ball signal is at the
        beginning.

        Args:
            timeline: High-resolution speed timeline
            ball_timestamp_ms: When ball was first detected in the timeline
            ball_speed_mph: Detected ball speed for filtering
            window_ms: Time window after ball_timestamp_ms to analyze
            speed_tolerance_mph: Accept readings within this range of ball_speed_mph

        Returns:
            List of ball speed values for spin analysis
        """
        min_speed = ball_speed_mph - speed_tolerance_mph
        max_speed = ball_speed_mph + speed_tolerance_mph

        ball_speeds = [
            r.speed_mph
            for r in timeline.readings
            if r.is_outbound
            and ball_timestamp_ms <= r.timestamp_ms <= ball_timestamp_ms + window_ms
            and min_speed <= r.speed_mph <= max_speed
        ]

        return ball_speeds

    def detect_spin(
        self,
        capture: IQCapture,
        ball_speed_mph: float,
        ball_timestamp_ms: float,
    ) -> SpinResult:
        """
        Detect spin rate from amplitude envelope of the ball's Doppler signal.

        The golf ball seam creates amplitude modulation at 1x spin rate as it
        crosses the radar beam once per revolution. We isolate the ball's
        Doppler signal with a bandpass filter, extract the amplitude envelope,
        then find the modulation frequency.

        Primary: FFT on the envelope (good for irons/wedges with many cycles).
        Fallback: Autocorrelation (more robust for drivers with few cycles).
        """
        i_data = np.array(capture.i_samples, dtype=np.float64)
        q_data = np.array(capture.q_samples, dtype=np.float64)

        # Remove DC offset
        i_data -= np.mean(i_data)
        q_data -= np.mean(q_data)

        # Complex I/Q signal
        iq = i_data + 1j * q_data

        # Ball Doppler frequency
        ball_speed_mps = ball_speed_mph / self.MPS_TO_MPH
        ball_doppler_hz = 2 * ball_speed_mps / self.WAVELENGTH_M

        # Bandpass filter around ball Doppler frequency
        nyquist = self.SAMPLE_RATE / 2
        low = (ball_doppler_hz - self.SPIN_BANDPASS_BW_HZ) / nyquist
        high = (ball_doppler_hz + self.SPIN_BANDPASS_BW_HZ) / nyquist

        # Clamp to valid range
        low = max(low, 0.001)
        high = min(high, 0.999)
        if low >= high:
            return SpinResult.no_spin_detected("Ball Doppler outside filter range")

        try:
            sos = butter(self.SPIN_BANDPASS_ORDER, [low, high], btype="band", output="sos")
            filtered = sosfiltfilt(sos, iq)
        except Exception as e:
            return SpinResult.no_spin_detected(f"Bandpass filter failed: {e}")

        # Amplitude envelope
        envelope = np.abs(filtered)

        # Trim to ball-present window (from ball onset to end of capture)
        start_sample = max(0, int(ball_timestamp_ms * self.SAMPLE_RATE / 1000))
        ball_envelope = envelope[start_sample:]

        # Trim filter transients from both ends. sosfiltfilt's internal
        # padding doesn't fully eliminate edge ripple in the envelope.
        # Trim 1/(bandwidth) seconds from each end as a conservative estimate.
        transient_samples = int(self.SAMPLE_RATE / self.SPIN_BANDPASS_BW_HZ)
        if len(ball_envelope) > 2 * transient_samples + self.SPIN_MIN_SAMPLES:
            ball_envelope = ball_envelope[transient_samples:-transient_samples]

        if len(ball_envelope) < self.SPIN_MIN_SAMPLES:
            return SpinResult.no_spin_detected(
                f"Ball signal too short ({len(ball_envelope)} samples, need {self.SPIN_MIN_SAMPLES})"
            )

        # Check modulation depth before proceeding. Real seam modulation
        # creates 1-5% amplitude variation; quantization noise creates <0.5%.
        envelope_mean = np.mean(ball_envelope)
        envelope_std = np.std(ball_envelope)
        if envelope_mean > 0:
            modulation_depth = envelope_std / envelope_mean
            if modulation_depth < 0.005:
                return SpinResult.no_spin_detected(
                    f"Modulation depth too low ({modulation_depth:.4f})"
                )

        # Remove DC and apply Hann window
        ball_envelope -= envelope_mean
        if envelope_std < 1e-6:
            return SpinResult.no_spin_detected("Envelope variation too low")
        windowed = ball_envelope * np.hanning(len(ball_envelope))

        # --- Primary: FFT on envelope ---
        fft_result = np.fft.fft(windowed, self.SPIN_ENVELOPE_FFT_SIZE)
        freqs = np.fft.fftfreq(self.SPIN_ENVELOPE_FFT_SIZE, d=1 / self.SAMPLE_RATE)
        half = self.SPIN_ENVELOPE_FFT_SIZE // 2
        magnitude = np.abs(fft_result[1:half])
        freqs = freqs[1:half]

        # Restrict to seam frequency range
        valid_mask = (freqs >= self.SPIN_MIN_SEAM_HZ) & (freqs <= self.SPIN_MAX_SEAM_HZ)
        if not np.any(valid_mask):
            return SpinResult.no_spin_detected("No valid seam frequencies in range")

        valid_mag = magnitude[valid_mask]
        valid_freqs = freqs[valid_mask]

        # Reject first 2 bins in the valid range (DC leakage into envelope)
        if len(valid_mag) > 2:
            valid_mag = valid_mag.copy()
            valid_mag[:2] = 0

        peak_idx = np.argmax(valid_mag)
        peak_freq = valid_freqs[peak_idx]
        peak_mag = valid_mag[peak_idx]

        # SNR: peak vs median noise floor in valid range
        noise_floor = np.median(valid_mag[valid_mag > 0]) if np.any(valid_mag > 0) else 1.0
        fft_snr = peak_mag / noise_floor if noise_floor > 0 else 0

        # Seam frequency to spin RPM (seam = 1x spin, one seam crossing per revolution)
        spin_rpm = peak_freq * 60

        # Check minimum cycles in window
        window_seconds = len(ball_envelope) / self.SAMPLE_RATE
        seam_cycles = peak_freq * window_seconds

        logger.info(
            "[PROCESSOR] Spin envelope: peak=%.1f Hz (%.0f RPM), SNR=%.1f, "
            "cycles=%.1f, window=%.0fms, samples=%d",
            peak_freq, spin_rpm, fft_snr, seam_cycles,
            window_seconds * 1000, len(ball_envelope),
        )

        # --- Fallback: Autocorrelation for marginal FFT ---
        autocorr_confirmed = False
        if fft_snr < self.SPIN_SNR_MEDIUM and fft_snr >= self.SPIN_SNR_MIN:
            norm = np.correlate(windowed, windowed, mode="full")
            norm = norm[len(norm) // 2:]  # positive lags only
            if norm[0] > 0:
                norm = norm / norm[0]

            min_lag = int(self.SAMPLE_RATE / self.SPIN_MAX_SEAM_HZ)
            max_lag = int(self.SAMPLE_RATE / self.SPIN_MIN_SEAM_HZ)
            max_lag = min(max_lag, len(norm) - 1)

            if min_lag < max_lag:
                search_region = norm[min_lag:max_lag]
                if len(search_region) > 0:
                    acorr_peak_idx = np.argmax(search_region)
                    acorr_peak_val = search_region[acorr_peak_idx]
                    acorr_lag = min_lag + acorr_peak_idx

                    if acorr_peak_val >= self.SPIN_AUTOCORR_MIN and acorr_lag > 0:
                        acorr_freq = self.SAMPLE_RATE / acorr_lag
                        acorr_rpm = acorr_freq * 60

                        if abs(acorr_rpm - spin_rpm) / max(spin_rpm, 1) < 0.10:
                            autocorr_confirmed = True
                            logger.info(
                                "[PROCESSOR] Spin autocorrelation confirms: %.0f RPM (corr=%.2f)",
                                acorr_rpm, acorr_peak_val,
                            )
                        elif acorr_peak_val >= 0.4:
                            spin_rpm = acorr_rpm
                            peak_freq = acorr_freq
                            autocorr_confirmed = True
                            logger.info(
                                "[PROCESSOR] Spin autocorrelation override: %.0f RPM (corr=%.2f)",
                                acorr_rpm, acorr_peak_val,
                            )

        # --- Quality assessment ---
        if seam_cycles < self.SPIN_MIN_CYCLES:
            return SpinResult.no_spin_detected(
                f"Too few seam cycles ({seam_cycles:.1f}, need {self.SPIN_MIN_CYCLES})"
            )

        if fft_snr < self.SPIN_SNR_MIN and not autocorr_confirmed:
            return SpinResult.no_spin_detected(
                f"SNR too low ({fft_snr:.1f}, need {self.SPIN_SNR_MIN})"
            )

        if fft_snr >= self.SPIN_SNR_HIGH and seam_cycles >= 5:
            quality = "high"
            confidence = 0.9
        elif fft_snr >= self.SPIN_SNR_MEDIUM or autocorr_confirmed:
            quality = "medium"
            confidence = 0.7
        elif fft_snr >= self.SPIN_SNR_MIN:
            quality = "low"
            confidence = 0.4
        else:
            quality = "low"
            confidence = 0.3

        return SpinResult(
            spin_rpm=round(spin_rpm),
            confidence=confidence,
            snr=round(fft_snr, 2),
            quality=quality,
        )

    def find_club_speed(
        self,
        timeline: SpeedTimeline,
        ball_speed_mph: float,
        ball_timestamp_ms: float,
        max_window_ms: float = 100,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Find club head speed from readings before ball impact.

        Club speed should be:
        - Before ball (temporally)
        - 67-85% of ball speed (smash factor 1.18-1.50)
        - Outbound direction

        Args:
            timeline: Speed timeline
            ball_speed_mph: Detected ball speed
            ball_timestamp_ms: When ball was detected
            max_window_ms: Maximum time before ball to search

        Returns:
            Tuple of (club_speed_mph, club_timestamp_ms) or (None, None)
        """
        # Expected club speed range
        min_club = ball_speed_mph * 0.67
        max_club = ball_speed_mph * 0.85

        # Get readings at or before ball timestamp (covers software trigger
        # latency where club and ball appear in the same FFT block)
        pre_ball = [r for r in timeline.readings if r.timestamp_ms <= ball_timestamp_ms]

        # Filter to valid club candidates, excluding the ball reading itself
        candidates = [
            r
            for r in pre_ball
            if r.is_outbound
            and min_club <= r.speed_mph <= max_club
            and ball_timestamp_ms - r.timestamp_ms <= max_window_ms
            and abs(r.speed_mph - ball_speed_mph) > 1.0  # exclude ball
        ]

        if not candidates:
            return None, None

        # Select highest magnitude (club head has larger radar cross-section)
        club_reading = max(candidates, key=lambda r: r.magnitude)

        return club_reading.speed_mph, club_reading.timestamp_ms

    @staticmethod
    def _find_consistent_ball_speed(outbound_readings: list) -> float:
        """Find the ball speed that appears most consistently across FFT windows.

        Bins outbound readings to 1-mph buckets and returns the peak of the
        densest cluster. This is robust against single-window outliers (noise
        spikes, harmonics) that would fool a raw max().

        The ball produces a consistent Doppler return across many windows,
        while noise spikes appear in only 1-2 windows.
        """
        if not outbound_readings:
            return 0.0

        speeds = [r.speed_mph for r in outbound_readings]

        # Bin to 1-mph buckets, find the mode
        from collections import Counter
        binned = Counter(round(s) for s in speeds)

        # The ball is the highest-speed cluster with significant repetition.
        # Sort bins by count descending, then by speed descending to break ties.
        # Require at least 2 occurrences to be considered a real signal.
        frequent = [(spd, cnt) for spd, cnt in binned.items() if cnt >= 2]
        if not frequent:
            # No repeated speeds — fall back to max
            return max(speeds)

        # Among bins with meaningful repetition, pick the fastest.
        # The ball is always the fastest real signal; club is slower.
        frequent.sort(key=lambda x: x[0], reverse=True)
        ball_bin = frequent[0][0]

        # Log if max speed differs significantly from mode (outlier rejected)
        max_speed = max(speeds)
        if max_speed > ball_bin + 10:
            logger.info("[PROCESSOR] Ball speed outlier rejected: max=%.1f, mode=%.1f mph (%d occurrences)", max_speed, float(ball_bin), frequent[0][1])

        # Return the actual max speed within ±2 mph of the mode bin
        # for sub-mph precision
        nearby = [s for s in speeds if abs(s - ball_bin) <= 2.0]
        return max(nearby) if nearby else float(ball_bin)

    def process_capture(self, capture: IQCapture) -> Optional[ProcessedCapture]:
        """
        Full processing pipeline: I/Q -> speeds -> spin -> shot data.

        Args:
            capture: Raw I/Q capture from radar

        Returns:
            ProcessedCapture with all extracted data, or None if processing fails
        """
        # Use non-overlapping (standard) processing to find ball speed.
        # Ball speed = the most-repeated speed across independent windows,
        # NOT the maximum. A single FFT window with a noise spike at 200 mph
        # would poison max(), but mode-based detection ignores it because
        # the real ball signal appears consistently in many windows.
        standard = self.process_standard(capture)
        std_outbound = [r for r in standard.readings if r.is_outbound]
        if not std_outbound:
            logger.warning("[PROCESSOR] No outbound readings found")
            return None

        ball_speed_mph = self._find_consistent_ball_speed(std_outbound)
        logger.info("[PROCESSOR] Ball speed: %.1f mph (mode-based, %d outbound readings)", ball_speed_mph, len(std_outbound))

        # Process with overlapping FFT for high-resolution timeline (needed for spin)
        timeline = self.process_overlapping(capture)

        if not timeline.readings:
            logger.warning("[PROCESSOR] No valid readings extracted from capture")
            return None

        # Find the ball in the overlapping timeline at the standard-detected speed
        # (within tolerance) to get the precise timestamp for spin analysis
        outbound = [r for r in timeline.readings if r.is_outbound]
        ball_candidates = [
            r for r in outbound
            if abs(r.speed_mph - ball_speed_mph) <= 3.0
        ]
        if ball_candidates:
            ball_reading = max(ball_candidates, key=lambda r: r.magnitude)
        elif outbound:
            # Fallback: closest speed to standard result
            ball_reading = min(outbound, key=lambda r: abs(r.speed_mph - ball_speed_mph))
        else:
            # No outbound readings in overlapping timeline at all —
            # use midpoint of capture as best-guess timestamp
            ball_reading = None
            logger.warning("[PROCESSOR] No outbound readings in overlapping timeline")

        ball_timestamp_ms = ball_reading.timestamp_ms if ball_reading else 68.0

        # Find club speed
        club_speed_mph, club_timestamp_ms = self.find_club_speed(
            timeline, ball_speed_mph, ball_timestamp_ms
        )
        if club_speed_mph is not None:
            logger.info("[PROCESSOR] Club speed: %.1f mph at %.1fms before ball", club_speed_mph, ball_timestamp_ms - club_timestamp_ms)
        else:
            logger.debug("[PROCESSOR] No club speed found (ball=%.1f mph)", ball_speed_mph)

        # Spin detection via amplitude envelope demodulation on raw I/Q
        spin = self.detect_spin(capture, ball_speed_mph, ball_timestamp_ms)

        logger.info(
            "[PROCESSOR] Spin result: %.0f RPM, SNR=%.2f, quality=%s",
            spin.spin_rpm, spin.snr, spin.quality,
        )

        return ProcessedCapture(
            timeline=timeline,
            ball_speed_mph=ball_speed_mph,
            ball_timestamp_ms=ball_timestamp_ms,
            club_speed_mph=club_speed_mph,
            club_timestamp_ms=club_timestamp_ms,
            spin=spin,
            capture=capture,
        )
