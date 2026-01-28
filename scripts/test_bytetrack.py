#!/usr/bin/env python3
"""
Test ByteTrack ball tracking on camera feed or video.

This script tests the trackers library (ByteTrack) for maintaining
persistent object IDs across frames - essential for trajectory analysis.

Usage:
    # On Pi with display
    DISPLAY=:0 python scripts/test_bytetrack.py

    # Headless mode (saves frames)
    python scripts/test_bytetrack.py --headless --num-frames 30

    # Test with video file
    python scripts/test_bytetrack.py --video golf_swing.mp4

    # Test with image sequence (simulates tracking)
    python scripts/test_bytetrack.py --images frame_*.png

    # Use white blob detection (better for carpet/grass)
    python scripts/test_bytetrack.py --white-detect

    # Use YOLO detection instead of Hough circles
    python scripts/test_bytetrack.py --detector yolo --model models/golf_ball_yolo11n_new_256.onnx

    # Adjust tracking parameters
    python scripts/test_bytetrack.py --track-thresh 0.3 --track-buffer 30

    # Fix camera colors (white balance)
    python scripts/test_bytetrack.py --awb auto
"""

import argparse
import glob
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("OpenCV required: pip install opencv-python")

try:
    from trackers import ByteTrackTracker
    import supervision as sv
    TRACKERS_AVAILABLE = True
except ImportError:
    TRACKERS_AVAILABLE = False
    print("trackers required: pip install trackers supervision")

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False


@dataclass
class Detection:
    """A single detection with bounding box."""
    x: float
    y: float
    radius: float
    confidence: float

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        """Return as (x1, y1, x2, y2)."""
        return (
            self.x - self.radius,
            self.y - self.radius,
            self.x + self.radius,
            self.y + self.radius
        )


