# OPS-Guided Vertical Recovery

The production runtime keeps frozen LCMF-v1 as its first pass, then performs a
bounded second pass when the selected TI range track differs from OPS ball
speed by more than 15% or LCMF withholds an angle. Speed-consistent first-pass
results are never revisited.

## Approach

The recovery search generates burst- and window-MTI range walks and uses only
radar/OPS observables:

- TI range-track speed relative to OPS ball speed
- range-track support, span, and fit residual
- multi-frame LCMF evidence
- agreement between the independent `two8` and `four4_path_tdm` models

Near-duplicate RANSAC lines are collapsed before at most eight candidates pass
through unchanged LCMF. A dual-model result outranks a single-model result. A
single-model recovery remains available when no corroborated candidate
survives, but its existing `single_channel` flag keeps UI confidence lower.
Results at or below 2 degrees are rejected as collapsed spatial solutions.

TrackMan launch angle is never passed to candidate generation or ranking.

## 53-Bin Holdout, 2026-08-11

The replay corpus contained 79 TrackMan-aligned 53-bin captures:

| Dataset | Baseline coverage | Baseline MAE | Recovery coverage | Recovery MAE |
|---|---:|---:|---:|---:|
| July 22 | 19/20 | 1.545 degrees | 20/20 | 1.522 degrees |
| August 9 wide IQ16 | 59/59 | 0.781 degrees | unchanged | unchanged |
| Combined | 78/79 | 0.967 degrees | 79/79 | 0.969 degrees |

The deterministic selector recovered the one naturally rejected capture at
21.702 degrees against TrackMan's 20.613 degrees, an absolute error of 1.089
degrees. Its selected track used 23 inliers across seven frames with 0.248-bin
RMS. An earlier stochastic prototype found a nearby 0.990-degree candidate;
that result is not claimed here because it changed with the random seed.

## Live Policy

- A speed-consistent accepted result remains unchanged.
- A credible OPS-matched candidate is reported as `accepted_ops_guided`.
- A one-model candidate is reported as `accepted_ops_guided_single_channel`.
- If no candidate survives, an accepted baseline remains visible as
  `accepted_track_speed_warning`; a rejected baseline remains rejected.
- Any recovery exception preserves the baseline rather than losing the shot.

## Validation

On the August 9 TrackMan-aligned corpus, the live trigger policy leaves the
known-good 53-bin distribution effectively unchanged while recovering the one
offline rejection:

| Dataset | Coverage | MAE | P50 | P75 | P90 |
|---|---:|---:|---:|---:|---:|
| Wide 53-bin IQ16 | 100% | 0.856 degrees | 0.700 | 1.055 | 1.753 |
| All August 9 captures | 100% | 1.788 degrees | 1.019 | 2.625 | 4.339 |

The 2026-08-14 low-mounted enclosure session exposed the intended failure
mode: several first-pass tracks were 20-38% faster than OPS. The second pass
changed shot 6 from 10.66 degrees on a 128.0 mph TI track to a lower-confidence
16.80 degrees on a 97.1 mph track matching OPS. Its `two8` model remained
collapsed, so a future camera observation can arbitrate that single-model
recovery rather than the radar claiming unsupported certainty.

## Remaining Risk

- Only one naturally rejected 53-bin TrackMan capture was available.
- A speed-matched ghost can still exist, especially with a very low antenna
  height and strong floor multipath.
- Single-model values need camera or additional truth validation.
- Recovery adds processing only to suspicious shots; on the August 14 Mac
  replay those shots required approximately 2-3 seconds beyond baseline.

Treat the `ops_guided_single_channel` status as a lower-confidence measured
angle, not equivalent evidence to a corroborated LCMF result.

## Offline Usage

```bash
uv run python scripts/analysis/replay_iwr6843_low_confidence.py \
  ~/openflight_sessions/session_a.jsonl \
  ~/openflight_sessions/session_b.jsonl \
  --tee-m 1.626 \
  --net-m 5.131 \
  --tilt-deg 12.1 \
  --radar-height-m 0.1524 \
  --club 9i \
  --out ~/openflight_sessions/iwr6843_recovery.jsonl
```
