# K-LD7 Launch Angle & Direction

!!! warning "DEPRECATED HARDWARE"

    The K-LD7 angle radars are deprecated. The supported angle radar is the
    **TI IWR6843** — see the [IWR6843 operator guide](../iwr6843/index.md).
    Do not buy K-LD7s for a new build; this page is kept for existing builds
    and for reading historical session logs.

The K-LD7 radars measure the ball's **launch angle** (vertical) and
**launch direction** (horizontal aim) to complement the OPS243's ball
speed. Two modules are used: one mounted to look in the vertical plane,
one in the horizontal plane. They are enabled together with a single
flag.

- **Launch angle (vertical)** — extracted with the **two-ray**
  estimator, which models the indoor ground-bounce multipath directly.
  Indoor accuracy is ~2–3° on irons and wedges.
- **Launch direction (horizontal)** — uses the legacy estimator (see
  [Horizontal / aim](#horizontal-aim) below).
- Both axes are filtered by the OPS243 ball speed and correlated to the
  shot via the OPS impact timestamp.

For how the estimator works internally, see
[kld7-launch-angle-explained.html](launch-angle-explained.html) and
[kld7-ball-detection-theory.md](ball-detection-theory.md).

## Enabling it

```bash
scripts/start-kiosk.sh --kld7 --kld7-mount-tilt <degrees>
```

`--kld7` turns on both radars (vertical + horizontal auto-detected) and,
with them, the two-ray launch-angle estimator and the ball-speed cosine
correction. The only value you must supply is the **mount tilt** — the
rest have sensible defaults you can override.

## Measuring the rig

The estimator is geometry-sensitive: a wrong physical parameter shows up
directly as a launch-angle error. Measure these once whenever the rig
moves and pass them on the command line.

| Parameter | Flag | Default | How to measure | Sensitivity |
|---|---|---|---|---|
| **Mount tilt** | `--kld7-mount-tilt` | **required** | Phone inclinometer app against the radar face | Offsets launch angle ~1:1 — the most important number, which is why there is no default |
| Radar height | `--kld7-radar-height-inches` | 4.0 | Center of the radar above **the surface the ball sits on** (the mat top, *not* the floor) | ~0.7–0.8° per inch |
| Radar-to-ball distance | `--kld7-ball-distance` | 5.0 ft | Tape from the radar face to the tee | ~1–1.5° per half-foot (partly self-corrected by the range clock) |
| Boresight offset | `--kld7-angle-offset` | 1.5 | Not user-measurable — requires a corner reflector against a truth source. Leave at the default unless you have calibrated your own mount. | Constant bias on launch angle |

> **Why mount tilt is required but boresight offset is not:** tilt varies
> with every setup and is easy to measure with a phone, so a stale default
> would silently corrupt results. Boresight offset needs lab calibration
> (corner reflector + a truth launch monitor); `1.5°` is our
> corner-reflector-derived value and the right default for the standard
> mount.

## Other flags

| Flag | Purpose |
|---|---|
| `--kld7-port` / `--kld7-horizontal-port` | Override serial port autodetection |
| `--kld7-horizontal-offset` | Boresight offset for the horizontal radar |
| `--kld7-vertical-raw` | Emit the raw vertical estimator output with **all display gating bypassed** (plausibility, lane, and confidence guards). For debugging/validation only. |
| `--kld7-raw-logging` | Log raw RADC frames to the session file for offline replay and review |
| `--calculated-spin` | Off by default. Replaces radar spin with the kinematic estimate (`170·v·sin(LA)^1.2`). Opt-in; see the spin notes. |

## Reviewing a session offline

After a session, render a **per-shot HTML report** that re-runs the
two-ray estimator offline on the saved RADC frames and lays the result
next to what the system logged live (displayed angle, source, two_ray's
own answer, the accept/reject gate, frame timing, and the tier
classification). Because the offline columns use the *current* code, this
doubles as a regression lens — replay an old session to see how today's
gates would classify each shot.

```bash
uv run python scripts/analysis/session_shot_report.py SESSION.jsonl --open
```

- `SESSION.jsonl` — a session log that contains raw RADC frames (run the
  live session with `--kld7-raw-logging`).
- `-o, --output PATH` — output HTML path (default: `SESSION.report.html`).
- `--open` — open the report in the default browser when done.
- **Geometry** (must match the physical rig; printed into the report
  header so the result is never ambiguous):
  - `--mount-tilt` (default 10.3)
  - `--angle-offset` (default: auto-detected from the log, else 2.5)
  - `--ball-distance` (default 5.0 ft)
  - `--radar-height-inches` (default 4.0)
  - `--net-distance` (default 10.0 ft; enables de-aliasing past the range wrap)

Example, matching the standard mount:

```bash
uv run python scripts/analysis/session_shot_report.py \
    ~/openflight_sessions/session_20260620_121141_trackman.jsonl \
    --mount-tilt 10.3 --ball-distance 5.0 --radar-height-inches 4.0 --open
```

> An older text/CSV review workflow also exists
> ([kld7-session-review.md](session-review.md)); the HTML report
> above is the recommended reviewer.

## Horizontal / aim

`--kld7` also enables the **horizontal** radar for launch direction, but
that axis still uses the **legacy** estimator — the two-ray upgrade
applies to the vertical (launch-angle) axis only. The horizontal radar
runs with its defaults; `--kld7-horizontal-offset` sets its boresight and
`--kld7-horizontal-port` overrides the serial port. Launch direction is
therefore lower-fidelity than launch angle and is not gated or corrected
by the two-ray pipeline.

## Troubleshooting

See [kld7-troubleshooting.md](troubleshooting.md) for detection and
serial issues. For validation sessions and offline tooling, see the
[TrackMan test process](../development/trackman-testing.md) and
[K-LD7 analysis tools](../development/analysis-tooling.md).
