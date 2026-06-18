<p align="center">
<img src="./ui/public/openflightlogo.svg">
  DIY Golf Launch Monitor using the OPS243-A Doppler Radar.
</p>

<p align="center">
  <a href="https://buymeacoffee.com/colemangolfs">
    <img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-yellow?style=for-the-badge&logo=buy-me-a-coffee&logoColor=white" alt="Buy Me a Coffee" />
  </a>
</p>

> [!WARNING]
> **This project is in active development.** Features may be incomplete, unstable, or change without notice. Contributions and bug reports are welcome!

## Overview

OpenFlight is an open-source golf launch monitor that uses Doppler radar to measure ball speed, club speed, launch angle, spin rate, and carry distance.

### What It Measures

- **Ball Speed**: 35-200 mph range with ±0.5% accuracy (OPS243-A)
- **Club Speed**: Detected from pre-impact readings (OPS243-A)
- **Smash Factor**: Ball speed / club speed ratio
- **Launch Angle**: Vertical launch measured by K-LD7 angle radar
- **Club Path**: Horizontal aim direction measured by second K-LD7
- **Spin Rate**: Via rolling buffer I/Q analysis (the hardest radar measurement — see [Limitations](#limitations))
- **Carry Distance**: Computed from ball speed, launch angle, and spin

### Hardware at a Glance

| Component | What it does | ~Cost |
|-----------|-------------|-------|
| OPS243-A Radar | Ball speed, club speed, spin | $249 |
| Raspberry Pi 5 | Runs everything | $60 |
| 7" Touchscreen | Shows shot data | $46 |
| SparkFun SEN-14262 | Impact sound trigger for shot capture | $18 |
| K-LD7 (×2) + FTDI adapters | Launch angle + club path | $140 |
| Power supply + accessories | | $27 |
| **Total** | | **~$540** |

> The K-LD7 angle radars are optional. Without them you still get ball speed, club speed, smash factor, spin rate, and estimated carry. See the [full parts list](docs/PARTS.md) for details and links.

## Getting Started

### 1. Get the parts

See the **[Parts List](docs/PARTS.md)** for everything you need with purchase links.

### 2. Wire it up

Follow the **[Sound Trigger Wiring Guide](docs/sound-trigger-wiring.md)** to connect the SEN-14262 to the OPS243-A. The K-LD7 modules connect via USB — no wiring needed.

### 3. Set up the Pi

Flash Raspberry Pi OS (64-bit), plug in the radars, then run the interactive setup:

```bash
git clone https://github.com/jewbetcha/openflight.git
cd openflight
./scripts/setup/setup.sh
```

The script installs everything and walks you through the one-time hardware
configuration (radar flash setup, K-LD7 device naming, auto-start) with
prompts — no manual config editing needed. It's safe to re-run any time.
See the **[Raspberry Pi Setup Guide](docs/raspberry-pi-setup.md)** for
details and troubleshooting.

### 4. Hit balls

```bash
# Default: rolling buffer mode with sound trigger
scripts/start-kiosk.sh

# With K-LD7 launch-angle geometry defaults
scripts/start-kiosk.sh --kld7-geometry

# Development mode (no hardware)
scripts/start-kiosk.sh --mock
```

Then open http://localhost:8080 or use the touchscreen.

### 5. Sync to the cloud (optional)

OpenFlight can push your sessions to the **FlightWeb** cloud so you can review
shots from any device. It's opt-in, and **raw radar data never leaves your
Pi** — only shot results and session metadata are uploaded (verify with
`openflight-cloud push --dry-run`).

`setup.sh` offers to enable this and link your Pi. To do it by hand:

```bash
openflight-cloud link       # pair this Pi (enter a short code in your browser)
openflight-cloud status     # linked? queued? parked?
```

Once linked, sessions sync automatically (on session end and via a ~10-minute
timer that heals wifi outages). See the **[Cloud Sync Guide](docs/cloud-sync.md)**
for details.

### TV Display Mode

OpenFlight also serves a fullscreen-friendly browser display for tablets, TV browsers, or a Chrome tab cast to Chromecast.

1. Start OpenFlight as usual with `scripts/start-kiosk.sh`.
2. Find the OpenFlight host IP address on your LAN.
3. Open `http://<openflight-host-ip>:8080/display` from another laptop, tablet, or TV browser.
4. For Chromecast, open the display page in Chrome and use Chrome's built-in **Cast** feature to cast the tab.

This is browser/tab casting only. OpenFlight does not include native Cast SDK support yet.

## How It Works

### System Architecture

```
┌─────────────┐  USB/Serial  ┌─────────────┐  Callback   ┌─────────────┐  WebSocket  ┌─────────────┐
│  OPS243-A   │ ───────────▶ │   Rolling   │ ──────────▶ │   Flask     │ ──────────▶ │   React     │
│   Radar     │  I/Q buffer  │   Buffer    │  on_shot()  │   Server    │   "shot"    │     UI      │
└─────────────┘              │   Monitor   │             └─────────────┘             └─────────────┘
                             └─────────────┘
                                                               ▲
┌─────────────┐  USB/Serial                                    │
│ K-LD7 (×2)  │ ──────────────────── angle data ──────────────┘
│ Angle Radar │
└─────────────┘
```

1. **Sound trigger fires** — SEN-14262 detects club impact, triggers OPS243-A HOST_INT
2. **OPS243-A dumps buffer** — Rolling buffer I/Q data is captured and analyzed for ball speed, club speed, and spin
3. **K-LD7 correlates** — The server uses the OPS243-A impact timestamp to find the matching ball burst in the K-LD7 ring buffer, extracting launch angle and club path
4. **Carry computed** — Ball speed + spin + launch angle → carry distance
5. **UI updates** — Shot data emitted via WebSocket to the React frontend

### Doppler Radar Basics

The OPS243-A transmits a 24 GHz signal. When it bounces off a moving object (the golf ball), the frequency shifts proportionally to the object's speed — this is the Doppler effect. At 24.125 GHz, each 1 mph of speed creates a ~71.7 Hz Doppler shift.

### Positioning

Place the radar **3-5 feet behind the tee**, pointing at the hitting area:

```
                Ball Flight Direction
                ======================>

[Tee]  ←--- 3-5 ft ---→  [OPS243-A]  [K-LD7 vertical]  [K-LD7 horizontal]
```

The K-LD7 modules are positioned near the OPS243-A, one mounted vertically (launch angle) and one horizontally (club path / aim direction).

## Configuration

### Radar Settings for Golf

| Setting        | Value                  | Why                                          |
| -------------- | ---------------------- | -------------------------------------------- |
| Mode           | Rolling buffer         | Raw I/Q capture for spin + precise speeds    |
| Sample Rate    | 30 ksps                | Supports up to ~208 mph ball speed           |
| Capture        | 4096 I/Q samples       | ~136 ms around impact                        |
| Trigger        | Sound (SEN-14262)      | ~10 µs hardware latency via HOST_INT         |
| Min Ball Speed | 35 mph                 | Filter club waggle and slow movements        |
| DC Mask        | ~15 mph exclusion zone | Reject body movement and environmental noise |

These are applied automatically — the one-time flash configuration is handled
by the setup script.

### Python API

```python
from openflight.rolling_buffer import RollingBufferMonitor

monitor = RollingBufferMonitor()   # auto-detects the OPS243-A
monitor.connect()
monitor.start()

print("Swing when ready...")
shot = monitor.wait_for_shot(timeout=60)
if shot:
    print(f"Ball Speed: {shot.ball_speed_mph:.1f} mph")
    print(f"Est. Carry: {shot.estimated_carry_yards:.0f} yards")

monitor.stop()
monitor.disconnect()
```

## Limitations

- **Cosine error**: If ball doesn't travel directly toward/away from radar, measured speed will be slightly lower than actual
- **Spin detection**: The hardest radar measurement, especially indoors — the usable signal window ends when the ball hits the net, and short windows can't resolve low spin (commercial radar units have the same constraint and fall back to estimated spin indoors). Low driver-band readings (≤~3100 RPM) are reported at reduced confidence. When spin isn't measured, carry falls back to club-typical spin values. Improving this is an active focus.
- **K-LD7 speed aliasing**: The K-LD7 max speed is 62 mph, so it's used only for angle/distance, not speed

### Ball Markings

Reflective markings (aluminum stickers, painted dots) noticeably improve K-LD7 launch-angle extraction — the stronger return gives multi-frame tracking, higher SNR, and more confident angles. However, a specular patch produces a pulsed, non-sinusoidal amplitude modulation that the spin detector can't interpret as seam modulation, so measured spin degrades (typically locks to the top of the valid frequency band with low confidence). Low-confidence spin automatically falls back to club-typical values in the ballistics model, so the net effect of marking a ball is better angles with no worse carry estimates. A thin painted stripe (rather than a patch) is a reasonable middle ground if you want both — it rotates through the beam more like a seam.

## Hardware Diagnostic

To verify every component of your build in one shot:

```bash
uv run python scripts/hardware-test/diagnose.py
```

The diagnostic walks through 6 checks:
1. OPS243 connectivity
2. OPS243 rolling buffer mode persistence
3. OPS243 software trigger
4. K-LD7 vertical (launch angle)
5. K-LD7 horizontal (aim direction, optional)
6. Sound trigger end-to-end (interactive — prompts you to clap near the sensor)

Missing optional hardware (like the horizontal K-LD7) is reported as a skip rather than a failure. Pass `--require-all` to fail on skips, or `--no-interactive` to skip the sound-trigger prompt in unattended runs.

## Project Structure

```
openflight/
├── src/openflight/
│   ├── ops243.py              # OPS243-A radar driver
│   ├── launch_monitor.py      # Shot detection & club/ball separation
│   ├── server.py              # Flask server, K-LD7 correlation, carry
│   ├── session_logger.py      # JSONL session logging
│   ├── kld7/                  # K-LD7 angle radar
│   │   ├── radc.py            # FFT, phase interferometry, angle extraction
│   │   ├── tracker.py         # Ring buffer, shot correlation
│   │   ├── geometry.py        # Launch-angle trajectory fitting
│   │   └── types.py           # Data types
│   └── rolling_buffer/        # Spin rate detection
│       ├── monitor.py         # Rolling buffer monitor
│       ├── processor.py       # I/Q processing for spin
│       ├── trigger.py         # Trigger strategies
│       └── types.py           # Data types
├── ui/                        # React frontend
├── scripts/                   # Utility & setup scripts
├── docs/                      # Documentation
└── pyproject.toml
```

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas of interest:

- **Better spin detection**: A dechirped Doppler-sideband estimator is in development (`scripts/analysis/replay_spin_dechirp.py`) — help validating it against launch-monitor truth data is especially welcome
- **K-LD7 signal processing**: Improve ball detection from sparse radar frames
- **Mobile app**: Bluetooth connection to phone

### Running Tests

```bash
uv run pytest tests/ -v
```

## Documentation

- **[Parts List](docs/PARTS.md)** — What to buy
- **[Sound Trigger Wiring](docs/sound-trigger-wiring.md)** — How to wire the sound trigger
- **[Raspberry Pi Setup](docs/raspberry-pi-setup.md)** — Full setup guide
- **[Simulator Connectors](docs/simulator/README.md)** — Stream shots to GSPro, OpenGolfSim, and others
- **[Cloud Sync](docs/cloud-sync.md)** — Push filtered sessions to FlightWeb
- **[Rolling Buffer & Spin Detection](docs/rolling_buffer_spin_detection.md)** — Spin measurement details
- **[Dechirped-Sideband Spin Replay](docs/spin-dechirp-replay.md)** — Next-gen spin estimator test bench
- **[K-LD7 Ball Detection Theory](docs/kld7-ball-detection-theory.md)** — How angle detection works
- **[K-LD7 Session Review](docs/kld7-session-review.md)** — Offline review workflow for session JSONL files
- **[Observability & Log Shipping](docs/observability.md)** — Ship logs to Grafana Cloud
- **[Contributing Guide](CONTRIBUTING.md)** — How to contribute
- **[Changelog](docs/CHANGELOG.md)** — Version history

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later) - see LICENSE file.

## Acknowledgments

- [OmniPreSense](https://omnipresense.com/) for the OPS243-A radar and documentation
- The golf hacker community for inspiration
