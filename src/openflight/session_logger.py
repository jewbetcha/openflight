"""
Session logging for OpenFlight field testing.

Provides structured logging of all radar data, shots, and metrics
for analysis and debugging.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ops243 import SpeedReading


@dataclass
class SessionMetadata:
    """Metadata about a logging session."""
    session_id: str
    start_time: str
    radar_port: Optional[str]
    firmware_version: Optional[str]
    camera_enabled: bool
    camera_model: Optional[str]
    config: Dict[str, Any]
    mode: str  # "streaming" or "rolling-buffer"
    trigger_type: Optional[str]  # For rolling-buffer mode: "polling", "threshold", etc.


class SessionLogger:
    """
    Comprehensive session logger for field testing.

    Creates structured log files with semantic naming:
    - session_YYYYMMDD_HHMMSS_<location>.jsonl - Main session log (JSON lines)
    - radar_raw_YYYYMMDD_HHMMSS.log - Raw radar serial data

    Log entry types:
    - session_start: Session metadata
    - session_end: Session summary
    - reading_accepted: Reading that passed all filters
    - shot_detected: A shot was recorded
    - shot_camera: Camera tracking data for a shot
    - config_change: Radar configuration changed
    - error: Any errors during processing
    """

    DEFAULT_LOG_DIR = Path.home() / "openflight_sessions"

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        location: str = "range",
        enabled: bool = True
    ):
        """
        Initialize session logger.

        Args:
            log_dir: Directory for log files (default: ~/openflight_sessions)
            location: Location identifier for file naming (e.g., "range", "course", "home")
            enabled: Whether logging is enabled
        """
        self.log_dir = Path(log_dir) if log_dir else self.DEFAULT_LOG_DIR
        self.location = location
        self.enabled = enabled

        self._session_id: Optional[str] = None
        self._session_file: Optional[Any] = None
        self._raw_file: Optional[Any] = None
        self._session_path: Optional[Path] = None
        self._raw_path: Optional[Path] = None

        # Counters for session summary
        self._stats = {
            "readings_accepted": 0,
            "shots_detected": 0,
            "errors": 0,
        }

        # Setup Python logger for raw radar data
        self._raw_logger = logging.getLogger("ops243.raw")
        self._radar_logger = logging.getLogger("ops243")

    def start_session(
        self,
        radar_port: Optional[str] = None,
        firmware_version: Optional[str] = None,
        camera_enabled: bool = False,
        camera_model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        mode: str = "streaming",
        trigger_type: Optional[str] = None
    ) -> str:
        """
        Start a new logging session.

        Args:
            radar_port: Serial port for radar
            firmware_version: Radar firmware version
            camera_enabled: Whether camera is enabled
            camera_model: Camera/YOLO model being used
            config: Current radar configuration
            mode: Radar mode ("streaming" or "rolling-buffer")
            trigger_type: Trigger strategy for rolling-buffer mode

        Returns:
            Session ID
        """
        if not self.enabled:
            return ""

        # Create log directory
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Generate session ID and filenames
        timestamp = datetime.now()
        self._session_id = timestamp.strftime("%Y%m%d_%H%M%S")

        # Semantic file naming: session_DATE_TIME_LOCATION.jsonl
        session_filename = f"session_{self._session_id}_{self.location}.jsonl"
        raw_filename = f"radar_raw_{self._session_id}.log"

        self._session_path = self.log_dir / session_filename
        self._raw_path = self.log_dir / raw_filename

        # Open log files
        self._session_file = open(self._session_path, "w")
        self._raw_file = open(self._raw_path, "w")

        # Setup raw radar logging to file
        self._setup_raw_logging()

        # Reset stats
        self._stats = {k: 0 for k in self._stats}

        # Write session start entry
        metadata = SessionMetadata(
            session_id=self._session_id,
            start_time=timestamp.isoformat(),
            radar_port=radar_port,
            firmware_version=firmware_version,
            camera_enabled=camera_enabled,
            camera_model=camera_model,
            config=config or {},
            mode=mode,
            trigger_type=trigger_type
        )

        self._write_entry("session_start", asdict(metadata))

        print(f"[SESSION] Started logging: {self._session_path}")
        print(f"[SESSION] Mode: {mode}" + (f" (trigger: {trigger_type})" if trigger_type else ""))
        print(f"[SESSION] Raw radar log: {self._raw_path}")

        return self._session_id

    def _setup_raw_logging(self):
        """Configure Python logging for raw radar data."""
        # Remove existing handlers
        for handler in self._raw_logger.handlers[:]:
            self._raw_logger.removeHandler(handler)
        for handler in self._radar_logger.handlers[:]:
            self._radar_logger.removeHandler(handler)

        # Add file handler for raw data
        file_handler = logging.FileHandler(self._raw_path)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s.%(msecs)03d - %(message)s', datefmt='%H:%M:%S')
        )

        self._raw_logger.addHandler(file_handler)
        self._raw_logger.setLevel(logging.DEBUG)

        self._radar_logger.addHandler(file_handler)
        self._radar_logger.setLevel(logging.DEBUG)

    def end_session(self):
        """End the current logging session and write summary."""
        if not self.enabled or not self._session_file:
            return

        # Calculate session duration
        end_time = datetime.now()

        # Write session end with summary
        summary = {
            "end_time": end_time.isoformat(),
            "stats": self._stats.copy(),
            "shot_rate": (
                self._stats["shots_detected"] / max(1, self._stats["readings_accepted"])
                if self._stats["readings_accepted"] > 0 else 0
            ),
        }

        self._write_entry("session_end", summary)

        # Close files
        if self._session_file:
            self._session_file.close()
            self._session_file = None

        if self._raw_file:
            self._raw_file.close()
            self._raw_file = None

        # Remove logging handlers
        for handler in self._raw_logger.handlers[:]:
            handler.close()
            self._raw_logger.removeHandler(handler)
        for handler in self._radar_logger.handlers[:]:
            handler.close()
            self._radar_logger.removeHandler(handler)

        print(f"[SESSION] Ended. Total shots: {self._stats['shots_detected']}")
        print(f"[SESSION] Logs saved to: {self._session_path}")

    def _write_entry(self, entry_type: str, data: Dict[str, Any]):
        """Write a log entry to the session file."""
        if not self._session_file:
            return

        entry = {
            "ts": datetime.now().isoformat(),
            "type": entry_type,
            **data
        }

        self._session_file.write(json.dumps(entry) + "\n")
        self._session_file.flush()

    def log_accepted_reading(self, reading: SpeedReading):
        """Log a reading that passed all filters and will be processed."""
        if not self.enabled:
            return

        self._stats["readings_accepted"] += 1

        self._write_entry("reading_accepted", {
            "speed": reading.speed,
            "direction": reading.direction.value,
            "magnitude": reading.magnitude,
        })

    def log_shot(
        self,
        ball_speed_mph: float,
        club_speed_mph: Optional[float],
        smash_factor: Optional[float],
        estimated_carry_yards: float,
        club: str,
        peak_magnitude: Optional[float],
        readings_count: int,
        readings: Optional[List[Dict]] = None,
        spin_rpm: Optional[float] = None,
        spin_confidence: Optional[float] = None,
        mode: str = "streaming"
    ):
        """
        Log a detected shot with all metrics.

        Args:
            ball_speed_mph: Ball speed in MPH
            club_speed_mph: Estimated club speed
            smash_factor: Calculated smash factor
            estimated_carry_yards: Estimated carry distance
            club: Club type used
            peak_magnitude: Peak radar magnitude
            readings_count: Number of readings in the shot window
            readings: Optional list of individual readings that comprised the shot
            spin_rpm: Spin rate in RPM (rolling buffer mode only)
            spin_confidence: Confidence of spin detection (rolling buffer mode only)
            mode: Radar mode ("streaming" or "rolling-buffer")
        """
        if not self.enabled:
            return

        self._stats["shots_detected"] += 1

        self._write_entry("shot_detected", {
            "shot_number": self._stats["shots_detected"],
            "ball_speed_mph": ball_speed_mph,
            "club_speed_mph": club_speed_mph,
            "smash_factor": smash_factor,
            "estimated_carry_yards": estimated_carry_yards,
            "club": club,
            "peak_magnitude": peak_magnitude,
            "readings_count": readings_count,
            "readings": readings,
            "spin_rpm": spin_rpm,
            "spin_confidence": spin_confidence,
            "mode": mode,
        })

    def log_camera_data(
        self,
        shot_number: int,
        launch_angle_vertical: Optional[float],
        launch_angle_horizontal: Optional[float],
        confidence: Optional[float],
        positions_tracked: int,
        launch_detected: bool
    ):
        """Log camera tracking data for a shot."""
        if not self.enabled:
            return

        self._write_entry("shot_camera", {
            "shot_number": shot_number,
            "launch_angle_vertical": launch_angle_vertical,
            "launch_angle_horizontal": launch_angle_horizontal,
            "confidence": confidence,
            "positions_tracked": positions_tracked,
            "launch_detected": launch_detected,
        })

    def log_config_change(self, config: Dict[str, Any], source: str = "user"):
        """Log a radar configuration change."""
        if not self.enabled:
            return

        self._write_entry("config_change", {
            "config": config,
            "source": source,
        })

    def log_iq_reading(
        self,
        speed_mph: float,
        direction: str,
        magnitude: float,
        snr: float,
        peak_bin: int,
        cfar_validated: bool,
        block_count: int
    ):
        """
        Log a speed reading detected from I/Q streaming mode.

        Args:
            speed_mph: Detected speed in mph
            direction: "outbound" or "inbound"
            magnitude: Peak FFT magnitude
            snr: Signal-to-noise ratio
            peak_bin: FFT bin of the peak
            cfar_validated: Whether this was validated by CFAR
            block_count: Number of I/Q blocks processed
        """
        if not self.enabled:
            return

        self._write_entry("iq_reading", {
            "speed_mph": speed_mph,
            "direction": direction,
            "magnitude": magnitude,
            "snr": snr,
            "peak_bin": peak_bin,
            "cfar_validated": cfar_validated,
            "block_count": block_count,
        })

    def log_iq_blocks(
        self,
        shot_number: int,
        blocks: List[Dict[str, Any]]
    ):
        """
        Log raw I/Q blocks for a shot (for post-session analysis).

        Args:
            shot_number: Shot number this data belongs to
            blocks: List of I/Q block data dicts with i_samples, q_samples, timestamp
        """
        if not self.enabled:
            return

        self._write_entry("iq_blocks", {
            "shot_number": shot_number,
            "block_count": len(blocks),
            "blocks": blocks,
        })

    def log_error(self, error: str, context: Optional[Dict] = None):
        """Log an error."""
        if not self.enabled:
            return

        self._stats["errors"] += 1

        self._write_entry("error", {
            "error": error,
            "context": context or {},
        })

    @property
    def session_path(self) -> Optional[Path]:
        """Get the current session log file path."""
        return self._session_path

    @property
    def raw_path(self) -> Optional[Path]:
        """Get the current raw radar log file path."""
        return self._raw_path

    @property
    def session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self._session_id

    @property
    def stats(self) -> Dict[str, int]:
        """Get current session statistics."""
        return self._stats.copy()


# Global session logger instance
_session_logger: Optional[SessionLogger] = None


def get_session_logger() -> Optional[SessionLogger]:
    """Get the global session logger instance."""
    return _session_logger


def init_session_logger(
    log_dir: Optional[Path] = None,
    location: str = "range",
    enabled: bool = True
) -> SessionLogger:
    """
    Initialize and return the global session logger.

    Args:
        log_dir: Directory for log files
        location: Location identifier
        enabled: Whether logging is enabled

    Returns:
        SessionLogger instance
    """
    global _session_logger
    _session_logger = SessionLogger(log_dir=log_dir, location=location, enabled=enabled)
    return _session_logger
