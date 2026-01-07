"""
Camera-based ball tracking for launch angle detection.

Uses YOLO or Roboflow to detect the golf ball across multiple frames and
calculates launch angle from the trajectory.
"""

import math
import os
import time
from dataclasses import dataclass
from typing import Optional, List
from collections import deque

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

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


@dataclass
class BallPosition:
    """A detected ball position in a frame."""
    x: int  # pixels from left
    y: int  # pixels from top
    radius: int  # estimated ball radius in pixels
    confidence: float
    timestamp: float


@dataclass
class LaunchAngle:
    """Calculated launch angle from ball trajectory."""
    vertical: float  # degrees, positive = up
    horizontal: float  # degrees, positive = right of target
    confidence: float  # 0-1, based on detection quality
    positions: List[BallPosition]  # positions used for calculation


class CameraTracker:
    """
    Tracks golf ball using YOLO and calculates launch angle.

    Camera is positioned BEHIND the ball, looking down the target line.
    This allows us to see both vertical and horizontal launch angles
    directly from ball movement in the frame.

    Coordinate system (from camera's perspective):
    - Origin: Ball position at address (tee) - center of frame
    - X: Left/right in frame (positive = right, ball going right of target)
    - Y: Up/down in frame (positive = up, ball launching upward)
    - Z: Depth (ball moving away = getting smaller in frame)

    Vertical launch angle: arctan(Y movement / Z movement)
    Horizontal launch angle: arctan(X movement / Z movement)

    We estimate Z (depth) from ball size change - ball getting smaller
    means it's moving away from the camera toward the target.
    """

    # Detection settings
    MIN_CONFIDENCE = 0.3
    BALL_CLASS_NAME = "golf-ball"  # For fine-tuned model
    SPORTS_BALL_CLASS = 32  # COCO class for generic model

    # Tracking settings
    MAX_POSITIONS = 10  # Max positions to store
    MIN_POSITIONS_FOR_ANGLE = 2  # Minimum positions to calculate angle
    POSITION_TIMEOUT = 0.5  # Seconds before clearing old positions

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        camera_height_inches: float = 12,
        camera_distance_inches: float = 48,
        camera_angle_degrees: float = 0,
        frame_width: int = 640,
        frame_height: int = 480,
        roboflow_api_key: Optional[str] = None,
        roboflow_model_id: Optional[str] = None,
        imgsz: int = 256,
    ):
        """
        Initialize the camera tracker.

        Args:
            model_path: Path to YOLO model (.pt or NCNN folder)
            camera_height_inches: Height of camera lens above ground
            camera_distance_inches: Distance from camera to ball (perpendicular)
            camera_angle_degrees: Camera tilt angle (0 = level, positive = tilted up)
            frame_width: Camera frame width in pixels
            frame_height: Camera frame height in pixels
            roboflow_api_key: Roboflow API key (uses Roboflow if provided)
            roboflow_model_id: Roboflow model ID (e.g., "golfballdetector/10")
            imgsz: YOLO inference input size (256 for speed, 640 for accuracy)
        """
        if not CV2_AVAILABLE:
            raise ImportError("opencv required: pip install opencv-python")

        # Determine which backend to use
        self.use_roboflow = roboflow_model_id is not None
        self.model = None
        self.roboflow_client = None
        self.roboflow_model_id = roboflow_model_id
        self.model_path = model_path

        # Store inference settings
        self.imgsz = imgsz

        if self.use_roboflow:
            if not ROBOFLOW_AVAILABLE:
                raise ImportError("inference-sdk required: pip install inference-sdk")

            # Get API key from parameter or environment
            api_key = roboflow_api_key or os.environ.get("ROBOFLOW_API_KEY")

            self.roboflow_client = InferenceHTTPClient(
                api_url="https://detect.roboflow.com",
                api_key=api_key,
            )
            print(f"Using Roboflow model: {roboflow_model_id}")
        else:
            if not YOLO_AVAILABLE:
                raise ImportError("ultralytics required: pip install ultralytics")
            self.model = YOLO(model_path)
            print(f"Using local YOLO model: {model_path} (imgsz={imgsz})")

        # Camera calibration
        self.camera_height = camera_height_inches
        self.camera_distance = camera_distance_inches
        self.camera_angle = camera_angle_degrees
        self.frame_width = frame_width
        self.frame_height = frame_height

        # Estimate pixels per inch at ball distance
        # Rough approximation - proper calibration would use checkerboard
        # Assuming ~60 degree FOV for typical Pi camera
        fov_horizontal = 62  # degrees
        view_width_at_distance = 2 * camera_distance_inches * math.tan(math.radians(fov_horizontal / 2))
        self.pixels_per_inch = frame_width / view_width_at_distance

        # Tracking state
        self.positions: deque = deque(maxlen=self.MAX_POSITIONS)
        self.last_detection_time: float = 0
        self.is_tracking: bool = False

        # For detecting launch (ball moving fast)
        self.launch_detected: bool = False
        self.launch_positions: List[BallPosition] = []

    def process_frame(self, frame: np.ndarray) -> Optional[BallPosition]:
        """
        Process a frame and detect ball position.

        Args:
            frame: RGB image from camera

        Returns:
            BallPosition if ball detected, None otherwise
        """
        now = time.time()

        # Clear old positions if too much time has passed
        if self.positions and (now - self.last_detection_time) > self.POSITION_TIMEOUT:
            self.positions.clear()
            self.launch_detected = False
            self.launch_positions = []

        # Run detection based on backend
        ball_detections = []

        if self.use_roboflow:
            ball_detections = self._detect_roboflow(frame, now)
        else:
            ball_detections = self._detect_yolo(frame, now)

        if not ball_detections:
            return None

        # Use highest confidence detection
        best = max(ball_detections, key=lambda b: b.confidence)

        # Add to tracking
        self.positions.append(best)
        self.last_detection_time = now

        # Check for launch (sudden movement)
        if len(self.positions) >= 2:
            prev = self.positions[-2]
            curr = self.positions[-1]
            dt = curr.timestamp - prev.timestamp

            if dt > 0:
                # Calculate velocity in pixels/second
                dx = curr.x - prev.x
                dy = prev.y - curr.y  # Invert Y (image coords are top-down)
                velocity = math.sqrt(dx*dx + dy*dy) / dt

                # If ball is moving fast (>500 pixels/sec), it's launching
                if velocity > 500 and not self.launch_detected:
                    self.launch_detected = True
                    self.launch_positions = [prev, curr]
                elif self.launch_detected and len(self.launch_positions) < 5:
                    self.launch_positions.append(curr)

        return best

    def _detect_yolo(self, frame: np.ndarray, timestamp: float) -> List[BallPosition]:
        """Run YOLO detection on frame."""
        ball_detections = []

        results = self.model(frame, conf=self.MIN_CONFIDENCE, imgsz=self.imgsz, verbose=False)

        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                class_name = self.model.names[cls]

                # Check if it's a ball (works with fine-tuned or generic model)
                is_ball = (
                    cls == self.SPORTS_BALL_CLASS or
                    'ball' in class_name.lower() or
                    'golf' in class_name.lower()
                )

                if is_ball:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)
                    radius = int((x2 - x1 + y2 - y1) / 4)

                    ball_detections.append(BallPosition(
                        x=cx,
                        y=cy,
                        radius=radius,
                        confidence=conf,
                        timestamp=timestamp
                    ))

        return ball_detections

    def _detect_roboflow(self, frame: np.ndarray, timestamp: float) -> List[BallPosition]:
        """Run Roboflow detection on frame."""
        ball_detections = []

        try:
            # Encode frame as JPEG for API
            _, buffer = cv2.imencode('.jpg', frame)
            image_bytes = buffer.tobytes()

            # Run inference via Roboflow API
            result = self.roboflow_client.infer(image_bytes, model_id=self.roboflow_model_id)

            # Parse predictions
            predictions = result.get('predictions', [])
            for pred in predictions:
                conf = pred.get('confidence', 0)
                if conf < self.MIN_CONFIDENCE:
                    continue

                # Get bounding box (Roboflow returns center + width/height)
                cx = int(pred.get('x', 0))
                cy = int(pred.get('y', 0))
                width = int(pred.get('width', 0))
                height = int(pred.get('height', 0))
                radius = int((width + height) / 4)

                ball_detections.append(BallPosition(
                    x=cx,
                    y=cy,
                    radius=radius,
                    confidence=conf,
                    timestamp=timestamp
                ))

        except Exception as e:
            print(f"Roboflow detection error: {e}")

        return ball_detections

    def calculate_launch_angle(self) -> Optional[LaunchAngle]:
        """
        Calculate launch angle from tracked positions.

        With camera BEHIND the ball looking down target line:
        - Vertical angle: How much the ball moves UP in frame vs. away (size decrease)
        - Horizontal angle: How much the ball moves LEFT/RIGHT in frame vs. away

        Returns:
            LaunchAngle if enough data, None otherwise
        """
        # Use launch positions if we detected a launch, otherwise use recent positions
        positions = self.launch_positions if self.launch_positions else list(self.positions)

        if len(positions) < self.MIN_POSITIONS_FOR_ANGLE:
            return None

        # Use first and last position for angle calculation
        start = positions[0]
        end = positions[-1]

        # Calculate pixel displacement in frame
        # X: positive = ball moving right in frame (right of target)
        # Y: positive = ball moving up in frame (launching upward)
        dx_pixels = end.x - start.x
        dy_pixels = start.y - end.y  # Invert because image Y is top-down

        # Estimate depth (Z) movement from ball size change
        # Ball getting smaller = moving away from camera
        # Use golf ball diameter (1.68") as reference
        if start.radius > 5 and end.radius > 5:
            # Ratio of size change indicates how far ball traveled
            size_ratio = end.radius / start.radius

            if size_ratio < 0.95:  # Ball is moving away
                # Estimate distance traveled based on size decrease
                # If ball is half the size, it's roughly twice as far
                # This is approximate - proper calibration would be better
                distance_ratio = start.radius / end.radius
                dz_estimated = self.camera_distance * (distance_ratio - 1)
            else:
                # Ball hasn't moved away much, can't calculate angles reliably
                dz_estimated = 0
        else:
            dz_estimated = 0

        # Calculate angles
        # Need some forward movement to calculate angles
        if dz_estimated > 1:  # At least 1 inch of forward movement
            # Convert pixel displacement to inches at the starting distance
            dx_inches = dx_pixels / self.pixels_per_inch
            dy_inches = dy_pixels / self.pixels_per_inch

            # Vertical launch angle: arctan(rise / run)
            vertical_angle = math.degrees(math.atan2(dy_inches, dz_estimated))

            # Horizontal launch angle: arctan(horizontal deviation / run)
            # Positive = right of target, Negative = left of target
            horizontal_angle = math.degrees(math.atan2(dx_inches, dz_estimated))
        else:
            # Fallback: estimate from frame movement alone
            # Less accurate but better than nothing
            # Assume typical forward distance based on time between frames
            dt = end.timestamp - start.timestamp
            if dt > 0:
                # Assume ball traveling ~150mph = ~2640 inches/sec
                estimated_ball_speed_ips = 2640
                dz_estimated = estimated_ball_speed_ips * dt

                dx_inches = dx_pixels / self.pixels_per_inch
                dy_inches = dy_pixels / self.pixels_per_inch

                vertical_angle = math.degrees(math.atan2(dy_inches, dz_estimated))
                horizontal_angle = math.degrees(math.atan2(dx_inches, dz_estimated))
            else:
                vertical_angle = 0
                horizontal_angle = 0

        # Calculate confidence based on:
        # - Number of positions tracked
        # - Detection confidence
        # - Whether we got good size-based depth estimate
        position_conf = min(1.0, len(positions) / 5)
        detection_conf = min(1.0, (end.confidence + start.confidence) / 2 / 0.5)
        depth_conf = 1.0 if dz_estimated > 1 else 0.5
        confidence = position_conf * detection_conf * depth_conf

        return LaunchAngle(
            vertical=round(vertical_angle, 1),
            horizontal=round(horizontal_angle, 1),
            confidence=round(confidence, 2),
            positions=positions.copy()
        )

    def reset(self):
        """Clear tracking state for new shot."""
        self.positions.clear()
        self.launch_detected = False
        self.launch_positions = []
        self.last_detection_time = 0

    def get_debug_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Draw debug overlay on frame showing detections and trajectory.

        Args:
            frame: Original RGB frame

        Returns:
            Frame with debug overlay
        """
        display = frame.copy()

        # Draw all tracked positions
        for i, pos in enumerate(self.positions):
            # Color from red (old) to green (new)
            t = i / max(1, len(self.positions) - 1)
            color = (int(255 * (1-t)), int(255 * t), 0)
            cv2.circle(display, (pos.x, pos.y), pos.radius, color, 2)
            cv2.circle(display, (pos.x, pos.y), 3, color, -1)

        # Draw trajectory line
        if len(self.positions) >= 2:
            points = [(p.x, p.y) for p in self.positions]
            for i in range(len(points) - 1):
                cv2.line(display, points[i], points[i+1], (0, 255, 255), 2)

        # Show launch angle if calculated
        angle = self.calculate_launch_angle()
        if angle:
            text = f"Launch: {angle.vertical:.1f}° (conf: {angle.confidence:.0%})"
            cv2.putText(display, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # Show tracking status
        status = "LAUNCH DETECTED" if self.launch_detected else f"Tracking: {len(self.positions)} positions"
        cv2.putText(display, status, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        return display
