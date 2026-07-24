# Rev C ADC Interface Pin Map

The RF cable is Samtec `FFSD-15-D-03.00-01-N`, straight-through, pin N to pin
N. Reverse (`-R`) and reverse-wired (`-RW`) cable variants are not permitted.

Complete RF-board-to-ADC-board cable map:

| RF J1 pin | ADC J1 pin | Signal |
|---:|---:|---|
| 1 | 1 | +5V |
| 2 | 2 | +5V |
| 3 | 3 | GND |
| 4 | 4 | GND |
| 5 | 5 | BB1_P |
| 6 | 6 | BB1_N |
| 7 | 7 | GND |
| 8 | 8 | GND |
| 9 | 9 | BB2_P |
| 10 | 10 | BB2_N |
| 11 | 11 | GND |
| 12 | 12 | GND |
| 13 | 13 | BB3_P |
| 14 | 14 | BB3_N |
| 15 | 15 | GND |
| 16 | 16 | GND |
| 17 | 17 | BB4_P |
| 18 | 18 | BB4_N |
| 19 | 19 | GND |
| 20 | 20 | GND |
| 21 | 21 | SPI_SCLK |
| 22 | 22 | SPI_SDATA |
| 23 | 23 | SPI_SDO |
| 24 | 24 | GND |
| 25 | 25 | LE_5901 |
| 26 | 26 | LE_5904 |
| 27 | 27 | LE_4159 |
| 28 | 28 | CE_RX |
| 29 | 29 | TX_EN |
| 30 | 30 | RAMP_SYNC |

RF control connections forwarded to the Raspberry Pi:

| RF J1 | Signal | Pi J2 physical pin | BCM GPIO |
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

ADC/Pi connections:

| Function | Pi physical pin | BCM GPIO |
|---|---:|---:|
| I2C_SDA | 3 | 2 |
| I2C_SCL | 5 | 3 |
| I2S_BCLK | 12 | 18 |
| I2S_LRCLK | 35 | 19 |
| I2S_DIN | 38 | 20 |
| ADC_SHDNZ | 16 | 23 |

This board does not use USB. It connects directly to the Raspberry Pi 40-pin
GPIO header for power, I2C control, TDM/I2S data, RF SPI control, and enables.
