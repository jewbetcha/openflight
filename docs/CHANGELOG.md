# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Optional second K-LD7 connector for dual-radar setups
  - `--kld7-secondary-port` and `--kld7-secondary-orientation` server flags
  - `start-kiosk.sh` support for wiring a second K-LD7 without changing the single-radar flow
- K-LD7 shot-correlation analysis workflow and theory writeup
  - `scripts/analyze_kld7.py --pair-shots` for offline club-to-ball pairing on `.pkl` captures
  - `docs/kld7-ball-detection-theory.md` with capture findings and detection rationale
- Persistent rolling buffer mode workaround for OPS243-A HOST_INT pin bug (per OmniPreSense)
  - `persist_rolling_buffer_mode()` method saves settings to flash memory
  - `test_rolling_buffer_persist.py` script for one-time radar setup and verification
  - Rolling buffer + sound trigger is now the default operating mode
- Grafana Alloy integration for shipping session logs to Grafana Cloud Loki
  - Setup script (`scripts/setup_alloy.sh`) and config (`config/alloy.alloy`)
  - Auto-starts with `start-kiosk.sh` when credentials are configured
  - Observability documentation with LogQL query examples
- Launch angle estimation from club type and ball speed (fallback when camera unavailable)
- Tunable Hough circle detection with all 5 parameters as CLI args (`--hough-param1`, `--hough-param2`, `--hough-min-radius`, `--hough-max-radius`, `--hough-min-dist`)
- Interactive `--tune` mode in `test_launch_angle.py` with live OpenCV trackbar sliders
- Mock mode now simulates realistic spin and launch angle data (TrackMan-based per-club averages)
- Sound trigger wiring guide with MOSFET circuit design (`docs/sound-trigger-wiring.md`)
- Camera integration with real-time ball detection in UI
- Ball detection indicator in header (shows detection status)
- Camera tab with live MJPEG stream and detection overlay
- Hough circle transform as default ball detector (replaces YOLO dependency)
- ByteTrack object tracking for persistent ball identification
- Club speed detection and smash factor calculation
- Rolling buffer mode for experimental spin rate detection
- Session logging to JSONL files (`~/openflight_sessions/`)
- I/Q streaming mode with FFT and 2D CFAR noise rejection
- `--mode rolling-buffer` flag for spin detection
- `--session-location` and `--log-dir` flags for session logging
- Roboflow API integration as optional detection backend
- YOLO performance tuning documentation for Raspberry Pi
- ONNX model export support for faster inference
- Threaded camera capture for improved FPS
- Rolling buffer spin detection documentation

### Changed
- K-LD7 launch-angle processing now uses OPS243 impact timestamps for live correlation
- K-LD7 ball-burst selection now prefers coherent far-target paths instead of averaging all far PDAT detections
- Live K-LD7 vertical launch angles now fall back to the existing club-and-speed estimate when the radar result is an obvious false positive
- Spin detection improved: Hann windowing, zero-padding to 256 points, band-limited search
- All shot metrics (spin, launch angle, club speed, carry) always shown in UI
- Shot logging unified — all metrics in single `shot_detected` entry
- Shot `mode` and `readings_data` are now proper dataclass fields (no more monkey-patching)
- Session logging enabled in mock mode for testing Alloy integration
- Default ball detection uses Hough circles instead of YOLO (no ML model required)
- Camera enabled by default in kiosk mode (use `--no-camera` to disable)
- Dropped Python 3.9 support (requires >=3.10)
- Updated Raspberry Pi setup guide with camera UI and observability instructions

## [0.2.0] - 2024-12-01

### Added
- Web UI with React frontend and Flask-SocketIO backend
- Real-time shot display with ball speed, carry distance, smash factor
- Session statistics view with per-club filtering
- Shot history with pagination
- Debug panel for radar tuning and raw readings
- Mock mode for development without hardware
- Kiosk mode script for Raspberry Pi deployment
- Systemd service for auto-start on boot
- Camera module for launch angle detection (experimental)
- Camera-based ball tracking for launch angle
- Club type selection (Driver through PW)

### Changed
- Migrated from CDM324/HB100 radar to OPS243-A
- Improved carry distance estimation model

## [0.1.0] - 2024-10-01

### Added
- Initial OPS243-A radar driver
- Basic launch monitor with shot detection
- CLI interface for monitoring shots
- Python API for integration
- Carry distance estimation based on ball speed

[Unreleased]: https://github.com/jewbetcha/openflight/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jewbetcha/openflight/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jewbetcha/openflight/releases/tag/v0.1.0
