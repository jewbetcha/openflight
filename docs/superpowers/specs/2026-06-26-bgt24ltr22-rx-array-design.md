# BGT24LTR22 RX Array Rev B1 Design

## Goal

Create a reviewable Gerber package for a low-cost all-in-one 24 GHz prototype
that can test both passive OPS243 listening and self-transmit radar operation.

## Scope

Rev B1 is an RF/mixed-signal prototype package, not a production-ready design.
It is intended for PCB fab and assembly review before ordering.

The board includes:

- Four 24.125 GHz RX patch antennas.
- Two Infineon BGT24LTR22 radar MMIC footprints.
- Two 24.125 GHz TX/sync patch antennas.
- RF traces between patches and MMIC RF pins.
- 1.5 V, SPI, control, and test breakout areas.
- Differential IF breakout pads for all four RX channels.
- 4-layer stackup notes for Rogers RF dielectric over a solid ground layer.

The board does not include:

- A selected 8-channel simultaneous ADC.
- Raspberry Pi data interface circuitry.
- Verified regulator design.
- EM simulation results.
- VNA or phase calibration results.

## Architecture

```text
4 RX patches
    -> 2x BGT24LTR22
    -> 8 differential IF pairs total: I/Q for 4 RX channels
    -> board-edge IF breakout pads
    -> external simultaneous ADC for Rev B1

TX/sync patches and RF test areas
    -> allow active radar experiments
    -> allow passive OPS243-listening experiments with transmit disabled
```

## Board Assumptions

- Board size: 120 mm x 80 mm.
- Layers: 4.
- L1: RF copper, antennas, BGT24LTR22 pads, critical RF traces.
- L2: solid RF ground plane under L1.
- L3: control, IF, and low-frequency breakout routing.
- L4: ground and low-frequency support copper.
- Critical dielectric: 0.254 mm / 10 mil Rogers RO4350B or equivalent between
  L1 and L2.

## Risk Register

- The BGT24LTR22 package is a 52-terminal 0.4 mm pitch WLCSP and requires proper
  PCB assembly review.
- The footprint in Rev B1 is generated from public package and pinout data and
  must be checked against Infineon's current package drawing before ordering.
- The RF traces and patches are first-pass geometry and are not EM simulated.
- MUSIC angle estimation depends on phase coherence across both radar chips.
- Rev B1 breaks out IF signals instead of selecting the final ADC, because ADC
  choice should be made after RF signal-level measurements.

