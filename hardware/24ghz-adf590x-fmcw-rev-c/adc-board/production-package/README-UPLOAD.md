# PCBWay Upload - Rev C ADC/Pi Interface

## Upload Files

1. Upload `openflight-adc-pi-interface-rev-c-pcbway-gerbers-2026-07-13.zip`
   as the PCB files.
2. Upload `openflight-adc-pi-interface-rev-c-bom.csv` as the assembly BOM.
3. Upload `openflight-adc-pi-interface-rev-c-cpl.csv` as the pick-and-place file.
4. Attach `openflight-adc-pi-interface-rev-c-assembly-notes.md`,
   `openflight-adc-pi-interface-rev-c-production-release-report.md`, the
   schematic PDF, and both assembly PDFs to the order notes.

## Required Board Settings

- Board: 55 mm x 65 mm
- Layers: 4
- Thickness: 1.6 mm
- Copper: 1 oz outer and inner unless PCBWay engineering recommends otherwise
- Surface finish: ENIG
- Solder mask: green
- Silkscreen: white
- Controlled impedance: not required
- Electrical test: 100 percent flying-probe test
- Assembly: top and bottom; J2 is bottom-side THT/manual assembly
- Via-in-pad: resin fill and copper cap (VIPPO) all through vias that fall
  inside J1, C6, or C7 SMD pads; confirm this option before fabrication
- Interface: Raspberry Pi 40-pin GPIO socket; this board does not use USB

## Copper Layer Order

Enter this exact top-to-bottom order if PCBWay asks:

1. `F.Cu`
2. `In1.Cu`
3. `In2.Cu`
4. `B.Cu`

## Do Not Substitute

- U1: `TLV320ADC3140IRTWT`, 24-pin RTW WQFN
- J1: `FTSH-115-01-L-DV-K`
- J2: `ESQ-120-58-S-D`, installed on the bottom side

Obtain written approval before changing any of these three parts.

PCBWay supports plugged CNC vias and lists a 3 mil advanced-process minimum via
annular ring. This design uses 0.30 mm drills with 0.50 mm via pads (0.10 mm /
3.94 mil annular ring), so it must be reviewed against the selected advanced
process rather than silently enlarged or clipped.