class HoughDetector:
    """Detect balls using Hough Circle Transform with golf ball filtering."""

    def __init__(
        self,
        min_radius: int = 8,
        max_radius: int = 40,
        param1: int = 50,
        param2: int = 25,  # Balance between sensitivity and noise
        min_dist: int = 40,
        min_brightness: int = 140,  # Golf balls are WHITE
        min_uniformity: float = 0.7,  # How uniform the circle brightness is
        brightness_filter: bool = True,
        enhance_contrast: bool = True,
        use_white_detection: bool = False,  # Color-based white detection
    ):
        self.min_radius = min_radius
        self.max_radius = max_radius
        self.param1 = param1
        self.param2 = param2
        self.min_dist = min_dist
        self.min_brightness = min_brightness
        self.min_uniformity = min_uniformity
        self.brightness_filter = brightness_filter
        self.enhance_contrast = enhance_contrast
        self.use_white_detection = use_white_detection

    def _detect_white_blobs(self, frame: np.ndarray, is_rgb: bool = False) -> List[Detection]:
        """
        Detect white circular objects using color-based detection.

        Better for low-contrast situations (ball on carpet, grass, etc.)
        where edge-based Hough detection struggles.
        """
        # Convert to HSV for color-based detection
        if is_rgb:
            hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        else:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        h, w = gray.shape[:2]

        # White color detection: low saturation, high value
        # Golf balls are very white (low saturation, high brightness)
        lower_white = np.array([0, 0, 180])   # Any hue, low sat, high value
        upper_white = np.array([180, 60, 255])  # Any hue, low sat, max value

        white_mask = cv2.inRange(hsv, lower_white, upper_white)

        # Morphological operations to clean up mask
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_OPEN, kernel)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)

        # Find contours of white regions
        contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for contour in contours:
            area = cv2.contourArea(contour)

            # Filter by area (approximate ball size)
            min_area = np.pi * self.min_radius ** 2
            max_area = np.pi * self.max_radius ** 2
            if area < min_area or area > max_area:
                continue

            # Get enclosing circle
            (cx, cy), radius = cv2.minEnclosingCircle(contour)
            cx, cy, radius = int(cx), int(cy), int(radius)

            # Check circularity (area vs enclosing circle area)
            enclosing_area = np.pi * radius ** 2
            circularity = area / enclosing_area if enclosing_area > 0 else 0

            # Golf balls should be fairly circular (>0.7)
            if circularity < 0.65:
                continue

            # Radius bounds check
            if radius < self.min_radius or radius > self.max_radius:
                continue

            # Bounds check
            if cx - radius < 0 or cx + radius >= w or cy - radius < 0 or cy + radius >= h:
                continue

            # Get brightness of the region
            mask = np.zeros_like(gray)
            cv2.circle(mask, (cx, cy), radius, 255, -1)
            mean_brightness = cv2.mean(gray, mask=mask)[0]

            if mean_brightness < self.min_brightness:
                continue

            # Confidence based on circularity and brightness
            confidence = circularity * (mean_brightness / 255.0)

            detections.append(Detection(
                x=float(cx),
                y=float(cy),
                radius=float(radius),
                confidence=confidence
            ))

        return detections

    def detect(self, frame: np.ndarray, is_rgb: bool = False) -> List[Detection]:
        """Detect circles in frame, filtering for bright golf ball candidates."""
        # Use white blob detection if enabled (better for low-contrast surfaces)
        if self.use_white_detection:
            return self._detect_white_blobs(frame, is_rgb)

        # Convert to grayscale
        if len(frame.shape) == 3:
            if is_rgb:
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        # Keep original for brightness checking (before CLAHE)
        gray_original = gray.copy()

        h, w = gray.shape[:2]

        # Enhance contrast for edge detection only
        if self.enhance_contrast:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

        # Apply blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)

        # Detect circles
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
                x, y, r = int(circle[0]), int(circle[1]), int(circle[2])

                # Bounds check
                if x - r < 0 or x + r >= w or y - r < 0 or y + r >= h:
                    continue

                if self.brightness_filter:
                    # Use ORIGINAL image for brightness (not CLAHE enhanced)
                    # Create circular mask for the detection
                    mask = np.zeros((2*r, 2*r), dtype=np.uint8)
                    cv2.circle(mask, (r, r), r, 255, -1)

                    # Extract ROI
                    roi = gray_original[y-r:y+r, x-r:x+r]
                    if roi.shape[0] != 2*r or roi.shape[1] != 2*r:
                        continue

                    # Get pixels inside the circle
                    circle_pixels = roi[mask == 255]
                    if len(circle_pixels) == 0:
                        continue

                    # Check brightness
                    mean_brightness = np.mean(circle_pixels)
                    if mean_brightness < self.min_brightness:
                        continue  # Too dark

                    # Check uniformity - golf balls are solid white, not edges/gradients
                    std_brightness = np.std(circle_pixels)
                    uniformity = 1.0 - (std_brightness / 128.0)  # Lower std = more uniform
                    if uniformity < self.min_uniformity:
                        continue  # Too varied, probably an edge or texture

                    # CIRCULARITY CHECK - verify it's actually round, not a white rectangle
                    # Compare brightness inside circle vs corners of bounding box
                    # A real circle should have darker corners (background showing)
                    corner_mask = np.ones((2*r, 2*r), dtype=np.uint8) * 255
                    cv2.circle(corner_mask, (r, r), r, 0, -1)  # Mask out the circle
                    corner_pixels = roi[corner_mask == 255]

                    if len(corner_pixels) > 10:
                        corner_brightness = np.mean(corner_pixels)
                        # Ball should be significantly brighter than corners
                        # If corners are also bright, it's probably a white rectangle
                        if corner_brightness > self.min_brightness * 0.85:
                            continue  # Corners too bright - probably a white box, not a ball

                    # Confidence based on brightness and uniformity
                    confidence = (mean_brightness / 255.0) * uniformity
                else:
                    confidence = 0.8

                detections.append(Detection(
                    x=float(x),
                    y=float(y),
                    radius=float(r),
                    confidence=confidence
                ))

        return detections


