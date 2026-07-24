# OpenFlight 24 GHz FMCW RF Board Rev C Production Review

**Date:** 2026-07-13  
**Project:** KiCad 10.0.4, four copper layers, 82 x 50 mm  
**Scope:** Schematic, PCB, RF simulations, BOM/CPL, and production Gerbers

## Verdict

**Small first-article release candidate; manufacturer hold remains.** The current
design passes ERC, DRC, netlist/pad parity, focused regression tests, standalone
antenna acceptance, loop-filter analysis, BOM completeness, and Gerber
completeness. It is not RF-qualified for a repeat or volume build.

Do not authorize fabrication until both of these external conditions close:

1. PCBWay returns and accepts the exact 0.254 mm RO4350B L1-L2 hybrid stackup,
   the 0.556 mm 50 ohm RF geometry, and no-CAM-change antenna requirement.
2. PCBWay accepts the 0.50/0.30 mm vias and 0.10 mm nominal annular ring without
   altering pads or drills.

The exact one-port grid control passes within 1.00 dB of the standalone S11
reference. Three full-grid checkpoints all pass the -20 dB coupling screen; the
conservative worst case is -22.95 dB. The 200k-step run did not reach its energy
decay criterion and failed the checkpoint-drift gate, so its exact S11 and
coupling values are not accepted as RF qualification. This residual risk is
assigned to mandatory first-article VNA and multiport testing rather than a
speculative copper change.

## Previous Review Delta

| Prior blocker | Current status |
|---|---|
| As-built TX 2x2 had no accepted simulation | Closed by reciprocity against identical RX 2x2 copper; 10.38 dBi gain and 2 degree beam offset |
| RX far-field result normalized near-zero power | Closed by valid full-sphere NF2FF run; 85.6% radiation efficiency |
| RX-grid coupling absent | First-article screen closed at -22.95 dB conservative worst case; converged RF qualification remains a bench gate |
| BOM only partially locked | Closed: 33/33 production BOM rows have exact MPNs; 97 fitted placements |
| Loop filter used unverified eval values | Closed: topology corrected to UG-866 Figure 12 and values retuned across 128 corners |
| Board generator could restore old loop filter | Closed: route plan, net classes, and C35 orientation corrected; clean rebuild verified |

## Verification Summary

| Gate | Result | Evidence |
|---|---|---|
| ERC | PASS: 0 error-level violations | `rf-board/production-package/verification/erc-errors.json` |
| DRC | PASS: 0 violations, 0 unconnected | `rf-board/production-package/verification/drc.json` |
| Netlist | PASS: 98 components, 80 nets | `verification/netlist-verification.txt` |
| PCB parity | PASS: 350 pad/net assignments, 16 fixtures | `verification/board-verification.txt` |
| Focused tests | PASS: 43 | `verification/focused-tests.txt` |
| Deterministic rebuild | PASS: 663 tracks, 172 vias, DRC 0/0 | Temporary rebuild audit, 2026-07-13 |
| Production BOM | PASS: 33 rows, 100% MPN coverage | Production BOM CSV |
| Production CPL | PASS: 97 fitted placements; C51 excluded | Production CPL CSV |
| Gerbers | PASS: required layers and PTH/NPTH present | `gerbers.json` plus X2 job file |

## Analyzers Run

- `analyze_schematic.py`
- `analyze_pcb.py --full`
- `cross_analysis.py`
- `analyze_thermal.py`
- `analyze_gerbers.py`
- KiCad ERC and DRC
- Custom netlist and board pad/net parity gates
- Analytical PLL loop-filter corner sweep
- openEMS patch, 2x2 subarray, far-field, TX reciprocity, and grid coupling runs

## Component Summary

| Type | Fitted quantity |
|---|---:|
| Capacitors | 69 |
| Resistors | 16 |
| ICs | 8 |
| Diodes | 1 |
| Ferrite beads | 1 |
| Connectors | 1 |
| Oscillators | 1 |
| **Total** | **97** |

`C51` is the only DNP schematic component. The production BOM's external MPN
override map is authoritative; the schematic analyzer's 13/32 MPN warning does
not inspect that map and is superseded by the 33/33 production BOM gate.

## Power Tree

