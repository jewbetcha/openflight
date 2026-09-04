# K-LD7 Analysis Tooling

> **⚠️ DEPRECATED:** The K-LD7 angle radars are deprecated — OpenFlight has moved to a more capable radar chip for angle measurement. This tooling is kept for existing K-LD7 builds and historical session logs only.

This guide covers the K-LD7 offline and live analysis workflow built around:

- `kld7_geometry_selection_report.py`
- `kld7_live_sync.py`
- `kld7_timing_shift_visualizer.html`

The goal is to make K-LD7 frame selection visible shot-by-shot so we can answer
questions that are difficult to see from the kiosk UI alone:

- Which RADC frames were considered?
- Which frames did the replay selector choose?
- Did the chosen frames match the OPS ball-speed bin?
- Did the selected bearings produce a plausible launch angle?
- Would a small whole-shot timing shift improve the geometry fit?
- Does F1B range agree with the expected ball position?

This tooling is for analysis and development. It does not replace the live kiosk
path, but `frames_live.csv` is intended to mirror the current OPS-bin/live-style
selection logic closely enough to debug production behavior.

## File Roles

`kld7_geometry_selection_report.py`

Builds a report from a saved OpenFlight session JSONL. It extracts K-LD7 RADC
frames, replays vertical frame selection, writes CSV files, copies the HTML
visualizer into the report folder, and writes a session summary.

`kld7_live_sync.py`

Polls the Pi over SSH/SCP, pulls the latest session JSONL when new shots appear,
regenerates the report, and serves the visualizer locally from the generated
report directory.

`kld7_timing_shift_visualizer.html`

Browser tool for loading `frames.csv` or `frames_live.csv`, selecting a shot and
up to two frames, and visualizing launch-angle geometry, timing shifts, F1B
range overlays, and start-position error.

## Generated Files

The report script writes these files:

- `summary.md`: human-readable session summary.
- `config.json`: report configuration used for the replay.
- `shots.csv`: broad exploratory selector output, one row per shot.
- `frames.csv`: broad exploratory frame rows.
- `shots_live.csv`: live-style replay output, one row per shot.
- `frames_live.csv`: live-style replay frame rows.
- `index.html`: copied visualizer.

## `frames.csv` vs `frames_live.csv`

Use `frames_live.csv` when you want to debug what the current production-like
selector would do.

Use `frames.csv` when you want a broader exploratory view of strong returns,
including frames or bins the production-style selector may intentionally avoid.

`frames_live.csv` / `shots_live.csv`

- Replays the current OPS-bin/live-style selection logic.
- Prioritizes the OPS-anchored ball-speed bin.
- Marks the selected anchor and neighbor frames.
- Is the right default for validating kiosk behavior.
- Is the file the live-sync browser URL loads by default.

`frames.csv` / `shots.csv`

- Uses a broader/high-SNR exploratory pass.
- Can surface clutter, net/screen returns, or alternate strong bins.
- Is useful when the live selector rejects a shot and you want to inspect what
  else was present in the RADC data.
- Can show high-SNR frames that should not necessarily be trusted as ball frames.

In short: start with `frames_live.csv`; use `frames.csv` when you are hunting
for why something went wrong.

## Offline Workflow

Run this from the repo on your Mac:

```bash
cd /path/to/openflight

uv run python scripts/analysis/kld7_geometry_selection_report.py \
  /path/to/openflight_sessions/session_YYYYMMDD_HHMMSS_trackman.jsonl \
  --angle-offset-deg 2.5 \
  --ball-distance-ft 5 \
  --mount-deg 10
```

The report directory is created next to the session file unless `--output-dir`
is supplied.

To write to a specific folder:

```bash
uv run python scripts/analysis/kld7_geometry_selection_report.py \
  /path/to/session.jsonl \
  --output-dir /path/to/openflight_sessions/my_report \
  --angle-offset-deg 2.5 \
  --ball-distance-ft 5 \
  --mount-deg 10
```

Then open the generated `index.html`, or serve that report folder and load:

```text
index.html?csv=frames_live.csv
```

## Live Workflow

Use this while the Pi is running the kiosk and writing session logs:

### SSH Prerequisite

Live sync uses your Mac's `ssh` and `scp` commands. The `--pi-host` value is the
normal SSH destination for the Pi:

```text
pi-user@pi-host.local
```

Before running live sync, verify that this works from the Mac:

```bash
ssh pi-user@pi-host.local
```

For continuous live polling, passwordless SSH is strongly recommended. Otherwise
the script can block or repeatedly prompt for a password when it checks for new
shots. The private key stays on the Mac, usually in:

```text
~/.ssh/id_ed25519
```

The matching public key is installed on the Pi in:

