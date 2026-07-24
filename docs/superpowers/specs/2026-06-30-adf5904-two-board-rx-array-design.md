# ADF5904 Two-Board RX Array Rev B2 Design

## Goal

Create the next OpenFlight 24 GHz receive-array prototype around the cheapest
practical coherent signal path:

```text
24 GHz RX antenna array
    -> 4-channel 24 GHz receiver downconverter
    -> 4 coherent audio/baseband ADC channels
    -> Raspberry Pi capture
    -> MUSIC / beamforming / calibration experiments
```

Rev B2 replaces the Rev B1 BGT24LTR22 all-in-one experiment with a two-board
architecture:

1. An RF/downconverter board on a controlled RF stackup.
2. A lower-cost ADC/Pi interface board on standard FR-4.

The design optimizes for sensitivity, cost control, and iteration speed. It is
still a research prototype, not a production launch-monitor module.

## Decision Summary

- Use **four independent RX channels** for spatial processing.
- Give each RX channel a **2x2 patch subarray** for higher gain than the Rev B1
  single-patch-per-channel geometry.
- Use one **Analog Devices ADF5904** as the 4-channel 24 GHz receiver
  downconverter.
- Use a separate ADC/Pi board with **TI TLV320ADC3140** as the default
  4-channel ADC.
- Keep **PCM1864** as a lower-assembly-risk fallback ADC.
- Do not use a boxed USB audio interface as the main product path. Keep devices
  like the Behringer UMC404HD only as lab fallbacks.

## Architecture

```text
Board 1: RF / Downconverter, Rogers or equivalent RF stackup

    Four 2x2 RX patch subarrays
        -> ADF5904 RX inputs
        -> baseband filtering / gain / protection
        -> four differential analog baseband pairs
        -> board-to-board or cable connector

Board 2: ADC / Pi Interface, standard FR-4

    Four differential analog baseband channels
        -> TLV320ADC3140
        -> I2S/TDM digital audio
        -> Raspberry Pi

    I2C or SPI control
        -> ADC configuration
        -> optional RF board control lines
```

## Board 1: RF / Downconverter Board

### Scope

The RF board contains the parts that benefit from RF laminate and controlled
24 GHz layout:

- Four RX antenna subarrays.
- One ADF5904 4-channel 24 GHz receiver downconverter.
- RF feedlines from each subarray to its ADF5904 RX input.
- LO/reference input strategy for the ADF5904.
- Differential baseband output conditioning sufficient to drive the ADC board.
- Power filtering and local decoupling for the ADF5904.
- Mechanical datums for phase-center measurement and calibration.

### RX Antenna Geometry

Each independent RX channel should use a 2x2 patch subarray:

```text
RX1 = 2x2 patches -> one feed -> ADF5904 RX1
RX2 = 2x2 patches -> one feed -> ADF5904 RX2
RX3 = 2x2 patches -> one feed -> ADF5904 RX3
RX4 = 2x2 patches -> one feed -> ADF5904 RX4
```

The four subarrays remain four coherent channels. The extra patch elements
increase antenna gain for each channel; they do not increase channel count.

Starting assumptions:

- Target frequency: 24.125 GHz.
- Subarray layout: 2x2 corporate-fed patch group per channel.
- Patch/feed dimensions must be recalculated from the exact PCBWay stackup.
- A vendor RF review or EM simulation is required before treating the antenna
  geometry as tuned.

### Receiver Downconverter

Default receiver:

- Analog Devices ADF5904.
- 4 RX inputs.
- Shared LO input.
- Differential baseband outputs.
- SPI/3-wire-style configuration interface per the ADF5904 reference material.

This is a better match than two BGT24LTR22 devices because the four RX channels
share one receiver IC and one LO strategy. That simplifies channel coherence,
calibration, and routing.

### Passive vs Active Illumination

Rev B2 remains focused on passive listening to OPS243-reflected energy, but the
RF board must not block active experiments later.

Passive OPS243 mode:

