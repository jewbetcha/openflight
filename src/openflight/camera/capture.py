"""
High-speed camera capture for golf ball tracking.

Designed for Raspberry Pi HQ Camera with IR illumination,
capturing frames at 120fps to track ball trajectory.
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from datetime import datetime

try:
    from picamera2 import Picamera2
    from picamera2.encoders import Encoder
    from picamera2.outputs import CircularOutput
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


@dataclass
class CaptureConfig:
    """Configuration for camera capture."""
    # Resolution - lower = faster framerate
    width: int = 640
    height: int = 480

    # Target framerate (Pi HQ Camera supports up to 120fps at 640x480)
    framerate: int = 120

    # Pre-trigger buffer (frames to keep before trigger)
    pre_trigger_frames: int = 30  # ~250ms at 120fps

    # Post-trigger capture (frames after trigger)
    post_trigger_frames: int = 60  # ~500ms at 120fps

    # Exposure settings for IR capture
    exposure_time_us: int = 2000  # 2ms - fast to reduce motion blur
    analogue_gain: float = 4.0    # Boost for IR sensitivity


@dataclass
class CapturedFrame:
    """A single captured frame with metadata."""
    data: "np.ndarray"
    timestamp: float
    frame_number: int


@dataclass
class CaptureResult:
    """Result of a triggered capture sequence."""
    frames: List[CapturedFrame] = field(default_factory=list)
    trigger_time: float = 0
    trigger_frame_index: int = 0

    @property
    def pre_trigger_frames(self) -> List[CapturedFrame]:
        """Frames captured before the trigger."""
        return self.frames[:self.trigger_frame_index]

    @property
    def post_trigger_frames(self) -> List[CapturedFrame]:
        """Frames captured after the trigger."""
        return self.frames[self.trigger_frame_index:]


class CameraCapture:
    """
    High-speed camera capture with circular buffer for triggered recording.

    Uses a circular buffer to continuously capture frames, then saves
    pre and post-trigger frames when a shot is detected by the radar.

    Example:
        camera = CameraCapture()
        camera.start()

        # When radar detects a shot:
        result = camera.trigger_capture()

        # Process frames
        for frame in result.frames:
            process(frame.data)

        camera.stop()
    """

    def __init__(self, config: Optional[CaptureConfig] = None):
        """
        Initialize camera capture.

        Args:
            config: Capture configuration, uses defaults if None
        """
        self.config = config or CaptureConfig()
        self._camera: Optional["Picamera2"] = None
        self._running = False
        self._circular_buffer: List[CapturedFrame] = []
        self._buffer_lock = threading.Lock()
        self._frame_count = 0
        self._capture_thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """
        Start camera capture with circular buffer.

        Returns:
            True if started successfully
        """
        if not PICAMERA_AVAILABLE:
            raise RuntimeError(
                "picamera2 not available. Install with: pip install picamera2"
            )

        try:
            self._camera = Picamera2()

            # Configure for high-speed capture
            video_config = self._camera.create_video_configuration(
                main={"size": (self.config.width, self.config.height),
                      "format": "RGB888"},
                controls={
                    "FrameRate": self.config.framerate,
                    "ExposureTime": self.config.exposure_time_us,
                    "AnalogueGain": self.config.analogue_gain,
                    # Disable auto-exposure for consistent frames
                    "AeEnable": False,
                }
            )
            self._camera.configure(video_config)
            self._camera.start()

            # Start capture thread
            self._running = True
            self._capture_thread = threading.Thread(
                target=self._capture_loop, daemon=True
            )
            self._capture_thread.start()

            return True

        except Exception as e:
            raise RuntimeError(f"Failed to start camera: {e}") from e

    def stop(self):
        """Stop camera capture."""
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None
        if self._camera:
            self._camera.stop()
            self._camera.close()
            self._camera = None

    def _capture_loop(self):
        """Continuous capture loop maintaining circular buffer."""
        buffer_size = self.config.pre_trigger_frames + self.config.post_trigger_frames

        while self._running:
            try:
                # Capture frame
                frame_data = self._camera.capture_array()
                timestamp = time.time()

                frame = CapturedFrame(
                    data=frame_data,
                    timestamp=timestamp,
                    frame_number=self._frame_count
                )
                self._frame_count += 1

                # Add to circular buffer
                with self._buffer_lock:
                    self._circular_buffer.append(frame)
                    # Trim buffer to max size
                    if len(self._circular_buffer) > buffer_size:
                        self._circular_buffer.pop(0)

            except Exception:
                if self._running:
                    time.sleep(0.001)

    def trigger_capture(self) -> CaptureResult:
        """
        Trigger capture - grab current buffer and continue capturing.

        Call this when the radar detects a shot to capture frames
        around the trigger point.

        Returns:
            CaptureResult with pre and post-trigger frames
        """
        trigger_time = time.time()

        # Wait for post-trigger frames
        post_frames_needed = self.config.post_trigger_frames
        frame_interval = 1.0 / self.config.framerate
        wait_time = post_frames_needed * frame_interval
        time.sleep(wait_time)

        # Grab buffer
        with self._buffer_lock:
            frames = self._circular_buffer.copy()

        # Find trigger point in frames
        trigger_frame_index = 0
        for i, frame in enumerate(frames):
            if frame.timestamp >= trigger_time:
                trigger_frame_index = i
                break

        return CaptureResult(
            frames=frames,
            trigger_time=trigger_time,
            trigger_frame_index=trigger_frame_index
        )

    def capture_single(self) -> Optional[CapturedFrame]:
        """
        Capture a single frame (for testing/calibration).

        Returns:
            Single captured frame or None
        """
        if not self._camera:
            return None

        frame_data = self._camera.capture_array()
        return CapturedFrame(
            data=frame_data,
            timestamp=time.time(),
            frame_number=self._frame_count
        )

    @property
    def is_running(self) -> bool:
        """Check if camera is currently capturing."""
        return self._running

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


class MockCameraCapture:
    """Mock camera for testing without hardware."""

    def __init__(self, config: Optional[CaptureConfig] = None):
        """Initialize mock camera."""
        self.config = config or CaptureConfig()
        self._running = False
        self._frame_count = 0

    def start(self) -> bool:
        """Start mock capture."""
        self._running = True
        return True

    def stop(self):
        """Stop mock capture."""
        self._running = False

    def trigger_capture(self) -> CaptureResult:
        """Generate mock capture result with synthetic frames."""
        if not NUMPY_AVAILABLE:
            return CaptureResult()

        frames = []
        trigger_time = time.time()
        total_frames = (self.config.pre_trigger_frames +
                        self.config.post_trigger_frames)

        for i in range(total_frames):
            # Create synthetic frame with a "ball" that moves
            frame_data = np.zeros(
                (self.config.height, self.config.width, 3),
                dtype=np.uint8
            )

            # Simulate ball moving up and away (shrinking)
            if i >= self.config.pre_trigger_frames:
                ball_frame = i - self.config.pre_trigger_frames
                # Ball starts center-bottom, moves up and shrinks
                cx = self.config.width // 2 + ball_frame * 2
                cy = self.config.height - 50 - ball_frame * 8
                radius = max(5, 20 - ball_frame)

                if 0 <= cy < self.config.height and radius > 0:
                    # Draw white circle (simulating IR-lit ball)
                    y, x = np.ogrid[:self.config.height, :self.config.width]
                    mask = (x - cx)**2 + (y - cy)**2 <= radius**2
                    frame_data[mask] = [255, 255, 255]

            timestamp = trigger_time + (i - self.config.pre_trigger_frames) / self.config.framerate
            frames.append(CapturedFrame(
                data=frame_data,
                timestamp=timestamp,
                frame_number=self._frame_count + i
            ))

        self._frame_count += total_frames

        return CaptureResult(
            frames=frames,
            trigger_time=trigger_time,
            trigger_frame_index=self.config.pre_trigger_frames
        )

    def capture_single(self) -> Optional[CapturedFrame]:
        """Capture single mock frame."""
        if not NUMPY_AVAILABLE:
            return None

        frame_data = np.zeros(
            (self.config.height, self.config.width, 3),
            dtype=np.uint8
        )
        return CapturedFrame(
            data=frame_data,
            timestamp=time.time(),
            frame_number=self._frame_count
        )

    @property
    def is_running(self) -> bool:
        """Check if mock camera is running."""
        return self._running

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False
