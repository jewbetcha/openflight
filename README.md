<p align="center">
  <img src="docs/logo2.png" alt="OpenLaunch" width="400">
</p>

<p align="center">
  DIY Golf Launch Monitor using the OPS243-A Doppler Radar.
</p>

## Overview

OpenLaunch is an open-source golf launch monitor that measures ball speed using a commercial Doppler radar sensor. The OPS243-A from OmniPreSense provides professional-grade speed measurement (±0.5% accuracy) in a simple USB-connected package.

### What It Measures

- **Ball Speed**: 30-220 mph range with ±0.5% accuracy
- **Estimated Carry Distance**: Based on ball speed (simplified model)
- **Launch Angle** (optional): With Raspberry Pi camera module

### Hardware

| Component      | Description                | Cost      |
| -------------- | -------------------------- | --------- |
| OPS243-A       | OmniPreSense Doppler Radar | ~$225     |
| Raspberry Pi 5 | (or any computer with USB) | ~$80      |
| USB Cable      | Micro USB to connect radar | ~$5       |
| **Total**      |                            | **~$310** |

See [docs/PARTS.md](docs/PARTS.md) for the full parts list including optional camera module.

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/jewbetcha/openlaunch.git
cd openlaunch

# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .

# For UI support (web interface)
uv pip install -e ".[ui]"
```

### Basic Usage (CLI)

```bash
# Run the launch monitor
openlaunch

# Specify serial port manually
openlaunch --port /dev/ttyACM0

# Show live readings
openlaunch --live

# Show radar info
openlaunch --info
```

### Web UI

```bash
# Build the frontend (first time only)
cd ui && npm install && npm run build && cd ..

# Run the UI server with radar
openlaunch-server

# Run in mock mode (no radar needed, for development)
openlaunch-server --mock
```

Then open http://localhost:8080 in a browser.

For kiosk mode on Raspberry Pi (fullscreen):

```bash
chromium-browser --kiosk http://localhost:8080
```

See [docs/raspberry-pi-setup.md](docs/raspberry-pi-setup.md) for complete Raspberry Pi setup instructions including auto-start and camera configuration.

### Python API

```python
from openlaunch import LaunchMonitor

# Simple usage
with LaunchMonitor() as monitor:
    print("Swing when ready...")
    shot = monitor.wait_for_shot(timeout=60)

    if shot:
        print(f"Ball Speed: {shot.ball_speed_mph:.1f} mph")
        print(f"Est. Carry: {shot.estimated_carry_yards:.0f} yards")
```

```python
# Continuous monitoring with callbacks
from openlaunch import LaunchMonitor

def on_shot(shot):
    print(f"Shot detected: {shot.ball_speed_mph:.1f} mph")

monitor = LaunchMonitor()
monitor.connect()
monitor.start(shot_callback=on_shot)

# ... do other things ...

stats = monitor.get_session_stats()
print(f"Average ball speed: {stats['avg_ball_speed']:.1f} mph")
```

### Low-Level Radar Access

```python
from openlaunch import OPS243Radar

# Direct radar control
with OPS243Radar() as radar:
    # Get radar info
    info = radar.get_info()
    print(f"Firmware: {info.get('Version')}")

    # Configure for golf
    radar.configure_for_golf()

    # Read speeds
    while True:
        reading = radar.read_speed()
        if reading:
            print(f"{reading.speed:.1f} {reading.unit}")
```

## Setup Guide

### 1. Connect the Radar

Connect the OPS243-A to your computer via USB. The radar will appear as a serial device:

- **Linux/Raspberry Pi**: `/dev/ttyACM0` or `/dev/ttyUSB0`
- **macOS**: `/dev/tty.usbmodem*`
- **Windows**: `COM3` (or similar)

### 2. Position the Radar

For best results, position the radar **3-5 feet behind the tee**, pointing at the hitting area. The radar has a 23° beam width.

```
                    Ball Flight Direction
                    ======================>

    [Tee]  ←--- 3-5 ft ---→  [OPS243-A Radar]
                                   ↓
                            Points at ball
