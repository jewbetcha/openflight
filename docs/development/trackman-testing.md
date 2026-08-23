# Trackman Test Process

> **⚠️ Note:** The K-LD7 angle radars referenced throughout this document are deprecated — OpenFlight has moved to a more capable radar chip for angle measurement. The K-LD7 steps apply to existing K-LD7 builds and historical session data only.

This note is a handoff for future agents working on OpenFlight accuracy against
Trackman. Treat Trackman as the source of truth for metric comparison.

## Goal

Use Trackman sessions to improve OpenFlight accuracy without hiding failures.
For every test pass, preserve enough raw data and diagnostics to answer:

- Did OpenFlight detect the same shot Trackman saw?
- Are ball speed, club speed, launch angles, spin, and carry biased?
- If spin or K-LD7 angles are missing, did the system log why?
- Are rejected values truly bad signal, or are guardrails too strict?

## Before A Session

1. Pull latest `main` on the Pi and restart OpenFlight with the Trackman test
   preset and the measured vertical-radar tilt:

   ```bash
   scripts/start-kiosk.sh --trackman-test \
     --kld7-mount-tilt <measured-degrees>
   ```

   This enables both K-LD7 radars, raw RADC payload logging, and
   `--session-location trackman`. It keeps production angle extraction while
   preserving raw payloads for replay. Mount tilt has no safe default because
   an incorrect value directly biases launch angle.
   To verify the exact server command without starting hardware or the kiosk,
   run:

   ```bash
   scripts/start-kiosk.sh --trackman-test \
     --kld7-mount-tilt <measured-degrees> --dry-run
   ```
2. Confirm the selected club in the UI matches the club being hit.
   - This matters for launch-angle fallbacks, spin expectations, and club-aware
     spin rail filtering.
3. Confirm OPS243 rolling buffer mode is active and sound trigger re-arms after
   each shot.
4. Confirm K-LD7 orientation and udev symlinks
   (`./scripts/setup/setup_kld7_devices.sh --show`):
   - horizontal: `/dev/kld7_horizontal`
   - vertical: `/dev/kld7_vertical`
5. Confirm both K-LD7 FTDI adapters are in low-latency mode. Run this once on
   the Pi if the udev rule has not been installed:

   ```bash
   sudo scripts/setup/setup_kld7_latency.sh
   ```

   Then verify startup logs show `USB serial latency_timer=1ms` for both
   vertical and horizontal K-LD7 devices.
6. For the primary K-LD7 replay path, rely on the `--trackman-test` JSONL raw
   RADC logging. Run the standalone RADC capture script only for extra
   short-window diagnostics, and make sure its capture window overlaps the
   Trackman comparison rows.
7. Make sure Trackman export includes shot number/order, club, ball speed, club
   speed, launch angle, launch direction, carry side, curve, spin rate, and
   carry.
8. Record the physical setup in the session notes:
   - club
   - vertical K-LD7 mount tilt
   - radar-to-ball distance
   - radar height relative to ball
   - screen/net distance from the ball
   - whether any shots were intentional low-launch, pushed, pulled, or curved

## Files To Collect

Always collect:

- OpenFlight JSONL session log: `session_logs/session_<timestamp>_range.jsonl`
- Trackman normalized CSV export
- Any generated comparison CSV/plots

Optional when debugging K-LD7 angles:

- K-LD7 raw ADC `.pkl` from `scripts/analysis/capture_kld7_radc.py`
- Any `diagnose_kld7_raw_adc.py` output directories

Session logs normally live in `~/openflight_sessions/`. Copy the matching log
and reference export into the same analysis workspace before comparing them.

## Raw K-LD7 ADC Capture

Use this when investigating horizontal or vertical launch-angle misses outside
the normal `--trackman-test` JSONL path:

```bash
uv run --no-project \
  --with pyserial --with numpy --with scipy \
  python scripts/analysis/capture_kld7_radc.py \
  --orientation horizontal \
  --duration 90
```

Notes:

- Default capture is RADC-only. Add `--include-targets` only when PDAT/TDAT are
  needed; they reduce available serial bandwidth.
- The script should leave OPS243 rolling buffer armed after each trigger and on
  shutdown.
- Store the `.pkl` next to session logs or copy it into a shared location.
- Standalone `.pkl` captures are useful only if their `capture_start` and
  `capture_end` overlap the Trackman comparison CSV timestamps. If they do not,
  replay cannot treat Trackman as source truth for those raw frames.
- If a capture has many short/invalid RADC payloads, note the K-LD7 frame rate
  and USB/serial contention before tuning angle logic.

Analyze a `.pkl`:

```bash
uv run --no-project \
  --with numpy --with scipy \
  python scripts/analysis/diagnose_kld7_raw_adc.py \
  session_logs/kld7_radc_<timestamp>.pkl \
  --output .context/raw_adc_diag_<timestamp>
```

Useful outputs:

- `radc_summary.json`
- `radc_frame_diagnostics.csv`
- `shot_summaries.csv`
- per-shot `shot_##_frame_diagnostics.csv`

