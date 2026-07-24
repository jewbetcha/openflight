# ADF590x Active FMCW Radar Rev C Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Design the Rev C active 24 GHz FMCW radar as two native-KiCad boards — an ADF5901/ADF5904/ADF4159 RF board on hybrid Rogers and a revised TLV320ADC3140 ADC/Pi board on FR4 — ready for a PCBWay order that passes every validation gate in the approved spec.

**Architecture:** Faithful port of ADI's radar chipset reference design; custom work limited to antennas (EM-simulated against the PCBWay-confirmed stackup), board outline, connector, and power entry. All fabrication artifacts are exported from KiCad by `kicad-cli` — the `generate_designs.mjs` pipeline is retired.

**Tech Stack:** KiCad 10 (`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`, 10.0.4), openEMS (conda-forge; Docker fallback) for antenna EM simulation, Python via `uv run` for design calculators, kicad skill analyzers (`.claude/skills/kicad/scripts/`) for verification.

**Spec:** `docs/superpowers/specs/2026-07-01-adf590x-active-fmcw-rev-c-design.md` — read it before starting any task.

## Global Constraints

- Chirp band 24.150–24.250 GHz; ≥25 MHz guard to the OPS243 carrier at 24.125 GHz.
- Must observe targets to 200 mph: slope such that range beat dominates ±14.4 kHz Doppler at ≥2 m; nominal 100 MHz / 150 µs.
- Antenna geometry verified three ways: openEMS sim on the confirmed stackup + written PCBWay stackup + VNA coupon strip on the same board outline.
- Raw bit-exact 4-channel capture at the Pi (ALSA `hw`, 384 kHz default); ADF5904 outputs are real-valued; software derives I/Q per chirp.
- Cost: RF board ≤ ~70×50 mm hybrid RO4350B/FR4 4-layer, 0402 passives, single-side placement, 2-of-5 assembled.
- Patch calculations use Rogers **design Dk 3.66**, not process Dk 3.48.
- All Python via `uv` (`uv run ...`), never bare `python`/`pip`. New Python deps go into `pyproject.toml`.
- **No commits by the executing agent.** The user commits. Each task ends by reporting completed work; checkpoint tasks pause for user review.
- Never state a datasheet-derived value without a page/table citation recorded in `hardware/24ghz-adf590x-fmcw-rev-c/datasheets/extracted/`.
- KiCad files are authored as S-expression text, but every artifact must load cleanly in KiCad: `kicad-cli` runs (ERC/DRC/export) are the acceptance test for file validity. macOS quirk (from Rev B2 README): run each `kicad-cli` invocation as its own fresh Bash call, never chained after another command.

---

## File Structure

```
hardware/24ghz-adf590x-fmcw-rev-c/
├── README.md                     # package status, validation commands
├── INTERFACE.md                  # connector pinout + Pi interface (contract, Task 2)
├── fabrication-notes.md          # PCBWay order guidance + stackup request/response
├── BOM.md                        # human-readable BOM summary
├── datasheets/                   # PDFs (curl-downloaded, gitignored)
│   └── extracted/                # *.md extraction notes WITH page cites (committed)
├── antenna/
│   ├── patch_design.py           # closed-form patch calculator
│   ├── sim_patch.py              # openEMS: single element
│   ├── sim_subarray.py           # openEMS: 2x2 + corporate feed
│   ├── sim_tx_column.py          # openEMS: 1x4 series-fed TX column
│   ├── sim_grid_coupling.py      # openEMS: 4-subarray mutual coupling
│   ├── geometry_to_footprint.py  # emits .kicad_mod from validated geometry JSON
│   └── results/*.json            # geometry + S-parameter results (committed)
├── library/
│   ├── openflight-revc.kicad_sym
│   └── openflight-revc.pretty/*.kicad_mod
├── rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.{kicad_pro,kicad_sch,kicad_pcb}
├── rf-board/gerbers/ + openflight-24ghz-fmcw-rf-rev-c-gerbers.zip
├── adc-board/kicad/openflight-adc-pi-interface-rev-c.{kicad_pro,kicad_sch,kicad_pcb}
└── adc-board/gerbers/ + openflight-adc-pi-interface-rev-c-gerbers.zip
```

Task dependency shape: Tasks 1–3 ground everything. Antenna track (4–8) and schematic track (9–15) can run in parallel; layout (16–19) needs both; ADC board (20–21) needs only Task 2; order package (22) needs everything.

---

