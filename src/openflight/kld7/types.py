"""Data types for K-LD7 angle radar integration."""

from dataclasses import dataclass
from typing import Any, Optional

RADC_PAYLOAD_BYTES = 3072


@dataclass
class KLD7Frame:
    """A single frame from the K-LD7 radar stream.

    Only RADC raw I/Q is collected — TDAT (single-target) and PDAT
    (CFAR target list) frames are no longer requested from the radar
    because all detection is done from RADC offline.
    """

    timestamp: float
    radc: Optional[bytes] = None  # raw 3072-byte ADC payload
    arrival_timestamp: Optional[float] = None
    complete_timestamp: Optional[float] = None
    read_duration_ms: Optional[float] = None


@dataclass
class KLD7Angle:
    """Angle measurement extracted from K-LD7 ring buffer after a shot."""

    vertical_deg: Optional[float] = None
    horizontal_deg: Optional[float] = None
    distance_m: float = 0.0
    magnitude: float = 0.0
    confidence: float = 0.0
    num_frames: int = 0
    # "ball", "club", or None (unclassified / horizontal orientation)
    detection_class: Optional[str] = None
    frames_examined: int = 0
    frames_available: int = 0
    frames_ignored_stale: int = 0
    radc_selection: Optional[dict[str, Any]] = None
