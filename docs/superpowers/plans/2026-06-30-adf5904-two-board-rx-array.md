# ADF5904 Two-Board RX Array Rev B2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Rev B2 two-board hardware design package for a low-cost 24 GHz coherent receive array: RF/downconverter board plus ADC/Pi interface board.

**Architecture:** Split controlled-impedance RF work from lower-cost digital/audio capture. Board 1 carries four 2x2 RX patch subarrays, one ADF5904 receiver downconverter, RF/LO routing, and four differential baseband outputs. Board 2 carries four differential baseband inputs, TLV320ADC3140 ADC, Raspberry Pi I2S/TDM + I2C headers, power filtering, and bring-up test points.

**Tech Stack:** KiCad 8/9/10-compatible generated `.kicad_pcb` review models, Gerber/Excellon generator scripts, Node.js validation scripts, PCBWay-style DFM notes, KiCad CLI DRC.

---

## File Structure

- Create `hardware/24ghz-adf5904-rx-array-rev-b2/README.md`
  - Explains the two-board design package, ordering status, and validation status.
- Create `hardware/24ghz-adf5904-rx-array-rev-b2/fabrication-notes.md`
  - Contains PCBWay RF-board and ADC-board order guidance.
- Create `hardware/24ghz-adf5904-rx-array-rev-b2/BOM.md`
  - Prototype BOM with selected MPNs, fallback parts, and hand-assembly risks.
- Create `hardware/24ghz-adf5904-rx-array-rev-b2/INTERFACE.md`
  - Defines RF-board-to-ADC-board signals and ADC-board-to-Raspberry-Pi signals.
- Create `hardware/24ghz-adf5904-rx-array-rev-b2/generate_designs.mjs`
  - Generates review-model KiCad boards, Gerbers, drill files, manifests, and upload ZIPs for both boards.
- Create `hardware/24ghz-adf5904-rx-array-rev-b2/check_designs.mjs`
  - Checks generated manifests, layer/file completeness, Gerber endings, board sizes, RF channel count, ADC channel count, and obvious top-copper trace collisions.
- Create `hardware/24ghz-adf5904-rx-array-rev-b2/check_kicad_drc.mjs`
  - Fails on KiCad DRC hard failures: shorts, clearances, crossing tracks, or error-severity violations.
- Create `hardware/24ghz-adf5904-rx-array-rev-b2/validate_rev_b2.sh`
  - Runs generation, static checks, ZIP rebuilds, KiCad DRC on both boards, and DRC report checks.
- Generate under `hardware/24ghz-adf5904-rx-array-rev-b2/rf-board/`
  - `gerbers/*`
  - `kicad/openflight-24ghz-adf5904-rf-board-rev-b2.kicad_pcb`
  - `kicad/openflight-24ghz-adf5904-rf-board-rev-b2.kicad_pro`
  - `openflight-24ghz-adf5904-rf-board-rev-b2-gerbers.zip`
- Generate under `hardware/24ghz-adf5904-rx-array-rev-b2/adc-board/`
  - `gerbers/*`
  - `kicad/openflight-24ghz-tlv320adc3140-pi-interface-rev-b2.kicad_pcb`
  - `kicad/openflight-24ghz-tlv320adc3140-pi-interface-rev-b2.kicad_pro`
  - `openflight-24ghz-tlv320adc3140-pi-interface-rev-b2-gerbers.zip`

## Task 1: Documentation Shell

**Files:**
- Create: `hardware/24ghz-adf5904-rx-array-rev-b2/README.md`
- Create: `hardware/24ghz-adf5904-rx-array-rev-b2/fabrication-notes.md`
- Create: `hardware/24ghz-adf5904-rx-array-rev-b2/BOM.md`
- Create: `hardware/24ghz-adf5904-rx-array-rev-b2/INTERFACE.md`

- [ ] **Step 1: Create README**

Write a concise README with:
- `Board 1: RF/downconverter board`
- `Board 2: ADC/Pi interface board`
- `Status: generated review model, not final RF-tuned fabrication release`
- `Validation command: bash hardware/24ghz-adf5904-rx-array-rev-b2/validate_rev_b2.sh`

- [ ] **Step 2: Create fabrication notes**

Document:
- RF board: Rogers RO4350B or equivalent, 4 layers, L1-to-L2 RF dielectric starts at 0.254 mm, controlled impedance required, ENIG or immersion silver finish, no soldermask over patch copper unless the RF model assumes it.
- ADC board: standard FR-4, 4 layers preferred for clean ground/power, PCBWay assembly review required for TLV320ADC3140 WQFN.
- Both boards: copper edge clearance target at least 0.3 mm.

- [ ] **Step 3: Create BOM**

Include these rows:
- `U1`, `ADF5904ACPZ`, Analog Devices, 32-lead 5 mm x 5 mm LFCSP receiver downconverter.
- `U1`, `TLV320ADC3140IRTE`, Texas Instruments, 24-pin WQFN quad ADC.
- `J_RF_ADC`, board-to-board/cable connector placeholder, 20 signal pins plus grounds.
- `J_PI`, Raspberry Pi 40-pin header subset placeholder.
- `PCM1864DBT`, Texas Instruments, fallback ADC option.

- [ ] **Step 4: Create interface doc**

Define these exact signal groups:
- RF board to ADC board: `BB1_P`, `BB1_N`, `BB2_P`, `BB2_N`, `BB3_P`, `BB3_N`, `BB4_P`, `BB4_N`, `AGND`, `RF_3V3`, `ADF_LE`, `ADF_CLK`, `ADF_DATA`, `ADF_CE`, `ADF_DOUT`.
- ADC board to Raspberry Pi: `I2S_BCLK`, `I2S_LRCLK`, `I2S_DIN`, `I2C_SCL`, `I2C_SDA`, `ADC_SHDNZ`, `3V3`, `5V`, `GND`.

