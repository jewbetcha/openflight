# 24 GHz Passive RX Array Prototype BOM

Prototype bill of materials for testing a passive 24 GHz receive array that listens to
the existing OPS243 transmitter and estimates spatial angle from the reflected signal.

This is a Rev A research BOM, not a production BOM. The goal is to prove that four
coherent receive channels can see enough OPS243-reflected ball energy for MUSIC or
beamforming before integrating custom RF hardware into OpenFlight.

## Recommended Rev A Architecture

```text
OPS243 transmitter
    -> reflected 24 GHz ball/club energy
    -> custom 4-patch RX antenna PCB
    -> ADF5904 4-channel 24 GHz RX downconverter
    -> baseband conditioning
    -> simultaneous 4-channel ADC
    -> Raspberry Pi capture + offline MUSIC/beamforming
```

## Top-Level BOM

| Qty | Item | Suggested source / part | Purpose | Notes |
| --- | --- | --- | --- | --- |
| 1 | 4-patch RX antenna PCB | Custom PCB, Rogers RO4350B or RO3003 | Four passive 24 GHz receive antennas | Rev A should be antenna-only so the RF geometry can be measured and reworked. |
| 1 | 4-channel 24 GHz receiver | Analog Devices EVAL-ADF5904 | Coherent 4-channel receiver downconverter | Exposes LO input, 4 RX inputs, and baseband outputs. Requires external LO and control board. |
| 1 | ADI controller | Analog Devices SDP-S | Programs/configures the ADF5904 eval board | Required by the ADI eval-board workflow. |
| 1 | 24 GHz LO source | Prefer EVAL-ADF5901, or EVAL-RADAR-MMIC if budget allows | Provides the shared LO for the ADF5904 | The LO must be common to all 4 RX channels. It does not need to be phase-locked to OPS243 for relative angle, but it must be tuned close enough that the IF lands inside the ADC bandwidth. |
| 1 | 4-channel simultaneous ADC | USB audio interface with 4+ balanced line inputs, or dedicated ADC board | Captures baseband channels on Raspberry Pi | For a first pass, a Linux class-compliant USB audio interface at 96 kHz or 192 kHz is the cheapest practical path. |
| 1 | Baseband conditioning board | Custom small board, or EV-ADAR-D2S if using EVAL-RADAR-MMIC | Converts/scales ADF5904 differential outputs for the ADC | The ADF5904 baseband outputs are differential; do not assume they can connect directly to arbitrary ADC inputs without checking bias, gain, and impedance. |
| 4 | RF patch-to-receiver cables | Phase-stable SMA/2.92 mm coax, equal length | Connects antenna PCB to ADF5904 RX inputs | Cable phase is part of calibration. Keep lengths equal and mechanically fixed. |
| 1 | Mechanical antenna fixture | Custom 3D print or machined plate | Holds patch locations repeatably | Needs known phase-center coordinates. Make both compact and OpenFlight-spacing fixture options if possible. |
| 1 | Calibration target set | Metal sphere/plate, fixed-height stand | Measures channel phase offsets and angle response | Required before trusting any MUSIC result. |

## Custom 4-Patch Antenna PCB BOM

Rev A Gerber package: `hardware/24ghz-rx-array-rev-a/`

| Qty | Item | Recommendation | Notes |
| --- | --- | --- | --- |
| 1 | RF laminate | Rogers RO4350B, 10 mil, 2-layer | Good first choice because it is lower-cost than PTFE and easier for PCB fabs to process. |
| 1 | Copper | 0.5 oz or 1 oz, controlled by fab stackup | Use the fab's exact stackup in the RF simulation/calculator. |
| 1 | Surface finish | Immersion silver preferred; ENIG acceptable for first prototype | Avoid soldermask over patches and RF feedlines. Nickel in ENIG can add RF loss, but may be acceptable for Rev A. |
| 4 | Patch antennas | Custom rectangular microstrip patches | Starting dimensions below; final geometry must be tuned. |
| 6 | RF launches | Southwest Microwave 2.92 mm end-launch jack, narrow block, for boards up to 0.065 in | Install 4; buy 2 spares. Use this instead of generic SMA. Exact pin/dielectric variant should be locked after the PCB fab confirms finished board thickness and launch stackup. |
| 16+ | Ground vias | Via fence around feedlines and launches | Keep the back side as continuous ground under patches and feedlines. |
| 4+ | Mounting holes | M2/M2.5 or 2-56, outside RF keepouts | Needed for repeatable fixture mounting. |
| 2+ | Fiducials / phase-center marks | Copper or silkscreen marks away from RF paths | Makes measurement and fixture alignment easier. |

