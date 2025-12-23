# Contributing to OpenLaunch

Thank you for your interest in contributing to OpenLaunch! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Node.js 20+ (for UI development)
- Git
- [uv](https://github.com/astral-sh/uv) package manager (recommended)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/jewbetcha/openlaunch.git
   cd openlaunch
   ```

2. **Create a virtual environment**
   ```bash
   # Using uv (recommended)
   uv venv
   source .venv/bin/activate

   # Or using standard venv
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   # Core + UI + camera + dev dependencies
   uv pip install -e ".[ui,camera]"
   uv pip install pytest pylint ruff

   # Or with pip
   pip install -e ".[ui,camera]"
   pip install pytest pylint ruff
   ```

4. **Build the UI** (for frontend development)
   ```bash
   cd ui
   npm install
   npm run dev  # Development server with hot reload
   ```

### Running in Development

```bash
# Run server in mock mode (no hardware needed)
openlaunch-server --mock

# Run with debug logging
openlaunch-server --mock --debug

# Run UI development server (separate terminal)
cd ui && npm run dev
```

## Code Quality Standards

### Python

We use **pylint** for linting with a minimum score of **9.0**.

```bash
# Check code quality
pylint src/openlaunch/

# Auto-format with ruff
ruff format src/
ruff check --fix src/
```

### TypeScript/React

```bash
cd ui
npm run lint      # ESLint
npm run build     # Type check + build
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_launch_monitor.py -v

# Run with coverage (if pytest-cov installed)
pytest tests/ --cov=src/openlaunch --cov-report=html
```

**All tests must pass before submitting a PR.**

## Submitting Changes

### Pull Request Process

1. **Fork the repository** and create a feature branch
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** with clear, focused commits

3. **Ensure quality checks pass**
   ```bash
   pytest tests/ -v
   pylint src/openlaunch/
   cd ui && npm run build
   ```

4. **Update documentation** if needed
   - Update README.md for user-facing changes
   - Update relevant docs in `docs/`
   - Add entry to CHANGELOG.md under `[Unreleased]`

5. **Submit a pull request** with:
   - Clear title describing the change
   - Description of what changed and why
   - Reference to any related issues

### Commit Messages

Use clear, descriptive commit messages:

```
Add ball detection indicator to UI header

- Create BallDetectionIndicator component
- Add camera status to useSocket hook
- Update App.tsx to display indicator
```

### What We're Looking For

**High-priority contributions:**
- Bug fixes with tests
- Documentation improvements
- Performance optimizations
- Test coverage improvements

**Feature ideas:**
- Launch angle detection improvements
- Better carry distance models
- Mobile app / Bluetooth support
- Integration with golf simulation software

## Project Structure

```
openlaunch/
├── src/openlaunch/       # Python package
│   ├── ops243.py         # Radar driver
│   ├── launch_monitor.py # Shot detection
│   ├── server.py         # WebSocket server
│   └── camera_tracker.py # Ball tracking
├── ui/                   # React frontend
│   └── src/
│       ├── components/   # UI components
│       └── hooks/        # React hooks
├── tests/                # Test suite
├── scripts/              # Utility scripts
├── models/               # ML models
└── docs/                 # Documentation
```

## Testing Without Hardware

OpenLaunch supports **mock mode** for development without radar/camera:

```bash
# Server with simulated shots
openlaunch-server --mock

# Camera calibration with synthetic frames
python scripts/calibrate_camera.py --mock
```

The `MockLaunchMonitor` class simulates realistic shot data based on TrackMan averages.

## Questions?

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Be respectful and constructive in discussions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
