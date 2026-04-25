"""
Data types for rolling buffer mode.

These types represent the raw I/Q data captured from the radar,
the processed speed timeline, and spin detection results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class IQCapture:
    """
    Raw I/Q data captured from S! command in rolling buffer mode.

    The radar returns 4096 samples each for I (in-phase) and Q (quadrature)
    components of the Doppler signal. At 30ksps, this represents ~136ms of data.

    Attributes:
        sample_time: Radar timestamp when sampling started (seconds since power-on)
        trigger_time: Radar timestamp when trigger fired
        i_samples: 4096 in-phase samples (raw ADC values, 0-4095)
        q_samples: 4096 quadrature samples (raw ADC values, 0-4095)
        sample_rate_hz: Capture sample rate in Hz
        timestamp: Python timestamp when capture was received
    """

    sample_time: float
    trigger_time: float
    i_samples: List[int]
    q_samples: List[int]
    sample_rate_hz: int = 30000
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    @property
    def num_samples(self) -> int:
        """Total number of I/Q sample pairs."""
        return len(self.i_samples)

    @property
    def duration_ms(self) -> float:
        """Duration of capture in milliseconds at the recorded sample rate."""
        return (self.num_samples / self.sample_rate_hz) * 1000

    @property
    def trigger_offset_ms(self) -> float:
        """Time offset of trigger from start of buffer in milliseconds."""
        return (self.trigger_time - self.sample_time) * 1000


@dataclass
class SpeedReading:
    """
    A single speed reading extracted from FFT processing.

    This matches the format used in streaming mode for compatibility.
    """

    speed_mph: float
    magnitude: float
    timestamp_ms: float  # Relative to capture start
    direction: str = "outbound"  # "inbound" or "outbound"

    @property
    def is_outbound(self) -> bool:
        return self.direction == "outbound"


@dataclass
class SpeedTimeline:
    """
    High-resolution speed timeline from overlapping FFT processing.

    With 32-sample stepping (vs 128), we get ~937 Hz temporal resolution
    instead of ~56 Hz from streaming mode.

    Attributes:
        readings: List of speed readings in chronological order
        sample_rate_hz: Effective sample rate (~937 Hz with 32-step overlap)
        capture: Reference to the original I/Q capture
    """

    readings: List[SpeedReading]
    sample_rate_hz: float
    capture: Optional[IQCapture] = None

    @property
    def duration_ms(self) -> float:
        """Duration of timeline in milliseconds."""
        if not self.readings:
            return 0
        return self.readings[-1].timestamp_ms - self.readings[0].timestamp_ms

    @property
    def peak_speed(self) -> Optional[SpeedReading]:
        """Reading with highest speed."""
        if not self.readings:
            return None
        return max(self.readings, key=lambda r: r.speed_mph)

    @property
    def speeds(self) -> List[float]:
        """List of just the speed values."""
        return [r.speed_mph for r in self.readings]

    @property
    def timestamps(self) -> List[float]:
        """List of just the timestamp values."""
        return [r.timestamp_ms for r in self.readings]

    def get_readings_after(self, timestamp_ms: float) -> List[SpeedReading]:
        """Get readings after a given timestamp."""
        return [r for r in self.readings if r.timestamp_ms > timestamp_ms]

    def get_readings_before(self, timestamp_ms: float) -> List[SpeedReading]:
        """Get readings before a given timestamp."""
        return [r for r in self.readings if r.timestamp_ms < timestamp_ms]


@dataclass
class SpinResult:
    """
    Result of spin rate detection from secondary FFT.

    Spin is detected by analyzing micro-variations in ball speed caused
    by the dimpled surface. Success rate is ~50-60% per OmniPreSense.

    Attributes:
        spin_rpm: Detected spin rate in revolutions per minute
        confidence: Quality score from 0-1 (high SNR, valid range = high confidence)
        snr: Signal-to-noise ratio of the spin peak
        quality: Human-readable quality assessment
    """

    spin_rpm: float
    confidence: float
    snr: float
    quality: str  # "high", "medium", "low", or reason for rejection

    @property
    def is_reliable(self) -> bool:
        """Whether spin detection is considered reliable."""
        return self.confidence >= 0.6 and self.quality in ("high", "medium")

    @classmethod
    def no_spin_detected(cls, reason: str = "No clear spin signal") -> "SpinResult":
        """Factory for when spin detection fails."""
        return cls(spin_rpm=0, confidence=0, snr=0, quality=reason)


@dataclass
class ProcessedCapture:
    """
    Fully processed capture with speed timeline and optional spin.

    This is the final output from RollingBufferProcessor, containing
    all extracted data ready for shot detection.

    Attributes:
        timeline: High-resolution speed timeline
        ball_speed_mph: Peak ball speed detected
        ball_timestamp_ms: When ball was detected in timeline
        club_speed_mph: Club speed if detected (before ball)
        club_timestamp_ms: When club was detected
        spin: Spin detection result (may indicate failure)
        capture: Original raw I/Q data
    """

    timeline: SpeedTimeline
    ball_speed_mph: float
    ball_timestamp_ms: float
    club_speed_mph: Optional[float] = None
    club_timestamp_ms: Optional[float] = None
    spin: Optional[SpinResult] = None
    capture: Optional[IQCapture] = None

    @property
    def smash_factor(self) -> Optional[float]:
        """Ball speed / club speed ratio."""
        if self.club_speed_mph and self.club_speed_mph > 0:
            return self.ball_speed_mph / self.club_speed_mph
        return None

    @property
    def has_spin(self) -> bool:
        """Whether reliable spin data is available."""
        return self.spin is not None and self.spin.is_reliable
