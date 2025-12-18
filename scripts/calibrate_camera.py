#!/usr/bin/env python3
"""
Camera calibration and testing script.

Use this to dial in detection settings by viewing live camera output
with ball detection overlays.

Usage:
    python scripts/calibrate_camera.py              # Live view with detection
    python scripts/calibrate_camera.py --no-detect  # Just camera feed
    python scripts/calibrate_camera.py --save       # Save test frames
    python scripts/calibrate_camera.py --exposure 1000  # Adjust exposure (µs)
"""

import argparse
import sys
import time

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("OpenCV required: pip install opencv-python")
    sys.exit(1)

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False


def create_test_frame(width, height, ball_x, ball_y, ball_radius):
    """Create a synthetic test frame with a white ball."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    # Add some noise
    frame += np.random.randint(0, 30, frame.shape, dtype=np.uint8)
    # Draw white ball
    cv2.circle(frame, (int(ball_x), int(ball_y)), int(ball_radius), (255, 255, 255), -1)
    return frame


def main():
    parser = argparse.ArgumentParser(description="Camera Calibration Tool")
    parser.add_argument("--no-detect", action="store_true",
                        help="Disable ball detection overlay")
    parser.add_argument("--save", action="store_true",
                        help="Save frames to disk")
    parser.add_argument("--mock", action="store_true",
                        help="Use synthetic frames (no camera)")
    parser.add_argument("--headless", action="store_true",
                        help="Headless mode - save frames without display (for SSH)")
    parser.add_argument("--num-frames", type=int, default=10,
                        help="Number of frames to capture in headless mode")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--exposure", type=int, default=2000,
                        help="Exposure time in microseconds")
    parser.add_argument("--gain", type=float, default=4.0,
                        help="Analogue gain for IR sensitivity")
    parser.add_argument("--threshold", type=int, default=200,
                        help="Brightness threshold (0-255)")
    parser.add_argument("--min-radius", type=int, default=5)
    parser.add_argument("--max-radius", type=int, default=50)
    parser.add_argument("--hough-param2", type=int, default=20,
                        help="Hough circle detection sensitivity (lower = more detections, default 20)")
    parser.add_argument("--use-contours", action="store_true",
                        help="Use contour detection instead of Hough circles")
    parser.add_argument("--circularity", type=float, default=0.3,
                        help="Minimum circularity for contour detection (0-1, default 0.3)")
    parser.add_argument("--min-area", type=int, default=0,
                        help="Minimum blob area in pixels (overrides min-radius calculation)")
    args = parser.parse_args()

    print("=" * 50)
    print("  OpenLaunch Camera Calibration")
    print("=" * 50)
    print()

    if args.headless:
        print(f"Headless mode: capturing {args.num_frames} frames to disk")
        print()
    else:
        print("Controls:")
        print("  q - Quit")
        print("  s - Save current frame")
        print("  t - Toggle threshold view")
        print("  d - Toggle detection overlay")
        print("  +/- - Adjust threshold")
        print("  [/] - Adjust min radius")
        print("  {/} - Adjust max radius")
        print()

    # Detection settings (can be adjusted live)
    settings = {
        "threshold": args.threshold,
        "min_radius": args.min_radius,
        "max_radius": args.max_radius,
        "hough_param2": args.hough_param2,
        "use_contours": args.use_contours,
        "circularity": args.circularity,
        "min_area": args.min_area,
        "show_threshold": False,
        "show_detection": not args.no_detect,
    }

    camera = None
    if not args.mock:
        if not PICAMERA_AVAILABLE:
            print("picamera2 not available, using mock mode")
            args.mock = True
        else:
            try:
                camera = Picamera2()
                config = camera.create_video_configuration(
                    main={"size": (args.width, args.height), "format": "RGB888"},
                    controls={
                        "FrameRate": 30,  # Lower for calibration
                        "ExposureTime": args.exposure,
                        "AnalogueGain": args.gain,
                        "AeEnable": False,
                    }
                )
                camera.configure(config)
                camera.start()
                print(f"Camera started: {args.width}x{args.height}")
                print(f"Exposure: {args.exposure}µs, Gain: {args.gain}")
            except Exception as e:
                print(f"Camera error: {e}")
                print("Falling back to mock mode")
                args.mock = True
                camera = None

    if args.mock:
        print("Using synthetic test frames")

    # Headless mode - capture frames without display
    if args.headless:
        print()
        for i in range(args.num_frames):
            if camera:
                frame = camera.capture_array()
            else:
                frame = create_test_frame(args.width, args.height, 320, 240, 20)

            filename = f"frame_{i:04d}.png"
            cv2.imwrite(filename, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            print(f"Saved: {filename}")

            # Also save threshold view
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            else:
                gray = frame
            _, thresh = cv2.threshold(gray, settings["threshold"], 255, cv2.THRESH_BINARY)
            thresh_filename = f"frame_{i:04d}_thresh.png"
            cv2.imwrite(thresh_filename, thresh)
            print(f"Saved: {thresh_filename}")

            time.sleep(0.5)  # Small delay between captures

        if camera:
            camera.stop()
            camera.close()

        print()
        print(f"Captured {args.num_frames} frames. Transfer to your computer to view:")
        print(f"  scp pi@<ip>:~/openlaunch/frame_*.png .")
        print()
        print("Settings used:")
        print(f"  brightness_threshold={settings['threshold']}")
        print(f"  min_radius={settings['min_radius']}")
        print(f"  max_radius={settings['max_radius']}")
        return

    cv2.namedWindow("Camera", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Camera", args.width, args.height)

    frame_count = 0
    ball_x, ball_y = args.width // 2, args.height - 100
    ball_radius = 20
    ball_vy = -5  # Moving up

    try:
        while True:
            # Capture frame
            if camera:
                frame = camera.capture_array()
            else:
                # Synthetic moving ball
                frame = create_test_frame(
                    args.width, args.height,
                    ball_x, ball_y, ball_radius
                )
                ball_y += ball_vy
                if ball_y < 50:
                    ball_y = args.height - 100
                    ball_radius = 20
                else:
                    ball_radius = max(5, ball_radius - 0.2)

            # Convert to grayscale for processing
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            else:
                gray = frame

            display = frame.copy()

            # Apply threshold
            _, thresh = cv2.threshold(
                gray, settings["threshold"], 255, cv2.THRESH_BINARY
            )

            if settings["show_threshold"]:
                # Show threshold view
                display = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

            if settings["show_detection"]:
                # Detect circles
                blurred = cv2.GaussianBlur(thresh, (5, 5), 0)

                if settings["use_contours"]:
                    # Alternative: contour-based detection (better for bright blobs)
                    contours, _ = cv2.findContours(blurred, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                    # Find the largest valid contour (most likely to be the ball)
                    best_contour = None
                    best_area = 0

                    for contour in contours:
                        area = cv2.contourArea(contour)

                        # Use min_area if specified, otherwise calculate from radius
                        if settings["min_area"] > 0:
                            min_area = settings["min_area"]
                        else:
                            min_area = 3.14159 * settings["min_radius"] ** 2
                        max_area = 3.14159 * settings["max_radius"] ** 2

                        if min_area <= area <= max_area:
                            # Check circularity (perimeter^2 / area, perfect circle = 4*pi)
                            perimeter = cv2.arcLength(contour, True)
                            if perimeter > 0:
                                circularity = 4 * 3.14159 * area / (perimeter ** 2)
                                if circularity >= settings["circularity"]:
                                    # Keep track of largest valid contour
                                    if area > best_area:
                                        best_area = area
                                        best_contour = (contour, circularity)

                    # Only draw the best (largest) detection
                    if best_contour is not None:
                        contour, circularity = best_contour
                        (cx, cy), r = cv2.minEnclosingCircle(contour)
                        cx, cy, r = int(cx), int(cy), int(r)
                        cv2.circle(display, (cx, cy), r, (0, 255, 0), 2)
                        cv2.circle(display, (cx, cy), 3, (0, 0, 255), -1)
                        cv2.putText(
                            display, f"r={r} c={circularity:.2f}",
                            (cx + 10, cy), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 255, 0), 1
                        )
                else:
                    # Hough circle detection
                    circles = cv2.HoughCircles(
                        blurred,
                        cv2.HOUGH_GRADIENT,
                        dp=1.2,
                        minDist=50,
                        param1=50,
                        param2=settings["hough_param2"],
                        minRadius=settings["min_radius"],
                        maxRadius=settings["max_radius"]
                    )

                    if circles is not None:
                        circles = np.uint16(np.around(circles))
                        for i in circles[0, :]:
                            cx, cy, r = i[0], i[1], i[2]
                            # Draw detected circle
                            cv2.circle(display, (cx, cy), r, (0, 255, 0), 2)
                            # Draw center
                            cv2.circle(display, (cx, cy), 3, (0, 0, 255), -1)
                            # Show radius
                            cv2.putText(
                                display, f"r={r}",
                                (cx + 10, cy), cv2.FONT_HERSHEY_SIMPLEX,
                                0.5, (0, 255, 0), 1
                            )

            # Draw settings overlay
            y_offset = 20
            cv2.putText(display, f"Threshold: {settings['threshold']}",
                        (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            y_offset += 20
            cv2.putText(display, f"Radius: {settings['min_radius']}-{settings['max_radius']}",
                        (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            y_offset += 20
            mode = "THRESH" if settings["show_threshold"] else "RGB"
            cv2.putText(display, f"Mode: {mode}",
                        (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

            # Calculate histogram of brightness (useful for IR setup)
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            max_brightness = np.argmax(hist[100:]) + 100 if np.max(hist[100:]) > 0 else 0
            y_offset += 20
            cv2.putText(display, f"Peak brightness: {max_brightness}",
                        (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

            cv2.imshow("Camera", display)

            # Handle keyboard input
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                filename = f"frame_{frame_count:04d}.png"
                cv2.imwrite(filename, frame)
                print(f"Saved: {filename}")
            elif key == ord('t'):
                settings["show_threshold"] = not settings["show_threshold"]
            elif key == ord('d'):
                settings["show_detection"] = not settings["show_detection"]
            elif key == ord('+') or key == ord('='):
                settings["threshold"] = min(255, settings["threshold"] + 5)
                print(f"Threshold: {settings['threshold']}")
            elif key == ord('-'):
                settings["threshold"] = max(0, settings["threshold"] - 5)
                print(f"Threshold: {settings['threshold']}")
            elif key == ord('['):
                settings["min_radius"] = max(1, settings["min_radius"] - 1)
                print(f"Min radius: {settings['min_radius']}")
            elif key == ord(']'):
                settings["min_radius"] = min(settings["max_radius"], settings["min_radius"] + 1)
                print(f"Min radius: {settings['min_radius']}")
            elif key == ord('{'):
                settings["max_radius"] = max(settings["min_radius"], settings["max_radius"] - 5)
                print(f"Max radius: {settings['max_radius']}")
            elif key == ord('}'):
                settings["max_radius"] = min(200, settings["max_radius"] + 5)
                print(f"Max radius: {settings['max_radius']}")

            frame_count += 1

    finally:
        cv2.destroyAllWindows()
        if camera:
            camera.stop()
            camera.close()

    print()
    print("Final settings:")
    print(f"  brightness_threshold={settings['threshold']}")
    print(f"  min_radius={settings['min_radius']}")
    print(f"  max_radius={settings['max_radius']}")


if __name__ == "__main__":
    main()
