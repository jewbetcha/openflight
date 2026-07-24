# Rev C RF Board Design Review

Date: 2026-07-13

## Verdict

**Ready for external design review. Not ready to order.** The generated PCB is
fully routed and reproducible, with 0 DRC violations and 0 unconnected items.
The Gerber/drill set is complete and shares a common coordinate origin. Release
is blocked by the antenna evidence, final PCBWay stackup, and BOM lock items
listed below.

## Release Blockers

| ID | Blocker | Confidence and evidence | Required disposition |
|---|---|---|---|
| B1 | The approved design calls for a 1x4 TX column, but the PCB uses `TX_ARRAY_2X2`, cloned from the RX subarray. No passing `tx_column.json` exists. | High; raw footprint, generator, board, and missing result file | Simulate/freeze the intended TX antenna or explicitly approve the 2x2 deviation and simulate it as TX. |
| B2 | The RX subarray's reported 22.79 dBi gain is invalid. `subarray_final/nf2ff.h5` reports `Prad = 1.7666e-27 W`; the directivity was normalized by effectively zero power. S11 and feed phase remain recorded, but gain acceptance is now false. | High; raw openEMS HDF5 plus aperture sanity check | Correct the NF2FF setup and rerun gain/pattern. |
| B3 | Full four-subarray coupling is not simulated. `grid.json` has `coupling_db_max: null` and `acceptance.coupling: false`. | High; frozen geometry JSON | Run the grid coupling simulation or obtain a documented vendor waiver. |
| B4 | PCBWay has not returned the exact hybrid stackup or controlled-impedance width. Current RF geometry assumes 0.254 mm RO4350B, design Dk 3.66, and 0.556 mm 50-ohm microstrip. | High; board stackup and fabrication notes | Obtain PCBWay stackup/field-solver result, then recalculate and rerun affected EM simulations. |
| B5 | Assembly BOM is not locked. It has 30 unique rows and 98 placements, but only 11 rows have exact MPNs. Passive voltage, dielectric, tolerance, and RF grade are incomplete. | High; generated BOM cross-checked to the CPL | Assign passive MPNs/specifications and resolve sourcing substitutions before turnkey assembly. |

