#!/usr/bin/env python3
"""
Test YOLO ball detection on camera feed.

This script tests if YOLOv8n can detect golf balls using the
pre-trained "sports ball" class from the COCO dataset.

Usage:
    # On Pi with display
    DISPLAY=:0 python scripts/test_yolo_detection.py

    # Headless mode (saves frames)
    python scripts/test_yolo_detection.py --headless --num-frames 5

    # Test with specific image file
    python scripts/test_yolo_detection.py --image frame_0000.png
"""

import argparse
import sys
import time

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("ultralytics required: pip install ultralytics")

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("OpenCV required: pip install opencv-python")

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False


# COCO class ID for "sports ball" is 32
SPORTS_BALL_CLASS = 32

# For fine-tuned golf ball models, class 0 is typically the golf ball
GOLF_BALL_CLASS = 0


def main():
    parser = argparse.ArgumentParser(description="Test YOLO Ball Detection")
    parser.add_argument("--image", type=str, help="Test on a single image file")
    parser.add_argument("--headless", action="store_true", help="Save frames instead of displaying")
    parser.add_argument("--num-frames", type=int, default=10, help="Number of frames to capture in headless mode")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--confidence", type=float, default=0.3, help="Minimum confidence threshold")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="YOLO model to use")
    parser.add_argument("--iou", type=float, default=0.5, help="IoU threshold for NMS (lower = fewer overlapping boxes)")
    parser.add_argument("--max-det", type=int, default=1, help="Maximum detections per frame")
    args = parser.parse_args()

    if not YOLO_AVAILABLE or not CV2_AVAILABLE:
        print("Missing dependencies. Install with:")
        print("  pip install ultralytics opencv-python")
        return 1

    print("=" * 50)
    print("  YOLO Ball Detection Test")
    print("=" * 50)
    print()

    # Load YOLO model
    print(f"Loading model: {args.model}")
    model = YOLO(args.model)
    print("Model loaded!")
    print()

    # Test on single image
    if args.image:
        print(f"Testing on image: {args.image}")
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"Error: Could not read image {args.image}")
            return 1

        # Run detection
        results = model(frame, conf=args.confidence, iou=args.iou, max_det=args.max_det, verbose=False)

        # Process results
        detections = []
        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                class_name = model.names[cls]
                x1, y1, x2, y2 = box.xyxy[0].tolist()

                detections.append({
                    "class": class_name,
                    "class_id": cls,
                    "confidence": conf,
                    "bbox": (x1, y1, x2, y2)
                })

                # Draw on frame
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                label = f"{class_name} {conf:.2f}"
                cv2.putText(frame, label, (int(x1), int(y1) - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        print(f"Found {len(detections)} objects:")
        for d in detections:
            print(f"  - {d['class']} (id={d['class_id']}, conf={d['confidence']:.2f})")
            if d['class_id'] == SPORTS_BALL_CLASS or d['class_id'] == GOLF_BALL_CLASS or 'ball' in d['class'].lower():
                print(f"    ^^^ BALL DETECTED!")

        # Save result
        output_file = args.image.replace('.png', '_yolo.png').replace('.jpg', '_yolo.jpg')
        cv2.imwrite(output_file, frame)
        print(f"\nSaved: {output_file}")
        return 0

    # Camera mode
    if not PICAMERA_AVAILABLE:
        print("picamera2 not available - use --image to test on a file")
        return 1

    print(f"Starting camera: {args.width}x{args.height}")
    camera = Picamera2()
    config = camera.create_video_configuration(
        main={"size": (args.width, args.height), "format": "RGB888"},
        controls={"FrameRate": 30}
    )
    camera.configure(config)
    camera.start()
    time.sleep(1)  # Let camera warm up

    if args.headless:
        print(f"Capturing {args.num_frames} frames...")
        print()

        for i in range(args.num_frames):
            frame = camera.capture_array()

            # Run YOLO detection
            start_time = time.time()
            results = model(frame, conf=args.confidence, iou=args.iou, max_det=args.max_det, verbose=False)
            inference_time = time.time() - start_time

            # Process and draw results
            ball_detected = False
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    class_name = model.names[cls]
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    # Draw box
                    color = (0, 255, 0) if cls == SPORTS_BALL_CLASS or cls == GOLF_BALL_CLASS or 'ball' in class_name.lower() else (255, 0, 0)
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                    label = f"{class_name} {conf:.2f}"
                    cv2.putText(frame, label, (int(x1), int(y1) - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                    if cls == SPORTS_BALL_CLASS or cls == GOLF_BALL_CLASS or 'ball' in class_name.lower():
                        ball_detected = True

            # Save frame
            filename = f"yolo_frame_{i:04d}.png"
            cv2.imwrite(filename, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

            ball_status = "BALL FOUND!" if ball_detected else "no ball"
            print(f"Frame {i}: {inference_time*1000:.0f}ms - {ball_status} - saved {filename}")

            time.sleep(0.5)

        camera.stop()
        camera.close()
        print()
        print("Done! Transfer frames to view:")
        print("  scp pi@<ip>:~/openlaunch/yolo_frame_*.png .")
        return 0

    # Live display mode
    print("Live mode - press 'q' to quit")
    print()

    cv2.namedWindow("YOLO Detection", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("YOLO Detection", args.width, args.height)

    fps_list = []

    try:
        while True:
            frame = camera.capture_array()

            # Run YOLO
            start_time = time.time()
            results = model(frame, conf=args.confidence, iou=args.iou, max_det=args.max_det, verbose=False)
            inference_time = time.time() - start_time
            fps = 1.0 / inference_time if inference_time > 0 else 0
            fps_list.append(fps)
            if len(fps_list) > 30:
                fps_list.pop(0)
            avg_fps = sum(fps_list) / len(fps_list)

            # Draw results
            ball_count = 0
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    class_name = model.names[cls]
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    is_ball = cls == SPORTS_BALL_CLASS or cls == GOLF_BALL_CLASS or 'ball' in class_name.lower()
                    color = (0, 255, 0) if is_ball else (128, 128, 128)
                    thickness = 2 if is_ball else 1

                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)
                    label = f"{class_name} {conf:.2f}"
                    cv2.putText(frame, label, (int(x1), int(y1) - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, thickness)

                    if is_ball:
                        ball_count += 1
                        # Draw center point
                        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                        cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

            # Draw FPS and status
            cv2.putText(frame, f"FPS: {avg_fps:.1f}", (10, 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(frame, f"Balls: {ball_count}", (10, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if ball_count > 0 else (128, 128, 128), 2)

            cv2.imshow("YOLO Detection", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        cv2.destroyAllWindows()
        camera.stop()
        camera.close()

    print(f"\nAverage FPS: {avg_fps:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