```text
J1 +5V
  -> D1 reverse protection -> FB1 -> +5V_REG
       -> U1 ADP7104 -> +3V3_TX -> ADF5901
       -> U2 ADP7104 -> +3V3_RX -> ADF4159 + ADF5904
       -> U3 ADP150  -> +1V8_DIG -> ADF digital I/O + level shifters
```

The connector and every critical power/RF net were traced in the generated
KiCad XML netlist. Direct PCB pad/net comparison passes for all 350 schematic
pin assignments.

## PLL And Signal Review

The PLL passive filter now implements the ADI UG-866 Figure 12 topology:

- C33 = 220 pF from charge pump to ground.
- C34 = 3.3 nF in series with R22 = 620 ohm to ground.
- R21 = 510 ohm from charge pump to the final VTUNE node.
- C35 = 47 pF from final VTUNE node to ground.
- R23 = 0 ohm from the final node to ADF5901 VTUNE.

The analytical open-loop sweep covers charge-pump current, feedback VCO gain,
and resistor/capacitor tolerances across 128 corners. Worst-case phase margin is
50.64 degrees, unity-gain frequency is 156.4 kHz, and the 150 us chirp contains
23.46 unity-gain cycles. All configured gates pass. This is analytical rather
than SPICE/ADIsimPLL evidence; first-article lock and ramp linearity still need
bench verification.

The 0.127 mm control and baseband traces are low-current signals and meet the
selected fabrication rule. BB2-BB4 P/N lengths are not matched as high-speed
digital differential pairs. Their propagation skew is negligible relative to
the sub-200 kHz radar beat signal, but channel common-mode rejection must be
checked during bring-up.

## RF And Antenna Review

The RX and TX antennas use identical generated 2x2 corporate-fed copper. The
validated 2x2 result records:

- Worst-band S11: -15.67 dB from 24.150 to 24.250 GHz.
- Feed phase imbalance: 3.132 degrees.
- Gain: 10.38 dBi.
- Radiation efficiency: 85.63%.
- Peak beam offset: 2 degrees.

By electromagnetic reciprocity, the same copper is accepted for the as-built TX
array. At the ADF5901 typical 8 dBm output, modeled EIRP is 18.38 dBm. Output
power tolerance and regional rules still require a programmed-power/EIRP review
before field operation; fabrication itself is not blocked by that software and
regulatory control.

The exact one-port grid setup matches the standalone model's 183 x 235 x 31
mesh, 27 top-copper primitives, port copper, ground, substrate, and six port
probe/excitation primitives. Reprocessing the long standalone transient through
the grid port model gives -17.39/-16.69/-16.67 dB S11 at 24.15/24.20/24.25 GHz,
within 1.00 dB of the accepted reference at every point.

The full-grid 100k, 142k, and 200k checkpoints all pass the coupling screen. The
conservative worst case is -22.95 dB, 2.95 dB below the -20 dB limit. However,
the 200k run stopped with -6.69 dB residual energy instead of the requested
-15.23 dB and drifted by up to 9.90 dB from the 142k checkpoint. Its -9.55 dB
S11 is therefore not treated as a physical failure or a pass. The result is
adequate to screen a small first article, not to qualify RF performance.

## PCB Layout And DFM

- L2/In1 is one continuous filled GND zone with one outline and 96.7% fill.
- All RF and antenna copper is on L1 referenced directly to L2.
- Four layers, 172 vias, 22 plated component holes, and four NPTH mounting holes
  are present in fabrication data.
- Three top-side fiducials and four power test points are present.
- J1's 0.30 mm body-to-edge placement is intentional for mating access. Copper
  meets the 0.30 mm edge rule.
- D1 is 0.65 mm from the edge; KiCad clearance passes, but PCBWay CAM should
  confirm handling clearance.
- Fourteen 0.50/0.30 mm vias have 0.10 mm nominal annular rings. PCBWay lists a
  3 mil advanced-process minimum, but written CAM acceptance is still required.
- PCBWay CAM inquiry `W1042560AS2Y11` identified vias overlapping solderable
  pads. The approved response is to resin-fill, planarize, and copper-cap only
  component-pad vias associated with U1, U2, C84, and J1. Ordinary RF/ground
  stitching and routing vias must remain unfilled.

## Thermal Review

