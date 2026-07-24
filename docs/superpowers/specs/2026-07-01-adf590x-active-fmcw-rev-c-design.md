# ADF590x Active FMCW Radar Rev C Design

## Goal

Replace the Rev B2 passive RX array with a self-contained active 24 GHz FMCW
radar that supplements the OPS243-A with range, Doppler, and angle-of-arrival
measurement of the golf ball and club:

```text
TX patch column <- ADF5901 (24 GHz VCO + PA + LO out)
                       |  LO (24 GHz)             ^ VTUNE via loop filter
                       v                          |
4x RX 2x2 subarrays -> ADF5904 (4ch RX)   ADF4159 (PLL + ramp gen) <- ref osc
                       |  4x differential baseband
                       v
       RC anti-alias -> interface connector -> TLV320ADC3140 (FR4 board)
                       -> Raspberry Pi I2S/TDM -> raw capture -> MUSIC/range-Doppler
```

Rev C abandons the passive-listening architecture because coherence with the
OPS243's free-running carrier requires ~1 ppm LO matching, which is not
achievable without a 24 GHz carrier-recovery or LO-amplification subsystem.
In the active architecture, TX and LO come from the same PLL, so coherence
holds by construction.

## Hard Constraints

1. **200 mph targets.** The signal chain must observe ball/club radial speeds
   up to 200 mph (Doppler ~14.4 kHz at 24.2 GHz). The chirp slope is chosen so
   the range beat dominates Doppler at all usable ranges (>= 2 m), avoiding
   fold-over ambiguity with the ADF5904's real-valued outputs.
2. **Antenna geometry verified three ways.** EM simulation against the
   PCBWay-confirmed stackup, written stackup confirmation before dimension
   freeze, and a VNA-measurable coupon panelized with the main board.
3. **Raw I/Q at the Raspberry Pi.** The Pi must receive raw, bit-exact
   4-channel samples (ALSA `hw` device, no resampling or mixing). The ADF5904
   outputs real-valued baseband (one mixer per channel, not hardware I/Q);
   complex I/Q per chirp is derived in software by per-chirp FFT, preserving
   inter-channel phase for MUSIC. Raw-sample session logging (like the
   existing `iq_blocks` entries) is part of the capture contract.
4. **Minimum cost.** Smallest viable Rogers area, hybrid stackup, 2-of-5
   assembly, 0402 passives, single-side placement.

## Decision Summary

- **Active slow-FMCW**: range + Doppler + AoA. CW mode retained as a
  bring-up/configuration option (it is a register setting, not hardware).
- **ADI three-chip lineup**: ADF5901 (TX + LO), ADF5904 (4-channel RX),
  ADF4159 (PLL/ramp generator). Application circuits ported verbatim from
  ADI's radar chipset reference design (EV-RADAR-MMIC2 class); custom design
  is limited to antennas, board outline, connector, and power entry.
- **Two boards**: RF board on hybrid Rogers, ADC/Pi interface board on FR4.
  The Rev B2 ADC board design carries forward with a revised control header
  and anti-alias values.
- **Compact RX array**: four 2x2 patch subarrays in a 2x2 grid at ~1 lambda
  pitch. Unambiguous AoA within the subarray beamwidth on both axes.
- **PCBWay assembly** of 2 of 5 RF boards (turnkey or partial turnkey).
- **Native KiCad authoring**: the `generate_designs.mjs` pipeline is retired
  for Rev C. Gerbers are produced only by `kicad-cli` export, so DRC/ERC
  certify the same artifact PCBWay receives.

## Band Plan and OPS243 Coexistence

- OPS243-A: CW at 24.125 GHz, unchanged.
- Rev C chirp band: **24.150 to 24.250 GHz** (upper ISM band), sawtooth
  up-chirps. Minimum 25 MHz guard to the OPS carrier.
- Coexistence holds in both directions: Rev C mixes against its own chirp, so
  OPS energy lands >= 25 MHz off in baseband, far outside the ~100 kHz
  anti-alias corner. Rev C's TX is always >= 25 MHz from 24.125 GHz, far
  outside the OPS's ~50 kHz Doppler baseband.
