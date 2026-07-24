# Rev C Board-to-Board Electrical Interface

## RF Board To ADC Board

2×15 header, 1.27 mm pitch, SMD, pin 1 marked. Odd pins row A, even pins row B.

| Pin | Net | Pin | Net |
| --- | --- | --- | --- |
| 1 | +5V | 2 | +5V |
| 3 | GND | 4 | GND |
| 5 | BB1_P | 6 | BB1_N |
| 7 | GND | 8 | GND |
| 9 | BB2_P | 10 | BB2_N |
| 11 | GND | 12 | GND |
| 13 | BB3_P | 14 | BB3_N |
| 15 | GND | 16 | GND |
| 17 | BB4_P | 18 | BB4_N |
| 19 | GND | 20 | GND |
| 21 | SPI_SCLK | 22 | SPI_SDATA |
| 23 | SPI_SDO | 24 | GND |
| 25 | LE_5901 | 26 | LE_5904 |
| 27 | LE_4159 | 28 | CE_RX |
| 29 | TX_EN | 30 | RAMP_SYNC |

### Semantics

- **`CE_RX`** (Pin 28): Drives ADF5904 + ADF4159 chip enables (active high). Used to enable/disable both receiver and LO PLL in sync.
- **`TX_EN`** (Pin 29): Drives ADF5901 CE only (active high). Hardware TX/LO kill switch; independent from receiver enable.
- **`RAMP_SYNC`** (Pin 30): ADF4159 MUXOUT signal → Pi GPIO input. Used for ramp cycle timestamping and synchronization.
- **`SPI_SDO`** (Pin 23): Shared readback line for serial data output. Exact ADF5904 DOUT / ADF4159 MUXOUT wiring finalized when Task 3 datasheet extraction lands. Final mux configuration to be documented in the schematic.
- **Baseband pairs (BB1–BB4)**: Differential outputs from ADF5904 receiver channels. Each pair (P/N) has a dedicated GND pin adjacent to maintain signal integrity.
- **Latch enables**: `LE_5901` (TX LO), `LE_5904` (RX mixer), `LE_4159` (RX LO/ramp) are independent 3-wire latch strobes for SPI register loads.

## ADC Board To Raspberry Pi

| Signal | Direction | Notes |
| --- | --- | --- |
| `I2S_BCLK` | ADC <-> Pi | Bit clock for I2S/TDM. Direction depends on master/slave mode. |
| `I2S_LRCLK` | ADC <-> Pi | Frame sync / word select. Direction depends on master/slave mode. |
| `I2S_DIN` | ADC -> Pi | ADC serial audio data into Raspberry Pi. |
| `I2C_SCL` | Pi -> ADC | ADC control clock. |
| `I2C_SDA` | Pi <-> ADC | ADC control data. |
| `ADC_SHDNZ` | Pi -> ADC | ADC hardware shutdown/reset, active low. |
| `RAMP_SYNC` | RF/ADC -> Pi | GPIO input for ADF4159 ramp cycle sync and timestamping. |
| `3V3` | Pi/power -> ADC | Digital/control rail. Confirm current budget before powering from Pi only. |
| `5V` | Pi/power -> ADC | Optional upstream rail for local regulation. |
| `GND` | shared | Digital/board ground. Tie to analog return at the board ground strategy point. |

## Raw Capture Contract

The ADC board shall present a 4-channel audio capture device to the Linux kernel prior to integration into OpenFlight server code.

- **ALSA device:** Appears as `hw:ADC_BOARD,0` (or detected dynamically via UCM profile)
- **Sample rate:** 384 kHz (default and required)
- **Sample format:** 32-bit signed PCM slots (I2S 32-bit word boundaries)
- **Channels:** 4 (one per ADF5904 receiver output)
- **No resampling:** Route must operate without `dmix` or resampling plugins; sample rate must be exact
- **Bit-exact capture:** No level shifting or digital filtering applied by ALSA layer

### First Capture Validation

Before OpenFlight integration, inject the same coherent tone into all four ADC inputs and verify:

- Four channels are present and readable
- Sample rate is stable over shot-length captures (10+ seconds at 384 kHz ≈ 3.84M samples)
- No dropped frames are visible in continuous streaming
- Channel gain mismatch is measurable and repeatable (normalized per channel for factory calibration)
- Inter-channel phase is stable enough to permit coherent phase calibration
