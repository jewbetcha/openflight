#!/usr/bin/env python3
"""
Interactive camera ball detection test.

Verifies that the camera can detect golf balls using Hough circle detection
before running the full system. Supports Pi camera (picamera2) with USB
webcam fallback (OpenCV VideoCapture).

Usage:
    uv run python scripts/test_camera_detection.py
    uv run python scripts/test_camera_detection.py --headless --num-frames 200
    uv run python scripts/test_camera_detection.py --save-frames 10 --hough-param2 30
    uv run python scripts/test_camera_detection.py --resolution 1280x720 --framerate 60
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import cv2
import numpy as np

from openflight.camera.capture import CapturedFrame
from openflight.camera.detector import BallDetector, DetectorConfig


def parse_resolution(value: str) -> tuple:
    """Parse a WIDTHxHEIGHT resolution string."""
    try:
        parts = value.lower().split("x")
        if len(parts) != 2:
            raise ValueError
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        raise argparse.ArgumentTypeError(
            f"Invalid resolution '{value}'. Use format WIDTHxHEIGHT (e.g. 640x480)"
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test camera ball detection interactively"
    )
    parser.add_argument(
        "--resolution",
        type=parse_resolution,
        default=(640, 480),
        help="Camera resolution as WIDTHxHEIGHT (default: 640x480)",
    )
    parser.add_argument(
        "--framerate",
        type=int,
        default=120,
        help="Target framerate (default: 120)",
    )
    parser.add_argument(
        "--hough-param2",
        type=int,
        default=27,
        help="Hough circle detection threshold - lower = more detections (default: 27)",
    )
    parser.add_argument(
        "--brightness-threshold",
        type=int,
        default=200,
        help="Brightness threshold for IR ball isolation 0-255 (default: 200)",
    )
    parser.add_argument(
        "--num-frames",
        type=int,
        default=100,
        help="Number of frames to capture (default: 100)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="No display window, print stats to stdout only",
    )
    parser.add_argument(
        "--save-frames",
        type=int,
        default=0,
        metavar="N",
        help="Save N annotated frames with detections to camera_test_frames/",
    )
    return parser.parse_args()


def open_camera(width: int, height: int, framerate: int):
    """
    Try to open picamera2 first, fall back to USB webcam via OpenCV.

    Returns:
        (camera_object, camera_type) where camera_type is "picamera2" or "opencv"
    """
    # Try picamera2 first
    try:
        from picamera2 import Picamera2

        cam = Picamera2()
        video_config = cam.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"},
            controls={
                "FrameRate": framerate,
                "ExposureTime": 2000,
                "AnalogueGain": 4.0,
                "AeEnable": False,
            },
        )
        cam.configure(video_config)
        cam.start()
        print(f"Opened Pi camera via picamera2 at {width}x{height} @ {framerate}fps")
        return cam, "picamera2"
    except (ImportError, RuntimeError) as e:
        print(f"picamera2 not available ({e}), falling back to OpenCV webcam...")

    # Fall back to OpenCV VideoCapture
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open any camera (tried picamera2 and OpenCV)")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, framerate)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(
        f"Opened USB webcam via OpenCV at {actual_w}x{actual_h} "
        f"@ {actual_fps:.1f}fps (requested {width}x{height} @ {framerate}fps)"
    )
    return cap, "opencv"


def capture_frame(camera, camera_type: str, frame_number: int) -> CapturedFrame:
    """Capture a single frame from the camera."""
    if camera_type == "picamera2":
        data = camera.capture_array()
    else:
        ret, data = camera.read()
        if not ret:
            raise RuntimeError("Failed to capture frame from webcam")
        # OpenCV returns BGR, convert to RGB to match picamera2 and detector expectations
        data = cv2.cvtColor(data, cv2.COLOR_BGR2RGB)

    return CapturedFrame(
        data=data,
        timestamp=time.time(),
        frame_number=frame_number,
    )


def annotate_frame(frame_data: np.ndarray, detection) -> np.ndarray:
    """
    Draw detection circle and info on a frame copy.

    Args:
        frame_data: RGB frame array
        detection: DetectedBall or None

    Returns:
        Annotated BGR frame suitable for imwrite/imshow
    """
    # Convert RGB to BGR for OpenCV drawing/saving
    annotated = cv2.cvtColor(frame_data, cv2.COLOR_RGB2BGR)

    if detection is not None:
        cx, cy, r = int(detection.x), int(detection.y), int(detection.radius)
        # Green circle around detected ball
        cv2.circle(annotated, (cx, cy), r, (0, 255, 0), 2)
        # Small dot at center
        cv2.circle(annotated, (cx, cy), 2, (0, 0, 255), -1)
        # Label
        label = f"r={detection.radius:.0f} conf={detection.confidence:.2f}"
        cv2.putText(
            annotated, label, (cx + r + 5, cy),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
        )
    else:
        cv2.putText(
            annotated, "No detection", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
        )

    return annotated


def close_camera(camera, camera_type: str):
    """Clean up camera resources."""
    if camera_type == "picamera2":
        camera.stop()
        camera.close()
    else:
        camera.release()


def main():
    args = parse_args()
    width, height = args.resolution

    # Set up detector
    config = DetectorConfig(
        brightness_threshold=args.brightness_threshold,
        hough_param2=args.hough_param2,
    )
    detector = BallDetector(config)
    print(
        f"BallDetector config: brightness_threshold={config.brightness_threshold}, "
        f"hough_param2={config.hough_param2}, "
        f"min_radius={config.min_radius}, max_radius={config.max_radius}"
    )

    # Set up save directory if needed
    save_dir = None
    frames_saved = 0
    if args.save_frames > 0:
        save_dir = Path("camera_test_frames")
        save_dir.mkdir(exist_ok=True)
        print(f"Will save up to {args.save_frames} annotated frames to {save_dir}/")

    # Open camera
    camera, camera_type = open_camera(width, height, args.framerate)

    print(f"\nCapturing {args.num_frames} frames...")
    if not args.headless:
        print("Press 'q' in the display window to stop early.\n")
    else:
        print()

    # Capture loop
    detections_count = 0
    frame_times = []
    start_time = time.time()

    try:
        for i in range(args.num_frames):
            frame_start = time.time()

            # Capture
            frame = capture_frame(camera, camera_type, i)

            # Detect
            detection = detector.detect(frame)

            frame_end = time.time()
            frame_elapsed = frame_end - frame_start
            frame_times.append(frame_elapsed)

            if detection is not None:
                detections_count += 1
                print(
                    f"[{i+1:4d}/{args.num_frames}] "
                    f"DETECTED  pos=({detection.x:.0f}, {detection.y:.0f})  "
                    f"radius={detection.radius:.1f}  "
                    f"conf={detection.confidence:.2f}  "
                    f"fps={1.0/frame_elapsed:.1f}"
                )
            else:
                print(
                    f"[{i+1:4d}/{args.num_frames}] "
                    f"no detection  "
                    f"fps={1.0/frame_elapsed:.1f}"
                )

            # Save annotated frame if requested
            if save_dir is not None and frames_saved < args.save_frames:
                annotated = annotate_frame(frame.data, detection)
                save_path = save_dir / f"frame_{i:04d}.png"
                cv2.imwrite(str(save_path), annotated)
                frames_saved += 1

            # Display if not headless
            if not args.headless:
                annotated = annotate_frame(frame.data, detection)
                cv2.imshow("Camera Detection Test", annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("\nStopped early by user.")
                    break

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        close_camera(camera, camera_type)
        if not args.headless:
            cv2.destroyAllWindows()

    # Final summary
    total_time = time.time() - start_time
    total_frames = len(frame_times)

    if total_frames == 0:
        print("\nNo frames captured.")
        return

    avg_frame_time = sum(frame_times) / total_frames
    avg_fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
    detection_rate = (detections_count / total_frames) * 100

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total frames:    {total_frames}")
    print(f"  Detections:      {detections_count} ({detection_rate:.1f}%)")
    print(f"  Total time:      {total_time:.2f}s")
    print(f"  Avg FPS:         {avg_fps:.1f}")
    print(f"  Min frame time:  {min(frame_times)*1000:.1f}ms")
    print(f"  Max frame time:  {max(frame_times)*1000:.1f}ms")
    if frames_saved > 0:
        print(f"  Frames saved:    {frames_saved} to {save_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