- Regulatory checklist item: verify TX EIRP (~+8 dBm PA + ~10-11 dBi column,
  ~+18 dBm EIRP) against FCC Part 15.245/15.249 field-strength limits once
  the TX antenna gain is final.

## Waveform

| Parameter | Nominal | Notes |
| --- | --- | --- |
| Sweep bandwidth | 100 MHz (24.150-24.250 GHz) | 1.5 m range resolution |
| Chirp duration | 150 us (sawtooth) | configurable via ADF4159 registers |
| Slope | 6.7e11 Hz/s | range beat dominates 200 mph Doppler beyond ~2 m |
| Range beat, 2-15 m | 9-67 kHz | plus Doppler up to +/-14.4 kHz -> max ~81 kHz |
| ADC sample rate | 384 kHz default | 192 kHz acceptable for slower chirps |
| Anti-alias corner | ~100 kHz | values on the FR4 board, easy to revise |
| Chirp sync | ADF4159 MUXOUT -> Pi GPIO (coarse) + flyback artifact in baseband (fine) | no hardware trigger into the audio ADC needed |

Bring-up mode: fixed CW at 24.200 GHz for first Doppler/AoA validation before
enabling ramps.

## RF Board (hybrid Rogers, ~70 x 50 mm)

- **RX antennas**: four 2x2 patch subarrays in a 2x2 grid at 12.5 mm
  (~1 lambda at 24.2 GHz) pitch: azimuth pair + elevation pair. Grating
  ambiguity falls outside the subarray's ~+/-25 degree beam, so AoA is
  effectively unambiguous in the usable field of view. Each subarray uses an
  equal-path-length corporate feed with quarter-wave transformers, feeding
  the patch at an inset or edge feed point (not the patch center).
- **TX antenna**: single series-fed 1x4 patch column on ADF5901 TX1
  (~10-11 dBi). TX2 terminated per reference design. TX placed at the board
  edge >= 20 mm from the RX grid behind a stitched via fence.
- **ADF5904**: RX inputs matched per reference design; exposed pad on a full
  via field to the ground plane (this and all LFCSP exposed pads follow ADI
  land patterns).
- **ADF5901 + ADF4159**: loop filter, reference oscillator, and decoupling
  copied from the ADI reference design; component values confirmed against
  datasheets during schematic capture.
- **Baseband**: light RC network per reference design, then to the connector.
  Scaling and final anti-alias live on the FR4 board.
- **Power**: 5 V in from the interface connector; local regulator set ported
  from the ADI reference design. Datasheet extraction (2026-07-01) shows this
  includes a 1.8 V digital rail for the ADF4159 in addition to the analog
  3.3 V rails (reference board uses 4 regulators), and lower currents than
  first budgeted (ADF5901 ~170 mA; total ~380 mA), so the ~600 mA / 5 V
  budget has healthy headroom.
- **Stackup**: 4-layer hybrid, 10 mil RO4350B core L1-L2 (all RF references
  L2), FR4 below. Exact stackup table obtained in writing from PCBWay before
  any antenna dimension is frozen. Patch calculations use the Rogers design
  Dk (3.66), not the process Dk.
- **Finish**: ENIG. Soldermask pulled back from patches and all RF feed
  copper. Copper-to-edge clearance >= 0.3 mm everywhere, including planes.
- **Fiducials** (3x) and test points on control lines for assembly and
  bring-up.

## Interface (RF board <-> ADC board)

2x15 position, 1.27 mm pitch SMD header with ribbon harness (real MPN chosen
from stocked parts at schematic time). Signal groups:

- 8x baseband (BB1_P/N .. BB4_P/N), each pair separated by ground
- 5 V, interleaved grounds
- Shared SPI: SCLK, SDATA, SDO/MUXOUT readback
- LE_5901, LE_5904, LE_4159 (three latch lines)
- CE, TX_EN, RAMP_SYNC (ADF4159 MUXOUT -> Pi GPIO)

## ADC/Pi Board Changes from Rev B2

- New header pinout matching the interface above.
- Anti-alias/input scaling sized for the ~100 kHz beat band; values chosen
  after the first measured ADF5904 output levels (component sites reserved).
- Capture at 384 kHz (default) via TLV320ADC3140; ALSA `hw` device, bit-exact,
  32-bit slots, no dmix/resampling.
