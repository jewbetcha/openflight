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

    # Use YOLO detection instead of Hough circles
    python scripts/test_bytetrack.py --detector yolo --model models/golf_ball_yolo11n_new_256.onnx

    # Adjust tracking parameters
    python scripts/test_bytetrack.py --track-thresh 0.3 --track-buffer 30
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
    """Detect balls using Hough Circle Transform."""

    def __init__(
        self,
        min_radius: int = 5,
        max_radius: int = 50,
        param1: int = 50,
        param2: int = 20,  # Lower = more sensitive (was 30)
        min_dist: int = 50
    ):
        self.min_radius = min_radius
        self.max_radius = max_radius
        self.param1 = param1
        self.param2 = param2
        self.min_dist = min_dist

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Detect circles in frame."""
        # Convert to grayscale
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

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
                x, y, r = circle
                # Hough doesn't give confidence, use a fixed value
                detections.append(Detection(
                    x=float(x),
                    y=float(y),
                    radius=float(r),
                    confidence=0.8
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

    # Detector settings
    parser.add_argument("--detector", type=str, default="hough",
                       choices=["hough", "yolo"], help="Detection method")
    parser.add_argument("--model", type=str, default="models/golf_ball_yolo11n_new_256.onnx",
                       help="YOLO model path (if using yolo detector)")
    parser.add_argument("--imgsz", type=int, default=256, help="YOLO inference size")
    parser.add_argument("--confidence", type=float, default=0.3, help="Detection confidence")

    # Hough settings
    parser.add_argument("--min-radius", type=int, default=5, help="Min circle radius")
    parser.add_argument("--max-radius", type=int, default=50, help="Max circle radius")

    # ByteTrack settings
    parser.add_argument("--track-buffer", type=int, default=30,
                       help="Frames to keep lost tracks")
    parser.add_argument("--activation-thresh", type=float, default=0.7,
                       help="Confidence threshold for track activation")
    parser.add_argument("--min-iou", type=float, default=0.1,
                       help="Minimum IoU threshold for matching")

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
        print("Using Hough Circle detector")
        detector = HoughDetector(
            min_radius=args.min_radius,
            max_radius=args.max_radius
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

    # Track history for drawing trails
    track_history = {}
    fps_list = deque(maxlen=30)

    # Statistics
    total_frames = 0
    total_detections = 0
    unique_tracks = set()

    def process_frame(frame: np.ndarray, frame_num: int) -> Tuple[np.ndarray, int]:
        """Process a single frame and return annotated result."""
        nonlocal total_detections

        start_time = time.time()

        # Detect balls
        detections = detector.detect(frame)
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
        config = camera.create_video_configuration(
            main={"size": (args.width, args.height), "format": "RGB888"},
            buffer_count=2,
            controls={"FrameRate": args.fps}
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
