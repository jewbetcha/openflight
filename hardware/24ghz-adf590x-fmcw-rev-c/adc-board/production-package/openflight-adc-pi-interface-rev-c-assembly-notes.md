# Rev C ADC/Pi Interface Assembly Notes

## Critical Orientation

- Install J2 (`ESQ-120-58-S-D`) on the **bottom side** of the PCB.
- J2 pin 1 must match the square pad and Raspberry Pi physical pin 1.
- J2 is a 16.13 mm elevated female socket; do not substitute a male header or
  standard-height socket.
- Install J1 (`FTSH-115-01-L-DV-K`) on the top side with its polarization key
  matching the footprint outline.
- U1 pin 1 must match the footprint pin-1 marker.

## DNP Parts

Do not install: `CCP1-CCP4`, `CCN1-CCN4`, and `R5`.

Test points `TP1-TP22` are bare PCB pads, not placed components.

## Inspection

- X-ray or otherwise inspect U1's exposed pad and perimeter joints.
- Confirm no solder bridges at U1, J1, or J2.
- Confirm R6 and R7 are both fitted as 10 kohm pull-downs.
- Confirm all through vias located inside J1, C6, or C7 SMD pads are resin
  filled and copper capped before assembly; ordinary tenting is not sufficient.
- Confirm continuity from J1 pins 21-30 to their assigned J2 pins using the
  included pin map.
- Clean flux residue around all ADC input and reference components.

## Power Rule

The supported system has one 5 V source: the Raspberry Pi supply. Do not apply
a second external 5 V source to RF J1 while the Pi is powered.
