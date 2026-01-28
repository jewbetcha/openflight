"""
Golf ball tracking using ByteTrack.

Provides robust multi-frame tracking with persistent track IDs,
occlusion handling, and trajectory analysis. Designed to work with
the existing Hough circle detector for Pi-friendly performance.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from trackers import ByteTrackTracker
import supervision as sv

from .capture import CapturedFrame
from .detector import BallDetector, DetectedBall, DetectorConfig

logger = logging.getLogger("openflight.camera.tracker")


@dataclass
class TrackedBall:
    """A tracked golf ball with persistent ID across frames."""
    track_id: int
    x: float
    y: float
    radius: float
    confidence: float
    frame_number: int
    timestamp: float

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x, self.y)

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        """Bounding box as (x1, y1, x2, y2)."""
        return (
            self.x - self.radius,
            self.y - self.radius,
            self.x + self.radius,
            self.y + self.radius
        )


@dataclass
class BallTrajectory:
    """Complete trajectory of a tracked ball."""
    track_id: int
    positions: List[TrackedBall] = field(default_factory=list)

    @property
    def num_frames(self) -> int:
        return len(self.positions)

    @property
    def duration_ms(self) -> float:
        if len(self.positions) < 2:
            return 0
        return (self.positions[-1].timestamp - self.positions[0].timestamp) * 1000

    @property
    def start_position(self) -> Optional[TrackedBall]:
        return self.positions[0] if self.positions else None

    @property
    def end_position(self) -> Optional[TrackedBall]:
        return self.positions[-1] if self.positions else None

    @property
    def is_valid_golf_trajectory(self) -> bool:
        """Check if trajectory looks like a golf ball (moving up and away)."""
        if len(self.positions) < 3:
            return False

        # Ball should generally move upward (y decreases in image coords)
        y_positions = [p.y for p in self.positions]
        y_decreasing = sum(1 for i in range(1, len(y_positions))
                          if y_positions[i] < y_positions[i-1])

        # Ball should shrink (moving away from camera)
        radii = [p.radius for p in self.positions]
        radius_decreasing = sum(1 for i in range(1, len(radii))
                                if radii[i] <= radii[i-1] * 1.1)  # Allow some tolerance

        # At least 60% of frames should show expected motion
        threshold = 0.6
        return (y_decreasing / (len(y_positions) - 1) >= threshold and
                radius_decreasing / (len(radii) - 1) >= threshold)

    def get_velocity(self) -> Tuple[float, float]:
        """Calculate average velocity in pixels per frame."""
        if len(self.positions) < 2:
            return (0, 0)

        dx = self.positions[-1].x - self.positions[0].x
        dy = self.positions[-1].y - self.positions[0].y
        frames = self.positions[-1].frame_number - self.positions[0].frame_number

        if frames == 0:
            return (0, 0)

        return (dx / frames, dy / frames)


@dataclass
class TrackerConfig:
    """Configuration for ball tracking."""
    # ByteTrack parameters (v2.1.0+ API)
    lost_track_buffer: int = 30              # Frames to keep lost tracks (at 120fps = 250ms)
    track_activation_threshold: float = 0.7  # Confidence threshold for track activation
    minimum_iou_threshold: float = 0.1       # Minimum IoU for matching

    # Trajectory filtering
    min_trajectory_frames: int = 3  # Minimum frames for valid trajectory
    max_simultaneous_tracks: int = 5  # Maximum tracks to maintain


class BallTracker:
    """
    Track golf balls across frames using ByteTrack.

    Combines fast Hough circle detection with robust ByteTrack tracking
    for persistent track IDs and occlusion handling.

    Example:
        tracker = BallTracker()

        for frame in frames:
            tracked = tracker.update(frame)
            for ball in tracked:
                print(f"Track {ball.track_id}: ({ball.x}, {ball.y})")

        # Get the primary ball trajectory
        trajectory = tracker.get_primary_trajectory()
    """

    def __init__(
        self,
        detector_config: Optional[DetectorConfig] = None,
        tracker_config: Optional[TrackerConfig] = None
    ):
        self.detector = BallDetector(detector_config)
        self.config = tracker_config or TrackerConfig()

        # Initialize ByteTrack
        self._tracker = ByteTrackTracker(
            lost_track_buffer=self.config.lost_track_buffer,
            track_activation_threshold=self.config.track_activation_threshold,
            minimum_iou_threshold=self.config.minimum_iou_threshold,
        )
        logger.info("Using ByteTrack for ball tracking")

        # Track history
        self._trajectories: dict[int, BallTrajectory] = {}

    def reset(self):
        """Reset tracker state for new capture sequence."""
        self._tracker = ByteTrackTracker(
            lost_track_buffer=self.config.lost_track_buffer,
            track_activation_threshold=self.config.track_activation_threshold,
            minimum_iou_threshold=self.config.minimum_iou_threshold,
        )
        self._trajectories = {}

    def update(self, frame: CapturedFrame) -> List[TrackedBall]:
        """
        Process a frame and return tracked balls.

        Args:
            frame: Captured frame to process

        Returns:
            List of TrackedBall objects with persistent track IDs
        """
        # Detect balls using Hough circles
        detection = self.detector.detect(frame)

        if detection is None:
            return []

        return self._update_bytetrack(detection, frame)

    def _update_bytetrack(
        self,
        detection: DetectedBall,
        frame: CapturedFrame
    ) -> List[TrackedBall]:
        """Update tracking using ByteTrack."""
        # Convert detection to supervision format
        # ByteTrack expects bounding boxes as [x1, y1, x2, y2]
        x1 = detection.x - detection.radius
        y1 = detection.y - detection.radius
        x2 = detection.x + detection.radius
        y2 = detection.y + detection.radius

        detections = sv.Detections(
            xyxy=np.array([[x1, y1, x2, y2]]),
            confidence=np.array([detection.confidence]),
            class_id=np.array([0]),  # Single class: golf ball
        )

        # Update tracker
        tracked = self._tracker.update(detections)

        # Convert back to TrackedBall format
        tracked_balls = []
        for i in range(len(tracked)):
            bbox = tracked.xyxy[i]
            track_id = tracked.tracker_id[i] if tracked.tracker_id is not None else i

            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            radius = (bbox[2] - bbox[0]) / 2

            ball = TrackedBall(
                track_id=int(track_id),
                x=cx,
                y=cy,
                radius=radius,
                confidence=tracked.confidence[i] if tracked.confidence is not None else detection.confidence,
                frame_number=frame.frame_number,
                timestamp=frame.timestamp,
            )
            tracked_balls.append(ball)

            # Update trajectory
            if track_id not in self._trajectories:
                self._trajectories[track_id] = BallTrajectory(track_id=track_id)
            self._trajectories[track_id].positions.append(ball)

        return tracked_balls

    def process_sequence(self, frames: List[CapturedFrame]) -> dict[int, BallTrajectory]:
        """
        Process a sequence of frames and return all trajectories.

        Args:
            frames: List of captured frames

        Returns:
            Dict mapping track_id to BallTrajectory
        """
        self.reset()

        for frame in frames:
            self.update(frame)

        return self._trajectories.copy()

    def get_trajectories(self) -> dict[int, BallTrajectory]:
        """Get all tracked trajectories."""
        return self._trajectories.copy()

    def get_primary_trajectory(self) -> Optional[BallTrajectory]:
        """
        Get the most likely golf ball trajectory.

        Selects based on:
        1. Valid golf ball motion (up and away)
        2. Longest duration
        3. Highest average confidence

        Returns:
            Primary ball trajectory or None
        """
        if not self._trajectories:
            return None

        # Filter to valid golf trajectories
        valid = [t for t in self._trajectories.values()
                 if t.is_valid_golf_trajectory]

        if not valid:
            # Fall back to longest trajectory if none are "valid"
            valid = list(self._trajectories.values())

        if not valid:
            return None

        # Score trajectories
        def score(t: BallTrajectory) -> float:
            frames_score = t.num_frames / 10.0  # Normalize
            confidence_score = sum(p.confidence for p in t.positions) / max(1, len(t.positions))
            valid_motion_score = 1.0 if t.is_valid_golf_trajectory else 0.5
            return frames_score * confidence_score * valid_motion_score

        return max(valid, key=score)

    def get_ball_at_frame(self, frame_number: int) -> Optional[TrackedBall]:
        """Get the primary ball position at a specific frame."""
        trajectory = self.get_primary_trajectory()
        if not trajectory:
            return None

        for pos in trajectory.positions:
            if pos.frame_number == frame_number:
                return pos

        return None


class YOLOBallDetector:
    """
    YOLO-based ball detector for higher accuracy (optional).

    Use this when:
    - Running on hardware with GPU/TPU (Coral, Jetson)
    - IR illumination is not available
    - Higher accuracy is needed over speed

    Requires: pip install ultralytics
    """

    def __init__(self, model_path: str = "yolov8n.pt", device: str = "cpu"):
        try:
            from ultralytics import YOLO
            self._model = YOLO(model_path)
            self._model.to(device)
            self._available = True
            logger.info(f"YOLO detector initialized with {model_path} on {device}")
        except ImportError:
            self._model = None
            self._available = False
            logger.warning("YOLO not available. Install with: pip install ultralytics")

    @property
    def is_available(self) -> bool:
        return self._available

    def detect(self, frame: CapturedFrame) -> Optional[DetectedBall]:
        """Detect golf ball using YOLO."""
        if not self._available:
            return None

        # Run inference
        # Class 32 in COCO is "sports ball"
        results = self._model(frame.data, classes=[32], verbose=False)

        if not results or len(results[0].boxes) == 0:
            return None

        # Get highest confidence detection
        boxes = results[0].boxes
        best_idx = boxes.conf.argmax()

        bbox = boxes.xyxy[best_idx].cpu().numpy()
        confidence = float(boxes.conf[best_idx])

        # Convert to center + radius format
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        radius = (bbox[2] - bbox[0]) / 2

        return DetectedBall(
            x=float(cx),
            y=float(cy),
            radius=float(radius),
            confidence=confidence,
            frame_number=frame.frame_number,
            timestamp=frame.timestamp,
        )


class HybridBallTracker(BallTracker):
    """
    Hybrid tracker that can use either Hough or YOLO detection.

    Automatically falls back to Hough circles if YOLO is unavailable
    or too slow for the current hardware.
    """

    def __init__(
        self,
        use_yolo: bool = False,
        yolo_model: str = "yolov8n.pt",
        detector_config: Optional[DetectorConfig] = None,
        tracker_config: Optional[TrackerConfig] = None,
    ):
        super().__init__(detector_config, tracker_config)

        self._use_yolo = use_yolo
        if use_yolo:
            self._yolo = YOLOBallDetector(yolo_model)
            if not self._yolo.is_available:
                logger.warning("YOLO requested but not available, using Hough detection")
                self._use_yolo = False
        else:
            self._yolo = None

    def update(self, frame: CapturedFrame) -> List[TrackedBall]:
        """Process frame using configured detector."""
        # Detect using YOLO or Hough
        if self._use_yolo and self._yolo:
            detection = self._yolo.detect(frame)
        else:
            detection = self.detector.detect(frame)

        if detection is None:
            return []

        return self._update_bytetrack(detection, frame)