## Connector Decision

Use **2.92 mm end-launch jack/female connectors** for Rev A.

Default family:

- Southwest Microwave 2.92 mm 40 GHz end-launch jack/female, narrow block
- Board thickness range: up to 0.065 in
- Likely variants to evaluate after the final stackup:
  - 1092-01A-9
  - 1092-03A-9
  - 1092-04A-9

Why this choice:

- 2.92 mm connectors are rated well above 24.125 GHz.
- End-launch connectors make VNA measurement and cable connection straightforward.
- The Southwest Microwave clamp style is reusable, so a bad Rev A antenna board does
  not waste the connector set.
- Generic SMA is cheaper, but it is too easy to buy a connector/launch combination
  that performs poorly at 24 GHz.

Do not use U.FL, W.FL, MMCX, or low-cost generic SMA for this prototype. Those are
tempting mechanically, but they add too much uncertainty to the antenna measurement.

## Starting Patch Geometry

Use these values only as the initial layout point for EM simulation or VNA tuning.

Target frequency: 24.125 GHz

Approximate dimensions for 10 mil RO4350B:

| Parameter | Starting value |
| --- | ---: |
| Free-space wavelength | 12.43 mm |
| Half wavelength | 6.21 mm |
| Patch width | 4.15 mm |
| Patch length | 3.24 mm |

Recommended Rev A PCB format:

```text
Panel contains 4 identical antenna coupons:

  [patch + feed + launch] x 4

Each coupon has:
  - one patch
  - one 50 ohm grounded-coplanar or microstrip feed
  - one connector or coax launch
  - mounting/alignment holes
```

Why coupons first:

- They let each patch be measured independently with a VNA.
- They avoid committing to the wrong array spacing before signal strength is known.
- They can be mounted in either compact 2x2 spacing or OpenFlight corner spacing.

## Gerber Design Requirements

Do not generate final Gerbers until these are fixed:

1. PCB fab and exact RF stackup
2. Final 2.92 mm connector variant and launch footprint
3. Coupon panel vs fixed 2x2 array vs OpenFlight corner array
4. Soldermask/finish rules from the chosen fab
5. Whether the ADF5904 stays on an eval board or moves onto a custom RF PCB

Minimum Gerber acceptance checks:

- Patch copper dimensions match the chosen stackup.
- No soldermask over patches, RF feeds, or launch pads.
- Back side under patches is solid ground.
- Feedlines are controlled impedance.
- Launch geometry matches the connector datasheet and fab stackup.
- Patch phase-center coordinates are documented.
- Board includes a calibration/mechanical datum.

## Prototype Strategy

1. Build the custom 4-patch antenna coupon PCB.
2. Measure S11 for each patch at 24.125 GHz.
3. Connect all four antennas to the ADF5904 with equal-length cables.
4. Tune the LO so OPS243 leakage/reflection lands inside the ADC passband.
5. Capture a static calibration scene and a moving-ball test.
6. Estimate per-channel phase offsets.
7. Run offline beamforming/MUSIC before integrating anything into live OpenFlight.

## Likely Follow-Up BOM Revisions

Rev A:

- Antenna coupon PCB
- ADF5904 eval board
- external LO
- USB audio or simple simultaneous ADC capture

Rev B:

- fixed 4-patch array geometry
- cleaner baseband conditioning
- calibrated mechanical fixture

Rev C:

- ADF5904 and ADC on custom OpenFlight RF board
- production enclosure integration
- live server integration

## Alternate Infineon Rev B1 Package

Generated review package:

```text
hardware/24ghz-bgt24ltr22-rx-array-rev-b1/
```

This package explores a lower-cost all-in-one RF front end using two Infineon
BGT24LTR22 radar MMICs:

- 4 RX patch antennas
- 2 unconnected TX/sync patch review structures
- 2x BGT24LTR22 footprints
- 4-layer RF stackup assumption
- IF/control breakout placeholder geometry

This is a fab-review and assembly-review prototype, not an order-ready production
design. The BGT24LTR22 WLCSP footprint, RF routing, patch geometry, stackup, and
paste/mask rules must be reviewed before placing an assembled order.

Rev B1 no longer routes the IF/control fanout or TX/sync structures because the
first generated layout created real copper crossings. A functional coherent
receiver revision needs a proper WLCSP escape, IF/control routing, shared LO/sync
network, and ADC/Pi interface.