```text
~/.ssh/authorized_keys
```

If you do not already have an SSH key on the Mac, create one:

```bash
ssh-keygen -t ed25519 -C "openflight-live-sync"
```

Then copy the public key to the Pi:

```bash
ssh-copy-id pi-user@pi-host.local
```

If `ssh-copy-id` is unavailable on the Mac, use this fallback:

```bash
cat ~/.ssh/id_ed25519.pub | ssh pi-user@pi-host.local 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

Confirm the final connection does not ask for a password:

```bash
ssh pi-user@pi-host.local 'hostname'
```

If the Pi hostname does not resolve on the network, use the Pi's IP address
instead, for example:

```text
--pi-host pi-user@192.168.1.50
```

### Run Live Sync

```bash
cd /path/to/openflight

uv run python scripts/analysis/kld7_live_sync.py \
  --pi-host pi-user@pi-host.local \
  --angle-offset-deg 2.5 \
  --ball-distance-ft 5 \
  --mount-deg 10 \
  --serve-port 8765
```

Open:

```text
http://127.0.0.1:8765/index.html?csv=frames_live.csv&auto=1
```

The live sync script:

1. Finds the newest session JSONL on the Pi.
2. Checks whether the shot count changed.
3. Copies the session to the Mac.
4. Regenerates `frames_live.csv`, `shots_live.csv`, and related files.
5. Serves the report directory on the requested port.

The visualizer auto-reloads the CSV and selects the newest shot when `auto=1`.

For a one-time pull and report generation:

```bash
uv run python scripts/analysis/kld7_live_sync.py \
  --pi-host pi-user@pi-host.local \
  --angle-offset-deg 2.5 \
  --ball-distance-ft 5 \
  --mount-deg 10 \
  --once
```

## Important Configuration

`--angle-offset-deg`

K-LD7 boresight/electrical-zero correction. In kiosk geometry mode, the current
field default is positive `2.5` degrees. The corrected bearing is:

```text
corrected_bearing = raw_kld7_angle + angle_offset_deg
```

`--ball-distance-ft`

Distance from the radar face to the ball at address. This is critical for
geometry fitting. If the ball was moved from 5 ft to 4 ft, generate a separate
report or pass the correct distance for that session.

`--mount-deg`

Physical vertical radar mount tilt. Field default has been `10` degrees.

`--ball-above-radar-ft`

Vertical ball offset relative to the radar. Use this when the ball is known to
be above or below the radar face and you want that modeled explicitly.

`--report-arg`

Passes extra options from live sync to the report script. Repeat it for multiple
options:

```bash
uv run python scripts/analysis/kld7_live_sync.py \
  --pi-host pi-user@pi-host.local \
  --angle-offset-deg 2.5 \
  --ball-distance-ft 5 \
  --mount-deg 10 \
  --report-arg=--clock-error-ms \
  --report-arg=20
