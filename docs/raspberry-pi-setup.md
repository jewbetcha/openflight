# Raspberry Pi Setup Guide

Complete guide for setting up OpenLaunch on a Raspberry Pi 5 with the 7" touchscreen display.

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

### 2. Clone the Repository

```bash
cd ~
git clone https://github.com/yourusername/openlaunch.git
cd openlaunch
```

### 3. Create Virtual Environment

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv with system site packages (needed for picamera2)
python -m venv .venv --system-site-packages
source .venv/bin/activate

# Install dependencies
uv pip install -e ".[ui]"
```

### 4. Build the UI

```bash
cd ui
npm install
npm run build
cd ..
```

## Running OpenLaunch

### Manual Start

```bash
# With radar connected
openlaunch-server

# Mock mode (no radar needed)
openlaunch-server --mock
```

Then open `http://localhost:8080` in a browser.

### Kiosk Mode (Fullscreen)

```bash
./scripts/start-kiosk.sh
```

This starts the server and launches Chromium in fullscreen kiosk mode.

Options:
```bash
# Mock mode
./scripts/start-kiosk.sh --mock

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
sudo cp ~/openlaunch/scripts/openlaunch.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start
sudo systemctl enable openlaunch

# Start it now
sudo systemctl start openlaunch
```

### Service Management

```bash
# Check status
sudo systemctl status openlaunch --no-pager

# View logs
journalctl -u openlaunch -f

# Stop the service
sudo systemctl stop openlaunch

# Restart the service
sudo systemctl restart openlaunch

# Disable auto-start
sudo systemctl disable openlaunch
```

### Editing the Service

The service file is located at `/etc/systemd/system/openlaunch.service`.

If you need to modify it:
```bash
sudo nano /etc/systemd/system/openlaunch.service
sudo systemctl daemon-reload
sudo systemctl restart openlaunch
```

## Camera Setup (Optional)

For launch angle detection with the Raspberry Pi HQ Camera.

### Install Camera Dependencies

```bash
# Install system library for picamera2
sudo apt install libcap-dev

# Install Python packages
uv pip install -e ".[camera]"
```

### Test the Camera

```bash
# Check if camera is detected
rpicam-hello --list-cameras

# Quick preview test
rpicam-hello
```

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
openlaunch --port /dev/ttyACM0 --info
```

### Camera Black Screen

1. Check ribbon cable connection (reseat both ends)
2. Test with `rpicam-hello`
3. Check for power issues: `vcgencmd get_throttled` (should return `0x0`)

### Service Won't Start

```bash
# Check logs for errors
journalctl -u openlaunch --no-pager -n 50

# If service is masked
sudo systemctl unmask openlaunch
sudo cp ~/openlaunch/scripts/openlaunch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openlaunch
```

### Slow UI Updates

If shots take several seconds to appear in the UI, the WebSocket may be unstable. The server uses `async_mode="threading"` which should be stable on Pi 5. If issues persist, check:

```bash
# View server logs
journalctl -u openlaunch -f
```

Look for "Client disconnected/connected" messages which indicate WebSocket instability.

### Display Issues Over SSH

If you see Qt/display errors when running over SSH:
- Use `DISPLAY=:0` prefix for commands that need the Pi's display
- Or use `--headless` mode for camera calibration

## CLI Reference

### Launch Monitor

```bash
openlaunch              # Run with auto-detected radar
openlaunch --port /dev/ttyACM0  # Specify port
openlaunch --live       # Show live speed readings
openlaunch --info       # Show radar configuration
```

### Server

```bash
openlaunch-server           # Start server with radar
openlaunch-server --mock    # Mock mode (no radar)
openlaunch-server --web-port 3000  # Custom port
```

### Kiosk

```bash
./scripts/start-kiosk.sh        # Production mode
./scripts/start-kiosk.sh --mock # Mock mode
```
