# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Camera integration with real-time ball detection in UI
- Ball detection indicator in header (shows detection status)
- Camera tab with live MJPEG stream and detection overlay
- YOLO performance tuning documentation for Raspberry Pi
- ONNX model export support for faster inference
- Threaded camera capture for improved FPS

### Changed
- Camera enabled by default in kiosk mode (use `--no-camera` to disable)
- Updated Raspberry Pi setup guide with camera UI instructions

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
- YOLO-based ball tracking
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

[Unreleased]: https://github.com/jewbetcha/openlaunch/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jewbetcha/openlaunch/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jewbetcha/openlaunch/releases/tag/v0.1.0
