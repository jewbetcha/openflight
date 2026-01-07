"""
Golf ball detection using computer vision.

Optimized for IR-illuminated ball against dark background,
viewed from behind the tee.
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from .capture import CapturedFrame


@dataclass
class DetectedBall:
    """A detected golf ball in a frame."""
    # Center position in pixels
    x: float
    y: float

    # Radius in pixels (indicates distance - smaller = further away)
    radius: float

    # Detection confidence (0-1)
    confidence: float

    # Frame metadata
    frame_number: int
    timestamp: float

    @property
    def center(self) -> Tuple[float, float]:
        """Return (x, y) center tuple."""
        return (self.x, self.y)

    @property
    def area(self) -> float:
        """Approximate ball area in pixels."""
        return 3.14159 * self.radius ** 2


@dataclass
class DetectorConfig:
    """Configuration for ball detection."""
    # Brightness threshold for IR ball (0-255)
    brightness_threshold: int = 200

    # Expected ball radius range in pixels (at various distances)
    min_radius: int = 5      # Ball far away
    max_radius: int = 50     # Ball close to camera

    # Circle detection parameters
    hough_dp: float = 1.2           # Inverse ratio of accumulator resolution
    hough_min_dist: int = 50        # Min distance between detected circles
    hough_param1: int = 50          # Canny edge detection threshold
    hough_param2: int = 20          # Circle detection threshold (lower = more circles)

    # Filtering
    min_confidence: float = 0.5     # Minimum confidence to accept detection


class BallDetector:
    """
    Detect golf ball in frames using circle detection.

    Optimized for IR-illuminated white ball against dark background.
    Uses a combination of thresholding and Hough circle detection.

    Example:
        detector = BallDetector()
        for frame in capture_result.frames:
            ball = detector.detect(frame)
            if ball:
                print(f"Ball at ({ball.x}, {ball.y}), radius={ball.radius}")
    """

    def __init__(self, config: Optional[DetectorConfig] = None):
        """
        Initialize ball detector.

        Args:
            config: Detection configuration, uses defaults if None
        """
        if not CV2_AVAILABLE:
            raise RuntimeError(
                "OpenCV not available. Install with: pip install opencv-python"
            )
        self.config = config or DetectorConfig()

    def detect(self, frame: CapturedFrame) -> Optional[DetectedBall]:
        """
        Detect golf ball in a single frame.

        Args:
            frame: Captured frame to analyze

        Returns:
            DetectedBall if found, None otherwise
        """
        # Convert to grayscale if needed
        if len(frame.data.shape) == 3:
            gray = cv2.cvtColor(frame.data, cv2.COLOR_RGB2GRAY)
        else:
            gray = frame.data

        # Apply threshold to isolate bright ball (IR illuminated)
        _, thresh = cv2.threshold(
            gray,
            self.config.brightness_threshold,
            255,
            cv2.THRESH_BINARY
        )

        # Apply slight blur to reduce noise
        blurred = cv2.GaussianBlur(thresh, (5, 5), 0)

        # Detect circles using Hough transform
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=self.config.hough_dp,
            minDist=self.config.hough_min_dist,
            param1=self.config.hough_param1,
            param2=self.config.hough_param2,
            minRadius=self.config.min_radius,
            maxRadius=self.config.max_radius
        )

        if circles is None:
            return None

        # Find best circle (highest confidence based on brightness and roundness)
        best_circle = None
        best_confidence = 0

        for circle in circles[0]:
            x, y, r = circle
            confidence = self._calculate_confidence(gray, int(x), int(y), int(r))

            if confidence > best_confidence and confidence >= self.config.min_confidence:
                best_confidence = confidence
                best_circle = (x, y, r)

        if best_circle is None:
            return None

        x, y, r = best_circle
        return DetectedBall(
            x=float(x),
            y=float(y),
            radius=float(r),
            confidence=best_confidence,
            frame_number=frame.frame_number,
            timestamp=frame.timestamp
        )

    def _calculate_confidence(self, gray: "np.ndarray", x: int, y: int, r: int) -> float:
        """
        Calculate detection confidence based on circle properties.

        Args:
            gray: Grayscale image
            x, y: Circle center
            r: Circle radius

        Returns:
            Confidence score 0-1
        """
        h, w = gray.shape[:2]

        # Check bounds
        if x - r < 0 or x + r >= w or y - r < 0 or y + r >= h:
            return 0.3  # Partial circle at edge

        # Create circular mask
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(mask, (x, y), r, 255, -1)

        # Calculate mean brightness inside circle
        mean_inside = cv2.mean(gray, mask=mask)[0]

        # Calculate mean brightness in ring around circle
        ring_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(ring_mask, (x, y), int(r * 1.5), 255, -1)
        cv2.circle(ring_mask, (x, y), r, 0, -1)
        mean_ring = cv2.mean(gray, mask=ring_mask)[0]

        # Good detection: bright inside, dark outside
        brightness_ratio = mean_inside / max(mean_ring + 1, 1)

        # Normalize to 0-1 confidence
        # Expect ratio > 5 for good IR-lit ball
        confidence = min(1.0, brightness_ratio / 10.0)

        return confidence

    def detect_sequence(self, frames: List[CapturedFrame]) -> List[Optional[DetectedBall]]:
        """
        Detect ball in a sequence of frames.

        Args:
            frames: List of frames to analyze

        Returns:
            List of DetectedBall (or None) for each frame
        """
        return [self.detect(frame) for frame in frames]

    def detect_with_tracking(
        self,
        frames: List[CapturedFrame],
        expected_direction: str = "up_and_away"
    ) -> List[Optional[DetectedBall]]:
        """
        Detect ball with trajectory-based tracking.

        Uses previous detections to predict and validate next position,
        improving accuracy for fast-moving ball.

        Args:
            frames: List of frames to analyze
            expected_direction: Expected ball movement ("up_and_away" for golf)

        Returns:
            List of DetectedBall (or None) for each frame
        """
        detections: List[Optional[DetectedBall]] = []
        prev_detection: Optional[DetectedBall] = None

        for frame in frames:
            # First pass: standard detection
            detection = self.detect(frame)

            # If we have previous detection, validate trajectory
            if detection and prev_detection:
                if not self._validate_trajectory(prev_detection, detection, expected_direction):
                    # Detection doesn't match expected trajectory
                    # Try to find ball in predicted region
                    detection = self._detect_in_region(
                        frame,
                        self._predict_position(prev_detection, expected_direction)
                    )

            detections.append(detection)
            if detection:
                prev_detection = detection

        return detections

    def _validate_trajectory(
        self,
        prev: DetectedBall,
        curr: DetectedBall,
        direction: str
    ) -> bool:
        """Validate that current detection follows expected trajectory."""
        if direction == "up_and_away":
            # Ball should move up (y decreases in image coords)
            # Ball should shrink (radius decreases)
            y_moving_up = curr.y < prev.y
            ball_shrinking = curr.radius <= prev.radius * 1.2  # Allow some tolerance

            return y_moving_up and ball_shrinking

        return True

    def _predict_position(
        self,
        prev: DetectedBall,
        direction: str
    ) -> Tuple[int, int, int, int]:
        """
        Predict search region for next frame.

        Returns:
            (x, y, width, height) of search region
        """
        if direction == "up_and_away":
            # Predict ball moving up and slightly shrinking
            pred_x = int(prev.x)
            pred_y = int(prev.y - prev.radius * 2)  # Move up
            search_size = int(prev.radius * 6)

            return (
                max(0, pred_x - search_size // 2),
                max(0, pred_y - search_size // 2),
                search_size,
                search_size
            )

        return (0, 0, 640, 480)

    def _detect_in_region(
        self,
        frame: CapturedFrame,
        region: Tuple[int, int, int, int]
    ) -> Optional[DetectedBall]:
        """Detect ball within a specific region of the frame."""
        x, y, w, h = region

        # Extract region
        roi = frame.data[y:y+h, x:x+w]

        # Create temporary frame for ROI
        roi_frame = CapturedFrame(
            data=roi,
            timestamp=frame.timestamp,
            frame_number=frame.frame_number
        )

        detection = self.detect(roi_frame)

        # Adjust coordinates back to full frame
        if detection:
            detection.x += x
            detection.y += y

        return detection