class YOLODetector:
    """Detect balls using YOLO."""

    def __init__(self, model_path: str, imgsz: int = 256, confidence: float = 0.3):
        if not YOLO_AVAILABLE:
            raise RuntimeError("ultralytics required: pip install ultralytics")
        self.model = YOLO(model_path)
        self.imgsz = imgsz
        self.confidence = confidence

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Detect balls in frame."""
        results = self.model(
            frame,
            conf=self.confidence,
            imgsz=self.imgsz,
            verbose=False
        )

        detections = []
        for r in results:
            boxes = r.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])

                # Convert to center + radius
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                radius = (x2 - x1) / 2

                detections.append(Detection(
                    x=cx,
                    y=cy,
                    radius=radius,
                    confidence=conf
                ))

        return detections


class GolfBallFilter:
    """
    Smart filter for golf ball tracking.

    Keeps tracks that are either:
    1. Potentially the ball (bright, right size, could be on tee)
    2. Currently moving fast (ball in flight)
    3. Recently launched (was stationary, now moving)

    Filters out:
    - Objects that have been stationary for too long AND aren't bright enough
    """

    def __init__(
        self,
        launch_velocity: float = 8.0,
        stationary_timeout: int = 180,
        min_confidence: float = 0.4,
    ):
        """
        Args:
            launch_velocity: Velocity threshold to detect launch (pixels/frame)
            stationary_timeout: Frames before stationary low-confidence objects are filtered
            min_confidence: Minimum confidence to keep stationary objects
        """
        self.launch_velocity = launch_velocity
        self.stationary_timeout = stationary_timeout
        self.min_confidence = min_confidence
        self._track_data: dict = {}  # track_id -> {positions, stationary_frames, launched}

    def update(self, tracked: sv.Detections) -> sv.Detections:
        """Filter detections, keeping ball candidates and launched balls."""
        if tracked.tracker_id is None or len(tracked) == 0:
            return tracked

        keep_mask = []

        for i in range(len(tracked)):
            track_id = int(tracked.tracker_id[i])
            bbox = tracked.xyxy[i]
            confidence = tracked.confidence[i] if tracked.confidence is not None else 0.5
            cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2

            # Initialize track data
            if track_id not in self._track_data:
                self._track_data[track_id] = {
                    'positions': [],
                    'stationary_frames': 0,
                    'launched': False,
                    'peak_velocity': 0,
                }

            data = self._track_data[track_id]
            data['positions'].append((cx, cy))

            # Keep only recent positions
            if len(data['positions']) > 10:
                data['positions'] = data['positions'][-10:]

            # Calculate current velocity
            velocity = 0
            if len(data['positions']) >= 2:
                dx = data['positions'][-1][0] - data['positions'][-2][0]
                dy = data['positions'][-1][1] - data['positions'][-2][1]
                velocity = (dx * dx + dy * dy) ** 0.5
                data['peak_velocity'] = max(data['peak_velocity'], velocity)

            # Detect launch (sudden high velocity)
            if velocity >= self.launch_velocity:
                data['launched'] = True
                data['stationary_frames'] = 0

            # Track stationary time
            if velocity < 1.0:
                data['stationary_frames'] += 1
            else:
                data['stationary_frames'] = 0

            # Decision logic:
            # 1. Always keep launched/moving balls
            if data['launched'] or velocity >= self.launch_velocity:
                keep_mask.append(True)
            # 2. Keep high-confidence stationary objects (likely the ball on tee)
            elif confidence >= self.min_confidence:
                keep_mask.append(True)
            # 3. Filter out low-confidence objects that have been stationary too long
            elif data['stationary_frames'] > self.stationary_timeout:
                keep_mask.append(False)
            # 4. Keep everything else (give it time to prove itself)
            else:
                keep_mask.append(True)

        # Filter detections
        keep_mask = np.array(keep_mask)
        if not np.any(keep_mask):
            return sv.Detections.empty()

        return sv.Detections(
            xyxy=tracked.xyxy[keep_mask],
            confidence=tracked.confidence[keep_mask] if tracked.confidence is not None else None,
            class_id=tracked.class_id[keep_mask] if tracked.class_id is not None else None,
            tracker_id=tracked.tracker_id[keep_mask] if tracked.tracker_id is not None else None,
        )

    def get_launched_tracks(self) -> List[int]:
        """Get track IDs that have been launched (ball in flight)."""
        return [tid for tid, data in self._track_data.items() if data['launched']]

    def reset(self):
        """Reset filter state."""
        self._track_data = {}


# Color palette for different track IDs
TRACK_COLORS = [
    (255, 0, 0),    # Red
    (0, 255, 0),    # Green
    (0, 0, 255),    # Blue
    (255, 255, 0),  # Cyan
    (255, 0, 255),  # Magenta
    (0, 255, 255),  # Yellow
    (128, 0, 255),  # Purple
    (255, 128, 0),  # Orange
]


def get_track_color(track_id: int) -> Tuple[int, int, int]:
    """Get consistent color for a track ID."""
    return TRACK_COLORS[track_id % len(TRACK_COLORS)]


def draw_tracks(
    frame: np.ndarray,
    tracked: sv.Detections,
    track_history: dict,
    show_trails: bool = True
) -> np.ndarray:
    """Draw tracking annotations on frame."""
    annotated = frame.copy()

    for i in range(len(tracked)):
        bbox = tracked.xyxy[i]
        track_id = int(tracked.tracker_id[i]) if tracked.tracker_id is not None else i
        confidence = tracked.confidence[i] if tracked.confidence is not None else 0.0

        x1, y1, x2, y2 = map(int, bbox)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        color = get_track_color(track_id)

        # Update track history
        if track_id not in track_history:
            track_history[track_id] = deque(maxlen=30)
        track_history[track_id].append((cx, cy))

        # Draw bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        # Draw center point
        cv2.circle(annotated, (cx, cy), 4, color, -1)

        # Draw track ID and confidence
        label = f"ID:{track_id} ({confidence:.2f})"
        cv2.putText(annotated, label, (x1, y1 - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Draw trail
        if show_trails and len(track_history[track_id]) > 1:
            points = list(track_history[track_id])
            for j in range(1, len(points)):
                # Fade trail over time
                alpha = j / len(points)
                thickness = max(1, int(3 * alpha))
                cv2.line(annotated, points[j-1], points[j], color, thickness)

    return annotated


def main():
    parser = argparse.ArgumentParser(description="Test ByteTrack Ball Tracking")
    # Input sources
    parser.add_argument("--video", type=str, help="Test on video file")
    parser.add_argument("--images", type=str, help="Test on image sequence (glob pattern)")
    parser.add_argument("--headless", action="store_true", help="Save frames instead of displaying")
    parser.add_argument("--num-frames", type=int, default=30, help="Number of frames in headless mode")

    # Camera settings
    parser.add_argument("--width", type=int, default=640, help="Camera width")
    parser.add_argument("--height", type=int, default=480, help="Camera height")
    parser.add_argument("--fps", type=int, default=60, help="Camera FPS")
    parser.add_argument("--awb", type=str, default=None,
                       choices=["auto", "daylight", "cloudy", "tungsten", "fluorescent", "indoor"],
                       help="Camera auto white balance mode (fixes color issues)")

    # Detector settings
    parser.add_argument("--detector", type=str, default="hough",
                       choices=["hough", "yolo"], help="Detection method")
    parser.add_argument("--model", type=str, default="models/golf_ball_yolo11n_new_256.onnx",
                       help="YOLO model path (if using yolo detector)")
    parser.add_argument("--imgsz", type=int, default=256, help="YOLO inference size")
    parser.add_argument("--confidence", type=float, default=0.3, help="Detection confidence")

    # Hough settings
    parser.add_argument("--min-radius", type=int, default=8, help="Min circle radius")
    parser.add_argument("--max-radius", type=int, default=40, help="Max circle radius")
    parser.add_argument("--param2", type=int, default=25,
                       help="Hough sensitivity (lower=more detections)")
    parser.add_argument("--min-brightness", type=int, default=140,
                       help="Min brightness for golf ball (0-255, golf balls are WHITE)")
    parser.add_argument("--min-uniformity", type=float, default=0.7,
                       help="Min uniformity (0-1, golf balls are solid, not edges)")
    parser.add_argument("--no-brightness-filter", action="store_true",
                       help="Disable brightness/uniformity filtering")
    parser.add_argument("--no-contrast-enhance", action="store_true",
                       help="Disable contrast enhancement (CLAHE)")
    parser.add_argument("--white-detect", action="store_true",
                       help="Use color-based white detection (better for carpet/grass)")

    # ByteTrack settings
    parser.add_argument("--track-buffer", type=int, default=30,
                       help="Frames to keep lost tracks")
    parser.add_argument("--activation-thresh", type=float, default=0.7,
                       help="Confidence threshold for track activation")
    parser.add_argument("--min-iou", type=float, default=0.1,
                       help="Minimum IoU threshold for matching")

    # Golf ball filter settings
    parser.add_argument("--launch-velocity", type=float, default=8.0,
                       help="Velocity threshold to detect ball launch (pixels/frame)")
    parser.add_argument("--stationary-timeout", type=int, default=180,
                       help="Frames before filtering low-confidence stationary objects")
    parser.add_argument("--no-golf-filter", action="store_true",
                       help="Disable golf ball filtering (show all detections)")

    # Display settings
    parser.add_argument("--no-trails", action="store_true", help="Don't draw tracking trails")
    parser.add_argument("--output-dir", type=str, default=".", help="Output directory for saved frames")

    args = parser.parse_args()

    if not CV2_AVAILABLE or not TRACKERS_AVAILABLE:
        print("Missing dependencies. Install with:")
        print("  pip install opencv-python trackers supervision")
        return 1

    print("=" * 50)
    print("  ByteTrack Ball Tracking Test")
    print("=" * 50)
    print()

    # Initialize detector
    if args.detector == "yolo":
        if not YOLO_AVAILABLE:
            print("YOLO requested but ultralytics not installed")
            print("  pip install ultralytics")
            return 1
        print(f"Using YOLO detector: {args.model}")
        detector = YOLODetector(args.model, args.imgsz, args.confidence)
    else:
        if args.white_detect:
            print("Using WHITE BLOB detector (color-based)")
            print(f"  Better for low-contrast surfaces (carpet, grass)")
        else:
            print("Using Hough Circle detector")
            print(f"  Contrast enhancement: {'OFF' if args.no_contrast_enhance else 'ON (CLAHE)'}")
        print(f"  Sensitivity (param2): {args.param2} (lower=more sensitive)")
        if not args.no_brightness_filter:
            print(f"  Brightness filter: ON (min={args.min_brightness}, uniformity={args.min_uniformity})")
        else:
            print(f"  Brightness filter: OFF")
        detector = HoughDetector(
            min_radius=args.min_radius,
            max_radius=args.max_radius,
            param2=args.param2,
            min_brightness=args.min_brightness,
            min_uniformity=args.min_uniformity,
            brightness_filter=not args.no_brightness_filter,
            enhance_contrast=not args.no_contrast_enhance,
            use_white_detection=args.white_detect,
        )

    # Initialize ByteTrack
    print(f"ByteTrack settings:")
    print(f"  lost_track_buffer: {args.track_buffer}")
    print(f"  track_activation_threshold: {args.activation_thresh}")
    print(f"  minimum_iou_threshold: {args.min_iou}")
    print()

    tracker = ByteTrackTracker(
        lost_track_buffer=args.track_buffer,
        track_activation_threshold=args.activation_thresh,
        minimum_iou_threshold=args.min_iou,
    )

    # Initialize golf ball filter
    golf_filter = None
    if not args.no_golf_filter:
        print(f"Golf ball filter: ON")
        print(f"  launch_velocity: {args.launch_velocity} px/frame")
        print(f"  stationary_timeout: {args.stationary_timeout} frames")
        golf_filter = GolfBallFilter(
            launch_velocity=args.launch_velocity,
            stationary_timeout=args.stationary_timeout,
        )
    else:
        print("Golf ball filter: OFF")
    print()

    # Track history for drawing trails
    track_history = {}
    fps_list = deque(maxlen=30)

    # Statistics
    total_frames = 0
    total_detections = 0
    unique_tracks = set()

    def process_frame(frame: np.ndarray, frame_num: int, is_rgb: bool = False) -> Tuple[np.ndarray, int]:
        """Process a single frame and return annotated result."""
        nonlocal total_detections

        start_time = time.time()

        # Detect balls
        detections = detector.detect(frame, is_rgb=is_rgb)
        total_detections += len(detections)

        if detections:
            # Convert to supervision format
            xyxy = np.array([d.bbox for d in detections])
            confidence = np.array([d.confidence for d in detections])

            sv_detections = sv.Detections(
                xyxy=xyxy,
                confidence=confidence,
                class_id=np.zeros(len(detections), dtype=int)
            )

            # Update tracker
            tracked = tracker.update(sv_detections)

            # Apply golf ball filter
            if golf_filter is not None:
                tracked = golf_filter.update(tracked)

            # Track unique IDs
            if tracked.tracker_id is not None:
                for tid in tracked.tracker_id:
                    unique_tracks.add(int(tid))
        else:
            # No detections - create empty detections object
            tracked = sv.Detections.empty()

        process_time = time.time() - start_time
        fps = 1.0 / process_time if process_time > 0 else 0
        fps_list.append(fps)
        avg_fps = sum(fps_list) / len(fps_list)

        # Draw annotations
        annotated = draw_tracks(frame, tracked, track_history, not args.no_trails)

        # Draw stats
        num_tracked = len(tracked) if tracked.tracker_id is not None else 0
        cv2.putText(annotated, f"FPS: {avg_fps:.1f}", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.putText(annotated, f"Detections: {len(detections)}", (10, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(annotated, f"Tracked: {num_tracked}", (10, 75),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(annotated, f"Unique IDs: {len(unique_tracks)}", (10, 100),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
        cv2.putText(annotated, f"Frame: {frame_num}", (10, 125),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (128, 128, 128), 2)

        return annotated, num_tracked

    # Process video file
    if args.video:
        print(f"Processing video: {args.video}")
        cap = cv2.VideoCapture(args.video)
        if not cap.isOpened():
            print(f"Error: Could not open video {args.video}")
            return 1

        frame_num = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                annotated, num_tracked = process_frame(frame, frame_num)
                total_frames += 1
                frame_num += 1

                if args.headless:
                    filename = f"{args.output_dir}/track_frame_{frame_num:04d}.png"
                    cv2.imwrite(filename, annotated)
                    print(f"Frame {frame_num}: {num_tracked} tracked, saved {filename}")
                else:
                    cv2.imshow("ByteTrack", annotated)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

        finally:
            cap.release()
            if not args.headless:
                cv2.destroyAllWindows()

    # Process image sequence
    elif args.images:
        image_files = sorted(glob.glob(args.images))
        if not image_files:
            print(f"No images found matching: {args.images}")
            return 1

        print(f"Processing {len(image_files)} images")

        for frame_num, img_path in enumerate(image_files):
            frame = cv2.imread(img_path)
            if frame is None:
                print(f"Warning: Could not read {img_path}")
                continue

            annotated, num_tracked = process_frame(frame, frame_num)
            total_frames += 1

            if args.headless:
                filename = f"{args.output_dir}/track_frame_{frame_num:04d}.png"
                cv2.imwrite(filename, annotated)
                print(f"Frame {frame_num}: {num_tracked} tracked, saved {filename}")
            else:
                cv2.imshow("ByteTrack", annotated)
                key = cv2.waitKey(500)  # 500ms between frames for visibility
                if key & 0xFF == ord('q'):
                    break

        if not args.headless:
            cv2.destroyAllWindows()

    # Camera mode
    else:
        if not PICAMERA_AVAILABLE:
            print("picamera2 not available")
            print("Use --video or --images to test on files")
            return 1

        print(f"Starting camera: {args.width}x{args.height} @ {args.fps}fps")
        camera = Picamera2()

        # Build controls dict
        controls = {"FrameRate": args.fps}

        # Add white balance mode if specified
        if args.awb:
            # Map user-friendly names to libcamera AWB modes
            awb_modes = {
                "auto": 0,        # Auto
                "daylight": 1,    # Daylight
                "cloudy": 2,      # Cloudy
                "tungsten": 3,    # Tungsten
                "fluorescent": 4, # Fluorescent
                "indoor": 5,      # Indoor
            }
            controls["AwbMode"] = awb_modes.get(args.awb, 0)
            print(f"  White balance: {args.awb}")

        config = camera.create_video_configuration(
            main={"size": (args.width, args.height), "format": "RGB888"},
            buffer_count=2,
            controls=controls
        )
        camera.configure(config)
        camera.start()
        time.sleep(0.5)

        if args.headless:
            print(f"Capturing {args.num_frames} frames...")

            for frame_num in range(args.num_frames):
                frame = camera.capture_array()
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                annotated, num_tracked = process_frame(frame_bgr, frame_num)
                total_frames += 1

                filename = f"{args.output_dir}/track_frame_{frame_num:04d}.png"
                cv2.imwrite(filename, annotated)
                print(f"Frame {frame_num}: {num_tracked} tracked, saved {filename}")

            camera.stop()
            camera.close()

        else:
            print("Live mode - press 'q' to quit")
            cv2.namedWindow("ByteTrack", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("ByteTrack", args.width, args.height)

            frame_num = 0
            try:
                while True:
                    frame = camera.capture_array()
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                    annotated, _ = process_frame(frame_bgr, frame_num)
                    total_frames += 1
                    frame_num += 1

                    cv2.imshow("ByteTrack", annotated)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

            finally:
                cv2.destroyAllWindows()
                camera.stop()
                camera.close()

    # Print summary
    print()
    print("=" * 50)
    print("  Tracking Summary")
    print("=" * 50)
    print(f"  Total frames processed: {total_frames}")
    print(f"  Total detections: {total_detections}")
    print(f"  Unique track IDs: {len(unique_tracks)}")
    if unique_tracks:
        print(f"  Track IDs seen: {sorted(unique_tracks)}")
    if fps_list:
        print(f"  Average FPS: {sum(fps_list) / len(fps_list):.1f}")
    print()

    if args.headless:
        print("Transfer frames to view:")
        print(f"  scp pi@<ip>:~/{args.output_dir}/track_frame_*.png .")

    return 0


if __name__ == "__main__":
    sys.exit(main())
