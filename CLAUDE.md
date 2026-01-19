# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenFlight is a DIY golf launch monitor using the OPS243-A Doppler radar. It measures ball speed, estimates carry distance, and optionally tracks launch angle (camera) and spin rate (rolling buffer mode).

## Commands

### Python Backend

```bash
# Run tests
pytest tests/ -v

# Run single test file
pytest tests/test_launch_monitor.py -v

# Run single test
pytest tests/test_launch_monitor.py::TestLaunchMonitor::test_name -v

# Lint (must score 9.0+)
pylint src/openflight/ --fail-under=9

# Format check
ruff check src/openflight/
ruff format --check src/openflight/
```

### React UI (in /ui directory)

```bash
npm run dev      # Development server with hot reload
npm run build    # Production build
npm run lint     # ESLint
```

### Running the Application

```bash
openflight-server           # Web UI with real radar
openflight-server --mock    # Development mode without hardware
openflight                  # CLI-only mode
```

## Architecture

```
React UI (WebSocket) ──► Flask Server ──► LaunchMonitor ──► OPS243Radar
                              │                │
                              │                ├── StreamingSpeedDetector (FFT + CFAR)
                              │                └── Optional: CameraTracker, RollingBufferMonitor
                              │
                              └── SessionLogger (JSONL files)
```

### Data Flow

1. **OPS243Radar** (`ops243.py`) reads continuous I/Q samples via USB serial
2. **StreamingSpeedDetector** (`streaming/processor.py`) processes blocks with FFT and 2D CFAR detection
3. **LaunchMonitor** (`launch_monitor.py`) accumulates `SpeedReading` objects, detects shot completion after 0.5s gap
4. Creates `Shot` object with ball_speed, club_speed, estimated_carry_yards
5. **Flask server** (`server.py`) emits WebSocket "shot" event
6. **React UI** (`ui/src/`) renders shot data

### Key Modules

- `ops243.py` - Radar driver, handles I/Q streaming and configuration
- `launch_monitor.py` - Shot detection logic, separates club/ball speeds
- `streaming/processor.py` - Real-time FFT with CFAR noise rejection
- `streaming/cfar.py` - 2D CFAR detector using convolution
- `rolling_buffer/` - Spin rate estimation via continuous I/Q analysis
- `camera/` - Launch angle detection using YOLO ball tracking
- `session_logger.py` - JSONL logging for post-session analysis

### Processing Modes

1. **I/Q Streaming (default)** - Local FFT processing with CFAR detection, ~13k blocks/sec
2. **Direct Speed** - Uses radar's internal FFT (fallback mode)
3. **Rolling Buffer** - Continuous I/Q buffering for spin rate estimation

## Key Constants

- Sample rate: 30,000 Hz
- FFT window: 128 samples, zero-padded to 4096
- CFAR threshold: SNR > 15.0
- DC mask: 150 bins (~15 mph exclusion zone)
- Shot timeout: 0.5 seconds
- Min ball speed: 35 mph

## Session Logging

Logs written to `~/openflight_sessions/session_*.jsonl` with entry types:
- `session_start`, `session_end` - Session metadata
- `reading_accepted` - Individual radar readings
- `shot_detected` - Detected shots with metrics
- `iq_reading` - I/Q streaming detections with SNR/CFAR data
- `iq_blocks` - Raw I/Q data for post-session analysis
