# Rev C RF Board Fabrication Notes

Last updated: 2026-07-13

## Release State

The production package passes the internal schematic, layout, BOM, and Gerber
gates. PCBWay CAM may review and quote it, but fabrication remains on hold until
PCBWay confirms the custom hybrid stackup and the via annular ring in writing.

## Board Construction

- Board size: 82.0 x 50.0 mm, including the 12 mm RF coupon area.
- Copper layers, top to bottom: `F.Cu`, `In1.Cu`, `In2.Cu`, `B.Cu`.
- Finished thickness: 1.6 mm nominal.
- Surface finish: ENIG.
- Solder mask: green. Silkscreen: white.
- Outer and inner copper in the design model: 17 um (0.5 oz).
- Controlled impedance: 50 ohm single-ended microstrip on L1 referenced to L2,
  0.556 mm nominal trace width.

Required stackup, top to bottom:

| Layer | Material / thickness | Function |
|---|---|---|
| L1 | 17 um copper | RF, antennas, components |
| L1-L2 | 0.254 mm Rogers RO4350B, design Dk 3.66, Df 0.0037 | RF dielectric |
| L2 | 17 um copper | Continuous GND reference |
| L2-L3 | 0.500 mm FR4 prepreg | Bonding dielectric |
| L3 | 17 um copper | Power / low-speed routing |
| L3-L4 | 0.744 mm FR4 core | Mechanical build-up |
| L4 | 17 um copper | Power / low-speed routing |

PCBWay must return its proposed stackup table and calculated 50 ohm geometry
before production starts. Any change to the L1-L2 dielectric, Dk/Df, finished
L1 copper thickness, or 0.556 mm RF width requires OpenFlight approval and may
require antenna re-simulation.

## CAM Restrictions

- Do not resize, smooth, neck, add teardrops to, or otherwise alter antenna or
  RF copper without written approval.
- Do not add copper thieving or manufacturer markings inside antenna keepout
  regions or the RF coupon.
- Preserve the Gerber solder-mask openings over antenna and RF feed copper.
- Preserve the common origin and supplied board outline; do not independently
  scale or offset layers.
- The design uses 0.50 mm finished via pads with 0.30 mm drills: 0.10 mm nominal
  annular ring. PCBWay's advanced-process capability lists a 3 mil minimum, but
  CAM must explicitly accept this geometry without enlarging pads or drills.
- Per PCBWay CAM inquiry `W1042560AS2Y11`, fill only vias that overlap
  solderable component pads with non-conductive resin, planarize them, and
  copper-cap/plate them flush (VIPPO / IPC-4761 Type VII). This applies to the
  via-in-pad locations associated with U1, U2, C84, and J1. Do not resin-fill
  every via on the board; ordinary RF/ground stitching and routing vias remain
  as supplied in the solder-mask data.
- Minimum copper-to-board-edge spacing is 0.30 mm. J1 is intentionally placed at
  the lower edge for mating access.

## Assembly

- Build quantity: 5 boards; initial request is 2 turnkey assembled boards.
- Placement: top-side SMD only.
- DNP: `C51`. It is excluded from the production BOM and CPL.
- Use exact MPNs from the production BOM. No substitutions for U1-U8, X1,
  C50/C52/C53/C70-C74, the loop-filter parts C33-C35/R21-R23, or any antenna/RF
  component without written approval.
- Three top-side fiducials are provided for assembly alignment.
- TP1-TP4 expose +5V, +3V3_TX, +3V3_RX, and +1V8_DIG. Other control and
  baseband nets are accessible through J1.
- Inspect QFN exposed-pad soldering and thermal-via fill on the first article.
- Follow the top assembly PDF and 3D render for polarity and orientation. The
  CPL rotations are KiCad rotations and must be checked during assembly setup.

## Interface Connector

- J1: 2x15 SMD header, 1.27 mm pitch.
- It carries four differential baseband channels, interleaved grounds, +5V,
  SPI/control signals, TX/RX enables, and ramp synchronization.
- `INTERFACE.md` is the authoritative pin-by-pin contract.

## Release Checks

- [x] KiCad 10.0.4 ERC: 0 error-level violations.
- [x] KiCad 10.0.4 DRC: 0 violations / 0 unconnected items.
- [x] Netlist: 98 components, 80 nets, critical RF/power/connector checks pass.
- [x] PCB parity: 350 schematic pad/net assignments pass; 16 intentional board
  fixtures are present.
- [x] Production BOM: 33 lines, 97 fitted placements, 100% MPN coverage.
- [x] Gerbers: four copper layers, masks, paste, silks, Edge.Cuts, PTH, NPTH,
  and X2 job file present.
- [x] RX 2x2 subarray and as-built TX 2x2 antenna acceptance simulations pass.
- [x] Four-subarray first-article coupling screen: all checkpoints below -20 dB;
  conservative worst case -22.95 dB.
- [ ] PCBWay confirms the exact hybrid stackup and 50 ohm geometry.
- [ ] PCBWay confirms 0.50/0.30 mm vias with 0.10 mm annular ring unchanged.
- [ ] PCBWay confirms that only component-pad vias receive resin fill,
  planarization, and copper capping; ordinary vias remain unfilled.
- [ ] First-article VNA and multiport isolation qualification completed before
  any repeat or volume build.
- [ ] Regional EIRP/programmed TX-power review is approved before field use.

## Production Files

- Gerber ZIP: `rf-board/gerbers/openflight-24ghz-fmcw-rf-rev-c-production-gerbers.zip`
- BOM/CPL and assembly data: `rf-board/production-package/`
- Verification evidence: `rf-board/production-package/verification/`
- Production review: `analysis/production-review-2026-07-13-final/REPORT.md`
