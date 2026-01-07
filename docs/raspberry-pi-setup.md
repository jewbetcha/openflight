# Raspberry Pi Setup Guide

Complete guide for setting up OpenFlight on a Raspberry Pi 5 with the 7" touchscreen display.

## Hardware Requirements

- Raspberry Pi 5 (4GB+ recommended)
- 7" Touchscreen Display (e.g., HMTECH 1024x600 IPS)
- MicroSD Card (32GB+)
- 27W USB-C Power Supply (official Pi 5 PSU recommended)
- OPS243-A Doppler Radar
- USB-A to Micro-USB cable (for radar)

See [PARTS.md](../PARTS.md) for the full parts list.

## Initial Setup

### 1. Install Raspberry Pi OS

Use Raspberry Pi Imager to flash Raspberry Pi OS (64-bit) to your SD card.

### 2. Clone and Setup

```bash
cd ~
git clone https://github.com/jewbetcha/openflight.git
cd openflight

# Run the setup script (handles everything)
./scripts/setup.sh
```

The setup script will:
- Create a Python virtual environment (with system-site-packages for picamera2)
- Install all Python dependencies (including camera support on Pi)
- Install Node.js dependencies
- Build the UI
- Run tests to verify installation

Or manually:

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv with system site packages (needed for picamera2)
python -m venv .venv --system-site-packages
source .venv/bin/activate

# Install dependencies
uv pip install -e ".[ui,camera]"

# Build the UI
cd ui && npm install && npm run build && cd ..
```

## Running OpenFlight

### Manual Start

```bash
# With radar connected
openflight-server

# Mock mode (no radar needed)
openflight-server --mock
```

Then open `http://localhost:8080` in a browser.

### Kiosk Mode (Fullscreen)

```bash
./scripts/start-kiosk.sh
```

This starts the server and launches Chromium in fullscreen kiosk mode. Camera is enabled by default if available.

Options:
```bash
# Mock mode (no radar)
./scripts/start-kiosk.sh --mock

# Disable camera
./scripts/start-kiosk.sh --no-camera

# Use a custom YOLO model for ball detection
./scripts/start-kiosk.sh --camera-model models/golf_ball_yolo11n.onnx

# Custom port
./scripts/start-kiosk.sh --port 3000
```

### Running Over SSH

If you're SSHed into the Pi and want to launch on the Pi's display:

```bash
DISPLAY=:0 ./scripts/start-kiosk.sh
```

## Auto-Start on Boot

### Enable the Service

```bash
# Copy the service file
sudo cp ~/openflight/scripts/openflight.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start
sudo systemctl enable openflight

# Start it now
sudo systemctl start openflight
```

### Service Management

```bash
# Check status
sudo systemctl status openflight --no-pager

# View logs
journalctl -u openflight -f

# Stop the service
sudo systemctl stop openflight

# Restart the service
sudo systemctl restart openflight

# Disable auto-start
sudo systemctl disable openflight
```

### Editing the Service

The service file is located at `/etc/systemd/system/openflight.service`.

If you need to modify it:
```bash
sudo nano /etc/systemd/system/openflight.service
sudo systemctl daemon-reload
sudo systemctl restart openflight
```

## Camera Setup (Ball Detection)

The camera enables real-time ball detection in the UI. When a ball is detected, a green indicator appears in the header. You can also view the live camera feed with detection overlay in the Camera tab.

### Install Camera Dependencies

```bash
# Install system library for picamera2
sudo apt install libcap-dev

# Install Python packages (includes ultralytics for YOLO)
uv pip install -e ".[camera]"
```

### Test the Camera

```bash
# Check if camera is detected
rpicam-hello --list-cameras

# Quick preview test
rpicam-hello

# Test YOLO detection (see docs/yolo-performance-tuning.md for optimization)
DISPLAY=:0 python scripts/test_yolo_detection.py \
  --model models/golf_ball_yolo11n.onnx \
  --imgsz 256 \
  --threaded
```

### Camera in the UI

When the server is started with camera enabled (default), the UI provides:

1. **Ball Detection Indicator** (header) - Shows if a ball is currently detected
   - Click to toggle camera on/off
   - Green = ball detected, Yellow = searching, Gray = disabled

2. **Camera Tab** - View live camera feed
   - Enable/disable camera and streaming
   - Shows detection overlay with bounding boxes
   - Ball detection status with confidence percentage

### Camera Calibration

```bash
# Live view with detection overlay (run on Pi's display)
DISPLAY=:0 python scripts/calibrate_camera.py --use-contours --threshold 150 --min-radius 20

# Headless mode (over SSH) - saves frames to disk
python scripts/calibrate_camera.py --headless --num-frames 10
```

Calibration options:
| Option | Description |
|--------|-------------|
| `--threshold` | Brightness threshold (0-255, default 200) |
| `--min-radius` | Minimum ball radius in pixels (default 5) |
| `--max-radius` | Maximum ball radius in pixels (default 50) |
| `--use-contours` | Use contour detection (more stable) |
| `--circularity` | Minimum circularity for contours (0-1, default 0.3) |
| `--exposure` | Camera exposure in microseconds (default 2000) |
| `--gain` | Camera gain for IR sensitivity (default 4.0) |
| `--headless` | Save frames to disk instead of displaying |

## IR LED Setup

For optimal ball detection, use IR LEDs to illuminate the ball.

### Wiring

Connect IR LED modules to the Pi's GPIO:
- **5V**: Pin 2 or Pin 4
- **GND**: Pin 6, 9, 14, 20, 25, 30, 34, or 39

### Testing IR LEDs

Point your phone camera at the LEDs - you should see a faint purple/white glow if they're working (phone cameras can see IR light).

## Troubleshooting

### Radar Not Detected

```bash
# Check if radar is connected
ls /dev/ttyACM* /dev/ttyUSB*

# Test with specific port
openflight --port /dev/ttyACM0 --info
```

### Camera Black Screen

1. Check ribbon cable connection (reseat both ends)
2. Test with `rpicam-hello`
3. Check for power issues: `vcgencmd get_throttled` (should return `0x0`)

### Service Won't Start

```bash
# Check logs for errors
journalctl -u openflight --no-pager -n 50

# If service is masked
sudo systemctl unmask openflight
sudo cp ~/openflight/scripts/openflight.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openflight
```

### Slow UI Updates

If shots take several seconds to appear in the UI, the WebSocket may be unstable. The server uses `async_mode="threading"` which should be stable on Pi 5. If issues persist, check:

```bash
# View server logs
journalctl -u openflight -f
```

Look for "Client disconnected/connected" messages which indicate WebSocket instability.

### Display Issues Over SSH

If you see Qt/display errors when running over SSH:
- Use `DISPLAY=:0` prefix for commands that need the Pi's display
- Or use `--headless` mode for camera calibration

## CLI Reference

### Launch Monitor

```bash
openflight              # Run with auto-detected radar
openflight --port /dev/ttyACM0  # Specify port
openflight --live       # Show live speed readings
openflight --info       # Show radar configuration
```

### Server

```bash
openflight-server                    # Start server with radar
openflight-server --mock             # Mock mode (no radar)
openflight-server --camera           # Enable camera for ball detection
openflight-server --camera-model <path>  # Use custom YOLO model
openflight-server --web-port 3000    # Custom port
```

### Kiosk

```bash
./scripts/start-kiosk.sh              # Production mode (camera enabled by default)
./scripts/start-kiosk.sh --mock       # Mock mode
./scripts/start-kiosk.sh --no-camera  # Disable camera
./scripts/start-kiosk.sh --camera-model models/golf_ball_yolo11n.onnx  # Custom model
```
