"""
Camera-based ball tracking for launch angle detection.

Uses Hough circle detection with ByteTrack for persistent tracking,
or optionally YOLO/Roboflow for detection. Calculates launch angle
from the ball trajectory.
"""

import math
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import List, Optional

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import supervision as sv
    from trackers import ByteTrackTracker
    BYTETRACK_AVAILABLE = True
except ImportError:
    BYTETRACK_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

try:
    from inference_sdk import InferenceHTTPClient
    ROBOFLOW_AVAILABLE = True
except ImportError:
    ROBOFLOW_AVAILABLE = False


@dataclass
class BallPosition:
    """A detected ball position in a frame."""
    x: int
    y: int
    radius: int
    confidence: float
    timestamp: float
    track_id: Optional[int] = None


@dataclass
class LaunchAngle:
    """Calculated launch angle from ball trajectory."""
    vertical: float  # degrees, positive = up
    horizontal: float  # degrees, positive = right of target
    confidence: float  # 0-1
    positions: List[BallPosition]


class HoughDetector:
    """Detect balls using Hough Circle Transform."""

    def __init__(
        self,
        min_radius: int = 4,
        max_radius: int = 43,
        param1: int = 48,
        param2: int = 33,
        min_dist: int = 266
    ):
        self.min_radius = min_radius
        self.max_radius = max_radius
        self.param1 = param1
        self.param2 = param2
        self.min_dist = min_dist

    def detect(self, frame: np.ndarray) -> List[dict]:
        """Detect circles in frame, return list of detections."""
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        blurred = cv2.GaussianBlur(gray, (9, 9), 2)

        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=self.min_dist,
            param1=self.param1,
            param2=self.param2,
            minRadius=self.min_radius,
            maxRadius=self.max_radius
        )

        detections = []
        if circles is not None:
            circles = np.uint16(np.around(circles))
            for circle in circles[0, :]:
                x, y, r = circle
                detections.append({
                    'x': float(x),
                    'y': float(y),
                    'radius': float(r),
                    'confidence': 0.8
                })

        return detections


