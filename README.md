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

OpenLaunch is available in two implementations:

- **Python** (default): Full-featured with web UI, camera support, and session logging
- **Rust** (optional): High-performance CLI implementation for resource-constrained devices

### Python Implementation (Recommended)

The Python implementation is the primary version with the most features:

```bash
# Clone the repository
git clone https://github.com/jewbetcha/openlaunch.git
cd openlaunch

# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[ui]"

# Run the web UI server
openlaunch-server
```

Then open http://localhost:8080 in a browser.

For detailed Python setup instructions, see [README-Python.md](README-Python.md).

### Rust Implementation (Optional)

The Rust implementation provides significantly better performance on resource-constrained devices like Raspberry Pi:

#### Linux/macOS

```bash
# Install Rust if you haven't already
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build the project
cd rust
cargo build --release

# Run (auto-detect radar port)
cargo run --release

# Specify port manually
cargo run --release -- --port /dev/ttyACM0

# Show live readings
cargo run --release -- --live

# Mock mode (no hardware needed, for testing)
cargo run --release -- --mock
```

#### Windows

**Important**: You need both Rust AND a C compiler (for native dependencies).

1. **Install Rust**: Download and run [rustup-init.exe](https://rustup.rs/)
2. **Install C++ Build Tools**: Download [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
   - Select "C++ build tools" workload during installation
3. **Restart your terminal** after both installations
4. **Build**:
   ```powershell
   cd rust
   cargo build --release
   ```

See [rust/README.md](rust/README.md) for detailed setup instructions and [SETUP-WINDOWS.md](SETUP-WINDOWS.md) for Windows-specific guidance.

#### Performance Benefits

The Rust implementation offers significant performance improvements:

| Area               | Python    | Rust      |
| ------------------ | --------- | --------- |
| Sample ingestion   | ~5–10k/s  | 100k+/s   |
| Processing latency | ms spikes | stable μs |
| CPU usage          | High      | Low       |
| Memory usage       | High      | Very low  |

#### OpenGolfSim Integration

The Rust implementation can send shot data to OpenGolfSim:

```bash
# TCP mode (default)
cargo run --release -- --opengolfsim

# HTTP mode
cargo run --release -- --opengolfsim --opengolfsim-http

# Custom host/port
cargo run --release -- --opengolfsim --opengolfsim-host localhost --opengolfsim-port 8080
```

For detailed Rust setup instructions and all available options, see [rust/README.md](rust/README.md).

## Choosing an Implementation

| Feature | Python | Rust |
|---------|--------|------|
| **Web UI** | ✅ Yes | ❌ No (CLI only) |
| **Camera Support** | ✅ Yes | ❌ No |
| **Session Logging** | ✅ Yes | ❌ No |
| **Performance** | Good | **Excellent** |
| **Sample Rate** | ~5–10k/s | **100k+/s (10–20x faster)** |
| **Processing Latency** | ms spikes | **stable μs (1000x lower)** |
| **CPU Usage** | Moderate | **Low (~50% reduction)** |
| **Memory Usage** | Moderate | **Very Low (~70% reduction)** |
| **Ease of Setup** | Easy | Requires Rust toolchain |
| **Best For** | Most users | Raspberry Pi, embedded systems |

**Recommendation**: Start with Python unless you need the performance benefits of Rust or are targeting resource-constrained hardware. The Rust implementation is ideal for:
- Raspberry Pi deployments where CPU/memory are limited
- Embedded systems
- High-frequency shot detection scenarios
- Applications requiring minimal resource footprint

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

## Project Structure

```
openlaunch/
├── src/openlaunch/       # Python package (main implementation)
│   ├── ops243.py         # OPS243-A radar driver
│   ├── launch_monitor.py # Main launch monitor
│   ├── server.py         # WebSocket server for UI
│   └── camera_tracker.py # YOLO ball tracking
├── rust/                 # Rust implementation (optional)
│   ├── src/              # Rust source code
│   │   ├── main.rs           # CLI entry point
│   │   ├── ops243.rs         # OPS243 radar serial communication
│   │   ├── launch_monitor.rs # Shot detection and processing
│   │   ├── shot.rs           # Data structures and metrics calculation
│   │   ├── mock_radar.rs     # Mock radar for testing
│   │   └── opengolfsim.rs    # OpenGolfSim integration
│   ├── Cargo.toml        # Rust package configuration
│   └── README.md         # Rust-specific documentation
├── ui/                   # React frontend
│   └── src/
│       ├── components/   # React components
│       └── hooks/        # Custom hooks (WebSocket)
├── scripts/              # Utility scripts
├── models/               # YOLO models for ball detection
├── docs/                 # Documentation
├── pyproject.toml        # Python package config
└── README.md             # This file
```

## Documentation

- **[Python Implementation Guide](README-Python.md)** - Complete Python setup and usage
- **[Rust Implementation Guide](rust/README.md)** - Rust setup and usage
- **[Raspberry Pi Setup](docs/raspberry-pi-setup.md)** - Complete Pi 5 setup with touchscreen and camera
- **[Parts List](docs/PARTS.md)** - Full hardware requirements
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute
- **[Testing Guide](TESTING.md)** - Testing without hardware
- **[OpenGolfSim Integration](OPENGOLFSIM-INTEGRATION.md)** - Integration with OpenGolfSim
- **[Changelog](docs/CHANGELOG.md)** - Version history

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas of interest:

- **Better distance models**: Improve carry estimates with more physics
- **Club detection**: Detect club head speed
- **Spin detection**: Add high-speed camera for spin rate
- **Mobile app**: Bluetooth connection to phone
- **Hardware acceleration**: Optimize YOLO for Hailo/Coral accelerators
- **Rust improvements**: Add web UI, camera support, session logging

## License

MIT License - see LICENSE file.

## Acknowledgments

- [OmniPreSense](https://omnipresense.com/) for the OPS243-A radar and documentation
- The golf hacker community for inspiration
