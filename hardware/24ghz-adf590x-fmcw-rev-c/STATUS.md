# Rev C Status & Handoff

Latest update: 2026-07-13 — RF production package and first-article release gate.

## 2026-07-13 production update

The Rev C RF board is now a **production release candidate**:

- ERC: 0 error-level violations.
- DRC: 0 violations / 0 unconnected items.
- Netlist/PCB parity: 98 schematic components, 80 nets, 350 pad/net
  assignments, 16 intentional board fixtures.
- Deterministic rebuild: 663 tracks, 172 vias, parity pass, DRC 0/0.
- Production BOM: 33 rows, 97 fitted placements, 100% MPN coverage; C51 DNP.
- Production Gerbers, drills, X2 job, IPC-2581, BOM, CPL, schematic PDF,
  assembly PDFs, and 3D renders are in `rf-board/production-package/` and
  `rf-board/gerbers/openflight-24ghz-fmcw-rf-rev-c-production-gerbers.zip`.
- PLL loop filter corrected to the UG-866 topology and retuned; 128-corner
  analytical model passes with 50.64 degree minimum phase margin.
- RX/as-built-TX 2x2 antenna gates pass: -15.67 dB worst-band S11, 3.132
  degree phase imbalance, 10.38 dBi gain, 85.63% efficiency, 2 degree beam.

Two fabrication release holds remain:

1. PCBWay written confirmation of the exact 0.254 mm RO4350B L1-L2 hybrid
   stackup and 0.556 mm 50 ohm geometry, with no antenna/RF CAM changes.
2. PCBWay written acceptance of 0.50/0.30 mm vias with 0.10 mm annular ring.

The internal grid blocker is reclassified as a first-article qualification
item. The exact one-port control passes within 1.00 dB of the standalone model,
and all full-grid checkpoints pass the -20 dB coupling screen with a conservative
worst case of -22.95 dB. The full-grid transient did not converge, so its exact
S11/coupling values are not RF-qualification evidence. VNA and multiport checks
are mandatory before a repeat or volume build. See
`antenna/results/grid-screening-assessment.json`.

Current handoff: `RF-BOARD-HANDOFF.md`. Full production review:
`analysis/production-review-2026-07-13-final/REPORT.md`.

The historical sections below are retained for context and are superseded where
they conflict with this production update.

## Historical 2026-07-13 review checkpoint

The generated RF PCB is now fully routed and reproducible:

- KiCad DRC: **0 violations / 0 unconnected items**.
- Netlist and PCB verification: **PASS** (98 schematic components, 80 nets,
  350 pad/net assignments, 16 intentional board fixtures).
- Focused geometry/routing tests: **19 passed**.
- ERC: **0 errors**; 529 generated-schematic warnings were triaged with no new
  electrical error found.
- Review Gerbers, PTH/NPTH drills, X2 job, IPC-D-356, BOM, filtered 98-part CPL,
  assembly PDFs, layer plots, and 3D renders have been generated.
- Full report: `analysis/design-review-2026-07-13/REPORT.md`.
- Current handoff: `RF-BOARD-HANDOFF.md`.

**Verdict: ready for PCBWay design review, not ready to order.** Release blockers:

1. PCB uses a cloned 2x2 RX subarray for TX, not the specified/simulated 1x4 TX
   column; no passing TX antenna result exists.
2. RX-subarray NF2FF gain is invalid (`Prad = 1.7666e-27 W`); the old 22.79 dBi
   value is now marked untrusted and gain acceptance is false.
3. Full RX-grid mutual coupling remains unverified (`coupling_db_max: null`).
4. PCBWay's exact hybrid stackup/50-ohm geometry is still pending.
5. BOM/passive specifications are not locked (11/30 unique BOM rows have MPNs).

Review-only output paths:

- `rf-board/gerbers/openflight-24ghz-fmcw-rf-rev-c-review/`
- `rf-board/gerbers/openflight-24ghz-fmcw-rf-rev-c-review-gerbers.zip`
- `rf-board/review-package/`

The historical task status below is retained for context and is superseded where
it conflicts with this update.

Plan: `docs/superpowers/plans/2026-07-01-adf590x-active-fmcw-rev-c.md` (22 tasks)
Spec: `docs/superpowers/specs/2026-07-01-adf590x-active-fmcw-rev-c-design.md`
Execution ledger (fine-grained): `.superpowers/sdd/progress.md` + per-task briefs/reports in `.superpowers/sdd/`

## Done and review-approved (Tasks 1–5, 9–11, 14, 20)

