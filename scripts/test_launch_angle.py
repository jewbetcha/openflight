#!/usr/bin/env python3
"""
End-to-end test script for launch angle detection.

Shows a live camera preview (with Hough circle detection overlay) while
waiting for the sound sensor to detect a golf shot, then calculates
launch angle from the tracked ball trajectory.

Uses the same CameraTracker + HoughDetector as the main server.

Usage:
    # Real hardware: live preview + sound trigger
    uv run python scripts/test_launch_angle.py

    # Multiple shots
    uv run python scripts/test_launch_angle.py --shots 5

    # Save frames for review (SSH session)
    uv run python scripts/test_launch_angle.py --headless

    # Mock mode (no hardware required)
    uv run python scripts/test_launch_angle.py --mock

    # Tune Hough params with live sliders
    uv run python scripts/test_launch_angle.py --tune

    # Start tuning from your known-good values
    uv run python scripts/test_launch_angle.py --tune --hough-param2 36 --hough-param1 51
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

from openflight.camera_tracker import CameraTracker, HoughDetector

SAVE_DIR = Path("launch_angle_frames")


def run_tune_mode(camera, args, width, height):
    """
    Live tuning mode with OpenCV trackbar sliders.

    Adjust Hough parameters in real-time and see results immediately.
    Press 'q' to quit and print the final parameter values.
    """
    WINDOW = "Hough Tuner"
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    # Create trackbars with current values
    cv2.createTrackbar("param1", WINDOW, args.hough_param1, 200, lambda x: None)
    cv2.createTrackbar("param2", WINDOW, args.hough_param2, 100, lambda x: None)
    cv2.createTrackbar("minRadius", WINDOW, args.hough_min_radius, 100, lambda x: None)
    cv2.createTrackbar("maxRadius", WINDOW, args.hough_max_radius, 200, lambda x: None)
    cv2.createTrackbar("minDist", WINDOW, args.hough_min_dist, 500, lambda x: None)

    fps_start = time.time()
    fps_count = 0
    current_fps = 0.0

    print("  Drag sliders to tune. Press 'q' to quit and print values.")
    print()

    while True:
        frame = camera.capture_array()

        # Read current slider values
        p1 = max(1, cv2.getTrackbarPos("param1", WINDOW))
        p2 = max(1, cv2.getTrackbarPos("param2", WINDOW))
        min_r = cv2.getTrackbarPos("minRadius", WINDOW)
        max_r = max(min_r + 1, cv2.getTrackbarPos("maxRadius", WINDOW))
        min_d = max(1, cv2.getTrackbarPos("minDist", WINDOW))

        # Detect with current params
        detector = HoughDetector(
            param1=p1, param2=p2,
            min_radius=min_r, max_radius=max_r,
            min_dist=min_d,
        )
        detections = detector.detect(frame)

        # Draw detections
        display = frame.copy()
        for det in detections:
            cx, cy, r = int(det['x']), int(det['y']), int(det['radius'])
            cv2.circle(display, (cx, cy), r, (0, 255, 0), 2)
            cv2.circle(display, (cx, cy), 2, (0, 0, 255), -1)

        # FPS counter
        fps_count += 1
        elapsed = time.time() - fps_start
        if elapsed >= 1.0:
            current_fps = fps_count / elapsed
            fps_count = 0
            fps_start = time.time()

        n = len(detections)
        status = (f"p1={p1} p2={p2} r={min_r}-{max_r} dist={min_d} | "
                  f"{n} detection{'s' if n != 1 else ''} | FPS: {current_fps:.0f} | 'q' to quit")
        cv2.putText(display, status, (10, display.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)
        cv2.imshow(WINDOW, display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

    cv2.destroyAllWindows()

    # Print final values as a ready-to-use command
    print("=" * 60)
    print("  FINAL PARAMETERS")
    print("=" * 60)
    print(f"  param1={p1}  param2={p2}  radius={min_r}-{max_r}  minDist={min_d}")
    print()
    print("  Run with these settings:")
    print(f"  uv run python scripts/test_launch_angle.py \\")
    print(f"    --hough-param1 {p1} --hough-param2 {p2} \\")
    print(f"    --hough-min-radius {min_r} --hough-max-radius {max_r} \\")
    print(f"    --hough-min-dist {min_d}")
    print("=" * 60)


def wait_for_sound_trigger_with_preview(
    camera,
    tracker: CameraTracker,
    gpio_pin: int = 17,
    timeout: float = 60.0,
    headless: bool = False,
) -> bool:
    """
    Show live camera preview with detection overlay while waiting for sound trigger.

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

    fps_start = time.time()
    fps_count = 0
    current_fps = 0.0
    start = time.time()

    try:
        while not triggered and (time.time() - start) < timeout:
            frame = camera.capture_array()
            detection = tracker.process_frame(frame)

            fps_count += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                current_fps = fps_count / elapsed
                fps_count = 0
                fps_start = time.time()

            if not headless:
                display = tracker.get_debug_frame(frame)
                remaining = max(0, timeout - (time.time() - start))
                det_str = f"BALL ({detection.x},{detection.y})" if detection else "no ball"
                status = f"{det_str} | FPS: {current_fps:.0f} | {remaining:.0f}s | 'q' to quit"
                cv2.putText(display, status, (10, display.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)
                cv2.imshow("Launch Angle Test", display)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("  Quit by user.")
                    button.close()
                    return False
            else:
                if fps_count == 1:  # Once per second
                    det_str = f"ball at ({detection.x},{detection.y})" if detection else "no ball"
                    remaining = max(0, timeout - (time.time() - start))
                    print(f"  [preview] {det_str} | fps={current_fps:.0f} | {remaining:.0f}s remaining")
    finally:
        button.close()

    return triggered


def capture_post_trigger(camera, tracker: CameraTracker, num_frames: int, headless: bool):
    """
    Capture frames after trigger, running detection on each.

    Returns list of (frame, detection) tuples.
    """
    captures = []
    for i in range(num_frames):
        frame = camera.capture_array()
        detection = tracker.process_frame(frame)
        captures.append((frame, detection))

        if not headless:
            display = tracker.get_debug_frame(frame)
            cv2.putText(display, f"Capturing {i+1}/{num_frames}",
                        (10, display.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.imshow("Launch Angle Test", display)
            cv2.waitKey(1)

    return captures


def save_capture_frames(captures, shot_num: int, tracker: CameraTracker):
    """Save captured frames with debug overlay."""
    shot_dir = SAVE_DIR / f"shot_{shot_num:03d}"
    shot_dir.mkdir(parents=True, exist_ok=True)

    for i, (frame, detection) in enumerate(captures):
        display = tracker.get_debug_frame(frame)
        info = f"Frame {i}"
        if detection:
            info += f" | BALL ({detection.x},{detection.y}) r={detection.radius}"
        cv2.putText(display, info, (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.imwrite(str(shot_dir / f"frame_{i:04d}.png"), display)

    return shot_dir


def main():
    parser = argparse.ArgumentParser(
        description="Launch angle test — live preview + sound trigger + Hough detection"
    )
    parser.add_argument("--tune", action="store_true",
                        help="Live tuning mode — adjust Hough params with sliders")
    parser.add_argument("--mock", action="store_true",
                        help="Simulate a shot sequence (no hardware needed)")
    parser.add_argument("--headless", action="store_true",
                        help="No display window (for SSH sessions)")
    parser.add_argument("--shots", type=int, default=1,
                        help="Number of shots to capture (default: 1)")
    parser.add_argument("--post-frames", type=int, default=60,
                        help="Frames to capture after trigger (default: 60 = ~500ms at 120fps)")
    parser.add_argument("--gpio-pin", type=int, default=17,
                        help="BCM GPIO pin for SEN-14262 GATE (default: 17)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="Seconds to wait per shot (default: 60)")
    parser.add_argument("--hough-param2", type=int, default=33,
                        help="Hough accumulator threshold — lower = more sensitive (default: 33)")
    parser.add_argument("--hough-param1", type=int, default=48,
                        help="Canny edge threshold — lower = detects weaker edges (default: 48)")
    parser.add_argument("--hough-min-radius", type=int, default=4,
                        help="Min ball radius in pixels (default: 4)")
    parser.add_argument("--hough-max-radius", type=int, default=43,
                        help="Max ball radius in pixels (default: 43)")
    parser.add_argument("--hough-min-dist", type=int, default=266,
                        help="Min distance between detected circles (default: 266)")
    parser.add_argument("--resolution", type=str, default="640x480",
                        help="Camera resolution WIDTHxHEIGHT (default: 640x480)")
    parser.add_argument("--framerate", type=int, default=60,
                        help="Camera framerate (default: 60, matches server.py)")
    args = parser.parse_args()

    # Parse resolution
    try:
        width, height = [int(x) for x in args.resolution.split("x")]
    except ValueError:
        print(f"ERROR: Invalid resolution '{args.resolution}'. Use WIDTHxHEIGHT")
        sys.exit(1)

    print("=" * 60)
    print("  Launch Angle Detection Test")
    print("=" * 60)

    # Initialize CameraTracker (same as server.py)
    tracker = CameraTracker(
        use_hough=True,
        hough_param2=args.hough_param2,
        hough_param1=args.hough_param1,
        hough_min_radius=args.hough_min_radius,
        hough_max_radius=args.hough_max_radius,
        hough_min_dist=args.hough_min_dist,
        frame_width=width,
    )
    print(f"  Detector: Hough circles (param1={args.hough_param1}, param2={args.hough_param2}, "
          f"radius={args.hough_min_radius}-{args.hough_max_radius}, minDist={args.hough_min_dist})")
    print(f"  Resolution: {width}x{height} @ {args.framerate}fps")

    if args.mock:
        print("  Mode: Mock (simulated shot)")
        print()
        # Generate synthetic frames with a moving ball
        tracker.reset()
        for i in range(30):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            # Ball moves up and right, shrinks
            cx = width // 2 + i * 3
            cy = height - 80 - i * 10
            r = max(5, 20 - i // 2)
            if 0 <= cy < height:
                cv2.circle(frame, (cx, cy), r, (200, 200, 200), -1)
            tracker.process_frame(frame)

        angle = tracker.calculate_launch_angle()
        if angle:
            print(f"  Vertical:   {angle.vertical:+.1f} deg")
            print(f"  Horizontal: {angle.horizontal:+.1f} deg")
            print(f"  Confidence: {angle.confidence:.2f}")
            print(f"  Positions:  {len(angle.positions)}")
        else:
            print("  No launch angle calculated (need more detections)")
        print("=" * 60)
        return

    # Open Pi camera (same config as server.py init_camera)
    print("  Mode: Real camera + GPIO sound trigger")
    try:
        from picamera2 import Picamera2
    except ImportError:
        print("ERROR: picamera2 not available")
        sys.exit(1)

    camera = Picamera2()
    config = camera.create_video_configuration(
        main={"size": (width, height), "format": "RGB888"},
        buffer_count=2,
        controls={"FrameRate": args.framerate},
    )
    camera.configure(config)
    camera.start()
    print(f"  Camera started")
    print()

    # Warm up
    time.sleep(0.5)

    # Tune mode: live sliders, no shot capture
    if args.tune:
        print("  Mode: Tune (live sliders)")
        try:
            run_tune_mode(camera, args, width, height)
        finally:
            camera.stop()
            camera.close()
        return

    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    try:
        for shot_num in range(1, args.shots + 1):
            print("-" * 60)
            tracker.reset()

            print(f"Shot {shot_num}/{args.shots}: Live preview — position camera, then hit a ball")
            print(f"  (GPIO{args.gpio_pin}, timeout={args.timeout}s)")

            triggered = wait_for_sound_trigger_with_preview(
                camera, tracker,
                gpio_pin=args.gpio_pin,
                timeout=args.timeout,
                headless=args.headless,
            )
            if not triggered:
                print("  Timeout — no sound detected.")
                continue

            print(f"  BANG! Sound detected at {time.strftime('%H:%M:%S')}")

            # Capture post-trigger frames (ball in flight)
            print(f"  Capturing {args.post_frames} post-trigger frames...")
            captures = capture_post_trigger(
                camera, tracker, args.post_frames, args.headless,
            )

            detected = sum(1 for _, d in captures if d is not None)
            print(f"  Detection: {detected}/{len(captures)} frames")

            # Save frames
            shot_dir = save_capture_frames(captures, shot_num, tracker)
            print(f"  Frames saved to {shot_dir}/")

            # Calculate launch angle from all tracked positions
            angle = tracker.calculate_launch_angle()
            if angle:
                print(f"  >> Vertical: {angle.vertical:+.1f} deg  "
                      f"Horizontal: {angle.horizontal:+.1f} deg  "
                      f"Confidence: {angle.confidence:.2f}  "
                      f"Positions: {len(angle.positions)}")
                results.append(angle)
            else:
                print(f"  No launch angle (need {tracker.MIN_POSITIONS_FOR_ANGLE}+ positions, "
                      f"got {len(list(tracker.positions))})")
            print()

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        camera.stop()
        camera.close()
        if not args.headless:
            cv2.destroyAllWindows()

    # Summary
    if results:
        print("=" * 60)
        print(f"  RESULTS ({len(results)}/{args.shots} shots)")
        print("=" * 60)
        for i, a in enumerate(results, 1):
            print(f"  Shot {i}: V={a.vertical:+.1f}  H={a.horizontal:+.1f}  "
                  f"conf={a.confidence:.2f}  positions={len(a.positions)}")
        if len(results) > 1:
            avg_v = sum(a.vertical for a in results) / len(results)
            avg_h = sum(a.horizontal for a in results) / len(results)
            print(f"  Avg:    V={avg_v:+.1f}  H={avg_h:+.1f}")
        print("=" * 60)
    else:
        print("No successful measurements.")

    print(f"\nFrames saved to {SAVE_DIR}/")


if __name__ == "__main__":
    main()
