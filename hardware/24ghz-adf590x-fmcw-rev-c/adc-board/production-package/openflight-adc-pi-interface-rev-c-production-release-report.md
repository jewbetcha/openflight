# Rev C ADC/Pi Interface Production Release

Release date: 2026-07-13

## Release Verdict

The CAD package is ready for PCBWay engineering review and a small assembled
first-article order. It is not yet field-proven hardware; do not authorize a
large production run until the included first-article test passes.

## Verified Release Checks

- KiCad ERC: 0 errors.
- KiCad DRC: 0 errors, 0 unconnected items, 0 schematic parity issues.
- Interface contract: all 30 RF J1 pins and all 27 required Pi J2 pins match
  between the schematic and PCB.
- Safe startup: R6 and R7 pull `CE_RX` and `TX_EN` low until the Pi drives them.
- Assembly data: 32 fully specified BOM lines and 32 matching CPL placements.
- Gerbers: 4 copper layers, all expected mask/paste/silkscreen/outline files,
  PTH drill file, and NPTH drill file are present.
- Thermal analyzer: no findings.

## Reviewed Warnings

- Four KiCad `copper_sliver` warnings remain on `F.Cu`; there are no clearance
  or connectivity errors associated with them.
- The 0.30 mm drill / 0.50 mm pad vias use a 0.10 mm annular ring and require
  PCBWay's advanced process review.
- Vias in J1, C6, and C7 SMD pads require resin fill and copper cap (VIPPO).
- Four analog baseband pairs differ by about 1.9 mm in routed length. This is
  acceptable for the low-frequency radar IF/baseband signals and is not a
  high-speed serial timing interface.
- The Gerber analyzer's front-paste ratio warning counts THT pads, vias, test
  pads, and copper pours as copper flashes; those features correctly have no
  solder-paste aperture.

## System Connection Rules

- Use only Samtec cable `FFSD-15-D-03.00-01-N`, straight-through pin N to N.
- Install J2 `ESQ-120-58-S-D` on the PCB bottom side and align physical pin 1.
- Power the system from the Raspberry Pi supply only. Do not connect a second
  5 V source at RF J1 while the Pi is powered.
- This board connects to the Pi through its 40-pin GPIO header, not USB.
- Do not substitute U1, J1, or J2 without written approval.

## Review Gaps Before Volume Production

- ADC Linux configuration/driver integration has not been validated on an
  assembled board.
- Analog noise, channel gain/phase matching, and complete RF-board operation
  require first-article measurements.
- Automated EMC analysis and SPICE were unavailable in the current toolset;
  the existing schematic, layout, and thermal checks do not replace lab EMC
  or signal-quality measurements.
