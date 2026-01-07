# OpenLaunch Rust Implementation

This directory contains the Rust implementation of OpenLaunch, providing a high-performance alternative to the Python version.

## Why Rust?

The Rust implementation offers significant performance improvements, especially on resource-constrained devices like Raspberry Pi:

| Area               | Python    | Rust      |
| ------------------ | --------- | --------- |
| Sample ingestion   | ~5–10k/s  | 100k+/s   |
| Processing latency | ms spikes | stable μs |
| CPU usage          | High      | Low       |
| Memory usage       | High      | Very low  |

## Building

### Linux/macOS

```bash
# Install Rust if you haven't already
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build the project
cd rust
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
   cd rust
   cargo build --release
   ```

See [../SETUP-WINDOWS.md](../SETUP-WINDOWS.md) for detailed Windows setup instructions.

**Alternative**: Use WSL (Windows Subsystem for Linux) to avoid Windows-specific build tool issues.

## Usage

### With Real Hardware

```bash
cd rust

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
cd rust

# Run in mock mode (auto-generates shots every 20 seconds)
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

See [../TESTING.md](../TESTING.md) for detailed testing guide.

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
rust/src/
├── main.rs           # CLI entry point
├── ops243.rs         # OPS243 radar serial communication
├── launch_monitor.rs # Shot detection and processing
├── shot.rs           # Data structures and metrics calculation
├── mock_radar.rs     # Mock radar for testing
└── opengolfsim.rs    # OpenGolfSim integration
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
- **Smaller binary**: Single executable, no Python runtime

## OpenGolfSim Integration

OpenLaunch can send shot data to OpenGolfSim running on the same PC:

```bash
cd rust

# TCP mode (default)
cargo run --release -- --opengolfsim

# HTTP mode
cargo run --release -- --opengolfsim --opengolfsim-http

# Custom host/port
cargo run --release -- --opengolfsim --opengolfsim-host localhost --opengolfsim-port 8080
```

See [../OPENGOLFSIM-INTEGRATION.md](../OPENGOLFSIM-INTEGRATION.md) for details.

## Development

### Running Tests

```bash
cd rust
cargo test
```

### Code Formatting

```bash
cd rust
cargo fmt
```

### Linting

```bash
cd rust
cargo clippy
```

## Status

**Phase 1: ✅ Complete**

Phase 1 replaces the Python signal loop with a Rust binary that:
- Connects to OPS243-A radar via serial port
- Reads speed readings continuously
- Detects shots (accumulates readings, processes when gap > 0.5s)
- Calculates metrics (ball speed, club speed, smash factor, estimated carry)
- Prints shot metrics to stdout

**Phase 2: Planned**

Phase 2 will add:
- JSON output over stdout
- TCP socket server
- Python bindings (pyo3)

**Phase 3: Future**

Phase 3 will add:
- SIMD optimizations for signal processing
- FFT using rustfft
- Kalman filtering for smoother readings

## Comparison with Python Version

The Rust implementation matches the Python logic as closely as possible:
- All constants and thresholds are identical
- Distance estimation uses the same lookup table
- Club/ball separation uses the same temporal + magnitude analysis

The main differences are:
- **No callbacks**: Direct processing instead of callback-based architecture
- **Synchronous I/O**: Single-threaded loop (can be made async in Phase 2)
- **Simpler error handling**: Uses `anyhow::Result` instead of exceptions
- **No session logging**: Phase 1 focuses on core functionality

