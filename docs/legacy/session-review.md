# K-LD7 Session Review

!!! warning "DEPRECATED HARDWARE"

    The K-LD7 angle radars are deprecated. The supported angle radar is the
    **TI IWR6843** — see the [IWR6843 operator guide](../iwr6843/index.md).
    Do not buy K-LD7s for a new build; this page is kept for existing builds
    and for reading historical session logs.

> **⚠️ DEPRECATED:** The K-LD7 angle radars are deprecated — OpenFlight has moved to a more capable radar chip for angle measurement. This workflow is kept for existing K-LD7 builds and historical session logs only.

This workflow is for reviewing a full `session_logs/session_*.jsonl` file after a K-LD7 tuning change.

It is intentionally an **offline empirical review tool**, not a live detector.

## What It Does

For each shot in a session log, the review script:

1. parses `rolling_buffer_capture`, `kld7_buffer`, `shot_detected`, and `error` rows by `shot_number` or timestamp
2. re-detects likely club-impact anchors directly from the raw K-LD7 frame buffer
3. scores outward post-impact `pdat` paths by:
   - timing after impact
   - distance growth
   - angle continuity
   - magnitude strength
   - lingering-clutter penalties
4. keeps the best path per shot
5. exports per-shot and session-level plots

The result is a quick way to see whether a session contains real-looking ball-flight distance profiles or mostly clutter.

## How The Grades Are Used

The exported `strong`, `partial`, and `weak` labels are **review grades for signal recoverability**:

- `strong`: the session produced a coherent outward path that is good evidence for a real tracked shot
- `partial`: the session exposed part of the shot pattern, but the path is short or noisy
- `weak`: the reviewed path is mostly clutter or too incomplete to trust

These grades are for K-LD7 review and tuning. They are **not** grades of player performance, shot outcome, or launch-angle correctness by themselves.

## Usage

For a one-off review on any machine, run the script in an isolated `uv`
environment with only the analysis dependencies it needs:

```bash
uv run --no-project --with numpy --with matplotlib python scripts/analysis/review_kld7_session.py session_logs/session_20260403_133805_range.jsonl
```

If you already have the repo environment synced with the analysis extras, the
regular project command also works:

```bash
uv run python scripts/analysis/review_kld7_session.py session_logs/session_20260403_133805_range.jsonl
```

If you want to remove previously generated files in the output directory first,
use `--clean`. Cleanup is intentionally restricted to directories that look like
`<repo>/shots/session_review_*`.

```bash
uv run --no-project --with numpy --with matplotlib python scripts/analysis/review_kld7_session.py session_logs/session_20260403_133805_range.jsonl --clean
```

Default output location:

```text
<repo>/shots/session_review_session_20260403_133805_range/
```

That directory is ignored by git.

## Generated Files

- `shot_01_profile.png` ... `shot_N_profile.png`
- `all_shot_profiles_overlay.png`
- `launch_angle_review.png`
- `shot_profiles.csv`
- `summary.md`

## How To Read The Plots

Per-shot plot:

- gray points: all post-impact detections in the selected review window
- black connected line: the chosen coherent path
- orange dashed line: path angle trace
- green lower panel: path magnitude over time

Overlay plot:

- blue: stronger reviewed profiles
- orange: partial profiles
- red: weak/noisy profiles
- black line + gold band: median path and IQR across the session

## Interpretation Rules

Treat a shot as stronger evidence when it shows:

- multiple consecutive frames
- outward distance growth
- limited angle jump
- no obvious lingering return at the same far location afterward

Treat a shot as weak evidence when it:

- starts already deep in a far clutter band
- stays almost flat in distance
- shows only one noisy frame
- leaves obvious lingering returns after the burst

## Session `error` entries

OpenFlight writes `type: "error"` lines to the same JSONL session file when shot
processing, K-LD7 streaming, rolling-buffer capture, or radar config updates fail.
These are separate from Python stderr logs and are useful when reviewing a session
offline.

Typical fields:

| Field | Meaning |
|-------|---------|
| `error` | Short description (e.g. `K-LD7 shot processing failed`) |
| `context.component` | Subsystem (`server`, `kld7_tracker`, `rolling_buffer_monitor`, …) |
| `context.stage` | Step within the pipeline (`kld7`, `set_radar_config`, …) |
| `context.exception_type` | Exception class when one was caught |
| `context.exception_message` | `str(exception)` |

Quick filter while inspecting a session:

```bash
grep '"type": "error"' session_logs/session_*.jsonl
```

In Grafana/Loki (see [observability.md](../using/observability.md)):

```logql
{app="openflight", log_type="error"}
```

A burst of `error` rows around a shot often explains missing `kld7_buffer` or
launch-angle gaps in the review plots.

## Limits

- This is not a physics model.
- The inferred impact anchor is heuristic.
- The path angle trace is a secondary diagnostic, not ground truth.
- A single improved session supports further study, but does not by itself validate a K-LD7 tuning change.