## Trackman Comparison

Generate an OpenFlight vs Trackman comparison:

```bash
PYTHONPATH=scripts/analysis uv run --no-project \
  --with numpy \
  python scripts/analysis/compare_trackman.py \
  --openflight session_logs/session_<timestamp>_range.jsonl \
  --trackman session_logs/<trackman_export>.csv \
  --output session_logs/comparison_<timestamp>.csv
```

The comparison script reports per-club bias and writes row-level deltas for:

- ball speed
- club speed
- smash
- vertical launch
- horizontal launch
- spin
- carry

Historical saved-angle comparisons are useful for spotting bias, but they are
not enough to justify changing the live K-LD7 path because they lack raw RADC
payloads. Use new `--trackman-test` sessions for signal-processing validation.

It also includes OpenFlight spin diagnostics when present:

- `spin_candidate_of`
- `spin_confidence_of`
- `spin_quality_of`
- `spin_snr_of`
- `spin_rejection_of`

Use these columns to determine whether OpenFlight had no spin signal, rejected a
candidate, or accepted a low-confidence value.

Before tuning K-LD7 signal-processing parameters, require raw RADC replayability:

```bash
uv run --no-sync python scripts/analysis/replay_kld7_trackman.py \
  --comparison session_logs/comparison_<timestamp>.csv \
  --openflight session_logs/session_<timestamp>_range.jsonl \
  --summary-output session_logs/kld7_replay_preflight_<timestamp>.json \
  --require-trackman-test-provenance \
  --check-raw-radc-only
```

The preflight prints `capture_raw_payloads` from top-level `kld7_buffer`
metadata and `raw_radc_readiness` from the comparison-to-buffer mapping. For a
usable Trackman replay, both should show raw payload coverage rather than zero
payloads, incomplete expected payloads, or invalid payload sizes. New
`--trackman-test` logs include per-frame `radc_payload_bytes`; `payload_invalid`
must stay at `0` because replay requires each decoded RADC payload to be exactly
3072 bytes. Replay summary JSON also preserves the session
`config.kld7_experiments` block, so the artifact should show
`raw_radc_payload_logging_requested: true`, `raw_radc_payload_logging_enabled:
true`, `trackman_calibration_enabled: false`, and `radc_tuning_enabled: false`
for the default `--trackman-test` collection run.
With `--check-raw-radc-only`, `--summary-output` writes a preflight JSON
artifact with `raw_radc_readiness_passes`,
`raw_radc_readiness_by_first_shot`, `trackman_test_provenance_passes`, and
`trackman_test_provenance_issues`.

Then run the full TrackMan gate:

```bash
uv run --no-sync python scripts/analysis/replay_kld7_trackman.py \
  --comparison session_logs/comparison_<timestamp>.csv \
  --openflight session_logs/session_<timestamp>_range.jsonl \
  --summary-output session_logs/kld7_replay_summary_<timestamp>.json \
  --diagnostics-output session_logs/kld7_replay_diagnostics_<timestamp>.jsonl \
  --require-trackman-test-provenance \
  --require-raw-radc \
  --require-within-half-degree
```

The full replay summary JSON includes `trackman_replay_gate_passes` and
`trackman_replay_gate_issues`, which combine raw-RADC readiness, clean
Trackman-test provenance, and the within-0.5° accuracy gate into one verdict.

If this fails with `buffers missing radc_b64` or `invalid RADC payload size`,
the session can still evaluate saved OpenFlight angles, but it cannot prove a
new RADC extraction algorithm. When raw RADC is present but the within-0.5° gate
fails, inspect the diagnostics
JSONL first. Each row includes the TrackMan target, replay result, target bands,
expected OPS bin, SNR, peak-bin error, phase coherence, ADC health warnings, and
the parameter set that produced the replay.

## Reading Session Logs

Important JSONL rows:

- `shot_detected`: user-facing shot values and per-shot diagnostics
- `rolling_buffer_capture`: raw OPS243 I/Q plus detailed speed/spin processing
- `kld7_buffer`: buffered K-LD7 frames and selected angle diagnostics
- `trigger_diagnostic`: trigger acceptance, latency, and speed timeline details

Spin diagnostics to inspect:

- `spin_rpm`: accepted user-facing spin, or `null`
- `spin_candidate_rpm`: candidate RPM even when rejected
- `spin_snr`: envelope peak SNR
- `spin_quality`: processor quality label for accepted spin
- `spin_rejection_reason`: why spin was withheld
- `spin_at_lower_rail` / `spin_at_upper_rail`: boundary artifacts

Launch-angle diagnostics to inspect:

- `launch_angle_vertical`
- `launch_angle_horizontal`
- `launch_angle_confidence`
- `angle_source`
- `club_angle_deg`
- `club_path_deg`
- `spin_axis_deg`

## Interpreting Spin

Current spin handling is intentionally conservative:

- Upper-rail candidates near 12000 RPM are usually rejected as filter-edge noise.
- Lower-rail candidates around 3300-3500 RPM are capped to low confidence.
- For high-spin clubs such as 7-iron, PW, GW, SW, and LW, implausibly low
  lower-rail candidates are withheld and logged with a plausibility reason.