- **T1–T2**: Package scaffold, fabrication notes with the PCBWay stackup request text (NOT YET SENT — see Actions), INTERFACE.md 30-pin contract (verified cell-by-cell, and later verified consistent across both boards' schematics).
- **T3**: Datasheet extractions for ADF5901/5904/4159/TLV320ADC3140/EV-RADAR-MMIC2 + support parts (ADP7104, ADP150, CWX113) + TI RTW0024 land data — all page-cited; 28 independent reviewer pin-checks passed. Verified orderable MPNs: ADF5901WCCPZ / ADF5904WCCPZ / ADF4159CCPZ (+`-RL7` reels), DigiKey stock confirmed.
- **T4**: openEMS toolchain — Docker image `openems-local` (from-source, pinned commit 5e007ea, h5py/matplotlib included). Canary sim PASS.
- **T5**: Patch element VALIDATED: W=4.058, L=2.970 mm, inset 0.850/gap 0.200 mm, f_res 24.187 GHz, worst-band S11 −21 dB (`antenna/results/patch_element.json`). Interim substrate 10-mil RO4350B Dk 3.66 — re-run if PCBWay's stackup table differs.
- **T9–T10**: Footprint + symbol libraries (`library/`), datasheet-grounded after three fix rounds (caught: ADP7104 symbol with all 8 pins wrong; ADP150 pin swap; wrong TCXO variant; wrong ADP7104 EP). Deep review approved (33-pin ADF5901 diff, ADF5904 pad audit, header zigzag vs INTERFACE.md).
- **T11**: RF project + power sheet — ERC 0 errors; coordinate-level regulator audit clean; rails +5V/+3V3_TX/+3V3_RX/+1V8_DIG (+5V_REG internal).
- **T14**: ADF5904 RX sheet (`rf-board/kicad/rx.kicad_sch`) — approved AFTER a fix round: review caught a fabrication-fatal short (one wire through the label column collapsed 6 of 8 baseband nets). Now netlist-proven: 8 clean differential BB nets, 33/33 pins correct.
- **T20**: ADC/Pi board schematic — approved: 25/25 pins, both connector contracts verified, Pi header vs official pinout, AA filter 97 kHz corner (values provisional pending measured ADF5904 levels), I2C 0x4C.

## In flight when session wrapped (VERIFY BEFORE TRUSTING THESE FILES)

Three agents were mid-work; their target files may be complete, partial, or unchanged:

1. **T13 VREG short fix** (`rf-board/kicad/tx.kicad_sch`): FIX LANDED at session end, netlist-verified by the fix agent — `Net-(U5-VREG)` = exactly {U5.18, C58.2}; C58.1 on GND; DVDD trunk rerouted to y=57.15; ERC back to pre-existing boundary artifacts only; no other pin's net membership changed. The earlier DVDD triad (C18–C20) is also verified. **Remaining: one final reviewer sign-off pass on the sheet (the fix agent's own netlist evidence is strong, but the sheet has had three defect rounds — a fresh-eyes re-audit before Task 15 integration is warranted).**
2. **T12 level-shifter fix** (`rf-board/kicad/pll.kicad_sch` + library): LANDED at session end, netlist-verified by the fix agent — U7 SN74AVC4T245 (TSSOP-16, 3.3→1.8 V for SCLK/SDATA/LE/CE) and U8 SN74AVC2T245 (UQFN-10 — datasheet corrected the brief's "UQFN-12"; 1.8→3.3 V for MUXOUT→RAMP_SYNC), stock footprints, decoupling per TI, sheet-boundary labels unchanged. All four shifted paths netlist-traced; **no 3.3 V net touches any ADF4159 digital pin** — the abs-max violation is eliminated. SDO decision: MUXOUT→RAMP_SYNC only; SPI_SDO stays with ADF5904 DOUT (matches INTERFACE.md). **Remaining: the full Task 12 review has NOT run** (implementation + fix are both unreviewed as a whole — dispatch the task reviewer before Task 15; include the loop filter values, TCXO/REFIN coupling, supply-domain mapping, and the new shifter wiring in its audit scope).
3. **T21 ADC board layout** (`adc-board/kicad/*.kicad_pcb`): reported DONE_WITH_CONCERNS at session end. Placement, 4-layer stackup (55×65 mm, Pi-HAT mount spacing), net map (schematic↔PCB sync clean), pours, fiducials: all done and verified. **Routing is NOT DRC-clean: 276 real violations** (mostly B.Cu lanes crossing the J2 40-pin THT field + analog crossings near U1); the agent stopped per its non-convergence rule instead of thrashing. Next step is re-routing ~11 J2-bound nets and the analog crossings — placement can be kept. Gotcha recorded: `pcbnew.SaveBoard()` wipes the .kicad_pro net classes; re-run `scratchpad/patch_pro.py` after any scripted board write (already applied to the on-disk state). Cross-analysis flagged 2 I2S return-path findings to address during re-route.

## Not started

- **T15**: Root-sheet integration (instantiate pll/tx/rx/io sheets, wire J1 stubs) + the full-schematic verification gate. IMPORTANT: add netlist net-membership assertions for every supply/decoupling node — this session proved coordinate traces and ERC both miss misplaced-GND shorts; only netlist assertions caught/proved the VREG and BB-short defects.
- **T16–T19**: RF board layout chain — blocked on antenna geometry (see below) + T15.
- **T22**: Fabrication outputs + order package (kicad-cli-exported gerbers only, PCBWay BOM/CPL, final checklist).
- **Sim track T6–T8**: parked — see the dedicated section below and `antenna/SIM-STATUS.md`.

## Simulation work remaining (T6–T8) — the antenna gate

The patch **element** is validated (T5). What's missing is everything built from it:

1. **T6 — 2×2 subarray feed (the blocker).** Topology is now correct (co-oriented
   patches, exactly equal path lengths, radiates broadside) but the root port sees
   |S11| ≈ −0.4 dB — near-total reflection. Debug sequence, in order, all with SHORT
   sims (−30 dB criterion, small domains):
   a. Port reference-plane audit (code check, no sim): confirm the MSL measurement
      plane sits on the 50 Ω root feed line, not inside the λ/4 transformer, and mesh
      lines land on transformer step edges.
   b. Extract complex Zin(f) at the root (one fast run): near-short ⇒ resonant artifact
      (meander self-coupling, junction stub); smooth wrong-R ⇒ transformer mistuning.
   c. Isolate a 1×2 column (half domain, ~7 min/run): match that stage first.
   d. Meander audit: the inner-column equalizing fold may couple to itself if spacing
      < ~3 line widths.
   e. Fallback architecture: retune inset for ~100 Ω elements, parallel two → 50 Ω at
      the column junction (no transformer there), single 35.4 Ω λ/4 at the root only.
   Partial debug scripts already exist: `antenna/debug_column.py`, `debug_single_branch.py`.
   Acceptance (unchanged): root S11 ≤ −10 dB across 24.150–24.250 GHz, ≤5° co-pol phase
   imbalance, ≥9 dBi. Output: `results/subarray.json` (currently holds FAILING numbers).
   **2026-07-02 update:** the 100Ω direct-column fallback was simulated. It passes
   root match but still fails co-phasing and gain: right-delay enabled = S11 −14.41 dB
   PASS, phase 162.2° FAIL, gain 4.84 dBi FAIL; right-delay disabled = S11 −13.02 dB
   PASS, phase 166.8° FAIL, gain −2.88 dBi FAIL. Do not keep iterating the compact
   row-gap delay without a topology change.
2. **T7 — TX 1×4 series-fed column.** Parked mid-iteration: bottom-patch inset shows
   Zin ≈ R − j39 Ω (series C from asymmetric inset + link loading); a link-length sweep
   (frac 0.40/0.46) was running when killed. Consider edge-feed + transformer instead of
   inset if the reactance won't null. Acceptance: S11 ≤ −10 dB across band, ~10–12 dBi,
   beam broadside ±3° at 24.2 GHz; also record EIRP vs FCC 15.245/249. Output:
   `results/tx_column.json`.
3. **T8 — grid mutual coupling** (unstarted, needs T6): 4 subarrays at 12.5 mm pitch,
   coupling ≤ −20 dB, emits the frozen phase-center coordinates layout consumes.
   Output: `results/grid.json`.
4. **Re-run trigger:** when PCBWay's stackup table arrives, if h/Dk differ from the
   simulated 10-mil/3.66 assumption, T5–T8 re-run from the calculator (env overrides
   exist in `sim_patch.py`; ~+0.7 GHz per −0.05 mm L trim).

Run discipline (full rationale in `antenna/SIM-STATUS.md`): one sim at a time, detached
with a progress log (`nohup docker run … > results/<name>.log &`), −30 dB criterion for
iteration / −40 dB once for the record, ~6-iteration cap before re-diagnosing, overnight
queue for the full T6→T7→T8 chain. Escape hatch if sims stay stuck: PCBWay vendor RF
review + the VNA coupon strip can stand in as the antenna verification, but T16/T17
still need *some* signed-off geometry JSONs to place copper.

## Missing information before gerbers can be generated (T22 gate)

Gerbers are exported by `kicad-cli` from finished layouts, so everything below is really
"what the layouts still need":

**RF board (`rf-board/`):**
1. **PCBWay stackup table** — REQUEST NOT YET SENT (text ready in `fabrication-notes.md`).
   Gates three things: final patch/feed dimensions (sim re-run if different), the exact
   50 Ω microstrip width (0.55 mm assumed — PCBWay must confirm for their build), and
   final board thickness. Without it, any exported gerber has unverifiable RF geometry.
2. **Antenna geometry JSONs** (`subarray.json` passing, `tx_column.json`, `grid.json`) —
   T17 generates the antenna copper 1:1 from these; no JSONs, no antenna copper.
3. **Schematic closure**: T12 full review (never ran — implementation + level-shifter fix
   are unreviewed as a whole), T13 fresh-eyes sign-off (three defect rounds on that
   sheet), then T15 root integration (io sheet + sheet instances + J1 stub wiring +
   zero-error ERC + analyzer pin-level diff + netlist net-membership assertions on every
   supply/decoupling node).
4. **Layout itself**: T16 (outline incl. 12×50 mm coupon strip, placement, mounting
   holes, fiducials), T17 (antenna copper import), T18 (RF routing, planes, via fences,
   length-matched RX feeds ≤0.5 mm delta), T19 (DRC zero-violation/zero-unconnected gate
   + full analyzer suite + user checkpoint).
5. Housekeeping that blocks the *order* but not the export: cap refdes renumber (semantic
   C2I/C2O names), 100 pF DC-block verification, ADIsimPLL loop-filter check, BOM/CPL
   generation (PCBWay format), chirp-band top-edge decision (register-level only).

**ADC board (`adc-board/`):**
1. **ADC fabrication package exists.** The ADC/Pi board was rerouted through the remaining
   analog, BB, I2S/I2C, +3V3, testpoint, and GND-island issues. Fresh DRC is **0
   error-level violations / 0 unconnected items**. Warning-inclusive DRC still reports
   four coordinate-less `copper_sliver` warnings on F.Cu; these are the only remaining
   DRC output and should be visually reviewed or explicitly waived before ordering.
2. **Generated outputs:** Gerbers/drills are in
   `adc-board/gerbers/openflight-adc-pi-interface-rev-c/`; order zip is
   `adc-board/gerbers/openflight-adc-pi-interface-rev-c-gerbers.zip`. Gerber analyzer
   result: complete expected layers, PTH + NPTH drill present, aligned layers, zero
   findings (`gerber-analysis.json`).
3. **Export discipline:** run `kicad-cli pcb drc --refill-zones --save-board` before
   Gerber export so zone fills are persisted. Do **not** use `pcb export ... --check-zones`
   on this macOS/KiCad 10.0.4 setup; it aborts during zone fill. Export without
   `--check-zones` after the saved-zone DRC step.
4. Tooling note: any scripted `pcbnew.SaveBoard()` write may wipe the `.kicad_pro` net
   classes — re-check net classes afterward.

## Open items for the pre-order checklist (Task 22)

- 100 pF DC-block value on all 24 GHz RF/LO paths (TX + RX sheets) is an engineering choice — NOT dimensioned in the eval BOM (both reviewers confirmed). Verify against ADI eval hardware/vendor guidance before ordering.
- Loop filter values are eval-board defaults — re-verify with ADIsimPLL for Rev C's actual chirp (100 MHz / 150 µs).
- Semantic cap refdes (C2I/C2O style on power sheet) need renumbering before BOM lock.
- ADC AA corner shifts DOWN (~67 kHz) with ADF5904's ~900 Ω source impedance — recompute/refit at bring-up (sites are DNP-flexible).
- FCC 15.245/249 EIRP check once TX column gain is simulated/final.
- Chirp top edge 24.250 GHz sits at the MMICs' exact operating max — consider shifting band down ~5 MHz (guard to OPS shrinks 25→20 MHz, still enormous); register-level decision, no hardware impact.

## Actions for Coleman

1. **Send the PCBWay stackup request** (text ready in `fabrication-notes.md`) — its reply gates final antenna dimensions and the T16 layout.
2. **Commit the work** — everything is untracked files on `main` (per your no-agent-commits preference): `hardware/24ghz-adf590x-fmcw-rev-c/`, `docs/superpowers/{specs,plans}/2026-07-01-*`, and optionally `.superpowers/sdd/` (session scratch; the ledger inside it is the resume map).
3. Decide sim-track fate: resume per `antenna/SIM-STATUS.md` (overnight detached run recommended) or lean on vendor review + coupon.

## Process lessons this session (why the review gates stayed strict)

Real defects caught by review/fix rounds that would each have killed or crippled a $700 board: ADP7104 all-pins-wrong symbol; ADF4159 3.3 V abs-max violation (missing level shifters); RX baseband 6-net short; TX VREG-to-GND short; wrong TCXO variant; wrong ADP7104 EP. Hand-authored KiCad gotchas for future sessions: symbol-instance pin Y-inversion (global = unit_y − local_y); `;;` comments break KiCad 10's parser; ERC cannot see power_out-to-GND shorts; never bucket ERC warnings (`multiple_net_names` is never benign); netlist net-membership assertions are the only trustworthy gate.
