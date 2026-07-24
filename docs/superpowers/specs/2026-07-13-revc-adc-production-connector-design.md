# Rev C ADC Production Connector Design

## Goal

Make the ADC board a complete, fail-safe bridge between the Rev C RF board and
a Raspberry Pi, then produce a PCBWay fabrication and assembly package.

## Approved Physical Interfaces

- RF board J1 and ADC board J1 remain Samtec `FTSH-115-01-L-DV-K` male,
  keyed, 2x15, 1.27 mm headers.
- The boards connect with one straight-through Samtec
  `FFSD-15-D-03.00-01-N` 30-conductor cable. Pin N connects to pin N; reverse
  or reverse-wired FFSD variants are prohibited.
- ADC board J2 becomes a bottom-mounted Samtec `ESQ-120-58-S-D` 2x20 female
  socket. Its 16.13 mm body height provides Raspberry Pi HAT+ clearance.
- J2 pad locations and physical Raspberry Pi pin numbers remain unchanged.

## Electrical Interface

The existing four differential baseband channels, power, ground, ADC I2C/TDM,
ADC shutdown, and ramp sync connections remain unchanged. The missing RF
control path is added as follows:

| RF J1 | Signal | Raspberry Pi physical pin | BCM GPIO |
|---:|---|---:|---:|
| 21 | SPI_SCLK | 23 | 11 |
| 22 | SPI_SDATA | 19 | 10 |
| 23 | SPI_SDO | 21 | 9 |
| 25 | LE_5901 | 24 | 8 |
| 26 | LE_5904 | 26 | 7 |
| 27 | LE_4159 | 29 | 5 |
| 28 | CE_RX | 22 | 25 |
| 29 | TX_EN | 37 | 26 |
| 30 | RAMP_SYNC | 18 | 24 |

`CE_RX` and `TX_EN` each receive a 10 kohm pulldown on the ADC board so the RF
receiver/PLL and transmitter remain disabled until software deliberately
enables them. The supported power topology has one 5 V source: the Raspberry
Pi supply powers the ADC and RF boards through J2 and the RF cable. An external
5 V source must not be connected to RF J1 at the same time.

## Assembly Rules

- Fit J2 on the PCB bottom side with pin 1 aligned to Raspberry Pi physical
  pin 1.
- Do not populate `CCP1-CCP4`, `CCN1-CCN4`, or `R5`; these are documented
  tuning options.
- Test pads are copper features and are excluded from the assembly BOM/CPL.
- Order the RF cable separately; it is not placed on either PCB.

## Release Gates

- Schematic netlist assertions cover every RF and Raspberry Pi connector pin.
- ERC has zero errors and warnings.
- PCB DRC has zero errors and zero unconnected items; any warning must be
  individually reviewed.
- BOM has an MPN for every populated line item and CPL references match the BOM.
- Gerbers contain `F.Cu`, `In1.Cu`, `In2.Cu`, and `B.Cu`, both masks, both
  silkscreens, board outline, and plated/non-plated drills.

Electrical and manufacturing checks can establish design consistency, but the
first assembled article still requires current-limited power-up, rail checks,
I2C discovery, TDM capture, and RF-disabled boot verification before a larger
production run.