## Task 2: Generator Script

**Files:**
- Create: `hardware/24ghz-adf5904-rx-array-rev-b2/generate_designs.mjs`

- [ ] **Step 1: Implement shared Gerber helpers**

Implement functions for:
- aperture definitions: circles and rectangles
- flashes
- line drawing
- Gerber headers with X2 file function attributes
- Excellon drill output
- KiCad board string generation
- ZIP creation handled by `validate_rev_b2.sh`

- [ ] **Step 2: Implement RF board model**

Generate:
- Board size `120 mm x 80 mm`.
- Four 2x2 RX subarrays, one subarray per channel.
- One ADF5904 LFCSP-32 review footprint with pins named from the datasheet.
- Four RF feed routes from subarray combiners to `RX1_RF`, `RX2_RF`, `RX3_RF`, `RX4_RF`.
- One `LO_IN` SMA/edge-launch placeholder.
- One board-to-board analog/control connector exposing four differential baseband pairs and control pins.
- Ground via fences around RF structures and board perimeter.
- Four-layer stackup with Rogers L1/L2 dielectric metadata.

- [ ] **Step 3: Implement ADC board model**

Generate:
- Board size `85 mm x 56 mm`.
- One TLV320ADC3140 WQFN-24 review footprint with pins named from the datasheet.
- One matching RF-board connector.
- One Raspberry Pi header subset.
- Four differential analog input routes from connector to ADC inputs.
- I2S/TDM, I2C, shutdown, power, and test headers.
- Four-layer FR-4 stackup metadata.

## Task 3: Validation Scripts

**Files:**
- Create: `hardware/24ghz-adf5904-rx-array-rev-b2/check_designs.mjs`
- Create: `hardware/24ghz-adf5904-rx-array-rev-b2/check_kicad_drc.mjs`
- Create: `hardware/24ghz-adf5904-rx-array-rev-b2/validate_rev_b2.sh`

- [ ] **Step 1: Static design checks**

Check:
- RF manifest has `board.width === 120`, `board.height === 80`, `rxChannels.length === 4`, `patchesPerChannel === 4`, `receiver.part === "ADF5904ACPZ"`.
- ADC manifest has `board.width === 85`, `board.height === 56`, `adc.part === "TLV320ADC3140IRTE"`, `adc.channels === 4`.
- Every Gerber ends with `M02*`.
- Every drill file ends with `M30`.
- Each generated board has 12 fabrication files: 9 Gerbers, 2 drills, and 1 manifest.

- [ ] **Step 2: KiCad DRC checks**

Run:

```bash
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc --refill-zones --format json --output hardware/24ghz-adf5904-rx-array-rev-b2/rf-board/kicad/drc-report.json hardware/24ghz-adf5904-rx-array-rev-b2/rf-board/kicad/openflight-24ghz-adf5904-rf-board-rev-b2.kicad_pcb
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc --refill-zones --format json --output hardware/24ghz-adf5904-rx-array-rev-b2/adc-board/kicad/drc-report.json hardware/24ghz-adf5904-rx-array-rev-b2/adc-board/kicad/openflight-24ghz-tlv320adc3140-pi-interface-rev-b2.kicad_pcb
node hardware/24ghz-adf5904-rx-array-rev-b2/check_kicad_drc.mjs
```

Expected:
- No `shorting_items`.
- No `clearance` errors.
- No `tracks_crossing` errors.
- Unconnected warnings are allowed only for intentional bring-up/test pads.

## Task 4: Generate Outputs

**Files:**
- Generated: RF board Gerbers/KiCad/ZIP
- Generated: ADC board Gerbers/KiCad/ZIP

- [ ] **Step 1: Run generation**

Run:

```bash
node hardware/24ghz-adf5904-rx-array-rev-b2/generate_designs.mjs
```

Expected:
- RF board generated under `hardware/24ghz-adf5904-rx-array-rev-b2/rf-board/`.
- ADC board generated under `hardware/24ghz-adf5904-rx-array-rev-b2/adc-board/`.

- [ ] **Step 2: Run validation**

Run:

```bash
bash hardware/24ghz-adf5904-rx-array-rev-b2/validate_rev_b2.sh
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc --refill-zones --format json --output hardware/24ghz-adf5904-rx-array-rev-b2/rf-board/kicad/drc-report.json hardware/24ghz-adf5904-rx-array-rev-b2/rf-board/kicad/openflight-24ghz-adf5904-rf-board-rev-b2.kicad_pcb
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc --refill-zones --format json --output hardware/24ghz-adf5904-rx-array-rev-b2/adc-board/kicad/drc-report.json hardware/24ghz-adf5904-rx-array-rev-b2/adc-board/kicad/openflight-24ghz-tlv320adc3140-pi-interface-rev-b2.kicad_pcb
node hardware/24ghz-adf5904-rx-array-rev-b2/check_kicad_drc.mjs
```

Expected:
- Static design checks pass.
- KiCad DRC hard-failure checks pass for both boards.
- RF and ADC Gerber ZIP files are rebuilt.

## Task 5: Self-Review And Handoff

**Files:**
- Modify: `hardware/24ghz-adf5904-rx-array-rev-b2/README.md`
- Modify: `hardware/24ghz-adf5904-rx-array-rev-b2/fabrication-notes.md`

- [ ] **Step 1: Record validation output**

Add a short validation section with:
- command run
- pass/fail result
- allowed warning classes
- explicit statement that RF antenna tuning still requires stackup-specific RF review or EM simulation

- [ ] **Step 2: Handoff summary**

Tell the user:
- Which files to open in KiCad.
- Which ZIPs are generated.
- Which board should be fabricated first.
- Which issues still block “safe to order” status.
