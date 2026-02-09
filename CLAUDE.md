# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenFlight is a DIY golf launch monitor using the OPS243-A Doppler radar. It measures ball speed, estimates carry distance, and optionally tracks launch angle (camera) and spin rate (rolling buffer mode).

## Development Rules

- **Always use `uv` for Python commands.** Use `uv run` to execute Python tools (pytest, pylint, ruff, etc.). Never use bare `python`, `pip`, `pytest`, etc.
- **Update `pyproject.toml` when adding dependencies.** If new Python packages are introduced, add them to the appropriate dependency list in `pyproject.toml`.
- **Bug reports: write a failing test first.** When the user reports a bug, write a test that reproduces and confirms the bug before investigating or fixing it.
- **Default startup is `scripts/start-kiosk.sh`.** Assume the project is started via this script unless told otherwise. It handles venv activation, UI build, and server launch.

# Claude Code Prompt for Plan Mode

Review this plan thoroughly before making any code changes. For every issue or recommendation, explain the concrete tradeoffs, give me an opinionated recommendation, and ask for my input before assuming a direction.

My engineering preferences (use these to guide your recommendations):

- DRY is important—flag repetition aggressively.
- Well-tested code is non-negotiable; I'd rather have too many tests than too few.
- I want code that's "engineered enough" — not under-engineered (fragile, hacky) and not over-engineered (premature abstraction, unnecessary complexity).
- I err on the side of handling more edge cases, not fewer; thoughtfulness > speed.
- Bias toward explicit over clever.

## 1. Architecture review

Evaluate:

- Overall system design and component boundaries.
- Dependency graph and coupling concerns.
- Data flow patterns and potential bottlenecks.
- Scaling characteristics and single points of failure.
- Security architecture (auth, data access, API boundaries).

## 2. Code quality review

Evaluate:

- Code organization and module structure.
- DRY violations—be aggressive here.
- Error handling patterns and missing edge cases (call these out explicitly).
- Technical debt hotspots.
- Areas that are over-engineered or under-engineered relative to my preferences.

## 3. Test review

Evaluate:

- Test coverage gaps (unit, integration, e2e).
- Test quality and assertion strength.
- Missing edge case coverage—be thorough.
- Untested failure modes and error paths.

## 4. Performance review

Evaluate:

- N+1 queries and database access patterns.
- Memory-usage concerns.
- Caching opportunities.
- Slow or high-complexity code paths.

**For each issue you find**

For every specific issue (bug, smell, design concern, or risk):

- Describe the problem concretely, with file and line references.
- Present 2–3 options, including "do nothing" where that's reasonable.
- For each option, specify: implementation effort, risk, impact on other code, and maintenance burden.
- Give me your recommended option and why, mapped to my preferences above.
- Then explicitly ask whether I agree or want to choose a different direction before proceeding.

**Workflow and interaction**

- Do not assume my priorities on timeline or scale.
- After each section, pause and ask for my feedback before moving on.

---

BEFORE YOU START:
Ask if I want one of two options:
1/ BIG CHANGE: Work through this interactively, one section at a time (Architecture → Code Quality → Tests → Performance) with at most 4 top issues in each section.
2/ SMALL CHANGE: Work through interactively ONE question per review section

FOR EACH STAGE OF REVIEW: output the explanation and pros and cons of each stage's questions AND your opinionated recommendation and why, and then use AskUserQuestion. Also NUMBER issues and then give LETTERS for options and when using AskUserQuestion make sure each option clearly labels the issue NUMBER and option LETTER so the user doesn't get confused. Make the recommended option always the 1st option.

## Commands

### Python Backend

```bash
# Run tests
uv run pytest tests/ -v

# Run single test file
uv run pytest tests/test_launch_monitor.py -v

# Run single test
uv run pytest tests/test_launch_monitor.py::TestLaunchMonitor::test_name -v

# Lint (must score 9.0+)
uv run pylint src/openflight/ --fail-under=9

# Format check
uv run ruff check src/openflight/
uv run ruff format --check src/openflight/
```

### React UI (in /ui directory)

```bash
npm run dev      # Development server with hot reload
npm run build    # Production build
npm run lint     # ESLint
```

### Running the Application

```bash
scripts/start-kiosk.sh              # Default: kiosk mode with real radar
scripts/start-kiosk.sh --mock       # Development mode without hardware
scripts/start-kiosk.sh --mode rolling-buffer --trigger sound  # Rolling buffer with direct hardware sound trigger (recommended)
scripts/start-kiosk.sh --mode rolling-buffer --trigger sound-gpio  # Rolling buffer with GPIO software sound trigger (fallback)
scripts/start-kiosk.sh --mode rolling-buffer --trigger speed  # Rolling buffer with speed-based trigger
```

### Sound Trigger Testing

```bash
# Test direct hardware sound trigger (GATE → Level Shifter → HOST_INT)
uv run python scripts/test_sound_trigger_hardware.py

# Test GPIO software sound trigger (GATE → Pi GPIO → S! command)
uv run python scripts/test_sound_trigger_software.py
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
- `shot_detected` - Detected shots with metrics (ball_speed, club_speed, spin_rpm, carry_spin_adjusted)
- `iq_reading` - I/Q streaming detections with SNR/CFAR data
- `iq_blocks` - Raw I/Q data for post-session analysis
- `trigger_event` - Trigger accept/reject with latency (for rolling buffer mode)
- `rolling_buffer_capture` - Raw I/Q samples (4096 each) for offline analysis

## Sound Trigger Hardware

For rolling buffer mode with sound triggering, use the SparkFun SEN-14262:

**Wiring (Direct Hardware Trigger - Recommended):**

Uses a BSS138 level shifter module to boost GATE signal current drive for HOST_INT.

```
SEN-14262 GATE → Level Shifter LV1 (input)
Level Shifter HV1 → OPS243-A HOST_INT (J3 Pin 3)
SEN-14262 VCC → 3.3V (shared with Level Shifter LV)
Level Shifter LV → 3.3V
Level Shifter HV → 3.3V
All GND → GND (shared)
```

**Wiring (GPIO Software Trigger - Fallback):**

If direct hardware trigger doesn't work, use Pi GPIO to detect sound and send S! command.

```
SEN-14262 GATE → GPIO17 (pin 11) [input]
SEN-14262 VCC → 3.3V (pin 1)
SEN-14262 GND → GND (pin 6)
```

**Trigger Latency:**
| Trigger | Latency | Description |
|---------|---------|-------------|
| `sound` | ~10μs | Direct hardware: GATE → Level Shifter → HOST_INT |
| `sound-gpio` | ~1-18ms | Software: GATE → Pi GPIO → Python S! command |
| `speed` | ~5-6ms | Radar speed detection triggers capture |
