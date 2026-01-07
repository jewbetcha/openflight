"""Tests for camera module."""

import pytest
import math

# Mock numpy for testing
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from openflight.camera import (
    CaptureConfig,
    CapturedFrame,
    CaptureResult,
    MockCameraCapture,
    DetectedBall,
    DetectorConfig,
    LaunchAngles,
    CameraCalibration,
)


class TestCaptureConfig:
    """Tests for CaptureConfig dataclass."""

    def test_default_config(self):
        """Default config should have reasonable values."""
        config = CaptureConfig()
        assert config.width == 640
        assert config.height == 480
        assert config.framerate == 120
        assert config.pre_trigger_frames == 30
        assert config.post_trigger_frames == 60

    def test_custom_config(self):
        """Custom config values should be respected."""
        config = CaptureConfig(
            width=1280,
            height=720,
            framerate=60,
            pre_trigger_frames=15,
            post_trigger_frames=45
        )
        assert config.width == 1280
        assert config.height == 720
        assert config.framerate == 60


class TestCapturedFrame:
    """Tests for CapturedFrame dataclass."""

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_frame_creation(self):
        """Create a basic captured frame."""
        data = np.zeros((480, 640, 3), dtype=np.uint8)
        frame = CapturedFrame(
            data=data,
            timestamp=12345.67,
            frame_number=42
        )
        assert frame.timestamp == 12345.67
        assert frame.frame_number == 42
        assert frame.data.shape == (480, 640, 3)


class TestCaptureResult:
    """Tests for CaptureResult dataclass."""

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_empty_result(self):
        """Empty result should have no frames."""
        result = CaptureResult()
        assert len(result.frames) == 0
        assert result.trigger_frame_index == 0

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_pre_post_trigger_split(self):
        """Should correctly split pre and post trigger frames."""
        frames = []
        for i in range(10):
            data = np.zeros((100, 100, 3), dtype=np.uint8)
            frames.append(CapturedFrame(
                data=data,
                timestamp=float(i),
                frame_number=i
            ))

        result = CaptureResult(
            frames=frames,
            trigger_time=5.0,
            trigger_frame_index=5
        )

        assert len(result.pre_trigger_frames) == 5
        assert len(result.post_trigger_frames) == 5
        assert result.pre_trigger_frames[0].frame_number == 0
        assert result.post_trigger_frames[0].frame_number == 5


class TestMockCameraCapture:
    """Tests for MockCameraCapture."""

    def test_start_stop(self):
        """Mock camera should start and stop cleanly."""
        camera = MockCameraCapture()
        assert not camera.is_running

        camera.start()
        assert camera.is_running

        camera.stop()
        assert not camera.is_running

    def test_context_manager(self):
        """Mock camera should work as context manager."""
        with MockCameraCapture() as camera:
            assert camera.is_running
        assert not camera.is_running

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_trigger_capture(self):
        """Trigger capture should return frames with moving ball."""
        camera = MockCameraCapture()
        camera.start()

        result = camera.trigger_capture()

        assert len(result.frames) > 0
        assert result.trigger_frame_index == camera.config.pre_trigger_frames

        camera.stop()

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_capture_single(self):
        """Single capture should return one frame."""
        camera = MockCameraCapture()
        frame = camera.capture_single()

        assert frame is not None
        assert frame.data.shape == (480, 640, 3)


class TestDetectedBall:
    """Tests for DetectedBall dataclass."""

    def test_ball_creation(self):
        """Create a basic detected ball."""
        ball = DetectedBall(
            x=320.0,
            y=240.0,
            radius=15.0,
            confidence=0.85,
            frame_number=10,
            timestamp=12345.67
        )
        assert ball.x == 320.0
        assert ball.y == 240.0
        assert ball.radius == 15.0
        assert ball.confidence == 0.85

    def test_center_property(self):
        """Center property should return (x, y) tuple."""
        ball = DetectedBall(
            x=100.5,
            y=200.5,
            radius=10.0,
            confidence=0.9,
            frame_number=0,
            timestamp=0.0
        )
        assert ball.center == (100.5, 200.5)

    def test_area_property(self):
        """Area property should calculate circle area."""
        ball = DetectedBall(
            x=0, y=0,
            radius=10.0,
            confidence=1.0,
            frame_number=0,
            timestamp=0.0
        )
        # pi * r^2 = pi * 100 ≈ 314.159
        assert abs(ball.area - 314.159) < 1.0


class TestDetectorConfig:
    """Tests for DetectorConfig dataclass."""

    def test_default_config(self):
        """Default config should have reasonable values."""
        config = DetectorConfig()
        assert config.brightness_threshold == 200
        assert config.min_radius == 5
        assert config.max_radius == 50
        assert config.min_confidence == 0.5

    def test_custom_config(self):
        """Custom config values should be respected."""
        config = DetectorConfig(
            brightness_threshold=180,
            min_radius=3,
            max_radius=60,
            min_confidence=0.7
        )
        assert config.brightness_threshold == 180
        assert config.min_radius == 3


class TestLaunchAngles:
    """Tests for LaunchAngles dataclass."""

    def test_angles_creation(self):
        """Create basic launch angles."""
        angles = LaunchAngles(
            vertical_deg=12.5,
            horizontal_deg=-2.3,
            confidence=0.92,
            frames_used=8,
            initial_x=320.0,
            initial_y=400.0,
            velocity_x=2.5,
            velocity_y=-15.0
        )
        assert angles.vertical_deg == 12.5
        assert angles.horizontal_deg == -2.3
        assert angles.confidence == 0.92
        assert angles.frames_used == 8


