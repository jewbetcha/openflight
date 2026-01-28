"""
Rolling buffer signal processor.

Handles FFT processing of raw I/Q data to extract speed and spin information.
Based on OmniPreSense AN-027 Rolling Buffer application note.
"""

import json
import logging
from typing import List, Optional, Tuple

import numpy as np

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
    WINDOW_SIZE = 128        # Samples per FFT window
    FFT_SIZE = 4096          # Zero-padded FFT size
    STEP_SIZE_STANDARD = 128 # Non-overlapping step
    STEP_SIZE_OVERLAP = 32   # Overlapping step for high resolution
    SAMPLE_RATE = 30000      # 30 ksps

    # Speed conversion
    # Speed = bin_index * wavelength * sample_rate / (2 * fft_size)
    # For 24.125 GHz radar: wavelength = c / f = 0.01243 m
    # Simplified: bin * 0.0063 * (sample_rate / fft_size) gives m/s
    WAVELENGTH_M = 0.01243   # meters (24.125 GHz)
    MPS_TO_MPH = 2.23694

    # Signal processing
    ADC_RANGE = 4096         # 12-bit ADC
    VOLTAGE_REF = 3.3        # Reference voltage

    # Magnitude threshold for valid peaks (lowered for better detection)
    MAGNITUDE_THRESHOLD = 10

    # Spin detection
    MIN_SPIN_RPM = 1000
    MAX_SPIN_RPM = 10000
    MIN_SPIN_SNR = 3.0

    def __init__(self):
        """Initialize processor with pre-computed window function."""
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

            for line in response.strip().split('\n'):
                line = line.strip()
                if not line or not line.startswith('{'):
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
            logger.warning(f"Incomplete capture (missing: {', '.join(missing)})")
            return None

        except Exception as e:
            logger.error(f"Failed to parse capture: {e}")
            return None

    def _process_block(
        self,
        i_block: np.ndarray,
        q_block: np.ndarray,
    ) -> Tuple[float, float, str]:
        """
        Process a single 128-sample block through FFT.

        Steps:
        1. Remove DC offset (subtract mean)
        2. Scale to voltage (multiply by 3.3/4096)
        3. Apply Hanning window
        4. Create complex signal (I + jQ)
        5. FFT with zero-padding
        6. Find peak magnitude
        7. Convert bin to speed

        Args:
            i_block: 128 I samples
            q_block: 128 Q samples

        Returns:
            Tuple of (speed_mph, magnitude, direction)
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

        # Find peak in positive frequencies and negative frequencies
        half = self.FFT_SIZE // 2

        # OPS243 I/Q convention (empirically determined from diagnostic data):
        # - Positive frequencies (bins 1 to half-1) = OUTBOUND (away from radar, ball/club flying away)
        # - Negative frequencies (bins half+1 to end) = INBOUND (toward radar, backswing)
        pos_peak_bin = np.argmax(magnitude[1:half]) + 1
        pos_peak_mag = magnitude[pos_peak_bin]

        neg_peak_bin = np.argmax(magnitude[half + 1:]) + half + 1
        neg_peak_mag = magnitude[neg_peak_bin]

        # Choose strongest peak and determine direction
        if pos_peak_mag >= neg_peak_mag:
            peak_bin = pos_peak_bin
            peak_mag = pos_peak_mag
            direction = "outbound"  # Positive frequency = away from radar (ball/club)
        else:
            peak_bin = neg_peak_bin - self.FFT_SIZE  # Convert to negative bin
            peak_mag = neg_peak_mag
            direction = "inbound"  # Negative frequency = toward radar (backswing)

        # Convert bin to speed
        # Frequency = bin * sample_rate / fft_size
        # Speed = frequency * wavelength / 2 (factor of 2 for Doppler)
        freq_hz = abs(peak_bin) * self.SAMPLE_RATE / self.FFT_SIZE
        speed_mps = freq_hz * self.WAVELENGTH_M / 2
        speed_mph = speed_mps * self.MPS_TO_MPH

        return speed_mph, peak_mag, direction

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
            i_block = i_data[start:start + self.WINDOW_SIZE]
            q_block = q_data[start:start + self.WINDOW_SIZE]

            speed_mph, magnitude, direction = self._process_block(i_block, q_block)

            timestamp_ms = (start / self.SAMPLE_RATE) * 1000

            if magnitude >= self.MAGNITUDE_THRESHOLD:
                readings.append(SpeedReading(
                    speed_mph=speed_mph,
                    magnitude=magnitude,
                    timestamp_ms=timestamp_ms,
                    direction=direction,
                ))

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
        trigger_offset_ms: float,
        window_ms: float = 50,
    ) -> List[float]:
        """
        Extract ball speed readings after impact for spin analysis.

        Args:
            timeline: High-resolution speed timeline
            trigger_offset_ms: When trigger fired relative to buffer start
            window_ms: Time window after trigger to analyze

        Returns:
            List of ball speed values for spin analysis
        """
        # Get readings after trigger (post-impact ball flight)
        ball_readings = timeline.get_readings_after(trigger_offset_ms)

        # Filter to outbound only and within window
        ball_speeds = [
            r.speed_mph
            for r in ball_readings
            if r.is_outbound and r.timestamp_ms < trigger_offset_ms + window_ms
        ]

        return ball_speeds

    def detect_spin(
        self,
        ball_speeds: List[float],
        sample_rate_hz: float,
    ) -> SpinResult:
        """
        Detect spin rate from speed oscillations using secondary FFT.

        The dimpled golf ball surface causes periodic speed variations
        as the ball spins. We detect this by:
        1. Detrending the speed data (remove average)
        2. FFT to find dominant oscillation frequency
        3. Convert frequency to RPM

        Args:
            ball_speeds: Post-impact ball speed readings
            sample_rate_hz: Sample rate of the speed data (~937 Hz)

        Returns:
            SpinResult with detected spin or failure reason
        """
        if len(ball_speeds) < 10:
            return SpinResult.no_spin_detected("Insufficient ball speed samples")

        speeds = np.array(ball_speeds)

        # Detrend: remove mean (average ball speed)
        detrended = speeds - np.mean(speeds)

        # Check if there's enough variation to analyze
        if np.std(detrended) < 0.1:
            return SpinResult.no_spin_detected("Speed variation too low")

        # FFT on detrended speeds
        n = len(detrended)
        spin_fft = np.fft.fft(detrended)
        frequencies = np.fft.fftfreq(n, d=1 / sample_rate_hz)

        # Only look at positive frequencies (up to Nyquist)
        half = n // 2
        magnitude = np.abs(spin_fft[1:half])
        freqs = frequencies[1:half]

        # Find peak
        peak_idx = np.argmax(magnitude)
        peak_freq = freqs[peak_idx]
        peak_mag = magnitude[peak_idx]

        # Calculate SNR
        noise_floor = np.median(magnitude)
        snr = peak_mag / noise_floor if noise_floor > 0 else 0

        # Convert to RPM
        spin_rpm = abs(peak_freq) * 60

        # Validate result
        if spin_rpm < self.MIN_SPIN_RPM:
            return SpinResult.no_spin_detected(f"Spin {spin_rpm:.0f} RPM below minimum")

        if spin_rpm > self.MAX_SPIN_RPM:
            return SpinResult.no_spin_detected(f"Spin {spin_rpm:.0f} RPM above maximum")

        if snr < self.MIN_SPIN_SNR:
            return SpinResult(
                spin_rpm=spin_rpm,
                confidence=0.3,
                snr=snr,
                quality="low",
            )

        # Assess quality
        if snr >= 5.0:
            quality = "high"
            confidence = 0.9
        elif snr >= 4.0:
            quality = "medium"
            confidence = 0.7
        else:
            quality = "medium"
            confidence = 0.6

        return SpinResult(
            spin_rpm=spin_rpm,
            confidence=confidence,
            snr=snr,
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
        - 50-85% of ball speed (smash factor 1.18-2.0)
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
        min_club = ball_speed_mph * 0.50
        max_club = ball_speed_mph * 0.85

        # Get readings before ball
        pre_ball = timeline.get_readings_before(ball_timestamp_ms)

        # Filter to valid club candidates
        candidates = [
            r for r in pre_ball
            if r.is_outbound
            and min_club <= r.speed_mph <= max_club
            and ball_timestamp_ms - r.timestamp_ms <= max_window_ms
        ]

        if not candidates:
            return None, None

        # Select highest magnitude (club head has larger radar cross-section)
        club_reading = max(candidates, key=lambda r: r.magnitude)

        return club_reading.speed_mph, club_reading.timestamp_ms

    def process_capture(self, capture: IQCapture) -> Optional[ProcessedCapture]:
        """
        Full processing pipeline: I/Q -> speeds -> spin -> shot data.

        Args:
            capture: Raw I/Q capture from radar

        Returns:
            ProcessedCapture with all extracted data, or None if processing fails
        """
        # Process with overlapping FFT for high resolution
        timeline = self.process_overlapping(capture)

        if not timeline.readings:
            logger.warning("No valid readings extracted from capture")
            return None

        # Find ball (peak outbound speed)
        outbound = [r for r in timeline.readings if r.is_outbound]
        if not outbound:
            logger.warning("No outbound readings found")
            return None

        ball_reading = max(outbound, key=lambda r: r.speed_mph)
        ball_speed_mph = ball_reading.speed_mph
        ball_timestamp_ms = ball_reading.timestamp_ms

        # Find club speed
        club_speed_mph, club_timestamp_ms = self.find_club_speed(
            timeline, ball_speed_mph, ball_timestamp_ms
        )

        # Try spin detection
        trigger_offset_ms = capture.trigger_offset_ms
        ball_speeds = self.extract_ball_speeds(timeline, trigger_offset_ms)
        spin = self.detect_spin(ball_speeds, timeline.sample_rate_hz)

        return ProcessedCapture(
            timeline=timeline,
            ball_speed_mph=ball_speed_mph,
            ball_timestamp_ms=ball_timestamp_ms,
            club_speed_mph=club_speed_mph,
            club_timestamp_ms=club_timestamp_ms,
            spin=spin,
            capture=capture,
        )