## Task 1: Scaffold Rev C package and fabrication notes

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/README.md`
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/fabrication-notes.md`
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/.gitignore`

**Interfaces:**
- Produces: directory layout above; the PCBWay stackup request text (external gate for Tasks 5–8 dimension freeze).

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p hardware/24ghz-adf590x-fmcw-rev-c/{datasheets/extracted,antenna/results,library/openflight-revc.pretty,rf-board/kicad,rf-board/gerbers,adc-board/kicad,adc-board/gerbers}
```

- [ ] **Step 2: Write README.md**

Content must state: Rev C is an active FMCW two-board design (link the spec); native KiCad authored, `generate_designs.mjs` retired; validation = `kicad-cli` ERC/DRC + kicad-skill analyzers; status = in design, not ordered. Include the band plan line: "TX 24.150–24.250 GHz, ≥25 MHz below/above nothing — OPS243 at 24.125 GHz stays outside the chirp band."

- [ ] **Step 3: Write fabrication-notes.md with the stackup request**

Include verbatim, marked as the message to send to the PCBWay rep (Chloe thread):

```text
Requesting a hybrid-stackup quote and exact stackup table for a 4-layer RF board:
- Size ~70 x 50 mm, qty 5, 2 boards assembled (turnkey; BOM/CPL to follow)
- L1-L2 dielectric: Rogers RO4350B core, 10 mil / 0.254 mm (RF layer pair)
- L2-L3, L3-L4: standard FR4 prepreg/core, total thickness 1.0-1.6 mm (your standard hybrid build)
- Copper: 0.5 oz outer, 1 oz inner acceptable
- Finish: ENIG. Soldermask green; mask pulled back from antenna/RF copper per gerbers.
- Controlled impedance: 50 ohm microstrip on L1 referenced to L2 (please confirm trace width for your build)
Please send the exact stackup table (dielectric heights, Dk/Df at 10+ GHz, copper weights) — antenna dimensions will be finalized from it.
```

Also record: interim design assumption is 10 mil RO4350B, design Dk 3.66, Df 0.0037; any delta in the returned table triggers re-running Tasks 5–8 sims.

- [ ] **Step 4: Write .gitignore**

```
datasheets/*.pdf
rf-board/gerbers/
adc-board/gerbers/
```

- [ ] **Step 5: Verify and report**

Run: `find hardware/24ghz-adf590x-fmcw-rev-c -type f | sort` — expect the three files. Report to user: the stackup request text is ready to send to PCBWay; sims proceed on the interim assumption meanwhile.

---

## Task 2: Define the board-to-board interface contract

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/INTERFACE.md`

**Interfaces:**
- Produces: the exact 2×15 connector pinout table below. Tasks 13–15 (RF schematic), 20 (ADC schematic) wire nets to these exact pin numbers and net names. Do not deviate from it without updating this file first.

- [ ] **Step 1: Write INTERFACE.md with this exact pinout**

2×15 header, 1.27 mm pitch, SMD, pin 1 marked. Odd pins row A, even pins row B.

| Pin | Net | Pin | Net |
| --- | --- | --- | --- |
| 1 | +5V | 2 | +5V |
| 3 | GND | 4 | GND |
| 5 | BB1_P | 6 | BB1_N |
| 7 | GND | 8 | GND |
| 9 | BB2_P | 10 | BB2_N |
| 11 | GND | 12 | GND |
| 13 | BB3_P | 14 | BB3_N |
| 15 | GND | 16 | GND |
| 17 | BB4_P | 18 | BB4_N |
| 19 | GND | 20 | GND |
| 21 | SPI_SCLK | 22 | SPI_SDATA |
| 23 | SPI_SDO | 24 | GND |
| 25 | LE_5901 | 26 | LE_5904 |
| 27 | LE_4159 | 28 | CE_RX |
| 29 | TX_EN | 30 | RAMP_SYNC |

Semantics to document: `CE_RX` drives ADF5904 + ADF4159 chip enables; `TX_EN` drives ADF5901 CE only (hardware TX/LO kill); `RAMP_SYNC` is ADF4159 MUXOUT → Pi GPIO; `SPI_SDO` is the shared readback (ADF5904 DOUT / ADF4159 MUXOUT mux — final wiring per datasheet extraction, documented here when Task 3 lands). Also carry over the ADC-board→Pi table from Rev B2 `INTERFACE.md` (I2S_BCLK/LRCLK/DIN, I2C, SHDNZ, 3V3/5V/GND) plus one new line: `RAMP_SYNC → Pi GPIO (timestamping)`. Include the raw-capture contract: ALSA `hw` device, 384 kHz default, 32-bit slots, no dmix/resampling, 4 channels bit-exact.

- [ ] **Step 2: Verify**

Pinout table has 30 positions, 8 BB nets each adjacent to a GND, and every control net used later in Tasks 13–15/20 appears exactly once.

---

## Task 3: Download datasheets and extract verified design values

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/datasheets/extracted/{adf5901,adf5904,adf4159,tlv320adc3140,ev-radar-mmic2}.md`

