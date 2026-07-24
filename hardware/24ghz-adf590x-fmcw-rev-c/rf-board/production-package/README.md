# OpenFlight 24 GHz FMCW RF Board Rev C

Production release candidate generated 2026-07-13 from KiCad 10.0.4.

## Submit to PCBWay

- `openflight-24ghz-fmcw-rf-rev-c-production-gerbers.zip`
- `openflight-24ghz-fmcw-rf-rev-c-bom.csv`
- `openflight-24ghz-fmcw-rf-rev-c-cpl.csv`
- `openflight-24ghz-fmcw-rf-rev-c-top-assembly.pdf`
- `openflight-24ghz-fmcw-rf-rev-c-bottom-assembly.pdf`
- `openflight-24ghz-fmcw-rf-rev-c-top-3d.png`
- `openflight-24ghz-fmcw-rf-rev-c-bottom-3d.png`
- `fabrication-notes.md`

The schematic PDF and IPC-2581 file are included as engineering references.
The `verification/` directory contains fresh ERC, DRC, netlist, board-parity,
focused-test, and antenna-screening evidence.

## Manufacturing Hold

Do not authorize fabrication until PCBWay confirms the hybrid RO4350B/FR4
stackup, calculated 50 ohm geometry, and 0.10 mm annular ring without CAM
changes. PCBWay must also confirm that only component-pad vias are resin-filled,
planarized, and copper-capped; ordinary vias remain unfilled. See
`fabrication-notes.md` for the exact construction and restrictions.

`C51` is DNP and is intentionally absent from the BOM and CPL. All other 97
schematic placements are included.

This package is for a small first-article build. VNA and multiport isolation
measurements are required before any repeat or volume build; see
`verification/grid-screening-assessment.json`.
