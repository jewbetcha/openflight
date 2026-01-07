"""
Camera module for launch angle and spin detection.

Uses Raspberry Pi HQ Camera with IR illumination to track
golf ball trajectory from behind the tee.
"""

from .capture import (
    CameraCapture,
    MockCameraCapture,
    CaptureConfig,
    CapturedFrame,
    CaptureResult,
)
from .detector import (
    BallDetector,
    DetectedBall,
    DetectorConfig,
)
from .launch_angle import (
    LaunchAngleCalculator,
    LaunchAngles,
    CameraCalibration,
)

__all__ = [
    # Capture
    "CameraCapture",
    "MockCameraCapture",
    "CaptureConfig",
    "CapturedFrame",
    "CaptureResult",
    # Detection
    "BallDetector",
    "DetectedBall",
    "DetectorConfig",
    # Launch angle
    "LaunchAngleCalculator",
    "LaunchAngles",
    "CameraCalibration",
]
