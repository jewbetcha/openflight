#!/usr/bin/env python3
"""
End-to-end test script for launch angle detection.

Captures frames from the camera (or mock), runs ball detection
with tracking, and calculates launch angles.

Usage:
    # Mock mode (no hardware required)
    uv run python scripts/test_launch_angle.py --mock

    # Real camera
    uv run python scripts/test_launch_angle.py

    # With radar-derived ball speed for better accuracy
    uv run python scripts/test_launch_angle.py --mock --ball-speed 150

    # Custom camera calibration
    uv run python scripts/test_launch_angle.py --mock --camera-height 300 --camera-distance 2000 --focal-length 6.0

    # Custom frame count
    uv run python scripts/test_launch_angle.py --mock --num-frames 120
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openflight.camera.capture import CaptureConfig, MockCameraCapture
from openflight.camera.detector import BallDetector
from openflight.camera.launch_angle import CameraCalibration, LaunchAngleCalculator


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end launch angle detection test"
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="Use MockCameraCapture with synthetic ball trajectory"
    )
    parser.add_argument(
        "--ball-speed", type=float, default=None, metavar="MPH",
        help="Ball speed in mph for radar-derived distance calculation"
    )
    parser.add_argument(
        "--num-frames", type=int, default=90,
        help="Number of frames to capture (default: 90 = ~750ms at 120fps)"
    )
    parser.add_argument(
        "--camera-height", type=float, default=300,
        help="Camera height above ground in mm (default: 300)"
    )
    parser.add_argument(
        "--camera-distance", type=float, default=2000,
        help="Camera distance to ball in mm (default: 2000)"
    )
    parser.add_argument(
        "--focal-length", type=float, default=6.0,
        help="Lens focal length in mm (default: 6.0)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Launch Angle Detection Test")
    print("=" * 60)
    print()

    # Configure capture to match requested frame count
    # Split frames into pre-trigger (1/3) and post-trigger (2/3)
    pre_trigger = args.num_frames // 3
    post_trigger = args.num_frames - pre_trigger

    config = CaptureConfig(
        pre_trigger_frames=pre_trigger,
        post_trigger_frames=post_trigger,
    )

    # Set up camera
    if args.mock:
        print("Mode: Mock camera (synthetic ball trajectory)")
        camera = MockCameraCapture(config=config)
    else:
        print("Mode: Real camera (Pi HQ Camera)")
        try:
            from openflight.camera.capture import CameraCapture
            camera = CameraCapture(config=config)
        except Exception as e:
            print(f"ERROR: Failed to initialize camera: {e}")
            print("  Try --mock for testing without hardware.")
            sys.exit(1)

    print(f"Frames: {args.num_frames} ({pre_trigger} pre-trigger, {post_trigger} post-trigger)")
    print(f"Calibration: height={args.camera_height}mm, distance={args.camera_distance}mm, focal={args.focal_length}mm")
    if args.ball_speed:
        print(f"Ball speed: {args.ball_speed} mph (radar-derived distance)")
    print()

    # Start camera
    print("Starting camera...")
    try:
        camera.start()
    except Exception as e:
        print(f"ERROR: Failed to start camera: {e}")
        print("  Try --mock for testing without hardware.")
        sys.exit(1)

    print("Triggering capture...")
    try:
        result = camera.trigger_capture()
    except Exception as e:
        print(f"ERROR: Capture failed: {e}")
        camera.stop()
        sys.exit(1)
    finally:
        camera.stop()

    print(f"Captured {len(result.frames)} frames (trigger at index {result.trigger_frame_index})")
    print()

    if not result.frames:
        print("ERROR: No frames captured.")
        sys.exit(1)

    # Run ball detection
    print("-" * 60)
    print("Running ball detection with tracking...")
    try:
        detector = BallDetector()
    except Exception as e:
        print(f"ERROR: Failed to initialize BallDetector: {e}")
        sys.exit(1)

    detections = detector.detect_with_tracking(result.frames)

    detected_count = sum(1 for d in detections if d is not None)
    total_count = len(detections)
    detection_rate = (detected_count / total_count * 100) if total_count > 0 else 0

    print(f"Detection results:")
    print(f"  Total frames:    {total_count}")
    print(f"  Ball detected:   {detected_count}")
    print(f"  Detection rate:  {detection_rate:.1f}%")
    print()

    if detected_count == 0:
        print("ERROR: No ball detections found. Cannot calculate launch angle.")
        sys.exit(1)

    # Show first few detections
    valid_detections = [(i, d) for i, d in enumerate(detections) if d is not None]
    print(f"First detections (up to 5):")
    for i, det in valid_detections[:5]:
        print(f"  Frame {i:3d}: x={det.x:.1f}, y={det.y:.1f}, r={det.radius:.1f}, conf={det.confidence:.2f}")
    print()

    # Calculate launch angles
    print("-" * 60)
    print("Calculating launch angles...")

    calibration = CameraCalibration(
        camera_height_mm=args.camera_height,
        distance_to_ball_mm=args.camera_distance,
        focal_length_mm=args.focal_length,
    )
    calculator = LaunchAngleCalculator(calibration=calibration)

    if args.ball_speed:
        angles = calculator.calculate_with_radar(
            detections,
            ball_speed_mph=args.ball_speed,
            framerate=config.framerate,
        )
    else:
        angles = calculator.calculate(detections)

    if angles is None:
        print("ERROR: Launch angle calculation failed.")
        print(f"  Need at least {calculator.min_detections} detections, got {detected_count}.")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  LAUNCH ANGLE RESULTS")
    print("=" * 60)
    print(f"  Vertical angle:   {angles.vertical_deg:+.2f} deg")
    print(f"  Horizontal angle: {angles.horizontal_deg:+.2f} deg")
    print(f"  Confidence:       {angles.confidence:.2f}")
    print(f"  Frames used:      {angles.frames_used}")
    print(f"  Initial position: ({angles.initial_x:.1f}, {angles.initial_y:.1f})")
    print(f"  Velocity (px/fr): vx={angles.velocity_x:.2f}, vy={angles.velocity_y:.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