```text
OPS243 transmits
    -> ball/club reflection
    -> Rev B2 RX array receives
    -> ADF5904 mixes using local LO
```

The local LO must be close enough to the OPS243 carrier that the received
baseband falls inside the ADC bandwidth.

Active future mode:

```text
OpenFlight-controlled 24 GHz TX/LO source
    -> shared LO/reference
    -> ADF5904 downconversion
```

Active mode is out of scope for Rev B2 implementation, but the connector and
LO/reference architecture should leave room for it.

### RF Board Outputs

The RF board should expose four conditioned differential baseband pairs to the
ADC board. The preferred physical interface is a compact board-to-board
connector if the two boards stack mechanically; otherwise use a short cable
harness.

Signals from RF board to ADC board:

- `BB1_P`, `BB1_N`
- `BB2_P`, `BB2_N`
- `BB3_P`, `BB3_N`
- `BB4_P`, `BB4_N`
- analog ground/reference
- RF board status/control as needed

Signals from ADC/Pi board to RF board:

- regulated power rails as selected by power design
- ADF5904 configuration/control, routed through the ADC/Pi board if the Pi owns
  all low-speed control
- optional LO/control lines

## Board 2: ADC / Pi Interface Board

### Scope

The ADC board contains the lower-frequency mixed-signal and digital capture
path:

- Four differential analog baseband inputs from RF board.
- Anti-alias filtering and input scaling if not fully handled on RF board.
- TLV320ADC3140 4-channel ADC.
- I2S/TDM connection to Raspberry Pi.
- I2C or SPI control.
- Power filtering and ADC clocking.
- Test headers for analog and digital bring-up.

The ADC board should be standard FR-4 to keep iteration cheap.

### Default ADC

Default part: **TI TLV320ADC3140**.

Reasons:

- Four ADC channels.
- Differential or single-ended line-input support.
- I2S/TDM digital audio output.
- I2C/SPI control.
- Higher sample-rate headroom than 192 kHz audio ADCs.
- Small enough for eventual integration.
- Linux driver support exists in TI's published collateral.

Risks:

- 4 x 4 mm WQFN package is harder to hand assemble and inspect.
- Raspberry Pi I2S/TDM configuration must be proven early.
- The input full-scale range and common-mode requirements must be matched to the
  ADF5904 baseband path.

### Fallback ADC

Fallback part: **TI PCM1864**.

Use PCM1864 if WQFN assembly or Pi driver work for TLV320ADC3140 becomes the
dominant risk.

Reasons to keep it available:

- Four ADC channels.
- TSSOP package is easier to assemble and probe.
- 192 kHz sample rate may be enough for first Doppler/baseband experiments.
- Differential and single-ended input support.

Tradeoff: it is larger, older, and has less sample-rate headroom.

## Raspberry Pi Integration

The Pi integration should use Linux audio capture rather than custom high-speed
ADC polling.

Target flow:

```text
TLV320ADC3140
    -> I2S/TDM stream
    -> Raspberry Pi audio driver / ALSA device
    -> OpenFlight capture script
    -> calibration and MUSIC processing
```

First software validation should be standalone:

1. ADC board connected to Pi.
2. Inject same coherent tone into all four analog inputs.
3. Capture four channels through ALSA.
4. Verify sample rate, dropped-frame behavior, gain matching, and inter-channel
   phase stability.

Only after that should the ADC path be integrated into the OpenFlight server.

## Data Flow

Runtime prototype data flow:

```text
OPS243 impact / rolling buffer event
    -> timestamped shot candidate
    -> Rev B2 ADC capture window
    -> four baseband channel streams
    -> calibration correction
    -> MUSIC / beamforming angle estimate
    -> OpenFlight shot object
```

Offline-first processing remains the safest path:

- Capture raw four-channel baseband windows.
- Log raw data with shot metadata.
- Reprocess in Python until the signal model is stable.
- Only then fold the estimator into the live launch-monitor path.

## Calibration Plan

Calibration is required before trusting any spatial result.