- Rejected spin should still log candidate RPM, SNR, peak frequency, seam cycles,
  rail flags, and rejection reason.

Do not loosen spin guardrails just to increase read rate. First confirm from
Trackman and raw I/Q whether the accepted candidates would be accurate. A useful
spin improvement should increase matched, accurate readings without reintroducing
rail artifacts.

## Interpreting K-LD7 Angles

Current angle handling:

- Live shots should always emit some vertical and horizontal launch angle.
- Radar/camera measurements win when plausible.
- Vertical fallback uses club/speed/smash/spin estimates.
- Horizontal fallback is neutral `0.0`.
- K-LD7 RADC extraction is filtered by shot timestamp so stale frames do not
  dominate the result.
- Weak wall/edge candidates are retried with low-energy settings rather than
  blindly reported.

When debugging K-LD7 misses, prefer shot-window RADC analysis over whole-buffer
analysis. Whole-buffer replays can select stale frames that live processing now
ignores.

## Classifying K-LD7 Timing Misses

TrackMan sessions should not only report MAE. Also bucket each vertical K-LD7
shot by what the radar evidence says:

- Production two-frame geometry: live selection used `estimator=geometry` with
  two or more frames and the server accepted it.
- Timing-recoverable two-frame geometry: live selection missed or was rejected,
  but replaying the same physical frames with a plausible impact-time shift
  produces a two-frame geometry result close to TrackMan.
- One-frame diagnostic: only one good frame is available. This can explain what
  the radar saw, but do not count it as equivalent to constrained geometry.
- Signal/clutter/off-boresight miss: no nearby frame has a good OPS-bin match,
  good SNR, coherent phase, and plausible bearing progression.

For timing-sensitive shots, scan approximately `-100 ms` to `+100 ms` around the
K-LD7 impact timestamp. For each promising frame, record:

- frame index
- `t_ms` before any replay shift
- OPS bin error
- SNR
- phase coherence
- bearing angle
- whether the adjacent frame is rising
- geometry angle and RMSE for candidate pairs

Then replay trial shifts such as `-40`, `-30`, `-20`, `-10`, `+10`, `+20`,
`+30`, and `+40 ms`. A shift that recovers a two-frame pair is evidence that
the radar data is present but impact alignment is off. A shift that makes a
single frame match TrackMan is weaker; log it separately because a one-frame
solution can be moved around by timing.

Use the OPS transition fields in `rolling_buffer_capture` to understand which
impact instant the live K-LD7 path used:

- `impact_source`
- `impact_timestamp_ms`
- `impact_offset_from_trigger_ms`
- `impact_last_club_center_ms`
- `impact_first_ball_center_ms`
- `impact_speed_delta_mph`
- `impact_transition_gap_ms`
- `impact_reason`

`impact_source="ops_transition"` means the midpoint between the last club-like
OPS frame and first ball-like OPS frame was used. `impact_source="sound_trigger"`
means the transition was missing or failed the speed-delta threshold.

Keep timing-replay summaries split by frame count. A session summary should show
MAE for production two-frame shots, timing-recoverable two-frame shots,
one-frame diagnostics, and true misses separately. Mixing one-frame adjusted
shots into the production geometry MAE hides the most important risk.

## After A Session

1. Copy OpenFlight JSONL, Trackman CSV, and any `.pkl` into `session_logs/`.
2. Run `compare_trackman.py`.
3. For K-LD7 angle misses, run `diagnose_kld7_raw_adc.py`.
4. Summarize per-club bias and detection rate:
   - ball speed bias/stddev
   - vertical launch bias/RMSE
   - horizontal launch bias/RMSE
   - spin read rate and spin delta where accepted
   - rejected spin reasons by count
   - K-LD7 valid/invalid RADC frame counts
   - K-LD7 vertical shots by bucket:
     production two-frame, timing-recoverable two-frame, one-frame diagnostic,
     and signal/clutter/off-boresight miss
5. Only tune live processing after separating:
   - pairing errors
   - hardware/throughput problems
   - stale-buffer artifacts
   - real DSP/gating problems

## Commands For Validation

Run focused checks after changing launch angle, spin, logging, or comparison
scripts:

```bash
uv run ruff check \
  src/openflight/rolling_buffer \
  src/openflight/server.py \
  src/openflight/session_logger.py \
  scripts/analysis \
  tests/test_rolling_buffer.py \
  tests/test_server.py \
  tests/test_session_logger.py \
  tests/test_compare_trackman.py

uv run pytest \
  tests/test_rolling_buffer.py \
  tests/test_session_logger.py \
  tests/test_server.py \
  tests/test_compare_trackman.py
```

For the full suite:

```bash
uv run pytest tests
```

## Related Docs

- `docs/rolling_buffer_spin_detection.md`
- `docs/kld7-session-review.md`
- `docs/kld7-troubleshooting.md`
- `docs/kld7-ball-detection-theory.md`
- `docs/observability.md`
