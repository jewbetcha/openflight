"""
Launch angle calculation from ball trajectory.

Calculates vertical and horizontal launch angles from detected
ball positions across multiple frames.
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
import math

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from .detector import DetectedBall


@dataclass
class CameraCalibration:
    """Camera calibration parameters for angle calculation."""
    # Sensor dimensions
    sensor_width_mm: float = 6.287    # Pi HQ Camera IMX477 sensor
    sensor_height_mm: float = 4.712

    # Lens focal length in mm
    focal_length_mm: float = 6.0      # Default wide-angle lens

    # Image resolution
    image_width: int = 640
    image_height: int = 480

    # Camera position relative to ball (mm)
    # Behind and slightly above tee
    distance_to_ball_mm: float = 2000  # 2 meters behind
    camera_height_mm: float = 300      # 30cm above ground (tee height ~50mm)

    # Golf ball diameter for size reference
    ball_diameter_mm: float = 42.67    # Regulation golf ball

    @property
    def pixels_per_mm_at_ball(self) -> float:
        """Calculate pixels per mm at the ball distance."""
        # Field of view at ball distance
        fov_width_mm = (self.sensor_width_mm * self.distance_to_ball_mm) / self.focal_length_mm
        return self.image_width / fov_width_mm

    @property
    def horizontal_fov_deg(self) -> float:
        """Horizontal field of view in degrees."""
        return 2 * math.degrees(math.atan(self.sensor_width_mm / (2 * self.focal_length_mm)))

    @property
    def vertical_fov_deg(self) -> float:
        """Vertical field of view in degrees."""
        return 2 * math.degrees(math.atan(self.sensor_height_mm / (2 * self.focal_length_mm)))


@dataclass
class LaunchAngles:
    """Calculated launch angles from trajectory."""
    # Vertical angle (positive = up)
    vertical_deg: float

    # Horizontal angle (positive = right of target line)
    horizontal_deg: float

    # Confidence in the measurement (0-1)
    confidence: float

    # Number of frames used in calculation
    frames_used: int

    # Initial ball position in image
    initial_x: float
    initial_y: float

    # Velocity vector (pixels per frame)
    velocity_x: float
    velocity_y: float


class LaunchAngleCalculator:
    """
    Calculate launch angles from detected ball positions.

    Uses trajectory fitting across multiple frames to determine
    the initial launch angle of the golf ball.

    Camera is positioned behind the golfer, looking down the target line.
    - Vertical angle: derived from Y movement (up in image = positive angle)
    - Horizontal angle: derived from X movement (right = right of target)

    Example:
        calculator = LaunchAngleCalculator()

        # Get detections from BallDetector
        detections = detector.detect_with_tracking(frames)

        # Calculate launch angles
        angles = calculator.calculate(detections)
        if angles:
            print(f"Launch: {angles.vertical_deg}° up, {angles.horizontal_deg}° right")
    """

    def __init__(self, calibration: Optional[CameraCalibration] = None):
        """
        Initialize launch angle calculator.

        Args:
            calibration: Camera calibration parameters
        """
        if not NUMPY_AVAILABLE:
            raise RuntimeError("NumPy required for launch angle calculation")

        self.calibration = calibration or CameraCalibration()

        # Minimum detections needed for reliable angle
        self.min_detections = 3

        # Maximum frames to consider (ball moves fast, use early frames)
        self.max_frames = 10

    def calculate(self, detections: List[Optional[DetectedBall]]) -> Optional[LaunchAngles]:
        """
        Calculate launch angles from ball detections.

        Args:
            detections: List of detected balls (may contain None for missed frames)

        Returns:
            LaunchAngles if calculation successful, None otherwise
        """
        # Filter valid detections
        valid = [(i, d) for i, d in enumerate(detections) if d is not None]

        if len(valid) < self.min_detections:
            return None

        # Use only early frames (ball is clearest right after launch)
        valid = valid[:self.max_frames]

        # Extract positions
        indices = np.array([v[0] for v in valid])
        x_positions = np.array([v[1].x for v in valid])
        y_positions = np.array([v[1].y for v in valid])
        confidences = np.array([v[1].confidence for v in valid])

        # Fit linear trajectory to get velocity
        # For early flight, trajectory is approximately linear
        vx, x0 = self._fit_line(indices, x_positions, confidences)
        vy, y0 = self._fit_line(indices, y_positions, confidences)

        # Calculate angles from velocity
        # Note: In image coords, Y increases downward, so negate for angle
        vertical_angle = self._velocity_to_vertical_angle(-vy, vx)
        horizontal_angle = self._velocity_to_horizontal_angle(vx)

        # Calculate confidence based on fit quality and detection confidences
        fit_confidence = self._calculate_fit_confidence(
            indices, x_positions, y_positions, vx, vy, x0, y0
        )
        avg_detection_confidence = np.mean(confidences)
        overall_confidence = fit_confidence * avg_detection_confidence

        return LaunchAngles(
            vertical_deg=vertical_angle,
            horizontal_deg=horizontal_angle,
            confidence=overall_confidence,
            frames_used=len(valid),
            initial_x=x0,
            initial_y=y0,
            velocity_x=vx,
            velocity_y=vy
        )

    def _fit_line(
        self,
        x: "np.ndarray",
        y: "np.ndarray",
        weights: "np.ndarray"
    ) -> Tuple[float, float]:
        """
        Fit weighted linear regression.

        Returns:
            (slope, intercept) of best fit line
        """
        # Weighted least squares
        w = weights / np.sum(weights)
        x_mean = np.sum(w * x)
        y_mean = np.sum(w * y)

        numerator = np.sum(w * (x - x_mean) * (y - y_mean))
        denominator = np.sum(w * (x - x_mean) ** 2)

        if abs(denominator) < 1e-10:
            return 0.0, y_mean

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        return slope, intercept

    def _velocity_to_vertical_angle(self, vy: float, vx: float) -> float:
        """
        Convert vertical velocity to launch angle.

        The ball appears to move up in the image (negative Y direction)
        when launched with positive vertical angle.

        Args:
            vy: Vertical velocity (pixels/frame, positive = up)
            vx: Horizontal velocity for perspective correction

        Returns:
            Vertical launch angle in degrees
        """
        # Calculate angle from velocity using camera calibration
        # Pixels to mm at ball distance
        ppm = self.calibration.pixels_per_mm_at_ball

        # Velocity in mm/frame
        vy_mm = vy / ppm

        # Distance traveled per frame (approximation based on typical ball speed)
        # Ball at 150 mph = 67 m/s, at 120fps = 558mm per frame
        # This is a rough estimate - actual distance would come from radar
        distance_per_frame_mm = 500  # Conservative estimate

        # Angle = arctan(vertical / forward)
        if distance_per_frame_mm > 0:
            angle_rad = math.atan(vy_mm / distance_per_frame_mm)
            return math.degrees(angle_rad)

        return 0.0

    def _velocity_to_horizontal_angle(self, vx: float) -> float:
        """
        Convert horizontal velocity to launch angle.

        Positive X velocity (ball moving right in image) indicates
        ball is going right of the target line.

        Args:
            vx: Horizontal velocity (pixels/frame)

        Returns:
            Horizontal launch angle in degrees (positive = right)
        """
        ppm = self.calibration.pixels_per_mm_at_ball
        vx_mm = vx / ppm

        distance_per_frame_mm = 500

        if distance_per_frame_mm > 0:
            angle_rad = math.atan(vx_mm / distance_per_frame_mm)
            return math.degrees(angle_rad)

        return 0.0

    def _calculate_fit_confidence(
        self,
        indices: "np.ndarray",
        x_pos: "np.ndarray",
        y_pos: "np.ndarray",
        vx: float,
        vy: float,
        x0: float,
        y0: float
    ) -> float:
        """
        Calculate confidence in trajectory fit.

        Based on how well the linear fit matches the actual positions.
        """
        # Predicted positions
        x_pred = x0 + vx * indices
        y_pred = y0 + vy * indices

        # RMS error
        x_error = np.sqrt(np.mean((x_pos - x_pred) ** 2))
        y_error = np.sqrt(np.mean((y_pos - y_pred) ** 2))

        # Normalize by typical ball radius (~15 pixels)
        typical_radius = 15
        normalized_error = (x_error + y_error) / (2 * typical_radius)

        # Convert to confidence (low error = high confidence)
        confidence = max(0.0, 1.0 - normalized_error)

        return confidence

    def calculate_with_radar(
        self,
        detections: List[Optional[DetectedBall]],
        ball_speed_mph: float,
        framerate: float = 120.0
    ) -> Optional[LaunchAngles]:
        """
        Calculate launch angles using radar-measured ball speed.

        Using the actual ball speed from radar improves accuracy
        of the angle calculation.

        Args:
            detections: List of detected balls
            ball_speed_mph: Ball speed from radar in mph
            framerate: Camera framerate

        Returns:
            LaunchAngles with improved accuracy
        """
        # Convert ball speed to mm per frame
        ball_speed_mms = ball_speed_mph * 0.44704 * 1000  # mph to mm/s
        distance_per_frame_mm = ball_speed_mms / framerate

        # Filter valid detections
        valid = [(i, d) for i, d in enumerate(detections) if d is not None]

        if len(valid) < self.min_detections:
            return None

        valid = valid[:self.max_frames]

        indices = np.array([v[0] for v in valid])
        x_positions = np.array([v[1].x for v in valid])
        y_positions = np.array([v[1].y for v in valid])
        confidences = np.array([v[1].confidence for v in valid])

        vx, x0 = self._fit_line(indices, x_positions, confidences)
        vy, y0 = self._fit_line(indices, y_positions, confidences)

        # Use radar-derived distance for more accurate angles
        ppm = self.calibration.pixels_per_mm_at_ball
        vy_mm = -vy / ppm  # Negate for image coords
        vx_mm = vx / ppm

        vertical_angle = math.degrees(math.atan(vy_mm / distance_per_frame_mm))
        horizontal_angle = math.degrees(math.atan(vx_mm / distance_per_frame_mm))

        fit_confidence = self._calculate_fit_confidence(
            indices, x_positions, y_positions, vx, vy, x0, y0
        )
        overall_confidence = fit_confidence * np.mean(confidences)

        return LaunchAngles(
            vertical_deg=vertical_angle,
            horizontal_deg=horizontal_angle,
            confidence=overall_confidence,
            frames_used=len(valid),
            initial_x=x0,
            initial_y=y0,
            velocity_x=vx,
            velocity_y=vy
        )

    def estimate_ball_distance(self, ball: DetectedBall) -> float:
        """
        Estimate ball distance from camera using apparent size.

        Larger radius = closer ball.

        Args:
            ball: Detected ball

        Returns:
            Estimated distance in mm
        """
        # Ball diameter in pixels
        ball_diameter_px = ball.radius * 2

        # Using similar triangles:
        # actual_size / distance = sensor_size / focal_length
        # actual_size / distance = image_size_in_px / (focal_length * pixels_per_mm_sensor)

        # Pixels per mm on sensor
        ppm_sensor = self.calibration.image_width / self.calibration.sensor_width_mm

        # Distance = (actual_size * focal_length * ppm_sensor) / apparent_size_px
        distance = (
            self.calibration.ball_diameter_mm *
            self.calibration.focal_length_mm *
            ppm_sensor
        ) / ball_diameter_px

        return distance
