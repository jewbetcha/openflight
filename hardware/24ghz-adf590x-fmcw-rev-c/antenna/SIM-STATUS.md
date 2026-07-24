# Antenna Simulation Status & Resumption Guide

Updated 2026-07-01. Sim track paused mid-plan (Tasks 6–8) at user request — runs
were slow and progress was opaque. This note records exactly where each sim
stands and how to make the next attempt run smoothly.

## Status by task

| Task | State | Detail |
| --- | --- | --- |
| T5 patch element | **DONE / PASSED** | W=4.058, L=2.970 mm, inset 0.850/gap 0.200, f_res 24.187 GHz, worst-band S11 −21 dB. `results/patch_element.json` is valid and consumed downstream. |
| T6 2×2 subarray feed | **PARKED — failing** | Round 1: mirror-fed pairs cancelled (fixed). Round 2: co-phase translational topology radiates (path lengths exactly equal) but root S11 −0.41 dB — near-total reflection. Round 3: 100Ω direct-column fallback matches but does not co-phase. With right delay enabled: worst-band S11 −14.41 dB PASS, phase imbalance 162.2° FAIL, broadside gain 4.84 dBi FAIL. With right delay disabled: worst-band S11 −13.02 dB PASS, phase imbalance 166.8° FAIL, broadside gain −2.88 dBi FAIL. Diagnosis: the direct-column fallback fixes match but leaves a left/right column phase inversion; the compact row-gap right delay is too coupled/asymmetric to solve it. `results/subarray.json` holds FAILING numbers — do not consume. |
| T7 TX 1×4 column | **PARKED — mid-iteration** | Bottom-patch inset shows Zin ≈ R − j39 Ω (series C from asymmetric inset + link loading). A link-length sweep (frac 0.40/0.46) was running when killed. `sim_tx_column.py` on disk. |
| T8 grid coupling | **NOT STARTED** | Blocked on T6. |

## Next debugging steps (T6, in order)

1. Port reference-plane audit: confirm the MSL port measurement plane sits on
   the 50 Ω root feed line, not inside the root quarter-wave transformer, and
   that mesh lines land on transformer step edges.
2. Extract complex Zin(f) at the root — near-short vs. smoothly-wrong-R
   distinguishes a resonant artifact (meander coupling, junction stub) from
   genuine transformer mistuning.
3. Isolate a 1×2 column (half domain, ~half runtime): match that first.
4. Meander audit: the inner-column equalizing fold may couple to itself
   (spacing < ~3 line widths at 24 GHz = strong coupling).
5. Fallback architecture that removes the hardest stage: retune patch inset
   for ~100 Ω element Zin, parallel two at the column junction → 50 Ω directly,
   single 35.4 Ω λ/4 at the root only. Fewer impedance steps, wider tolerance.
6. New 2026-07-02 result: the fallback architecture passes S11 but fails
   broadside addition. Do not keep iterating the compact row-gap delay. Next
   viable topology work should either (a) redesign the same-edge corporate feed
   with a true non-coupled right-column phase delay or (b) switch to the
   documented vendor-review/VNA-coupon escape hatch.

## How to make sims run smoothly (lessons from this session)

- **One sim at a time.** Agents ran up to 6 containers concurrently; CPU
  contention made every run slower than sequential execution.
- **Detach + progress file, don't poll.** Launch as
  `nohup docker run --rm -v "$PWD":/work -w /work openems-local python3 <sim> > antenna/results/<name>.log 2>&1 &`
  and have the sim print one line per 10k timesteps (timestep, energy dB) —
  progress becomes a `tail -1` instead of a mystery. The openEMS `RunOpenEMS`
  verbose flag plus an explicit print in the convergence loop does this.
- **Two-tier convergence.** Iterate geometry at −30 dB energy criterion
  (~2–4 min); pay for −40 dB only on the final for-the-record run (~14 min for
  the full 2×2).
- **Budget iterations up front.** Cap any agent at ~6 design iterations before
  stopping to re-diagnose; the T6/T7 failure mode was open-ended iteration
  loops babysitting long runs.
- **Small domains first.** Single element ≈ 40 s; 1×2 column ≈ 7 min; full 2×2
  ≈ 14 min. Debug at the smallest scale that reproduces the problem.
- **Overnight option.** The full T6→T7→T8 chain can run unattended: queue the
  scripts sequentially in one detached shell script writing per-stage logs, and
  review results in the morning.
- **Known toolchain facts.** Image `openems-local` (pinned commit 5e007ea,
  h5py+matplotlib included). `AddLumpedPort` terminations do NOT work in this
  build — MSL ports + field probes only. KiCad/macOS quirk does not apply to
  docker, but keep kicad-cli invocations as fresh single commands.

## If sims stay parked

The spec's antenna-verification constraint can still be met before fab via:
PCBWay written stackup + their vendor RF review of the antenna copper, plus the
VNA coupon strip panelized on the board (Task 16 Step 3). EM sim remains the
cheapest first check, but it is not the only gate. Layout Tasks 16–17 consume
`results/subarray.json`, `tx_column.json`, `grid.json` — those tasks block
until this track resumes or the geometry is signed off another way.