class TestCameraCalibration:
    """Tests for CameraCalibration dataclass."""

    def test_default_calibration(self):
        """Default calibration should match Pi HQ Camera specs."""
        cal = CameraCalibration()
        # Pi HQ Camera IMX477 sensor dimensions
        assert cal.sensor_width_mm == 6.287
        assert cal.sensor_height_mm == 4.712
        assert cal.ball_diameter_mm == 42.67  # Regulation golf ball

    def test_pixels_per_mm(self):
        """Pixels per mm calculation should be reasonable."""
        cal = CameraCalibration()
        ppm = cal.pixels_per_mm_at_ball
        # At 2m distance with 6mm focal length, should be ~0.3 pixels/mm
        assert 0.1 < ppm < 1.0

    def test_field_of_view(self):
        """FOV calculations should be reasonable for 6mm lens."""
        cal = CameraCalibration()
        # 6mm lens on 6.287mm sensor should give ~55° horizontal FOV
        assert 40 < cal.horizontal_fov_deg < 70
        assert 30 < cal.vertical_fov_deg < 55


class TestLaunchAngleCalculation:
    """Tests for launch angle calculation logic."""

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_calculator_creation(self):
        """Calculator should be creatable."""
        from openflight.camera import LaunchAngleCalculator
        calc = LaunchAngleCalculator()
        assert calc.min_detections == 3
        assert calc.max_frames == 10

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_insufficient_detections(self):
        """Should return None with too few detections."""
        from openflight.camera import LaunchAngleCalculator
        calc = LaunchAngleCalculator()

        # Only 2 detections, need at least 3
        detections = [
            DetectedBall(x=320, y=400, radius=20, confidence=0.9, frame_number=0, timestamp=0.0),
            DetectedBall(x=322, y=380, radius=19, confidence=0.9, frame_number=1, timestamp=0.01),
        ]

        result = calc.calculate(detections)
        assert result is None

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_upward_trajectory(self):
        """Ball moving up should have positive vertical angle."""
        from openflight.camera import LaunchAngleCalculator
        calc = LaunchAngleCalculator()

        # Ball moving upward (y decreasing in image coords)
        detections = [
            DetectedBall(x=320, y=400, radius=20, confidence=0.9, frame_number=0, timestamp=0.0),
            DetectedBall(x=322, y=380, radius=19, confidence=0.9, frame_number=1, timestamp=0.01),
            DetectedBall(x=324, y=360, radius=18, confidence=0.9, frame_number=2, timestamp=0.02),
            DetectedBall(x=326, y=340, radius=17, confidence=0.9, frame_number=3, timestamp=0.03),
        ]

        result = calc.calculate(detections)
        assert result is not None
        assert result.vertical_deg > 0  # Moving up
        assert result.frames_used == 4

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_right_trajectory(self):
        """Ball moving right should have positive horizontal angle."""
        from openflight.camera import LaunchAngleCalculator
        calc = LaunchAngleCalculator()

        # Ball moving right (x increasing)
        detections = [
            DetectedBall(x=300, y=400, radius=20, confidence=0.9, frame_number=0, timestamp=0.0),
            DetectedBall(x=320, y=380, radius=19, confidence=0.9, frame_number=1, timestamp=0.01),
            DetectedBall(x=340, y=360, radius=18, confidence=0.9, frame_number=2, timestamp=0.02),
            DetectedBall(x=360, y=340, radius=17, confidence=0.9, frame_number=3, timestamp=0.03),
        ]

        result = calc.calculate(detections)
        assert result is not None
        assert result.horizontal_deg > 0  # Moving right

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_handles_none_detections(self):
        """Should handle None values in detection list."""
        from openflight.camera import LaunchAngleCalculator
        calc = LaunchAngleCalculator()

        # Some frames have no detection
        detections = [
            DetectedBall(x=320, y=400, radius=20, confidence=0.9, frame_number=0, timestamp=0.0),
            None,  # Missed frame
            DetectedBall(x=324, y=360, radius=18, confidence=0.9, frame_number=2, timestamp=0.02),
            None,  # Missed frame
            DetectedBall(x=328, y=320, radius=16, confidence=0.9, frame_number=4, timestamp=0.04),
        ]

        result = calc.calculate(detections)
        assert result is not None
        assert result.frames_used == 3  # Only 3 valid detections

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_with_radar_speed(self):
        """Calculate with radar-measured ball speed should work."""
        from openflight.camera import LaunchAngleCalculator
        calc = LaunchAngleCalculator()

        detections = [
            DetectedBall(x=320, y=400, radius=20, confidence=0.9, frame_number=0, timestamp=0.0),
            DetectedBall(x=322, y=380, radius=19, confidence=0.9, frame_number=1, timestamp=0.01),
            DetectedBall(x=324, y=360, radius=18, confidence=0.9, frame_number=2, timestamp=0.02),
            DetectedBall(x=326, y=340, radius=17, confidence=0.9, frame_number=3, timestamp=0.03),
        ]

        result = calc.calculate_with_radar(detections, ball_speed_mph=150.0)
        assert result is not None
        assert result.vertical_deg > 0

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_ball_distance_estimation(self):
        """Ball distance estimation from apparent size."""
        from openflight.camera import LaunchAngleCalculator
        calc = LaunchAngleCalculator()

        # Large ball (close)
        close_ball = DetectedBall(
            x=320, y=240, radius=30,
            confidence=0.9, frame_number=0, timestamp=0.0
        )

        # Small ball (far)
        far_ball = DetectedBall(
            x=320, y=240, radius=10,
            confidence=0.9, frame_number=0, timestamp=0.0
        )

        close_dist = calc.estimate_ball_distance(close_ball)
        far_dist = calc.estimate_ball_distance(far_ball)

        # Far ball should be further away
        assert far_dist > close_dist