- One Pi GPIO reserved for RAMP_SYNC timestamping.
- Test points on all analog inputs, clocks, I2C/SPI, and I2S/TDM.
- Everything else (TLV320ADC3140 application circuit, PCM1864 fallback
  decision, Pi header) carries over from the Rev B2 spec.

## Validation Gates Before Ordering

1. Datasheet sync for ADF5901, ADF5904, ADF4159, TLV320ADC3140; pin-level
   schematic verification against datasheets and the ADI reference design.
2. PCBWay written stackup confirmation (hybrid RO4350B/FR4) **before**
   antenna dimension freeze. Quote parameters must pin the stackup table
   explicitly, not defaults (the Rev B2 quote defaulted to 1.6 mm, which did
   not match the intended 0.8 mm/10 mil-core stackup).
3. EM simulation (openEMS) of patch element -> 2x2 subarray -> grid mutual
   coupling against the confirmed stackup; S11 bandwidth must cover
   24.150-24.250 GHz.
4. VNA coupon on the panel: standalone 2x2 subarray + 50 ohm line + connector
   launch.
5. Full kicad-skill analyzer suite, KiCad DRC/ERC clean on the exported
   gerbers, PCBWay assembly review of the three LFCSP land patterns.

## Cost (anchored to the real Rev B2 quote: $686/5 pcs at 120x80 mm)

| Item | Estimate | Notes |
| --- | --- | --- |
| Bare RF boards (5x, 70x50 mm hybrid) | $300-450 | area is ~1/3 of Rev B2; Rogers pricing is sublinear in area; hybrid stackup is the lever to reach the low end |
| Assembly (2 of 5) | $150-250 | quote-based; setup dominates |
| RF silicon + passives (2 boards) | ~$170 | ADF5904 ~$35, ADF5901 ~$25, ADF4159 ~$12, TCXO/LDOs/passives ~$15 per board |
| **RF board all-in** | **$650-850** | |
| ADC/Pi board (FR4) + parts | $100-150 | |

Cost floors applied: smallest viable Rogers area, 0402 passives, single-side
placement, 2-of-5 assembled, green mask, standard build time.

## Risk Register

| Risk | Mitigation |
| --- | --- |
| Patch/feed mistuned on real stackup | Three-way verification (EM sim + written stackup + VNA coupon); design Dk 3.66; soldermask pulled off RF copper |
| TX-to-RX leakage swamps close targets | >= 20 mm separation + via fence; leakage appears at near-zero beat and is filtered with the DC bin; measure during bring-up |
| Real-valued baseband folds range/Doppler | Slope chosen so range beat dominates at >= 2 m; slope configurable if field geometry differs |
| ADF4159/5901/5904 register bring-up complexity | Copy ADI eval software register sequences; CW bring-up mode first |
| Pi 5 V rail sags under ~600 mA extra load | Power budget check during ADC-board bring-up; external 5 V supply as fallback |
| PCBWay hybrid stackup differs from sim assumptions | Dimension freeze only after written stackup table; coupon verifies as-built |
| LFCSP assembly yield | PCBWay assembly with ADI land patterns, fiducials, assembly review gate |
| Interference with OPS243 despite band plan | 25 MHz guard verified at bring-up by capturing with OPS on/off |

## Out of Scope for Rev C

- TDM-MIMO (ADF5901 TX2) — candidate for Rev D once single-TX works.
- Replacing the OPS243 (it remains the ball-speed/spin/trigger instrument).
- Production enclosure, final mechanical stack.
- Live integration into the OpenFlight UI (offline raw-capture processing
  first, matching the existing session-log workflow).

## Bring-Up Order

1. ADC/Pi board first: prove 4-channel bit-exact 384 kHz capture with
   injected tones (same "first capture contract" as Rev B2's INTERFACE.md).
2. RF board in CW mode: verify LO lock, per-channel Doppler from a moving
   reflector, inter-channel phase stability.
3. Enable FMCW ramps: verify range beat against a corner reflector at known
   distances; verify OPS243 coexistence (capture with OPS on/off).
4. Calibrate per-channel gain/phase and array geometry; then MUSIC/
   range-Doppler on real shots, offline first.
