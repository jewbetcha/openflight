#!/usr/bin/env python3
"""
End-to-end test script for launch angle detection.

Shows a live camera preview while waiting for the sound sensor to detect
a golf shot, then captures frames and runs ball detection + launch angle
calculation. Saves annotated frames for review.

Usage:
    # Real hardware: live preview + sound trigger
    uv run python scripts/test_launch_angle.py

    # With known ball speed for better accuracy
    uv run python scripts/test_launch_angle.py --ball-speed 150

    # Multiple shots
    uv run python scripts/test_launch_angle.py --shots 5

    # Save frames without display (SSH session)
    uv run python scripts/test_launch_angle.py --headless

    # Mock mode (no hardware required)
    uv run python scripts/test_launch_angle.py --mock

    # Tune detection params
    uv run python scripts/test_launch_angle.py --brightness-threshold 180 --hough-param2 20
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Set DISPLAY for X11 on Pi (must be before cv2 import)
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import cv2
import numpy as np

from openflight.camera.capture import CaptureConfig, CapturedFrame, MockCameraCapture
from openflight.camera.detector import BallDetector, DetectedBall, DetectorConfig
from openflight.camera.launch_angle import CameraCalibration, LaunchAngleCalculator

SAVE_DIR = Path("launch_angle_frames")


def wait_for_sound_trigger_with_preview(
    camera,
    camera_type: str,
    detector: BallDetector,
    gpio_pin: int = 17,
    timeout: float = 60.0,
    headless: bool = False,
) -> bool:
    """
    Show live camera preview while waiting for sound trigger.

    The preview shows the camera feed with detection overlay so you can
    position the camera and verify the ball is visible before hitting.

    Returns:
        True if trigger detected, False on timeout/quit
    """
    try:
        from gpiozero import Button
    except ImportError:
        print("ERROR: gpiozero not available. Install with: uv pip install gpiozero lgpio")
        print("  Or use --mock for testing without hardware.")
        return False

    triggered = False

    def on_trigger():
        nonlocal triggered
        triggered = True

    button = Button(gpio_pin, pull_up=False, bounce_time=0.02)
    button.when_activated = on_trigger

    frame_num = 0
    fps_start = time.time()
    fps_count = 0
    current_fps = 0.0
    start = time.time()

    try:
        while not triggered and (time.time() - start) < timeout:
            # Capture and detect on live feed
            frame = _capture_frame(camera, camera_type, frame_num)
            detection = detector.detect(frame)

            # Update FPS counter
            fps_count += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                current_fps = fps_count / elapsed
                fps_count = 0
                fps_start = time.time()

            if not headless:
                # Annotate and show
                display = _annotate_frame(frame.data, detection)
                remaining = max(0, timeout - (time.time() - start))
                status = f"WAITING FOR SHOT | FPS: {current_fps:.0f} | Timeout: {remaining:.0f}s | Press 'q' to quit"
                cv2.putText(display, status, (10, display.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                cv2.imshow("Launch Angle Test - Live Preview", display)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("  Quit by user.")
                    button.close()
                    return False
            else:
                # Headless: periodic status
                if frame_num % 60 == 0:
                    det_str = f"ball at ({detection.x:.0f},{detection.y:.0f})" if detection else "no ball"
                    remaining = max(0, timeout - (time.time() - start))
                    print(f"  [preview] {det_str} | fps={current_fps:.0f} | {remaining:.0f}s remaining")

            frame_num += 1
    finally:
        button.close()

    return triggered


def _capture_frame(camera, camera_type: str, frame_number: int) -> CapturedFrame:
    """Capture a single frame from picamera2 or OpenCV."""
    if camera_type == "picamera2":
        data = camera.capture_array()
    else:
        ret, data = camera.read()
        if not ret:
            raise RuntimeError("Failed to capture frame")
        data = cv2.cvtColor(data, cv2.COLOR_BGR2RGB)

    return CapturedFrame(data=data, timestamp=time.time(), frame_number=frame_number)


def _annotate_frame(
    frame_data: np.ndarray,
    detection: DetectedBall = None,
) -> np.ndarray:
    """Draw detection overlay on a frame. Returns BGR for cv2."""
    annotated = cv2.cvtColor(frame_data, cv2.COLOR_RGB2BGR)

    if detection is not None:
        cx, cy, r = int(detection.x), int(detection.y), int(detection.radius)
        cv2.circle(annotated, (cx, cy), r, (0, 255, 0), 2)
        cv2.circle(annotated, (cx, cy), 2, (0, 0, 255), -1)
        label = f"r={detection.radius:.0f} conf={detection.confidence:.2f}"
        cv2.putText(annotated, label, (cx + r + 5, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    return annotated


def _open_camera(width: int, height: int, framerate: int):
    """Open picamera2 or fall back to OpenCV. Returns (camera, type_str)."""
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
        print(f"  Camera: picamera2 at {width}x{height} @ {framerate}fps")
        return cam, "picamera2"
    except (ImportError, RuntimeError) as e:
        print(f"  picamera2 not available ({e}), trying OpenCV webcam...")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return None, None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, framerate)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"  Camera: OpenCV webcam at {actual_w}x{actual_h}")
    return cap, "opencv"


def _close_camera(camera, camera_type: str):
    """Clean up camera resources."""
    if camera_type == "picamera2":
        camera.stop()
        camera.close()
    elif camera_type == "opencv":
        camera.release()


def save_capture_frames(frames, detections, shot_num: int):
    """Save all captured frames with detection annotations."""
    shot_dir = SAVE_DIR / f"shot_{shot_num:03d}"
    shot_dir.mkdir(parents=True, exist_ok=True)

    for i, frame in enumerate(frames):
        det = detections[i] if i < len(detections) else None
        annotated = _annotate_frame(frame.data, det)

        # Add frame info overlay
        info = f"Frame {i}"
        if det:
            info += f" | BALL ({det.x:.0f},{det.y:.0f}) r={det.radius:.0f}"
        cv2.putText(annotated, info, (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imwrite(str(shot_dir / f"frame_{i:04d}.png"), annotated)

    # Also save a brightness analysis image of a few key frames
    key_indices = [0, len(frames) // 4, len(frames) // 2, 3 * len(frames) // 4, len(frames) - 1]
    for idx in key_indices:
        if idx < len(frames):
            frame = frames[idx]
            gray = cv2.cvtColor(frame.data, cv2.COLOR_RGB2GRAY)
            mean_bright = np.mean(gray)
            max_bright = np.max(gray)
            bright_pixels = np.sum(gray > 200)

            # Create side-by-side: original + thresholded
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            thresh_bgr = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
            original_bgr = cv2.cvtColor(frame.data, cv2.COLOR_RGB2BGR)
            combined = np.hstack([original_bgr, thresh_bgr])

            info = f"Frame {idx} | mean={mean_bright:.0f} max={max_bright} bright_px={bright_pixels}"
            cv2.putText(combined, info, (10, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.imwrite(str(shot_dir / f"analysis_{idx:04d}.png"), combined)

    return shot_dir


def analyze_and_show(
    result,
    detector: BallDetector,
    calculator: LaunchAngleCalculator,
    ball_speed_mph: float,
    framerate: float,
    shot_num: int,
    headless: bool,
):
    """Run detection, save frames, optionally display, calculate angles."""
    print(f"  Captured {len(result.frames)} frames (trigger at index {result.trigger_frame_index})")

    if not result.frames:
        print("  ERROR: No frames captured.")
        return None

    # Run ball detection
    print("  Detecting ball...")
    detections = detector.detect_with_tracking(result.frames)

    detected_count = sum(1 for d in detections if d is not None)
    total_count = len(detections)
    detection_rate = (detected_count / total_count * 100) if total_count > 0 else 0

    print(f"  Detection: {detected_count}/{total_count} frames ({detection_rate:.1f}%)")

    # Frame brightness stats (diagnostic)
    post_trigger = result.frames[result.trigger_frame_index:]
    if post_trigger:
        brightnesses = []
        for f in post_trigger[:10]:
            gray = cv2.cvtColor(f.data, cv2.COLOR_RGB2GRAY)
            brightnesses.append(np.max(gray))
        print(f"  Post-trigger max brightness (first 10 frames): "
              f"min={min(brightnesses)} max={max(brightnesses)} avg={sum(brightnesses)/len(brightnesses):.0f}")
        bright_px_count = sum(1 for b in brightnesses if b > 200)
        if bright_px_count == 0:
            print("  WARNING: No bright pixels (>200) found — ball may not be IR-illuminated or visible")

    # Save frames for review
    shot_dir = save_capture_frames(result.frames, detections, shot_num)
    print(f"  Frames saved to {shot_dir}/")

    # Show captured frames as slideshow if display available
    if not headless and detected_count > 0:
        print("  Showing capture (press any key to advance, 'q' to skip)...")
        for i, frame in enumerate(result.frames):
            det = detections[i] if i < len(detections) else None
            display = _annotate_frame(frame.data, det)
            marker = ">>> TRIGGER" if i == result.trigger_frame_index else ""
            det_str = f"BALL ({det.x:.0f},{det.y:.0f})" if det else "no ball"
            cv2.putText(display, f"Frame {i}/{total_count} {det_str} {marker}",
                        (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            cv2.imshow("Launch Angle Test - Capture Review", display)
            key = cv2.waitKey(50) & 0xFF  # 50ms per frame = ~20fps review
            if key == ord("q"):
                break

    if detected_count == 0:
        print("  No ball detected. Check saved frames to diagnose.")
        print("  Possible issues:")
        print("    - Ball not in frame (check camera position)")
        print("    - Ball not bright enough (check IR illumination)")
        print("    - Threshold too high (try --brightness-threshold 150)")
        print("    - Detection params too strict (try --hough-param2 15)")
        return None

    # Show detections
    valid = [(i, d) for i, d in enumerate(detections) if d is not None]
    for i, det in valid[:5]:
        print(f"    Frame {i:3d}: ({det.x:.0f}, {det.y:.0f}) r={det.radius:.0f} conf={det.confidence:.2f}")

    # Calculate launch angles
    if ball_speed_mph:
        angles = calculator.calculate_with_radar(
            detections, ball_speed_mph=ball_speed_mph, framerate=framerate,
        )
    else:
        angles = calculator.calculate(detections)

    if angles is None:
        print(f"  Launch angle calc failed (need {calculator.min_detections}+ detections, got {detected_count})")
        return None

    return angles


def main():
    parser = argparse.ArgumentParser(
        description="Launch angle test — live preview + sound trigger + detection analysis"
    )
    parser.add_argument("--mock", action="store_true",
                        help="Synthetic trajectory, no hardware needed")
    parser.add_argument("--headless", action="store_true",
                        help="No display window (for SSH sessions)")
    parser.add_argument("--ball-speed", type=float, default=None, metavar="MPH",
                        help="Ball speed for radar-derived distance")
    parser.add_argument("--shots", type=int, default=1,
                        help="Number of shots to capture (default: 1)")
    parser.add_argument("--num-frames", type=int, default=90,
                        help="Frames per capture (default: 90 = ~750ms at 120fps)")
    parser.add_argument("--gpio-pin", type=int, default=17,
                        help="BCM GPIO pin for SEN-14262 GATE (default: 17)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="Seconds to wait per shot (default: 60)")
    parser.add_argument("--camera-height", type=float, default=300,
                        help="Camera height above ground in mm (default: 300)")
    parser.add_argument("--camera-distance", type=float, default=2000,
                        help="Camera distance to ball in mm (default: 2000)")
    parser.add_argument("--focal-length", type=float, default=6.0,
                        help="Lens focal length in mm (default: 6.0)")
    parser.add_argument("--brightness-threshold", type=int, default=200,
                        help="IR brightness threshold 0-255 (default: 200)")
    parser.add_argument("--hough-param2", type=int, default=20,
                        help="Hough circle threshold — lower = more detections (default: 20)")
    parser.add_argument("--resolution", type=str, default="640x480",
                        help="Camera resolution WIDTHxHEIGHT (default: 640x480)")
    parser.add_argument("--framerate", type=int, default=120,
                        help="Camera framerate (default: 120)")
    args = parser.parse_args()

    # Parse resolution
    try:
        width, height = [int(x) for x in args.resolution.split("x")]
    except ValueError:
        print(f"ERROR: Invalid resolution '{args.resolution}'. Use WIDTHxHEIGHT (e.g. 640x480)")
        sys.exit(1)

    print("=" * 60)
    print("  Launch Angle Detection Test")
    print("=" * 60)

    # Set up detector with tunable params
    det_config = DetectorConfig(
        brightness_threshold=args.brightness_threshold,
        hough_param2=args.hough_param2,
    )
    try:
        detector = BallDetector(det_config)
    except Exception as e:
        print(f"ERROR: BallDetector init failed: {e}")
        sys.exit(1)

    print(f"  Detector: brightness>{args.brightness_threshold}, hough_param2={args.hough_param2}")

    calibration = CameraCalibration(
        camera_height_mm=args.camera_height,
        distance_to_ball_mm=args.camera_distance,
        focal_length_mm=args.focal_length,
    )
    calculator = LaunchAngleCalculator(calibration=calibration)
    print(f"  Calibration: h={args.camera_height}mm, d={args.camera_distance}mm, f={args.focal_length}mm")

    if args.ball_speed:
        print(f"  Ball speed: {args.ball_speed} mph (radar-derived)")

    # Configure capture
    pre_trigger = args.num_frames // 3
    post_trigger = args.num_frames - pre_trigger
    config = CaptureConfig(
        width=width,
        height=height,
        framerate=args.framerate,
        pre_trigger_frames=pre_trigger,
        post_trigger_frames=post_trigger,
    )
    print(f"  Capture: {width}x{height} @ {args.framerate}fps, {pre_trigger} pre / {post_trigger} post")

    # Open camera
    if args.mock:
        print("  Mode: Mock (synthetic trajectory)")
        camera = MockCameraCapture(config=config)
        camera.start()
        camera_type = "mock"
    else:
        print("  Mode: Real camera + GPIO sound trigger")
        camera, camera_type = _open_camera(width, height, args.framerate)
        if camera is None:
            print("ERROR: Could not open any camera.")
            sys.exit(1)

    print()
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    try:
        for shot_num in range(1, args.shots + 1):
            print("-" * 60)

            if args.mock:
                print(f"Shot {shot_num}/{args.shots}: mock capture...")
                # MockCameraCapture generates frames in trigger_capture()
                result = camera.trigger_capture()
            else:
                print(f"Shot {shot_num}/{args.shots}: Live preview — position camera, then hit a ball")
                print(f"  (GPIO{args.gpio_pin}, timeout={args.timeout}s)")

                triggered = wait_for_sound_trigger_with_preview(
                    camera, camera_type, detector,
                    gpio_pin=args.gpio_pin,
                    timeout=args.timeout,
                    headless=args.headless,
                )
                if not triggered:
                    print("  Timeout — no sound detected.")
                    continue

                print(f"  BANG! Sound detected at {time.strftime('%H:%M:%S')}")

                # For real camera, we need to grab frames from the capture thread.
                # The CameraCapture class has a circular buffer - we need to use it.
                # But we opened the camera directly (not via CameraCapture) for live preview.
                # So we capture frames manually: grab post-trigger frames now.
                print("  Capturing post-trigger frames...")
                frames = []

                # We already have some pre-trigger frames in our preview loop,
                # but they weren't saved. Grab current + post-trigger frames.
                for i in range(args.num_frames):
                    frame = _capture_frame(camera, camera_type, i)
                    frames.append(frame)

                from openflight.camera.capture import CaptureResult
                # Trigger happened at the start — all frames are post-trigger
                result = CaptureResult(
                    frames=frames,
                    trigger_time=time.time(),
                    trigger_frame_index=0,
                )

            angles = analyze_and_show(
                result, detector, calculator,
                ball_speed_mph=args.ball_speed,
                framerate=args.framerate,
                shot_num=shot_num,
                headless=args.headless,
            )

            if angles:
                print(f"  >> Vertical: {angles.vertical_deg:+.2f} deg  "
                      f"Horizontal: {angles.horizontal_deg:+.2f} deg  "
                      f"Confidence: {angles.confidence:.2f}  "
                      f"Frames: {angles.frames_used}")
                results.append(angles)
            print()

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if args.mock:
            camera.stop()
        else:
            _close_camera(camera, camera_type)
        if not args.headless:
            cv2.destroyAllWindows()

    # Summary
    if results:
        print("=" * 60)
        print(f"  RESULTS ({len(results)}/{args.shots} shots)")
        print("=" * 60)
        for i, a in enumerate(results, 1):
            print(f"  Shot {i}: V={a.vertical_deg:+.2f}  H={a.horizontal_deg:+.2f}  "
                  f"conf={a.confidence:.2f}  frames={a.frames_used}")
        if len(results) > 1:
            avg_v = sum(a.vertical_deg for a in results) / len(results)
            avg_h = sum(a.horizontal_deg for a in results) / len(results)
            print(f"  Avg:    V={avg_v:+.2f}  H={avg_h:+.2f}")
        print("=" * 60)
    else:
        print("No successful measurements.")

    print(f"\nAll frames saved to {SAVE_DIR}/")


if __name__ == "__main__":
    main()