U4/U5/U6 exposed pads use 4/9/9 footprint vias. U1/U2 ADP7104 exposed pads have
no dedicated via field but connect to the large top ground copper. At the design
assumption of 170 mA, each 5 V to 3.3 V LDO dissipates about 0.29 W. The ADP7104
SOIC datasheet gives 48.5 degrees C/W on its reference four-layer board, implying
about 14 degrees C rise at that load; copper area and enclosure temperature make
the real value board-specific. First-article thermal measurement at maximum TX/RX
load is required.

The automated thermal result reports no warning and a 31.8 C hottest component,
but it only models U1-U3 and underestimates total board dissipation. It is treated
as a consistency check, not qualification evidence.

## EMC And Cross-Domain Review

The cross analyzer's plane-split errors are false positives: it evaluates sparse
front/power pours as return planes, while L2 is the actual continuous GND return.
Raw PCB and filled-zone inspection confirms one connected L2 GND outline beneath
the routed area. The analyzer's differential-pair mismatch warnings are retained
as a bring-up common-mode-rejection check, not a timing blocker.

No dedicated `analyze_emc.py` exists in the installed review skill, so formal
EMC pre-compliance analysis was not run. The board still requires radiated and
conducted pre-compliance testing in its enclosure.

## Gerber Verification

The release archive contains F.Cu, In1.Cu, In2.Cu, B.Cu, top/bottom mask,
top/bottom paste, top/bottom silkscreen, Edge.Cuts, separate PTH/NPTH drills, and
an X2 job file. The analyzer's width/height variance warnings compare sparse
artwork extents rather than file origins; all files come from one KiCad export,
declare a common coordinate system, and overlay correctly in visual review.

## Lifecycle And Sourcing

ADF5901 and ADF5904 are listed by Analog Devices as recommended for new designs.
The exact production MPNs are locked in the BOM. Availability, lead time, and
authorized-channel sourcing must be reconfirmed when PCBWay quotes assembly;
no lifecycle claim is made for passives based only on distributor listings.

## False Positives / Reviewer Overrides

- Schematic MPN blocker: production BOM override map gives 33/33 MPN coverage.
- Missing datasheets: PDFs exist at the Rev C project-level `datasheets/` path.
- J1 missing grounds: generated netlist verifies the intended interleaved GND pins.
- U5/U6 single-pin GND warnings: hierarchical parser artifact; netlist parity passes.
- TX_EN pull-up: CE is actively driven through the level-shifter architecture.
- Power-source warnings: hierarchical/global-power parser limitation; netlist passes.
- Plane split/return-path errors: L2 continuous GND is the actual reference plane.
- Test-point 0/74: TP1-TP4 are intentional board-only fixtures; J1 exposes I/O.
- Gerber alignment warnings: sparse layer extents, not coordinate misregistration.

## Not Performed / Review Limits

- No ngspice/Xyce executable is installed. The PLL filter uses an analytical
  corner model; no transistor-level or vendor behavioral SPICE model was run.
- No installed EMC analyzer script was available.
- The thermal analyzer does not model the RF MMICs.
- Antenna simulations use the requested, not yet manufacturer-confirmed,
  0.254 mm RO4350B stackup. A changed PCBWay stackup invalidates those results.
- The full-grid transient did not reach its convergence criterion. Grid S11 and
  precise coupling require first-article VNA/multiport confirmation.
- Simulation and review cannot replace VNA, spectrum, chirp-linearity, thermal,
  channel-balance, and range/angle testing on assembled first articles.

## Release Decision

The files are suitable for PCBWay engineering review, quote, and a small
first-article build after the two manufacturer confirmations. They must not be
used for a repeat or volume order until VNA S11 and multiport isolation pass
across 24.150-24.250 GHz. The board must not be described as RF-qualified
production hardware until bench and pre-compliance tests pass.

## Primary References

- ADI EV-RADAR-MMIC2 UG-866: `datasheets/EV-RADAR-MMIC2_UG-866.pdf`
- ADP7104 Rev. I: `datasheets/ADP7104.pdf`
- ADF5901 lifecycle: https://www.analog.com/en/products/ADF5901.html
- ADF5904 lifecycle: https://www.analog.com/en/products/adf5904.html
- PCBWay advanced capabilities: https://www.pcbway.com/advanced-pcb-capabilities.html
