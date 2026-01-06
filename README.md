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


# OpenLaunch Rust Implementation

This is the Rust implementation of the OpenLaunch golf launch monitor, providing a faster alternative to the Python version.

| Language | Relative Speed                                      |
| -------- | --------------------------------------------------- |
| **C++**  | 🚀 Fastest ([jinaldesai.com][1])                    |
| **Rust** | ⚡ Near C++ (safe) ([president-xd][2])               |
| **Go**   | 🐎 Moderate ([jinaldesai.com][1])                   |
| **Lua**  | 🐢 Slowest (interpreted) ([gdt050579.github.io][3]) |

[1]: https://jinaldesai.com/performance-comparison-of-python-golang-rust-and-c/?utm_source=chatgpt.com "Performance Comparison of Python, Golang, Rust, and C++ – Jinal Desai"
[2]: https://www.president-xd.com/blog/rust_vs_other_languages?utm_source=chatgpt.com "Rust vs Other Programming Languages: A Comprehensive Comparison 🦀 | president-xd"
[3]: https://gdt050579.github.io/poo_course_fii/courses/cpp_to_rust.pdf?utm_source=chatgpt.com "From C++ to Rust"


Using this, we decide to go with Rust. 
| Area               | Python    | Rust      |
| ------------------ | --------- | --------- |
| Sample ingestion   | ~5–10k/s  | 100k+/s   |
| Processing latency | ms spikes | stable μs |
| CPU usage          | High      | Low       |
| Memory usage       | High      | Very low  |

On a Raspberry Pi, this is night and day.

## Phase 1 Status: ✅ Complete

Phase 1 replaces the Python signal loop with a Rust binary that:
- Connects to OPS243-A radar via serial port
- Reads speed readings continuously
- Detects shots (accumulates readings, processes when gap > 0.5s)
- Calculates metrics (ball speed, club speed, smash factor, estimated carry)
- Prints shot metrics to stdout

## Building

### Linux/macOS

```bash
# Install Rust if you haven't already
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build the project
cargo build --release

# Run
cargo run --release -- --help
```

### Windows

**Important**: You need both Rust AND a C compiler (for native dependencies).

1. **Install Rust**: Download and run [rustup-init.exe](https://rustup.rs/)

2. **Install C++ Build Tools**: Download [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
   - Select "C++ build tools" workload during installation

3. **Restart your terminal** after both installations

4. **Build**:
   ```powershell
   cargo build --release
   ```

See [SETUP-WINDOWS.md](SETUP-WINDOWS.md) for detailed Windows setup instructions.

**Alternative**: Use WSL (Windows Subsystem for Linux) to avoid Windows-specific build tool issues.

## Usage

### With Real Hardware

```bash
# Auto-detect radar port
cargo run --release

# Specify port manually
cargo run --release -- --port /dev/ttyACM0

# Show live readings
cargo run --release -- --live

# Show radar info and exit
cargo run --release -- --info
```

### Testing Without Hardware (Mock Mode)

```bash
# Run in mock mode (auto-generates shots every 5 seconds)
cargo run --release -- --mock

# Custom shot interval (e.g., every 3 seconds)
cargo run --release -- --mock --mock-interval 3.0

# Show live readings in mock mode
cargo run --release -- --mock --live

# Show mock radar info
cargo run --release -- --mock --info
```

The mock radar simulates realistic golf shots with:
- Club readings (60-120 mph, higher magnitude)
- Ball readings (80-180 mph, lower magnitude)
- Realistic timing and smash factors
- Automatic shot generation at configurable intervals

See [TESTING.md](TESTING.md) for detailed testing guide.

## Example Output

```
==================================================
  OpenLaunch - Golf Launch Monitor (Rust)
  Using OPS243-A Doppler Radar
==================================================

Connected to: OPS243
Firmware: 1.2.3

Ready! Swing when ready...
Press Ctrl+C to stop

----------------------------------------
  Club Speed:   95.2 mph
  Ball Speed:   142.3 mph
  Smash Factor: 1.50
  Est. Carry:   234 yards
  Range:        211-257 yards
  Signal:       1250
----------------------------------------
```

## Architecture

```
src/
├── main.rs           # CLI entry point
├── ops243.rs         # OPS243 radar serial communication
├── launch_monitor.rs # Shot detection and processing
└── shot.rs           # Data structures and metrics calculation
```

### Key Components

1. **OPS243Radar** (`ops243.rs`)
   - Serial port communication
   - Radar configuration (sample rate, units, filters)
   - JSON parsing of speed readings
   - Direction detection (inbound/outbound from sign)

2. **LaunchMonitor** (`launch_monitor.rs`)
   - Continuous reading loop
   - Shot detection (0.5s timeout between readings)
   - Club/ball separation (temporal + magnitude analysis)
   - Metrics calculation

3. **Shot** (`shot.rs`)
   - Data structures for readings and shots
   - Distance estimation (TrackMan-derived lookup table)
   - Smash factor calculation

## Performance

The Rust implementation provides:
- **Lower latency**: Direct serial I/O without Python GIL
- **Lower CPU usage**: More efficient memory management
- **Better real-time performance**: No garbage collection pauses

## OpenGolfSim Integration

OpenLaunch can send shot data to OpenGolfSim running on the same PC:

```bash
# TCP mode (default)
cargo run --release -- --opengolfsim

# HTTP mode
cargo run --release -- --opengolfsim --opengolfsim-http

# Custom host/port
cargo run --release -- --opengolfsim --opengolfsim-host localhost --opengolfsim-port 8080
```

See [OPENGOLFSIM-INTEGRATION.md](OPENGOLFSIM-INTEGRATION.md) for details.

## Next Steps (Phase 2)

Phase 2 will add:
- JSON output over stdout
- TCP socket server
- Python bindings (pyo3)

## Next Steps (Phase 3)

Phase 3 will add:
- SIMD optimizations for signal processing
- FFT using rustfft
- Kalman filtering for smoother readings