**Interfaces:**
- Produces: the single source of truth for every datasheet-derived value. Downstream tasks reference these files by section name. Each extraction note must contain, with page/table cites: full pin table (number→name→function), package + exposed-pad dimensions and ADI/TI recommended land pattern, supply rails and max currents, application-circuit component values (loop filter, reference oscillator frequency and part, decoupling network, RF matching/coupling, baseband output stage, LDO parts used on the eval board), register map summary and power-up sequence, LO input frequency/power range (ADF5904), TX output power (ADF5901), REFIN range and MUXOUT modes (ADF4159).

- [ ] **Step 1: Download the PDFs**

```bash
cd hardware/24ghz-adf590x-fmcw-rev-c/datasheets
curl -fLO https://www.analog.com/media/en/technical-documentation/data-sheets/ADF5901.pdf
curl -fLO https://www.analog.com/media/en/technical-documentation/data-sheets/ADF5904.pdf
curl -fLO https://www.analog.com/media/en/technical-documentation/data-sheets/ADF4159.pdf
curl -fLO https://www.ti.com/lit/ds/symlink/tlv320adc3140.pdf
```

Then locate and download the EV-RADAR-MMIC2 user guide (search analog.com for "EV-RADAR-MMIC2 user guide UG PDF"; it contains the full reference schematic). If any URL 404s, find the current one via web search — do not proceed without all five documents.

- [ ] **Step 2: Read each PDF and write the extraction notes**

