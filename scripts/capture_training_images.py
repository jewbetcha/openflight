#!/usr/bin/env python3
"""
Capture training images for golf ball detection.

Place the golf ball at various distances and positions, then press SPACE
to capture a frame. Press Q to quit.

Usage:
    DISPLAY=:0 python scripts/capture_training_images.py

    # Headless mode - captures every N seconds
    python scripts/capture_training_images.py --headless --interval 2

Images are saved to training_images/ with timestamps.
"""

import argparse
import os
import time
from datetime import datetime

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("OpenCV required: pip install opencv-python")

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False


def main():
    parser = argparse.ArgumentParser(description="Capture training images")
    parser.add_argument("--output", type=str, default="training_images", help="Output directory")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--headless", action="store_true", help="Auto-capture mode")
    parser.add_argument("--interval", type=float, default=3, help="Seconds between captures in headless mode")
    parser.add_argument("--count", type=int, default=50, help="Number of images to capture in headless mode")
    args = parser.parse_args()

    if not CV2_AVAILABLE:
        print("OpenCV required")
        return 1

    if not PICAMERA_AVAILABLE:
        print("picamera2 required")
        return 1

    # Create output directory
    os.makedirs(args.output, exist_ok=True)

    print("=" * 50)
    print("  Golf Ball Training Image Capture")
    print("=" * 50)
    print()
    print(f"Output directory: {args.output}")
    print(f"Resolution: {args.width}x{args.height}")
    print()

    # Initialize camera
    camera = Picamera2()
    config = camera.create_video_configuration(
        main={"size": (args.width, args.height), "format": "RGB888"},
        controls={"FrameRate": 30}
    )
    camera.configure(config)
    camera.start()
    time.sleep(1)

    captured = 0

    if args.headless:
        print(f"Headless mode: capturing {args.count} images every {args.interval}s")
        print("Move the ball to different positions/distances between captures")
        print()

        for i in range(args.count):
            frame = camera.capture_array()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"ball_{timestamp}.jpg"
            filepath = os.path.join(args.output, filename)

            # Save as BGR for cv2
            cv2.imwrite(filepath, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            captured += 1

            print(f"[{captured}/{args.count}] Saved: {filename}")

            if i < args.count - 1:
                time.sleep(args.interval)

    else:
        print("Interactive mode:")
        print("  SPACE - Capture image")
        print("  Q     - Quit")
        print()
        print("Tips for good training data:")
        print("  - Vary the distance (1ft to 6ft)")
        print("  - Vary the position (center, edges, corners)")
        print("  - Include some frames WITHOUT a ball")
        print("  - Different lighting if possible")
        print()

        cv2.namedWindow("Capture", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Capture", args.width, args.height)

        while True:
            frame = camera.capture_array()
            display = frame.copy()

            # Show capture count
            cv2.putText(display, f"Captured: {captured}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(display, "SPACE=capture  Q=quit", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

            # Draw center crosshair for reference
            h, w = frame.shape[:2]
            cv2.line(display, (w//2 - 20, h//2), (w//2 + 20, h//2), (128, 128, 128), 1)
            cv2.line(display, (w//2, h//2 - 20), (w//2, h//2 + 20), (128, 128, 128), 1)

            cv2.imshow("Capture", cv2.cvtColor(display, cv2.COLOR_RGB2BGR))

            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                break
            elif key == ord(' '):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"ball_{timestamp}.jpg"
                filepath = os.path.join(args.output, filename)

                cv2.imwrite(filepath, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                captured += 1

                print(f"Saved: {filename} (total: {captured})")

        cv2.destroyAllWindows()

    camera.stop()
    camera.close()

    print()
    print(f"Done! Captured {captured} images in {args.output}/")
    print()
    print("Next steps:")
    print("  1. Transfer images to your computer:")
    print(f"     scp -r pi@<ip>:~/openflight/{args.output} .")
    print()
    print("  2. Label them at https://roboflow.com (free account)")
    print("     - Create new project > Object Detection")
    print("     - Upload images")
    print("     - Draw bounding boxes around golf balls")
    print("     - Export as YOLOv8 format")
    print()
    print("  3. Re-run training notebook with your dataset")

    return 0


if __name__ == "__main__":
    exit(main())