class CameraTracker:
    """
    Tracks golf ball using Hough circles + ByteTrack and calculates launch angle.

    Camera is positioned BEHIND the ball, looking down the target line.
    - X: Left/right in frame (positive = right of target)
    - Y: Up/down in frame (positive = up, launching upward)
    - Z: Depth estimated from ball size change (getting smaller = moving away)
    """

    MAX_POSITIONS = 30
    MIN_POSITIONS_FOR_ANGLE = 3
    POSITION_TIMEOUT = 0.5  # seconds

    # ByteTrack defaults
    _TRACK_BUFFER = 30
    _TRACK_ACTIVATION = 0.5
    _TRACK_MIN_IOU = 0.1

    def __init__(
        self,
        model_path: str = None,
        camera_distance_inches: float = 48,
        frame_width: int = 640,
        roboflow_api_key: Optional[str] = None,
        roboflow_model_id: Optional[str] = None,
        imgsz: int = 256,
        use_hough: bool = True,
        hough_param2: int = 33,
        hough_param1: int = 48,
        hough_min_radius: int = 4,
        hough_max_radius: int = 43,
        hough_min_dist: int = 266,
    ):
        if not CV2_AVAILABLE:
            raise ImportError("opencv required: pip install opencv-python")

        self.use_hough = use_hough
        self.use_roboflow = roboflow_model_id is not None
        self.model = None
        self.roboflow_client = None
        self.roboflow_model_id = roboflow_model_id
        self.imgsz = imgsz

        self.hough_detector = HoughDetector(
            param1=hough_param1,
            param2=hough_param2,
            min_radius=hough_min_radius,
            max_radius=hough_max_radius,
            min_dist=hough_min_dist,
        )
        self.tracker = self._create_tracker() if BYTETRACK_AVAILABLE else None

        # Initialize YOLO/Roboflow if not using Hough
        if not use_hough:
            if self.use_roboflow:
                if not ROBOFLOW_AVAILABLE:
                    raise ImportError("inference-sdk required")
                api_key = roboflow_api_key or os.environ.get("ROBOFLOW_API_KEY")
                self.roboflow_client = InferenceHTTPClient(
                    api_url="https://detect.roboflow.com",
                    api_key=api_key,
                )
            elif model_path and YOLO_AVAILABLE:
                self.model = YOLO(model_path)
            else:
                self.use_hough = True

        # Camera calibration
        self.camera_distance = camera_distance_inches
        fov_horizontal = 62  # degrees (typical Pi camera)
        view_width = 2 * camera_distance_inches * math.tan(math.radians(fov_horizontal / 2))
        self.pixels_per_inch = frame_width / view_width

        # Tracking state
        self.positions: deque = deque(maxlen=self.MAX_POSITIONS)
        self.last_detection_time: float = 0
        self.launch_detected: bool = False
        self.launch_positions: List[BallPosition] = []
        self.launch_velocity_threshold = 300  # pixels/second

    def _create_tracker(self):
        """Create a new ByteTrack tracker instance."""
        return ByteTrackTracker(
            lost_track_buffer=self._TRACK_BUFFER,
            track_activation_threshold=self._TRACK_ACTIVATION,
            minimum_iou_threshold=self._TRACK_MIN_IOU,
        )

    def process_frame(self, frame: np.ndarray) -> Optional[BallPosition]:
        """Process a frame and return detected ball position."""
        now = time.time()

        # Clear old positions if too much time has passed
        if self.positions and (now - self.last_detection_time) > self.POSITION_TIMEOUT:
            self._reset_tracking_state()

        # Run detection
        if self.use_hough:
            detections = self.hough_detector.detect(frame)
        elif self.use_roboflow:
            detections = self._detect_roboflow(frame)
        else:
            detections = self._detect_yolo(frame)

        if not detections:
            return None

        # Apply ByteTrack if available
        best = self._apply_tracking(detections)
        if not best:
            return None

        position = BallPosition(
            x=int(best['x']),
            y=int(best['y']),
            radius=int(best['radius']),
            confidence=best['confidence'],
            timestamp=now,
            track_id=best.get('track_id')
        )

        self.positions.append(position)
        self.last_detection_time = now
        self._check_launch(position)

        return position

    def _apply_tracking(self, detections: List[dict]) -> Optional[dict]:
        """Apply ByteTrack to detections, or pick best detection if unavailable."""
        if self.tracker and BYTETRACK_AVAILABLE:
            xyxy = np.array([
                [d['x'] - d['radius'], d['y'] - d['radius'],
                 d['x'] + d['radius'], d['y'] + d['radius']]
                for d in detections
            ])
            sv_detections = sv.Detections(
                xyxy=xyxy,
                confidence=np.array([d['confidence'] for d in detections]),
                class_id=np.zeros(len(detections), dtype=int)
            )

            tracked = self.tracker.update(sv_detections)
            if len(tracked) == 0:
                return None

            bbox = tracked.xyxy[0]
            return {
                'x': (bbox[0] + bbox[2]) / 2,
                'y': (bbox[1] + bbox[3]) / 2,
                'radius': (bbox[2] - bbox[0]) / 2,
                'confidence': tracked.confidence[0] if tracked.confidence is not None else 0.8,
                'track_id': int(tracked.tracker_id[0]) if tracked.tracker_id is not None else 0,
            }

        # No tracking - use highest confidence detection
        best = max(detections, key=lambda d: d['confidence'])
        best['track_id'] = None
        return best

    def _check_launch(self, current: BallPosition):
        """Check if ball has been launched based on velocity."""
        if len(self.positions) < 2:
            return

        prev = self.positions[-2]
        dt = current.timestamp - prev.timestamp
        if dt <= 0:
            return

        dx = current.x - prev.x
        dy = prev.y - current.y  # Invert Y (image coords are top-down)
        velocity = math.sqrt(dx*dx + dy*dy) / dt

        if velocity > self.launch_velocity_threshold and not self.launch_detected:
            self.launch_detected = True
            self.launch_positions = [prev, current]
        elif self.launch_detected and len(self.launch_positions) < 10:
            self.launch_positions.append(current)

    def _detect_yolo(self, frame: np.ndarray) -> List[dict]:
        """Run YOLO detection on frame."""
        if not self.model:
            return []

        results = self.model(frame, conf=0.3, imgsz=self.imgsz, verbose=False)
        detections = []

        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                class_name = self.model.names[cls]

                if cls == 32 or 'ball' in class_name.lower() or 'golf' in class_name.lower():
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    detections.append({
                        'x': (x1 + x2) / 2,
                        'y': (y1 + y2) / 2,
                        'radius': (x2 - x1 + y2 - y1) / 4,
                        'confidence': float(box.conf[0])
                    })

        return detections

    def _detect_roboflow(self, frame: np.ndarray) -> List[dict]:
        """Run Roboflow detection on frame."""
        if not self.roboflow_client:
            return []

        try:
            _, buffer = cv2.imencode('.jpg', frame)
            result = self.roboflow_client.infer(buffer.tobytes(), model_id=self.roboflow_model_id)

            return [
                {
                    'x': pred.get('x', 0),
                    'y': pred.get('y', 0),
                    'radius': (pred.get('width', 0) + pred.get('height', 0)) / 4,
                    'confidence': pred.get('confidence', 0)
                }
                for pred in result.get('predictions', [])
                if pred.get('confidence', 0) >= 0.3
            ]
        except Exception as e:
            print(f"Roboflow detection error: {e}")
            return []

    def _compute_angles(self, dx_pixels: float, dy_pixels: float, dz: float):
        """Convert pixel displacement to launch angles in degrees."""
        dx_inches = dx_pixels / self.pixels_per_inch
        dy_inches = dy_pixels / self.pixels_per_inch
        return (
            math.degrees(math.atan2(dy_inches, dz)),
            math.degrees(math.atan2(dx_inches, dz)),
        )

    def calculate_launch_angle(self) -> Optional[LaunchAngle]:
        """Calculate launch angle from tracked positions."""
        positions = self.launch_positions if self.launch_positions else list(self.positions)

        if len(positions) < self.MIN_POSITIONS_FOR_ANGLE:
            return None

        start = positions[0]
        end = positions[-1]

        dx_pixels = end.x - start.x
        dy_pixels = start.y - end.y  # Invert Y

        # Estimate depth from ball size change
        dz = 0.0
        if start.radius > 5 and end.radius > 5:
            size_ratio = end.radius / start.radius
            if size_ratio < 0.95:
                dz = self.camera_distance * (start.radius / end.radius - 1)

        # Fallback: estimate depth from elapsed time + assumed ball speed
        if dz <= 1:
            dt = end.timestamp - start.timestamp
            if dt > 0:
                dz = 2640 * dt  # ~150mph in inches/sec
            else:
                return None

        vertical, horizontal = self._compute_angles(dx_pixels, dy_pixels, dz)

        # Confidence from position count, detection quality, and depth estimation
        position_conf = min(1.0, len(positions) / 5)
        detection_conf = min(1.0, (end.confidence + start.confidence) / 2 / 0.5)
        depth_conf = 1.0 if dz > 1 else 0.5
        confidence = position_conf * detection_conf * depth_conf

        return LaunchAngle(
            vertical=round(vertical, 1),
            horizontal=round(horizontal, 1),
            confidence=round(confidence, 2),
            positions=positions.copy()
        )

    def _reset_tracking_state(self):
        """Reset all tracking state."""
        self.positions.clear()
        self.launch_detected = False
        self.launch_positions = []
        if self.tracker and BYTETRACK_AVAILABLE:
            self.tracker = self._create_tracker()

    def reset(self):
        """Clear tracking state for new shot."""
        self._reset_tracking_state()
        self.last_detection_time = 0

    def get_debug_frame(self, frame: np.ndarray) -> np.ndarray:
        """Draw debug overlay on frame showing detections and trajectory."""
        display = frame.copy()

        colors = [
            (255, 0, 0), (0, 255, 0), (0, 0, 255),
            (255, 255, 0), (255, 0, 255), (0, 255, 255)
        ]

        for i, pos in enumerate(self.positions):
            if pos.track_id is not None:
                color = colors[pos.track_id % len(colors)]
            else:
                t = i / max(1, len(self.positions) - 1)
                color = (int(255 * (1-t)), int(255 * t), 0)

            cv2.circle(display, (pos.x, pos.y), pos.radius, color, 2)
            cv2.circle(display, (pos.x, pos.y), 3, color, -1)

            if pos.track_id is not None:
                cv2.putText(display, f"ID:{pos.track_id}", (pos.x + 5, pos.y - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Draw trajectory line
        if len(self.positions) >= 2:
            points = [(p.x, p.y) for p in self.positions]
            for i in range(len(points) - 1):
                cv2.line(display, points[i], points[i+1], (0, 255, 255), 2)

        # Show launch angle if calculated
        angle = self.calculate_launch_angle()
        if angle:
            cv2.putText(display, f"Launch: {angle.vertical:.1f} V, {angle.horizontal:.1f} H",
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(display, f"Confidence: {angle.confidence:.0%}",
                       (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        status = "LAUNCH DETECTED" if self.launch_detected else f"Tracking: {len(self.positions)} positions"
        cv2.putText(display, status, (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        return display
