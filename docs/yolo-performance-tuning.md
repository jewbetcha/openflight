# YOLO Detection Performance Tuning on Raspberry Pi

This guide covers how to optimize YOLO golf ball detection for maximum FPS on Raspberry Pi 5.

## Camera in OpenFlight UI

The camera is enabled by default when running `start-kiosk.sh`. In the UI:
- **Header**: Ball detection indicator shows if a ball is detected (click to toggle camera)
- **Camera Tab**: View live feed with detection overlay

To customize the model used:
```bash
./scripts/start-kiosk.sh --camera-model models/golf_ball_yolo11n.onnx
```

## Quick Start (Best Balance)

For ~30 FPS with good detection quality:

```bash
# Export model to ONNX at 256px
python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.pt \
  --imgsz 256 \
  --export-onnx

# Run detection
DISPLAY=:0 python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.onnx \
  --imgsz 256 \
  --threaded
```

## Performance vs Quality Tradeoffs

| Input Size | Expected FPS | Detection Quality | Notes |
|------------|--------------|-------------------|-------|
| 640 | ~12 | Best | Default, too slow for real-time |
| 320 | ~20 | Good | Solid detection |
| 288 | ~25 | Good | Good middle ground |
| 256 | ~30 | Good | Recommended balance |
| 224 | ~40 | Acceptable | Slight quality drop |
| 192 | ~50 | Reduced | Small objects harder to detect |

## Export Formats

### ONNX (Recommended)
Most stable and well-supported on Pi:

```bash
python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.pt \
  --imgsz <SIZE> \
  --export-onnx
```

### OpenVINO
Alternative runtime, supports INT8 quantization:

```bash
pip install openvino

python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.pt \
  --imgsz <SIZE> \
  --export-openvino
```

With INT8 quantization (faster but lower accuracy):
```bash
python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.pt \
  --imgsz <SIZE> \
  --export-openvino --int8
```

### NCNN
Theoretically fastest on ARM, but has stability issues (segfaults). Not recommended.

## Runtime Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--imgsz` | Inference input size (smaller = faster) | 640 |
| `--threaded` | Separate capture/inference threads | off |
| `--half` | FP16 half-precision (PyTorch only) | off |
| `--confidence` | Detection threshold (lower = more detections) | 0.3 |
| `--no-display` | Skip drawing overlays for benchmarking | off |
| `--fps` | Target camera FPS | 60 |
| `--buffer-count` | Camera buffer count (lower = less latency) | 2 |

## Example Commands

### Maximum FPS (reduced detection quality)
```bash
DISPLAY=:0 python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.onnx \
  --imgsz 192 \
  --threaded \
  --confidence 0.2
```

### Best detection (slower)
```bash
DISPLAY=:0 python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.onnx \
  --imgsz 320 \
  --threaded
```

### Headless benchmark
```bash
python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.onnx \
  --imgsz 256 \
  --threaded \
  --no-display
```

### Lower confidence for more detections
```bash
DISPLAY=:0 python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.onnx \
  --imgsz 224 \
  --threaded \
  --confidence 0.15
```

## Optimization Summary

1. **Use ONNX export** - More stable than NCNN on Pi
2. **Reduce input size** - Biggest performance gain (256 or 224 recommended)
3. **Use `--threaded`** - Separates capture from inference
4. **Match camera to inference size** - Reduces scaling overhead
5. **INT8 quantization** - Faster but hurts small object detection

## Hardware Upgrades for 60+ FPS

To exceed ~50 FPS on Pi, you'd need:
- Coral USB TPU Accelerator (~$60)
- Or switch to a simpler non-YOLO detection method