```

## Visualizer Basics

The visualizer loads one CSV at a time. The normal live URL is:

```text
index.html?csv=frames_live.csv&auto=1
```

Useful controls:

- Shot dropdown: selects the shot to inspect.
- Frame list: click up to two frames.
- Shift controls: moves both selected frames by the same millisecond offset.
- Range overlay: toggles F1B range markers.
- Angle offset input: applies a display/replay bearing offset in the browser.

The visualizer intentionally shifts both selected frames together because the
timing concern is a per-shot alignment error, not independent per-frame drift.

## Visualizer Metrics

New Launch Angle

The primary geometry-fit result for the currently selected frame or frames. This
is the candidate angle to compare against TrackMan or the kiosk output.

Launch From Ball To Frame 2

The simple one-frame launch angle from the known ball position to frame 2. This
is useful when only one good frame exists, but it is sensitive to timing.

Free-Start 2-Frame Line

The line through frame 1 and frame 2 without forcing the line to start at the
known ball position. This helps show whether the selected frames imply a launch
line that crosses the floor before or after the ball.

Start Position Error

Where the free-start line crosses ball height relative to the configured ball
position. A large start-position error suggests timing, frame selection, or range
issues.

Frame 1 Miss

How far frame 1 is from the ball-to-frame-2 line. This is a quick visual cue for
whether the selected frames agree with the same trajectory.

Corrected Times

The selected frame timestamps after applying the current whole-shot shift.

Frame Distances

The physics distance from ball speed and corrected time:

```text
distance_from_ball = ball_speed * corrected_time
```

F1B Ranges

Range derived from F1B phase for the selected frame or frames. Treat this as a
diagnostic, not a final source of truth, until the F1B local-ball-bin selection
path is fully validated.

Range Delta

Difference between F1B range and the speed/time-derived frame distance. Large
deltas can indicate timing error, F1B clutter, wrong range unwrap, or a frame
that is not actually the ball.

## Reading Frame Rows

Important columns:

- `shot_number`: shot index from the session.
- `frame_index`: K-LD7 frame number within the shot window.
- `t_ms`: frame time relative to impact.
- `expected_bin`: OPS-derived expected K-LD7 Doppler bin.
- `peak_bin`: selected K-LD7 bin for that frame.
- `bin_error`: absolute difference between expected and selected bins.
- `speed_mph`: speed implied by the selected K-LD7 bin.
- `snr`: selected-bin signal-to-noise ratio.
- `angle_centroid_deg`: centroid bearing before browser offset handling.
- `bearing_deg`: bearing with configured offset applied by the report.
- `f1b_range_ft`: F1B phase-derived range estimate.
- `f1b_same_bin_snr`: F1B SNR at the selected F1A/F2A bin.
- `f1b_peak_bin_error`: current F1B peak error diagnostic.
- `selection_role`: `anchor`, `neighbor`, or blank.
- `status`: `selected`, `rejected`, or `invalid`.
- `reasons`: why a frame was not selected.

## F1B Range Caveats

F1B range has been useful, but the current CSV can still report a global F1B peak
that is not near the ball-speed bin. A frame can show a scary
`f1b_peak_bin_error` while still having good local F1B support at the selected
ball bin.

When evaluating F1B, prefer this order:

1. Is the main selected `peak_bin` close to the OPS `expected_bin`?
2. Is `f1b_same_bin_snr` decent at that selected ball bin?
3. Are nearby F1B bins around the selected ball bin coherent?
4. Does `f1b_range_ft` make physical sense for ball speed and `t_ms`?
5. Is the global F1B peak near DC/clutter, net/screen, or another non-ball
   return?

A follow-up improvement is to add explicit local F1B ball-bin columns so the CSV
distinguishes global F1B peaks from local ball-bin F1B support.

## TrackMan Test Workflow

For TrackMan comparison sessions:

1. Start the kiosk with geometry and raw RADC logging.
2. Start `kld7_live_sync.py` on the Mac.
3. Open the visualizer with `frames_live.csv&auto=1`.
4. Hit shots and record TrackMan launch angle, ball speed, horizontal direction,
   curve, carry side, and club.
5. For each shot, compare TrackMan launch to:
   - logged kiosk launch
   - New Launch Angle
   - one-frame angle
   - best whole-shot shift within a practical bound
   - F1B range consistency
6. Categorize each shot as:
   - clean 2-frame geometry
   - 2-frame geometry recoverable by small timing shift
   - one-frame geometry
   - one-frame plus F1B range candidate
   - rejected due to bin/SNR/clutter
   - estimated/no usable radar frame

The current hypothesis to test is whether two-frame shots can consistently use a
small whole-shot shift to minimize geometry error, and whether one-frame shots
can be validated or rejected with F1B range.

## Common Gotchas

Wrong ball distance

If `--ball-distance-ft` does not match the setup, all geometry fits shift. A 4 ft
setup analyzed as 5 ft can make otherwise good frames look wrong.

Wrong angle offset

The kiosk geometry default is positive `2.5` degrees. If the report and kiosk use
different offsets, browser angles will not match logged angles.

Frame timing from old sessions

Older sessions may have pre-OPS-clock timing behavior. Timing conclusions from
those sessions should be separated from newer sessions.

Single-frame angles are easy to fit

With one frame, a timing shift can make the launch angle look better, but there
is less evidence than with a two-frame fit. Treat one-frame recoveries as lower
confidence unless F1B range supports them.

High SNR can be clutter

The strongest bin is not always the ball. Net/screen returns, near-field clutter,
or club returns can have high SNR. Bin error, timing, rising trajectory, and F1B
range all matter.

## Quick Command Reference

Live:

```bash
cd /path/to/openflight
uv run python scripts/analysis/kld7_live_sync.py \
  --pi-host pi-user@pi-host.local \
  --angle-offset-deg 2.5 \
  --ball-distance-ft 5 \
  --mount-deg 10 \
  --serve-port 8765
```

Browser:

```text
http://127.0.0.1:8765/index.html?csv=frames_live.csv&auto=1
```

Offline:

```bash
cd /path/to/openflight
uv run python scripts/analysis/kld7_geometry_selection_report.py \
  /path/to/session.jsonl \
  --angle-offset-deg 2.5 \
  --ball-distance-ft 5 \
  --mount-deg 10
```

One-time Pi sync:

```bash
uv run python scripts/analysis/kld7_live_sync.py \
  --pi-host pi-user@pi-host.local \
  --angle-offset-deg 2.5 \
  --ball-distance-ft 5 \
  --mount-deg 10 \
  --once
```
