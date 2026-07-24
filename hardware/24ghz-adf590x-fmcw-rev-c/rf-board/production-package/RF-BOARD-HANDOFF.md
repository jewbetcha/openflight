# Rev C RF Board Production Handoff

Last updated: 2026-07-13

## Current State

**Small first-article release candidate. Do not authorize fabrication yet.**

The board and manufacturing files pass the internal electrical, layout,
rebuild, BOM, and Gerber gates. The package is ready for PCBWay engineering
review and a small first-article build after the two manufacturer confirmations
below. RF qualification remains required before a repeat or volume build.

## Authoritative Files

- PCB: `rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_pcb`
- Schematic: `rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_sch`
- Gerber ZIP: `rf-board/gerbers/openflight-24ghz-fmcw-rf-rev-c-production-gerbers.zip`
- BOM/CPL/assembly files: `rf-board/production-package/`
- Fabrication instructions: `fabrication-notes.md`
- Production review: `analysis/production-review-2026-07-13-final/REPORT.md`

Do not submit the older `review-package/`, `*-review-gerbers.zip`, or Rev B2
archives for this board.

## Completed

- KiCad 10.0.4 ERC: 0 error-level violations.
- KiCad 10.0.4 DRC: 0 violations / 0 unconnected items.
- Netlist gate: 98 components, 80 nets, connector and critical RF/power nets pass.
- PCB gate: 350 schematic pad/net assignments, 16 board fixtures, four layers,
  and 82 x 50 mm outline pass.
- Focused tests: 43 passed at final lock.
- Deterministic rebuild: 663 tracks, 172 vias, parity pass, DRC 0/0.
- Corrected the PLL filter to the ADI UG-866 Figure 12 topology.
- Retuned R21/R22/C35 to 510 ohm / 620 ohm / 47 pF; 128-corner analytical
  sweep passes with 50.64 degree minimum phase margin.
- Validated RX 2x2 antenna: -15.67 dB worst-band S11, 3.132 degree phase
  imbalance, 10.38 dBi gain, 85.63% efficiency, 2 degree beam offset.
- Accepted as-built TX 2x2 by copper identity and reciprocity; modeled typical
  EIRP is 18.38 dBm at 8 dBm PA output.
- Production BOM: 33 rows, 97 fitted placements, 100% MPN coverage; C51 DNP.
- Production Gerbers, PTH/NPTH drills, job file, IPC-2581, schematic PDF,
  assembly PDFs, and top/bottom 3D renders generated.
- Exact one-port grid control passes S11 within 1.00 dB of the standalone model.
- Full-grid checkpoints all pass the -20 dB coupling screen; conservative worst
  case is -22.95 dB. The transient did not converge, so this is first-article
  screening evidence rather than RF qualification.

## Release Holds

1. **PCBWay stackup:** written acceptance of 0.254 mm RO4350B between L1-L2,
   design Dk 3.66/Df 0.0037, 17 um L1 copper, and 0.556 mm 50 ohm microstrip.
   PCBWay must not alter antenna/RF copper without approval.
2. **Via geometry:** written CAM acceptance of 0.50 mm pads / 0.30 mm drills,
   0.10 mm nominal annular ring, without enlarging pads or drills.
Regional EIRP review and a programmed TX-power limit are required before field
operation, but they do not block fabrication of first articles.

## Residual RF Qualification Risk

`antenna/results/grid-screening-assessment.json` records the nonconverged grid
run and the conservative coupling envelope. Do not authorize a repeat or volume
build until first-article VNA and channel-isolation measurements confirm
S11 <= -10 dB and isolation >= 20 dB across 24.150-24.250 GHz.

## PCBWay Order Settings

- Layers: 4.
- Layer order: L1 F.Cu, L2 In1.Cu, L3 In2.Cu, L4 B.Cu.
- Size: 82 x 50 mm.
- Quantity: 5; initially 2 turnkey assembled.
- Finish: ENIG.
- Mask/silkscreen: green/white.
- Controlled impedance: yes, 50 ohm L1 microstrip referenced to L2.
- Material: hybrid RO4350B + FR4, exact construction per `fabrication-notes.md`.

## Rebuild Sequence

Run from repository root. KiCad's Python binding requires its bundled Python:

```bash
KICAD_PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
KICAD_SITE=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/lib/python3.9/site-packages
BASE=hardware/24ghz-adf590x-fmcw-rev-c/rf-board/kicad

env UV_CACHE_DIR=/tmp/openflight-uv-cache PYTHONPATH="$KICAD_SITE" \
  uv run --no-project --python "$KICAD_PY" python \
  "$BASE/scratchpad/build_rf_board.py"

env UV_CACHE_DIR=/tmp/openflight-uv-cache PYTHONPATH="$KICAD_SITE" \
  uv run --no-project --python "$KICAD_PY" python \
  "$BASE/scratchpad/route_rf_board.py"

env UV_CACHE_DIR=/tmp/openflight-uv-cache PYTHONPATH="$KICAD_SITE" \
  MERGE_NETS='Net-(U1-PG),Net-(U2-PG)' \
  uv run --no-project --python "$KICAD_PY" python \
  "$BASE/scratchpad/merge_low_speed_routes.py" \
  "$BASE/openflight-24ghz-fmcw-rf-rev-c.kicad_pcb" \
  "$BASE/openflight-24ghz-fmcw-rf-rev-c-control-final-candidate.kicad_pcb"
```

`merge_low_speed_routes.py` refills and saves zones. On macOS/KiCad 10.0.4,
avoid `pcb export --check-zones`; that CLI path can abort. Run DRC after the
saved fill and export without `--check-zones`.

## First-Article Qualification

- Verify all rails and current draw before enabling TX.
- Program a conservative TX power and chirp range below the 24.250 GHz edge.
- VNA-check the RF coupon and antenna match.
- Measure PLL lock, ramp linearity, and phase noise.
- Verify four baseband channel gain/phase balance and common-mode rejection.
- Measure U1/U2 and MMIC temperatures at maximum intended duty cycle.
- Run radiated/conducted pre-compliance tests in the final enclosure.
