"""Background filtering and pre-impact snapshot selection for an inclinometer."""

from __future__ import annotations

import logging
import math
import statistics
import threading
import time
from collections import deque
from typing import Protocol

from .models import AccelerationSample, OrientationSnapshot, SnapshotSelection

logger = logging.getLogger(__name__)


class Accelerometer(Protocol):  # pylint: disable=unnecessary-ellipsis
    """Sensor contract required by the service."""

    def initialize(self) -> None:
        """Configure and verify the sensor."""
        ...  # pylint: disable=unnecessary-ellipsis

    def read(self, *, timestamp: float | None = None) -> AccelerationSample:
        """Read one acceleration sample."""
        ...  # pylint: disable=unnecessary-ellipsis

    def close(self) -> None:
        """Release sensor resources."""
        ...  # pylint: disable=unnecessary-ellipsis


def pitch_degrees(sample: AccelerationSample) -> float:
    """Return enclosure pitch; positive Y is positive tilt-back."""
    return math.degrees(math.atan2(sample.y_g, math.hypot(sample.x_g, sample.z_g)))


class InclinometerService:
    """Sample, filter, and retain stable enclosure orientations."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        sensor: Accelerometer,
        *,
        zero_offset_deg: float = 0.0,
        sample_hz: float = 10.0,
        window_samples: int = 8,
        history_seconds: float = 15.0,
        max_snapshot_age_s: float = 2.0,
        max_pitch_std_deg: float = 0.5,
        gravity_range_g: tuple[float, float] = (0.85, 1.15),
    ):
        if sample_hz <= 0 or window_samples < 2:
            raise ValueError("sample_hz must be positive and window_samples must be at least 2")
        self.sensor = sensor
        self.zero_offset_deg = zero_offset_deg
        self.sample_hz = sample_hz
        self.window_samples = window_samples
        self.max_snapshot_age_s = max_snapshot_age_s
        self.max_pitch_std_deg = max_pitch_std_deg
        self.gravity_range_g = gravity_range_g
        self._samples: deque[AccelerationSample] = deque(maxlen=window_samples)
        history_size = max(window_samples, math.ceil(history_seconds * sample_hz))
        self._history: deque[OrientationSnapshot] = deque(maxlen=history_size)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error: str | None = None
        self._last_error_timestamp: float | None = None
        self._last_unstable_timestamp: float | None = None

    def start(self) -> None:
        """Initialize hardware and start the sampling thread."""
        self.sensor.initialize()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._sample_loop,
            name="openflight-inclinometer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop sampling and release the I2C bus."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.sensor.close()

    def _sample_loop(self) -> None:
        interval_s = 1.0 / self.sample_hz
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                self.add_sample(self.sensor.read())
                with self._lock:
                    self._last_error = None
                    self._last_error_timestamp = None
            except Exception as error:  # pylint: disable=broad-exception-caught
                with self._lock:
                    self._last_error = str(error)
                    self._last_error_timestamp = time.time()
                logger.warning("LIS3DH sample failed: %s", error)
            delay = max(0.0, interval_s - (time.monotonic() - started))
            self._stop_event.wait(delay)

    def add_sample(self, sample: AccelerationSample) -> OrientationSnapshot | None:
        """Add one sample and return a snapshot when the window is stationary."""
        with self._lock:
            self._samples.append(sample)
            if len(self._samples) < self.window_samples:
                return None
            samples = list(self._samples)
            pitches = [pitch_degrees(item) for item in samples]
            pitch_std = statistics.pstdev(pitches)
            x_g = statistics.median(item.x_g for item in samples)
            y_g = statistics.median(item.y_g for item in samples)
            z_g = statistics.median(item.z_g for item in samples)
            gravity_g = math.sqrt(x_g * x_g + y_g * y_g + z_g * z_g)
            if not self.gravity_range_g[0] <= gravity_g <= self.gravity_range_g[1]:
                self._last_unstable_timestamp = sample.timestamp
                return None
            if pitch_std > self.max_pitch_std_deg:
                self._last_unstable_timestamp = sample.timestamp
                return None
            raw_pitch = statistics.median(pitches)
            snapshot = OrientationSnapshot(
                timestamp=sample.timestamp,
                x_g=x_g,
                y_g=y_g,
                z_g=z_g,
                gravity_g=gravity_g,
                raw_pitch_deg=raw_pitch,
                calibrated_pitch_deg=raw_pitch + self.zero_offset_deg,
                pitch_std_deg=pitch_std,
                sample_count=len(samples),
            )
            self._history.append(snapshot)
            return snapshot

    def snapshot_for_impact(self, impact_timestamp: float) -> SnapshotSelection:
        """Select the newest stable snapshot at or before an impact."""
        with self._lock:
            candidates = [item for item in self._history if item.timestamp <= impact_timestamp]
            last_error = self._last_error
            error_timestamp = self._last_error_timestamp
            unstable_timestamp = self._last_unstable_timestamp
        if not candidates:
            status = "sensor_error" if last_error else "no_stable_preimpact_reading"
            return SnapshotSelection(snapshot=None, status=status)
        snapshot = candidates[-1]
        age_s = max(0.0, impact_timestamp - snapshot.timestamp)
        if error_timestamp is not None and snapshot.timestamp < error_timestamp <= impact_timestamp:
            return SnapshotSelection(snapshot=None, status="sensor_error", age_s=age_s)
        if (
            unstable_timestamp is not None
            and snapshot.timestamp < unstable_timestamp <= impact_timestamp
        ):
            return SnapshotSelection(snapshot=None, status="moving", age_s=age_s)
        if age_s > self.max_snapshot_age_s:
            return SnapshotSelection(snapshot=None, status="stale", age_s=age_s)
        return SnapshotSelection(snapshot=snapshot, status="stable", age_s=age_s)

    def wait_for_stable(self, timeout_s: float = 2.0) -> SnapshotSelection:
        """Wait briefly for a startup orientation diagnostic."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            selection = self.snapshot_for_impact(time.time())
            if selection.snapshot is not None:
                return selection
            time.sleep(min(0.05, 1.0 / self.sample_hz))
        return self.snapshot_for_impact(time.time())

    @property
    def last_error(self) -> str | None:
        """Most recent sensor error, cleared after the next valid read."""
        with self._lock:
            return self._last_error