```

**Important**: The radar measures radial velocity (speed toward/away from sensor). For accurate readings, the ball should travel roughly along the radar's line of sight.

### 3. Run the Monitor

```bash
openlaunch
```

The system will automatically detect the radar, configure it for golf ball detection, and start monitoring.

## How It Works

### Doppler Radar Basics

The OPS243-A transmits a 24 GHz signal. When this signal bounces off a moving object (the golf ball), the frequency shifts proportionally to the object's speed - this is the Doppler effect.

The relationship is:

```
Speed = (Doppler_Frequency × c) / (2 × Transmit_Frequency)
```

At 24.125 GHz, each 1 mph of speed creates a ~71.7 Hz Doppler shift.

### Golf Ball Detection

Golf balls are challenging targets for radar due to:

- **Small size**: ~1.68" diameter
- **Low RCS**: Radar cross-section of ~0.001 m²
- **High speed**: 100-180+ mph for well-struck shots
- **Brief detection window**: Ball is in range for < 100ms

The OPS243-A handles this with:

- High transmit power (11 dBm typical)
- 15 dBi antenna gain
- 24 GHz frequency (short wavelength suits small objects)
- Fast sampling (up to 100k samples/sec)

Based on link budget analysis, the OPS243-A should reliably detect golf balls at **4-5 meters (13-16 feet)**, making the 3-5 foot positioning ideal.

### System Architecture

The data flows from radar to UI like this:

```
┌─────────────┐  USB/Serial  ┌─────────────┐  Callback   ┌─────────────┐  WebSocket  ┌─────────────┐
│  OPS243-A   │ ───────────▶ │   Launch    │ ──────────▶ │   Flask     │ ──────────▶ │   React     │
│   Radar     │  Speed data  │   Monitor   │  on_shot()  │   Server    │   "shot"    │     UI      │
└─────────────┘              └─────────────┘             └─────────────┘             └─────────────┘
```

1. **Radar streams data** - The OPS243-A continuously sends speed readings over USB serial whenever it detects motion

2. **LaunchMonitor processes readings** - A background thread reads serial data, accumulates readings, and when there's a gap (no readings for 0.5s), analyzes the data to create a `Shot` object with ball speed, club speed, and smash factor

3. **Callback fires** - When a shot is detected, the callback function registered via `monitor.start(shot_callback=...)` is called with the `Shot` object

4. **Server broadcasts to clients** - The Flask server's callback converts the shot to JSON and emits it to all connected browsers via WebSocket

5. **React updates UI** - The `useSocket` hook receives the event and updates state, triggering a re-render with the new shot data

This callback pattern keeps the components decoupled - `LaunchMonitor` doesn't know about Flask or WebSockets, it just calls whatever function you give it.

## Configuration

The radar can be configured via API commands:

```python
from openlaunch import OPS243Radar, SpeedUnit, Direction

radar = OPS243Radar()
radar.connect()

# Set units to MPH
radar.set_units(SpeedUnit.MPH)

# Increase sample rate for faster balls (up to 139 mph at 20kHz)
radar.set_sample_rate(20000)

# Filter out slow movements
radar.set_min_speed_filter(20)  # Ignore < 20 mph

# Only detect outbound (ball going away)
radar.set_direction_filter(Direction.OUTBOUND)