Minimum calibration artifacts:

- Measured antenna phase-center coordinates.
- Per-channel gain correction.
- Per-channel phase offset correction.
- Known target or controlled reflector measurements.
- Empty-scene leakage/baseline capture.
- Repeatability checks after mechanical reassembly.

Expected calibration outputs:

```text
rx_channel_1: gain, phase_offset
rx_channel_2: gain, phase_offset
rx_channel_3: gain, phase_offset
rx_channel_4: gain, phase_offset
array_geometry: x/y/z phase-center coordinates
```

## PCBWay / Fabrication Constraints

RF board:

- Controlled RF stackup, likely Rogers RO4350B or equivalent.
- L1-to-L2 dielectric target starts at 0.254 mm / 10 mil, but must be confirmed
  with PCBWay before final antenna dimensions.
- Copper kept at least 0.3 mm from board edge.
- Minimum trace/space rules should target PCBWay's 4-layer capabilities:
  0.09 mm minimum trace and spacing or larger.
- No soldermask over patch copper or critical RF feed copper unless the RF model
  explicitly assumes it.
- Surface finish should be selected with RF loss and assembly in mind.

ADC board:

- Standard FR-4.
- Prefer assembly-friendly passives and test points.
- If TLV320ADC3140 is used, require PCBWay assembly review for WQFN paste/mask.

## Validation Gates

### Before RF Board Fabrication

- KiCad DRC with PCBWay-like rules.
- Gerber analyzer check.
- ADF5904 footprint and pinout checked against datasheet/package drawing.
- ADF5904 reference design compared against Rev B2 schematic.
- RF feed and antenna dimensions reviewed against final PCBWay stackup.
- Copper edge clearance checked.
- Soldermask openings checked around RF structures.
- Baseband output connector pinout reviewed against ADC board schematic.

### Before ADC Board Fabrication

- TLV320ADC3140 schematic checked against datasheet/reference design.
- Pi I2S/TDM pinout and overlay plan documented.
- Analog input common-mode and full-scale range checked against RF board output.
- ADC clock tree and power rails reviewed.
- KiCad ERC and DRC pass.
- Test points present for all analog inputs, clocks, I2C/SPI, and I2S/TDM.

### Before Combined Testing

- ADC board captures four coherent test-tone channels on Raspberry Pi.
- RF board baseband outputs can be measured independently.
- RF board and ADC board share a clear grounding/reference plan.
- Combined capture does not clip or sit below noise floor during controlled
  signal injection.

## Risk Register

| Risk | Mitigation |
| --- | --- |
| 2x2 patch subarray is mistuned | Recalculate from actual stackup, request RF vendor review, measure with VNA where possible. |
| Passive OPS243 downconversion lands outside ADC bandwidth | Include LO tuning plan and log measured beat frequency before relying on ball tests. |
| TLV320ADC3140 driver/overlay work takes longer than expected | Keep PCM1864 fallback and expose enough board-level test points to debug I2S/TDM. |
| ADF5904 baseband output does not match ADC input range | Add configurable gain/attenuation/filtering stage or component options. |
| Channel phase is not stable enough for MUSIC | Calibrate with known target, keep RF routing symmetric, use one ADF5904 and one ADC clock domain. |
| RF board is too expensive to iterate | Keep ADC separate on FR-4 and do not integrate extra digital complexity into the RF board. |

## Out Of Scope For Rev B2

- Fully integrated one-board RF + ADC + Pi module.
- Active 24 GHz transmitter design.
- Production enclosure integration.
- Live launch-angle replacement in the OpenFlight UI.
- Final spin/trajectory model integration.

## Immediate Next Steps After Spec Approval

1. Create a Rev B2 implementation plan.
2. Build the ADC/Pi board first as the cheapest risk reducer.
3. Validate four-channel coherent capture on Raspberry Pi.
4. Generate the RF board schematic/layout with ADF5904 and 2x2 RX subarrays.
5. Run KiCad/PCBWay validation gates before any new PCBWay upload.