PCBWay lists 0.254 mm as a standard RO4350B dielectric thickness, but that does
not define the complete hybrid construction or finished copper geometry:
[PCBWay/Rogers material table](https://www.pcbway.com/img/images/product/material-files/PCB-material/Rogers-High-Frequency-Laminates.pdf).

## Verified Results

- Clean generator rebuild: `build_rf_board.py` -> `route_rf_board.py` ->
  `merge_low_speed_routes.py` reproduces the routed board.
- KiCad 10.0.4 DRC: **0 violations, 0 unconnected items** (`drc-release.json`).
- Netlist verification: **PASS**, 98 schematic components, 80 nets, critical
  supply/control/RF memberships checked.
- PCB verification: **PASS**, 98 schematic components plus 16 intentional board
  fixtures, 350 pad/net assignments, 4 copper layers, 82 x 50 mm outline.
- Focused geometry/routing tests: **19 passed**.
- ERC: **0 errors**. The 529 warnings match prior generated-schematic reports:
  349 off-grid endpoints, 167 cached-symbol mismatches, 6 library issues,
  6 intentional isolated antenna/unused labels, and 1 PWR_FLAG pin-type warning.
- Gerber set: all 11 expected production layers, separate PTH/NPTH drill files,
  192 plated holes, 4 NPTH mounting holes, X2 job file, IPC-D-356, BOM, CPL,
  assembly PDFs, and top/bottom 3D renders.
- Visual review: continuous In1 GND reference, coherent outer/inner copper,
  exposed antenna copper/mask openings, closed outline, and no blank layers.

## Analyzer Trust Summary

| Analyzer | Findings | Trust | Review disposition |
|---|---:|---|---|
| Schematic | 1 error, 20 warnings, 36 info | Mixed | BOM coverage is real; hierarchy-related GND/source/connector findings are false positives. |
| PCB | 1 error, 29 warnings, 72 info | High geometry, no datasheet backing | DFM items triaged below; KiCad DRC remains authoritative for clearance/connectivity. |
| Cross-domain | 4 errors, 4 warnings, 2 info | Deterministic topology | Plane errors are analyzer limitations; baseband pair mismatch is real. |
| Thermal | 3 info | Mixed/incomplete | Only U1-U3 modeled; RF MMIC thermal behavior requires manual review. |
| Gerber | 2 warnings | High | Extent-based alignment warnings are false positives; every layer declares `SameCoordinates,Original`. |

## DFM and Electrical Review

- **Via annular ring:** general 0.5/0.3 mm vias have a 0.10 mm annular ring.
  Confirm as an advanced-process allowance in the PCBWay quote. Do not silently
  let CAM enlarge pads or reduce drills on RF/ground structures.
- **J1 edge warning:** the analyzer measured the courtyard at 0.30 mm from the
  edge, not copper. Pads and outline pass KiCad DRC. Mechanical acceptance is
  still required for the mated cable/connector envelope.
- **Via-in-pad warnings:** C84:2 and J1:30 are false positives from bounding-box
  proximity; raw coordinates place the vias outside the SMD lands.
- **Baseband pairs:** BB2, BB3, and BB4 have 30.2, 5.5, and 10.7 mm P/N length
  mismatch. Propagation skew is negligible at FMCW beat frequencies, but the
  asymmetry can reduce common-mode rejection. Accept only if the ADC/interface
  reviewer agrees; otherwise length-match before release.
- **Test access:** TP1-TP4 cover +5V, +3V3_TX, +3V3_RX, and +1V8_DIG. Control,
  baseband, and ground are accessible through J1, but there are no dedicated
  control-line probe pads.
- **Thermal:** U5/U6 have 3x3 EP via fields. U4 has the intended 2x2, 1.2 mm-grid
  via field. U1/U2 have soldered SOIC exposed pads and broad GND copper but no
  pad vias. At 170 mA load each LDO dissipates about 0.29 W from 5 V to 3.3 V;
  verify copper-area/ambient margin for the enclosure.
- **TX_EN pull-up warning:** low is the safe ADF5901 power-down state. A pull-up
  is not required, but firmware/host reset behavior must keep the line defined.
- **Loop filter and RF blocks:** the eval-board loop filter has not been checked
  in ADIsimPLL for the 100 MHz/150 us chirp, and the 100 pF 24 GHz DC-block
  implementation is not vendor-validated. Both remain pre-order checks.

## False-Positive Triage

- J1 does contain ten GND pins; the schematic analyzer lost hierarchical pin
  connectivity.
- U5/U6 GND single-pin warnings and +5V/+5V_REG source warnings are hierarchy
  parser artifacts. XML/netlist and PCB pad-net verification pass.
- Plane-split/return-path errors count F.Cu/In2 polygon fragments independently
  and ignore cross-layer connectivity. In1 is a continuous full-board GND
  reference and KiCad reports no opens.
- Gerber width/height warnings compare sparse artwork extents. X2 metadata and
  raw files use the same origin, and overlay review is aligned.

## Lifecycle and Sourcing

A point-in-time manufacturer check found ADF5901, ADF5904, ADF4159, and ADP7104
recommended for new designs; ADP150 is production; both TI level shifters are
active. Sources: [ADF5901](https://www.analog.com/en/products/adf5901.html),
[ADF5904](https://www.analog.com/en/products/adf5904.html),
[ADF4159](https://www.analog.com/en/products/adf4159.html),
[ADP7104](https://www.analog.com/en/products/adp7104.html),
[ADP150](https://www.analog.com/en/products/adp150.html),
[SN74AVC4T245](https://www.ti.com/product/SN74AVC4T245), and
[SN74AVC2T245RSWR](https://www.ti.com/product/SN74AVC2T245/part-details/SN74AVC2T245RSWR).

Sourcing risk remains: Samtec showed zero direct stock for the exact J1 variant,
and Mouser showed zero stock with future receipts for the exact ADP7104 SOIC
variant during this review. PCBWay must quote or approve alternates. This was a
manual partial audit, not a distributor-API stock lock.

PCBWay's current assembly guidance accepts CSV BOM/CPL files and says passive
value plus package can be used when no part number is supplied, but full passive
specifications are still needed to avoid uncontrolled substitutions:
[PCBWay assembly file requirements](https://www.pcbway.com/smt_ordering_guide.html).

## Review Gaps

- No SPICE simulator is installed, so no ngspice/Xyce subcircuit run was made.
- The installed KiCad skill package has no `analyze_emc.py`; EMC was reviewed
  manually from the continuous In1 plane, layer renders, routing, and connector.
- No DigiKey/Mouser lifecycle API credentials were available; lifecycle review
  was limited to manufacturer pages and point-in-time web results.
- Thermal automation did not model U4/U5/U6 and cannot replace enclosure-level
  thermal validation.

## Package Status

The Gerber ZIP and review bundle are intentionally marked **REVIEW ONLY**.
PCBWay requests Gerbers, BOM, centroid, and assembly references for PCBA review:
[PCBWay requested production files](https://www.pcbway.com/helpcenter/pcb_assembly_ordering/What_files_are_requested_for_assembly_production_.html).

Do not approve fabrication until B1-B5 are closed and a new final package is
regenerated from the same source scripts.