Use the Read tool with `pages` on each PDF. One `extracted/*.md` per document covering every item in the Produces list, each value followed by `(p.N, Table M)`. Flag any spec assumption the datasheet contradicts (e.g., LO power range, supply currents vs the spec's ~600 mA estimate) in a `## Spec deltas` section.

- [ ] **Step 3: Verify extraction completeness**

Checklist inside each note, all checked: pin table row count equals package lead count; EP size present; land pattern present; application circuit values present; power-up sequence present. Report any `## Spec deltas` to the user immediately.

---

## Task 4: Install openEMS and run a canary simulation

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_canary.py`

**Interfaces:**
- Produces: a working `uv run python -c "import openEMS"` (or documented Docker invocation) that Tasks 5–8 use.

- [ ] **Step 1: Try conda-forge install**

```bash
brew install micromamba 2>/dev/null || true
micromamba create -y -n openems -c conda-forge python=3.11 openems csxcad
micromamba run -n openems python -c "import openEMS, CSXCAD; print('openEMS OK')"
```

Expected: `openEMS OK`. If conda-forge has no arm64 build, fallback:

```bash
docker pull ghcr.io/thliebig/openems:latest
docker run --rm ghcr.io/thliebig/openems:latest python3 -c "import openEMS; print('openEMS OK')"
```

Record which path worked in `antenna/README` note inside `sim_canary.py` docstring; all sim scripts must run under that environment (`micromamba run -n openems python ...` or the docker equivalent with `-v "$PWD":/work`).

- [ ] **Step 2: Write and run the canary**

`sim_canary.py`: simulate a 50 Ω microstrip line (10 mm long, width 0.55 mm) on 0.254 mm εr 3.66 substrate, 20–28 GHz, one excitation port, one measurement port; assert |S21| > −1 dB and |S11| < −15 dB at 24.2 GHz. Run it. Expected: PASS printed with the two values. This validates the toolchain and the port setup pattern the later sims reuse.

---

## Task 5: Patch element design and simulation

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/patch_design.py`
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_patch.py`
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/results/patch_element.json`

**Interfaces:**
- Produces: `results/patch_element.json` = `{"f0_ghz": float, "W_mm": float, "L_mm": float, "inset_mm": float, "feed_w_mm": float, "substrate": {"h_mm": 0.254, "er": 3.66, "tand": 0.0037}, "s11_db_at_f0": float, "band_s11_db": {"24.15": float, "24.25": float}}`. Tasks 6–8 and 17 consume it verbatim.

- [ ] **Step 1: Write the closed-form calculator**

`patch_design.py` (plain Python, runs under `uv run`): standard rectangular-patch synthesis — W = c/(2·f0)·sqrt(2/(εr+1)); εeff via Hammerstad; ΔL via the standard fringing formula; L = c/(2·f0·sqrt(εeff)) − 2ΔL; inset depth for 50 Ω from the cos² input-resistance model; 50 Ω microstrip feed width via Hammerstad-Jensen (expect ≈0.55 mm on this substrate). Target f0 = 24.200 GHz. Print all dimensions.

- [ ] **Step 2: Run it**

`uv run python hardware/24ghz-adf590x-fmcw-rev-c/antenna/patch_design.py` — expect W ≈ 4.0–4.6 mm, L ≈ 3.1–3.4 mm. Sanity-check against the Rev B2 review estimate (4.15×3.25 mm computed ≈2–3% low).

- [ ] **Step 3: Write and run the openEMS element sim**

`sim_patch.py`: geometry from the calculator, lumped port at the inset feed, frequency sweep 23.5–25.0 GHz, ground plane 3λ padding, MSL feed de-embedded. Iterate L (calculator is a starting point): adjust until resonance within 24.20 ± 0.05 GHz. Acceptance: |S11| ≤ −10 dB across 24.150–24.250 GHz.

- [ ] **Step 4: Write results JSON and report**

Emit `results/patch_element.json` in the exact schema above. Report final dimensions and S11 values to the user (constraint #2 — geometry is triple-checked; this is check one).

---

## Task 6: 2×2 subarray with equal-length corporate feed

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_subarray.py`
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/results/subarray.json`

**Interfaces:**
- Consumes: `results/patch_element.json`.
- Produces: `results/subarray.json` = `{"element": <patch_element contents>, "pitch_mm": 6.2, "feed_tree": [{"seg": "name", "w_mm": float, "l_mm": float, "z_ohm": float}], "port_s11_db": {...}, "phase_balance_deg_max": float, "gain_dbi_est": float, "extent_mm": [x, y]}`.

- [ ] **Step 1: Design the feed tree**

Elements at 6.2 mm pitch (0.5λ at 24.2 GHz). H-tree: two 2-way splits. Each 2-way junction: two 50 Ω branches in parallel → 25 Ω, matched back to 50 Ω through a quarter-wave 35.4 Ω transformer (width from Hammerstad-Jensen, ≈0.95 mm; λg/4 ≈ 1.9 mm on this substrate — compute exactly in the script). All branch pairs mirror-symmetric so path lengths are equal by construction. Feed point at the tree root, patches fed at their inset points.

- [ ] **Step 2: Simulate**

Acceptance: root-port |S11| ≤ −10 dB across 24.150–24.250 GHz; max inter-element phase imbalance ≤ 5° at 24.2 GHz (probe fields or split simulations per branch); broadside gain ≥ 9 dBi estimate from the far-field NF2FF box.

- [ ] **Step 3: Emit results JSON, report numbers to user**

---

## Task 7: TX 1×4 series-fed column

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_tx_column.py`
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/results/tx_column.json`

**Interfaces:**
- Consumes: `results/patch_element.json`.
- Produces: `results/tx_column.json` (same shape as subarray.json, plus `"eirp_check": {"pa_dbm": <from adf5901.md extraction>, "gain_dbi": float, "eirp_dbm": float}`).

- [ ] **Step 1: Design and simulate**

Four patches vertically at λg spacing connected by high-impedance (100 Ω, ≈0.16 mm) series links, fed at the bottom; standard series-fed column. Acceptance: |S11| ≤ −10 dB across band, gain ≈ 10–12 dBi, main beam broadside ±3°.

- [ ] **Step 2: EIRP check**

Compute EIRP = PA output (from `extracted/adf5901.md`, cited) + simulated gain. Record in JSON. If EIRP > +20 dBm, flag to user for the FCC 15.245/249 check noted in the spec.

---

## Task 8: RX grid mutual coupling

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_grid_coupling.py`
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/results/grid.json`

**Interfaces:**
- Consumes: `results/subarray.json`.
- Produces: `results/grid.json` = final RX aperture geometry: 4 subarrays, phase centers at (±6.25, ±6.25) mm relative to grid center (12.5 mm pitch), worst-case inter-subarray coupling in dB, and the absolute phase-center coordinates Task 17 places on the board.

- [ ] **Step 1: Simulate the 2×2 grid of subarrays**

Excite one subarray port, measure S21 into the other three. Acceptance: coupling ≤ −20 dB across the band. If it fails, increase pitch in 0.5 mm steps (max 13.5 mm — note the AoA ambiguity tradeoff in the JSON if moved) and re-run.

- [ ] **Step 2: Emit grid.json; report the frozen aperture geometry**

State explicitly in the report: these dimensions remain provisional until the PCBWay stackup table (Task 1 gate) matches the simulated substrate; if it differs, Tasks 5–8 re-run from the calculator with new h/εr.

---

## Task 9: Footprint library

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/library/openflight-revc.pretty/*.kicad_mod` — one per: ADF5901, ADF5904, ADF4159, TLV320ADC3140 (WQFN-24), interface header (2×15 1.27 mm SMD), TCXO, each LDO package, plus any connector the ADC board carries over.

**Interfaces:**
- Consumes: land-pattern sections of `datasheets/extracted/*.md` (Task 3).
- Produces: footprint names referenced by Task 10 symbols, e.g. `openflight-revc:ADF5904_LFCSP32`, `openflight-revc:HDR_2x15_1.27MM_SMD`.

- [ ] **Step 1: Author each IC footprint from its recommended land pattern**

For each LFCSP/WQFN: pad size/pitch/EP exactly per the extraction note (cite in a `descr` field), EP paste windowed 4-quadrant at ~70% coverage, thermal via grid in the EP (0.3 mm drill / 0.6 mm pad, count per the land-pattern doc — this fixes the Rev B2 floating-EP defect), courtyard 0.25 mm, 3 fiducial-visible pin-1 marks. Passives use stock KiCad `Resistor_SMD:R_0402_1005Metric` / `Capacitor_SMD:C_0402_1005Metric` — do not re-create those.

- [ ] **Step 2: Validate footprints**

Run (fresh shell, one command): `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli fp validate hardware/24ghz-adf590x-fmcw-rev-c/library/openflight-revc.pretty 2>&1 || true` — if `fp validate` is unavailable in 10.0.4, instead create a scratch board containing every footprint and run DRC on it (see Task 19 DRC command). Acceptance: zero footprint errors; for each IC, pad count == datasheet lead count + 1 (EP).

- [ ] **Step 3: Cross-check one footprint manually**

Pick ADF5904: list pad numbers/positions from the `.kicad_mod` and diff against the extraction note's pin table order around the package. Any mismatch is a stop-the-line bug.

---

## Task 10: Symbol library

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/library/openflight-revc.kicad_sym`

**Interfaces:**
- Consumes: pin tables from `datasheets/extracted/*.md`.
- Produces: symbols `ADF5901`, `ADF5904`, `ADF4159`, `TLV320ADC3140`, `HDR_2x15` with pin numbers/names exactly matching the extractions; `Footprint` field set to the Task 9 names; `MPN`, `Manufacturer`, `Datasheet` fields populated (ADF5901WCCPZ / ADF5904ACPZ / ADF4159CCPZ / TLV320ADC3140IRTE — confirm exact orderable suffixes against the extractions and record them in BOM.md later).

- [ ] **Step 1: Author symbols** — every pin present including EP (pin number = lead count + 1, electrical type `power_in` for EP/GND, `passive` for RF, per extraction function column).

- [ ] **Step 2: Verify** — for each symbol, pin count equals extraction row count; spot-check 5 random pins per IC against the extraction note (number AND name).

---

## Task 11: RF board project + power entry sheet

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_pro`
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_sch` (root; power section)

**Interfaces:**
- Produces: nets `+5V`, `+3V3_TX` (ADF5901 rail), `+3V3_RX` (ADF5904+ADF4159 analog rail), `+1V8_DIG` (ADF4159 digital rail, per Task 3 extraction), `GND`; the project file with net classes (`RF` 0.55 mm/50 Ω, `BB_DIFF`, `CTRL`, `PWR`) and PCBWay 4-layer DRC minima (0.09 mm trace/space floor; working values 0.127 mm signal, 0.3/0.15 mm vias).

- [ ] **Step 1: Create `.kicad_pro`** with the net classes and rules above (JSON — follow the Rev B2 `.kicad_pro` shape but with these values).

- [ ] **Step 2: Power schematic** — 5 V entry from connector pins 1/2, then the full regulator set recorded in `extracted/ev-radar-mmic2.md` (per Task 3 extraction this includes a **1.8 V digital rail for the ADF4159**, not just the 3.3 V analog rails — reference board uses 4 regulators; add net `+1V8_DIG`). Same parts as the eval board unless unstocked at DigiKey — then nearest stocked equivalent with equal/better PSRR and current, decision recorded in BOM.md. Input/output caps exactly per each regulator datasheet application circuit, ferrite/RC split between `+3V3_TX` and `+3V3_RX` per the reference design.

- [ ] **Step 3: Verify** — run ERC (fresh shell): `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc --format json --output /tmp/erc.json hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_sch` — acceptance at this stage: file parses, no `error`-severity items other than expected unconnected hierarchical stubs (record their count for later tasks to burn down).

---

## Task 12: ADF4159 + reference + loop filter sheet

**Files:**
- Modify: root schematic (add hierarchical sheet `pll.kicad_sch` in same dir)

**Interfaces:**
- Consumes: `extracted/adf4159.md`, `extracted/ev-radar-mmic2.md` (loop filter values, REFIN frequency/part), symbols from Task 10.
- Produces: nets `VTUNE` (to ADF5901), `REFIN`, `SPI_SCLK`, `SPI_SDATA`, `LE_4159`, `CE_RX`, `RAMP_SYNC` (MUXOUT), `RFIN_DIV` (from ADF5901 divider output back to ADF4159 RF input).

- [ ] **Step 1: Author the sheet** — ADF4159 wired per the eval-board schematic: charge pump → loop filter (component values copied verbatim from the extraction, cited) → `VTUNE`; reference oscillator (exact part + frequency from extraction) into REFIN with its coupling/termination; MUXOUT → `RAMP_SYNC`; decoupling per datasheet, one 100 nF + one 10 pF per supply pin unless the extraction says otherwise.

- [ ] **Step 2: Verify** — every ADF4159 pin either wired or explicitly no-connect flagged, matching the extraction's function column; ERC delta shows no new errors.

---

## Task 13: ADF5901 TX sheet

**Files:**
- Modify: root schematic (add `tx.kicad_sch`)

**Interfaces:**
- Consumes: `extracted/adf5901.md`, `extracted/ev-radar-mmic2.md`; nets `VTUNE`, `RFIN_DIV`, `+3V3_TX`, SPI bus, `TX_EN`, `LE_5901`.
- Produces: nets `TX_ANT` (to TX column feed), `LO_OUT` (to ADF5904 LOIN), with coupling/matching per reference design.

- [ ] **Step 1: Author** — VCO/PA supply and decoupling per extraction; TX1 out → matching/coupling network → `TX_ANT`; TX2 output terminated exactly as the eval board terminates its unused output; LO out → `LO_OUT` with the reference design's coupling network; CE ← `TX_EN`.

- [ ] **Step 2: Verify** — pin coverage vs extraction; ERC delta clean.

---

## Task 14: ADF5904 RX + baseband sheet

**Files:**
- Modify: root schematic (add `rx.kicad_sch`)

**Interfaces:**
- Consumes: `extracted/adf5904.md`; nets `LO_OUT`, `+3V3_RX`, SPI, `LE_5904`, `CE_RX`.
- Produces: nets `RX1..RX4` (antenna feeds), `BB1_P/N .. BB4_P/N` (through the reference design's light RC network), `SPI_SDO` (DOUT).

- [ ] **Step 1: Author** — four RFIN paths with input coupling exactly per reference design; LOIN network from `LO_OUT`; EP + all GND pins to GND; baseband outputs through the reference RC values to the `BBx_P/N` nets; DOUT → `SPI_SDO`.

- [ ] **Step 2: Verify** — pin coverage vs extraction; ERC delta clean.

---

## Task 15: Connector sheet + full schematic verification

**Files:**
- Modify: root schematic (add `io.kicad_sch`); finalize root.

**Interfaces:**
- Consumes: `INTERFACE.md` pinout (Task 2), all prior nets.
- Produces: the complete, ERC-clean RF schematic; analyzer JSON under `rf-board/analysis/`.

- [ ] **Step 1: Author the connector sheet** — HDR_2x15 wired pin-for-pin to the Task 2 table. No spare nets, no renames.

- [ ] **Step 2: ERC to zero** — fresh shell: `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc --severity-error --format json --output rf-erc.json <root .kicad_sch>` — acceptance: 0 errors; every warning individually justified in the task report.

- [ ] **Step 3: Run the schematic analyzer**

```bash
python3 .claude/skills/kicad/scripts/analyze_schematic.py hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_sch --analysis-dir hardware/24ghz-adf590x-fmcw-rev-c/rf-board/analysis/
```

Acceptance: component count matches expectation; no PP-001 (power pin reached only through a cap); no high-severity sourcing findings once MPNs are set.

- [ ] **Step 4: Pin-level cross-verification (the anti-Rev-B2 gate)** — for each of the three ADF chips: dump the analyzer's `ic_pin_analysis` pin→net map and diff it row-by-row against the extraction note's pin table + the eval-board schematic wiring. Record the diff (should be empty) in the task report. This is a required deliverable, not optional.

---

## Task 16: RF board outline, stackup, placement

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_pcb`

**Interfaces:**
- Consumes: `results/grid.json` (RX aperture), `results/tx_column.json`, netlist from Task 15.
- Produces: placed, unrouted board with outline, stackup, keepouts.

- [ ] **Step 1: Board setup** — outline 70×50 mm **plus a 12×50 mm coupon strip** on the right edge separated by a mouse-bite/V-score line (same design, no extra PCBWay design fee); 4-layer stackup recorded per the interim (or confirmed, if arrived) PCBWay table; copper-to-edge rule 0.3 mm.

- [ ] **Step 2: Placement** — RX grid phase centers at `grid.json` coordinates centered on the board's left region; ADF5904 centered under/behind the grid with the four `RXn` feeds symmetric (equal length by placement); TX column ≥20 mm from the nearest RX subarray at the top/bottom edge; ADF5901 adjacent to both TX feed and ADF5904 LOIN; ADF4159 + reference + LDOs in the low-frequency corner; connector on the bottom edge; 3 fiducials; mounting holes at corners ≥3 mm from copper.

- [ ] **Step 3: Coupon strip contents** — one standalone 2×2 subarray (exact Task 6 geometry) with a probeable 50 Ω launch + ground vias, and one 50 Ω line (Task 4 canary width) with two launches. Label both in silkscreen.

- [ ] **Step 4: Verify** — analyzer placement pass: `python3 .claude/skills/kicad/scripts/analyze_pcb.py <pcb> --analysis-dir .../rf-board/analysis/` — no courtyard overlaps, no PM-002 edge findings at error severity.

---

## Task 17: Antenna copper generation

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/antenna/geometry_to_footprint.py`
- Modify: RF `.kicad_pcb` (antenna footprints placed)

**Interfaces:**
- Consumes: `results/subarray.json`, `results/tx_column.json`, `results/grid.json`.
- Produces: `.kicad_mod` footprints `RX_SUBARRAY_2X2` and `TX_COLUMN_1X4` generated 1:1 from the simulated geometry (patches + feed tree as pads/polygons on F.Cu with mask pullback), placed on the board and connected to `RXn`/`TX_ANT` nets.

- [ ] **Step 1: Write the generator** — reads the JSON, emits polygon/pad geometry with a single connect point per subarray at the feed-tree root. The generator asserts the emitted copper's patch W/L and every feed segment length/width equal the JSON values to 1 µm — the layout copper IS the simulated copper, no re-drawing.

- [ ] **Step 2: Generate, place, verify** — run it, place at grid coordinates, then re-run the PCB analyzer; verify mask openings exist over all antenna copper (F.Mask apertures cover patches AND feed lines — the Rev B2 gap).

---

## Task 18: RF routing, planes, via fences

**Files:**
- Modify: RF `.kicad_pcb`

**Interfaces:**
- Produces: fully routed RF board (all nets, including GND, routed/poured).

- [ ] **Step 1: RF nets** — `RXn` feeds: 50 Ω width from the confirmed stackup, F.Cu only, no vias, lengths matched across the four channels to ≤0.5 mm (record actual lengths); `TX_ANT` and `LO_OUT` per reference-design guidance from the extraction; ground pour on F.Cu around RF with stitching vias at ≤λg/8 (≈0.9 mm) spacing near feed edges.

- [ ] **Step 2: Planes** — In1 solid GND (no splits under any RF or BB trace); In2 power pours (+3V3_TX / +3V3_RX / +5V islands); B.Cu GND + slow control routing; via fence between TX column and RX grid (2 rows, 0.8 mm spacing); EP via fields per Task 9 footprints already carry them.

- [ ] **Step 3: BB + control** — BB pairs routed differentially (0.127 mm / 0.127 mm gap, In-layer or B.Cu, referenced to In1), pair intra-skew ≤0.2 mm; SPI/control on B.Cu.

- [ ] **Step 4: Verify** — `--full` PCB analyzer run: `routing_complete: true`, no RT-001, return-path findings reviewed; report the four RX feed lengths and BB pair skews.

---

## Task 19: RF board DRC + full analyzer gate

**Files:**
- Modify: RF `.kicad_pcb` (fixes only)

- [ ] **Step 1: DRC** (fresh shell, single command):

```bash
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc --refill-zones --format json --output hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad/drc-report.json hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_pcb
```

Acceptance: zero violations of any severity except explicitly waived ones (each waiver written into `fabrication-notes.md` with reason). Zero unconnected items — Rev C has no "expected unrouted" allowance.

- [ ] **Step 2: Analyzer suite** — schematic + PCB `--full` + `cross_analysis.py` (schematic JSON vs PCB JSON) from `.claude/skills/kicad/scripts/`; acceptance: no error-severity findings unwaived; TV-001 absent (EPs have via fields); FD-001 absent (fiducials present).

- [ ] **Step 3: CHECKPOINT — report to user** with: DRC summary, analyzer summary, RX feed length match, coupon strip screenshot (`kicad-cli pcb render` top view PNG). User reviews/commits before the order package task.

---

## Task 20: ADC/Pi board schematic (native KiCad redo of Rev B2)

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/adc-board/kicad/openflight-adc-pi-interface-rev-c.{kicad_pro,kicad_sch}`

**Interfaces:**
- Consumes: `extracted/tlv320adc3140.md`, `INTERFACE.md` (both tables).
- Produces: ERC-clean ADC board schematic: TLV320ADC3140 application circuit per datasheet (AVDD/IOVDD decoupling, MICBIAS unused per line-in config, SHDNZ from Pi GPIO), 4 differential inputs from the header through anti-alias RC sized for ~100 kHz corner **with DNP-flexible footprints** (per spec: final values after measured ADF5904 levels — place the sites, fit the calculated starting values, mark alternates in BOM.md), 40-pin Pi header (I2S/TDM, I2C, 5V/3V3/GND, RAMP_SYNC passthrough GPIO), test points on every analog input, clock, and control line.

- [ ] **Step 1: Author** (reuse Task 9/10 library; add the Pi header footprint from stock KiCad `Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical`).
- [ ] **Step 2: ERC zero-error** (same command pattern as Task 15), schematic analyzer run, pin-level diff of TLV320ADC3140 against the extraction — same required deliverable as Task 15 Step 4.

---

## Task 21: ADC board layout + DRC

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/adc-board/kicad/openflight-adc-pi-interface-rev-c.kicad_pcb`

- [ ] **Step 1: Layout** — 2-layer FR4 (cost floor: check 2-layer is enough; if analog/digital separation demands it, 4-layer FR4 is still cheap — decide and record in fabrication-notes.md), ~55×65 mm to stack under a Pi, ADC analog side toward the interface header, digital toward the Pi header, solid ground pour both sides stitched.
- [ ] **Step 2: DRC + analyzers** — same gate as Task 19: zero violations, zero unconnected, cross-analysis clean.

---

## Task 22: Fabrication outputs and order package

**Files:**
- Create: `rf-board/gerbers/*`, `adc-board/gerbers/*`, both ZIPs
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/BOM.md`; PCBWay BOM/CPL CSVs under each board dir
- Modify: `fabrication-notes.md`, `README.md`

- [ ] **Step 1: Export gerbers + drills via kicad-cli only** (fresh shells):

```bash
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb export gerbers --output hardware/24ghz-adf590x-fmcw-rev-c/rf-board/gerbers/ hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_pcb
```

```bash
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb export drill --output hardware/24ghz-adf590x-fmcw-rev-c/rf-board/gerbers/ hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_pcb
```

(repeat both for the ADC board), then zip each gerbers dir.

- [ ] **Step 2: Gerber analyzer gate** — `python3 .claude/skills/kicad/scripts/analyze_gerbers.py <dir> --analysis-dir ...` per board; acceptance: no error findings, layer completeness `complete: true`, board dimensions match the `.kicad_pcb`.

- [ ] **Step 3: BOM/CPL** — export PCBWay-format BOM CSV (Line#/Qty/Designator/MPN/Manufacturer/Description/Package/Type) and CPL from KiCad position export for the RF board (2 assembled); human-readable BOM.md for both boards with every MPN, including the LDO/TCXO decisions and their extraction citations.

- [ ] **Step 4: Order checklist in fabrication-notes.md** — hybrid stackup table (must be the confirmed one by now — hard gate: if PCBWay's table never arrived or differs from the simulated substrate, STOP and re-run Tasks 5–8 first), assembly notes for the three LFCSPs, mask-pullback note for antenna copper, coupon strip note ("do not depanel"), updated PCBWay message text.

- [ ] **Step 5: FINAL CHECKPOINT — report to user** with the spec's five validation gates each marked pass/fail with evidence links. User reviews, commits, and uploads to PCBWay.

---

## Self-Review Notes

- Spec coverage: band plan (Tasks 1/12–13 config + fabrication notes), 200 mph waveform (register configuration is bring-up scope, not board scope — board provides RAMP_SYNC and 384 kHz path, Tasks 2/20), triple antenna verification (Tasks 5–8 sim, Task 1 stackup gate re-checked in Task 22, Task 16 coupon), raw capture contract (Task 2 INTERFACE.md), cost floors (Tasks 16/21/22), native KiCad + kicad-cli-only exports (Tasks 11–22), all five spec validation gates (Tasks 3, 1→22 gate, 5–8, 16, 19/21/22).
- Register/bring-up software (ADF register sequences, ALSA overlay) is deliberately out of this plan: it needs assembled hardware and belongs to a bring-up plan after boards ship.
- Datasheet-dependent values (loop filter, TCXO, LDOs, RC networks) are data dependencies resolved by Task 3 with citations — later tasks reference the extraction files, never invent values.