# Save to persistent memory
radar.save_config()
```

### Key Settings for Golf

| Setting     | Value    | Why                         |
| ----------- | -------- | --------------------------- |
| Sample Rate | 20 kHz   | Supports up to ~139 mph     |
| Buffer Size | 512      | Faster updates (~10-15 Hz)  |
| Min Speed   | 10 mph   | Filter slow movements       |
| Direction   | Outbound | Ball moving away from radar |
| Power       | Max (0)  | Best detection range        |

## Limitations

### What OpenLaunch Does NOT Measure (Yet)

- **Spin Rate**: Requires high-speed camera
- **Club Speed**: Could be added with timing/positioning changes
- **Side Spin / Curve**: Requires multiple sensors or camera

Note: **Launch Angle** is available with the optional camera module. See [Camera Setup](#camera-calibration).

### Accuracy Considerations

- **Distance estimates are rough**: Without launch angle and spin, carry distance is estimated using a simplified model (~2.5 yards per mph of ball speed)
- **Cosine error**: If ball doesn't travel directly toward/away from radar, measured speed will be slightly lower than actual
- **Detection is probabilistic**: Very fast shots with weak returns may be missed

## Troubleshooting

### "No OPS243 radar found"

1. Check USB connection
2. Try a different USB cable
3. Check if device appears: `ls /dev/tty*` (Linux/Mac)
4. Try specifying port manually: `openlaunch --port /dev/ttyACM0`

### Weak or No Detection

1. Move radar closer to hitting area (try 3 feet)
2. Ensure radar is pointing at ball flight path
3. Check for obstructions
4. Try increasing transmit power: `radar.set_transmit_power(0)`

### Erratic Readings

1. Increase minimum speed filter to reduce noise
2. Increase magnitude filter to require stronger signals
3. Ensure stable mounting (vibration causes false readings)

## Project Structure

```
openlaunch/
├── src/openlaunch/
│   ├── __init__.py
│   ├── ops243.py          # OPS243-A radar driver
│   ├── launch_monitor.py  # Main launch monitor
│   ├── server.py          # WebSocket server for UI
│   └── camera_tracker.py  # YOLO ball tracking
├── ui/                    # React frontend
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── hooks/         # Custom hooks (WebSocket)
│   │   └── App.tsx        # Main app
│   └── package.json
├── scripts/               # Utility scripts
├── models/                # YOLO models for ball detection
├── docs/                  # Documentation
├── archive/               # Previous CDM324 approach (reference)
├── pyproject.toml
└── README.md
```

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas of interest:

- **Better distance models**: Improve carry estimates with more physics
- **Club detection**: Detect club head speed
- **Spin detection**: Add high-speed camera for spin rate
- **Mobile app**: Bluetooth connection to phone
- **Hardware acceleration**: Optimize YOLO for Hailo/Coral accelerators

### Camera Calibration

If you have the optional camera module for launch angle detection, first install the camera dependencies:

```bash
# Install camera support (OpenCV, NumPy, picamera2)
uv pip install -e ".[camera]"
```

Then use the calibration script to tune detection settings:

```bash
# Live view with ball detection overlay
python scripts/calibrate_camera.py

# Without detection overlay (just camera feed)
python scripts/calibrate_camera.py --no-detect

# Mock mode (no camera hardware, uses synthetic frames)
python scripts/calibrate_camera.py --mock

# Adjust camera settings
python scripts/calibrate_camera.py --exposure 2000 --gain 4.0 --threshold 200
```

**Keyboard controls during calibration:**
| Key | Action |
|-----|--------|
| `q` | Quit |
| `s` | Save current frame |
| `t` | Toggle threshold view |
| `d` | Toggle detection overlay |
| `+`/`-` | Adjust brightness threshold |
| `[`/`]` | Adjust minimum radius |
| `{`/`}` | Adjust maximum radius |

The script will display final settings when you exit - use these values to configure `DetectorConfig` in your code.

For YOLO model optimization and FPS tuning, see [docs/yolo-performance-tuning.md](docs/yolo-performance-tuning.md).

### Running Tests

```bash
# Install dev dependencies
uv pip install -e ".[ui]"
uv pip install pytest

# Run tests
pytest tests/ -v
```

### Contributing Guidelines

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines. Quick summary:

- **Tests required**: Run `pytest tests/ -v` before submitting a PR
- **Code quality**: Run `pylint src/openlaunch/` (score 9+)
- **UI changes**: Run `cd ui && npm run build` to verify

## Documentation

- [Raspberry Pi Setup Guide](docs/raspberry-pi-setup.md) - Complete Pi 5 setup with touchscreen and camera
- [Parts List](docs/PARTS.md) - Full hardware requirements
- [YOLO Performance Tuning](docs/yolo-performance-tuning.md) - Optimize ball detection FPS
- [Contributing Guide](CONTRIBUTING.md) - How to contribute
- [Changelog](docs/CHANGELOG.md) - Version history

## License

MIT License - see LICENSE file.

## Acknowledgments

- [OmniPreSense](https://omnipresense.com/) for the OPS243-A radar and documentation
- The golf hacker community for inspiration
