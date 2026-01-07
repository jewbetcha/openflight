# Rust Migration Guide

This document tracks the migration of OpenLaunch from Python to Rust.

## Phase 1: ✅ Complete

**Goal**: Replace Python signal loop with Rust binary that prints shot metrics to stdout.

### Implementation Status

- [x] Rust project structure (`Cargo.toml`, `src/`)
- [x] OPS243 radar serial communication (`src/ops243.rs`)
- [x] Speed reading parsing and data structures (`src/shot.rs`)
- [x] Shot detection and processing logic (`src/launch_monitor.rs`)
- [x] Distance estimation and metrics calculation
- [x] Main binary with CLI (`src/main.rs`)
- [x] Ctrl+C handling for graceful shutdown

### Key Features

1. **Serial Communication**: Direct serial port access using `serialport` crate
2. **JSON Parsing**: Parses radar JSON output (multi-object mode supported)
3. **Shot Detection**: Accumulates readings, detects shots on 0.5s timeout
4. **Club/Ball Separation**: Temporal + magnitude analysis to separate club from ball
5. **Metrics**: Calculates smash factor, estimated carry distance
6. **Output**: Prints formatted shot metrics to stdout

### Usage

```bash
# Build
cargo build --release

# Run (auto-detect port)
cargo run --release

# Run with options
cargo run --release -- --port /dev/ttyACM0 --live
```

### Architecture

```
src/
├── main.rs           # CLI entry point, argument parsing
├── ops243.rs         # OPS243 radar driver (serial I/O, configuration)
├── launch_monitor.rs # Shot detection loop, processing logic
└── shot.rs           # Data structures, distance estimation
```

### Differences from Python Version

1. **No callbacks**: Direct processing instead of callback-based architecture
2. **Synchronous I/O**: Single-threaded loop (can be made async in Phase 2)
3. **Simpler error handling**: Uses `anyhow::Result` instead of exceptions
4. **No session logging**: Phase 1 focuses on core functionality

### Performance Improvements

- **Lower latency**: Direct serial I/O without Python GIL
- **Lower CPU usage**: More efficient memory management
- **Better real-time**: No garbage collection pauses
- **Smaller binary**: Single executable, no Python runtime

## Phase 2: Planned

**Goal**: Expose Rust functionality via multiple interfaces.

### Planned Features

1. **JSON over stdout**: Add `--json` flag to output structured JSON
2. **TCP socket server**: Listen on port, send shot data to connected clients
3. **Python bindings (pyo3)**: Create Python module that wraps Rust code

### Implementation Plan

- [ ] Add JSON output mode to `main.rs`
- [ ] Create TCP server module (`src/server.rs`)
- [ ] Create pyo3 bindings crate (`openlaunch-py/`)
- [ ] Add configuration for server port, JSON format options
- [ ] Update Python code to optionally use Rust backend

## Phase 3: Future

**Goal**: Advanced optimizations for signal processing.

### Planned Features

1. **SIMD optimizations**: Use `packed_simd` or `std::arch` for vectorized operations
2. **FFT processing**: Use `rustfft` for frequency domain analysis
3. **Kalman filtering**: Implement Kalman filter for smoother readings

### Implementation Plan

- [ ] Profile current implementation to identify bottlenecks
- [ ] Add SIMD-optimized reading accumulation
- [ ] Implement FFT-based signal analysis
- [ ] Add Kalman filter for speed estimation
- [ ] Benchmark improvements

## Testing

To test the Rust implementation:

```bash
# Unit tests
cargo test

# Integration test (requires radar hardware)
cargo run --release -- --port /dev/ttyACM0
```

## Migration Strategy

1. **Phase 1**: Rust binary runs alongside Python (for comparison)
2. **Phase 2**: Python code can optionally use Rust backend via bindings
3. **Phase 3**: Optimize Rust implementation, deprecate Python version

## Notes

- The Rust implementation matches the Python logic as closely as possible
- All constants and thresholds are identical to Python version
- Distance estimation uses the same lookup table
- Club/ball separation uses the same temporal + magnitude analysis

