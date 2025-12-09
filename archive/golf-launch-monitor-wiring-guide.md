# DIY Golf Launch Monitor - Step-by-Step Wiring Guide

## Overview

This guide walks you through connecting:
1. **HB100 Doppler Radar** → Detects ball/club movement
2. **LM358 Amplifier Module** → Boosts the weak radar signal
3. **MCP3008 ADC** → Converts analog signal to digital
4. **Raspberry Pi 5** → Processes data and calculates speed

---

## ⚠️ CRITICAL WARNINGS

Before you start:

1. **MCP3008 uses 3.3V ONLY** - Connecting it to 5V will destroy it!
2. **HB100 and LM358 use 5V** - They need the higher voltage
3. **Double-check every connection** before powering on
4. **Never connect/disconnect wires while powered**

---

## Required Materials

- Breadboard (830 points recommended)
- Jumper wires (male-to-male, male-to-female)
- HB100 Doppler Radar Module
- LM358 Pre-amplifier Module (with 100x gain)
- MCP3008 ADC chip (DIP-16 package)
- Raspberry Pi 5

---

## Step 1: Set Up the Breadboard Power Rails

The breadboard has two power rails at the top and bottom (marked + and -).

### Connect from Raspberry Pi:
```
Pi Pin 2 (5V)    →  Breadboard top "+" rail (RED)
Pi Pin 4 (5V)    →  Breadboard bottom "+" rail (RED) [optional backup]
Pi Pin 6 (GND)   →  Breadboard top "-" rail (BLACK)
Pi Pin 9 (GND)   →  Breadboard bottom "-" rail (BLACK) [optional backup]
```

**Wire colors to use:**
- RED wire for 5V
- BLACK wire for Ground

---

## Step 2: Install the MCP3008 ADC

The MCP3008 is a 16-pin DIP chip. Install it straddling the center channel of the breadboard.

### Orientation:
- Find the **notch or dot** on one end of the chip - this marks Pin 1
- Place the chip with the notch pointing **LEFT**
- Pins 1-8 will be on the bottom, Pins 9-16 on top

```
                    MCP3008 Pin Layout
                    
        (notch)
          ↓
    ┌─────U─────┐
    │ 1      16 │  ← VDD (3.3V Power)
    │ 2      15 │  ← VREF (3.3V Reference)  
    │ 3      14 │  ← AGND (Analog Ground)
    │ 4      13 │  ← CLK (SPI Clock)
    │ 5      12 │  ← DOUT (SPI Data Out)
    │ 6      11 │  ← DIN (SPI Data In)
    │ 7      10 │  ← CS (Chip Select)
    │ 8       9 │  ← DGND (Digital Ground)
    └───────────┘
    
    Pin 1 = CH0 (where our signal connects!)
```

### MCP3008 Connections:

**⚠️ IMPORTANT: Use 3.3V from Pi Pin 1, NOT 5V!**

| MCP3008 Pin | Name | Connect To | Wire Color |
|-------------|------|------------|------------|
| Pin 16 | VDD | Pi Pin 1 (3.3V) | Orange |
| Pin 15 | VREF | Pi Pin 1 (3.3V) | Orange |
| Pin 14 | AGND | Pi Pin 6 (GND) | Black |
| Pin 13 | CLK | Pi Pin 23 (GPIO 11 / SCLK) | Yellow |
| Pin 12 | DOUT | Pi Pin 21 (GPIO 9 / MISO) | Orange |
| Pin 11 | DIN | Pi Pin 19 (GPIO 10 / MOSI) | Blue |
| Pin 10 | CS | Pi Pin 24 (GPIO 8 / CE0) | Purple |
| Pin 9 | DGND | Pi Pin 6 (GND) | Black |
| Pin 1 | CH0 | LM358 Output | Green |

---

## Step 3: Install the LM358 Amplifier Module

If using a pre-built LM358 module (recommended), it will have 4 pins:
- VCC (power in)
- GND (ground)
- IN (signal input)
- OUT (amplified signal output)

### LM358 Module Connections:

| LM358 Pin | Connect To | Wire Color |
|-----------|------------|------------|
| VCC | Breadboard 5V rail (+) | Red |
| GND | Breadboard GND rail (-) | Black |
| IN | HB100 IF pin | Orange |
| OUT | MCP3008 Pin 1 (CH0) | Green |

---

## Step 4: Install the HB100 Radar Module

The HB100 has 3 main connections:
- VCC (5V power)
- GND (ground)  
- IF (intermediate frequency output - the Doppler signal)

### HB100 Connections:

| HB100 Pin | Connect To | Wire Color |
|-----------|------------|------------|
| VCC | Breadboard 5V rail (+) | Red |
| GND | Breadboard GND rail (-) | Black |
| IF | LM358 IN pin | Orange |

---

## Step 5: Connect Everything to Raspberry Pi

### Summary of all Pi connections:

| Pi Pin | Pi Function | Connects To | Purpose |
|--------|-------------|-------------|---------|
| Pin 1 | 3.3V | MCP3008 VDD & VREF | ADC Power |
| Pin 2 | 5V | Breadboard + rail | Power for HB100/LM358 |
| Pin 6 | GND | Breadboard - rail, MCP3008 GND | Common ground |
| Pin 19 | GPIO 10 (MOSI) | MCP3008 DIN | SPI data to ADC |
| Pin 21 | GPIO 9 (MISO) | MCP3008 DOUT | SPI data from ADC |
| Pin 23 | GPIO 11 (SCLK) | MCP3008 CLK | SPI clock |
| Pin 24 | GPIO 8 (CE0) | MCP3008 CS | Chip select |

---

## Wiring Checklist

Before powering on, verify each connection:

### Power Connections:
- [ ] Pi Pin 2 (5V) → Breadboard + rail
- [ ] Pi Pin 6 (GND) → Breadboard - rail
- [ ] Pi Pin 1 (3.3V) → MCP3008 Pin 16 (VDD)
- [ ] Pi Pin 1 (3.3V) → MCP3008 Pin 15 (VREF)

### Ground Connections:
- [ ] MCP3008 Pin 14 (AGND) → Breadboard - rail
- [ ] MCP3008 Pin 9 (DGND) → Breadboard - rail
- [ ] LM358 GND → Breadboard - rail
- [ ] HB100 GND → Breadboard - rail

### SPI Connections (Pi to MCP3008):
- [ ] Pi Pin 19 (MOSI) → MCP3008 Pin 11 (DIN)
- [ ] Pi Pin 21 (MISO) → MCP3008 Pin 12 (DOUT)
- [ ] Pi Pin 23 (SCLK) → MCP3008 Pin 13 (CLK)
- [ ] Pi Pin 24 (CE0) → MCP3008 Pin 10 (CS)

### Signal Path:
- [ ] HB100 IF → LM358 IN
- [ ] LM358 OUT → MCP3008 Pin 1 (CH0)

### Component Power:
- [ ] HB100 VCC → Breadboard + rail (5V)
- [ ] LM358 VCC → Breadboard + rail (5V)

---

## Visual Connection Map

```
                                 RASPBERRY PI 5
                            ┌─────────────────────┐
                            │  3.3V ●  ● 5V       │ ← Pin 1, Pin 2
                            │ GPIO2 ○  ○ 5V       │
                            │ GPIO3 ○  ● GND      │ ← Pin 6
                            │ GPIO4 ○  ○ GPIO14   │
                            │   GND ○  ○ GPIO15   │
                            │GPIO17 ○  ○ GPIO18   │
                            │GPIO27 ○  ○ GND      │
                            │GPIO22 ○  ○ GPIO23   │
                            │  3.3V ○  ○ GPIO24   │
     To MCP3008 DIN ────────│  MOSI ●  ○ GND      │ ← Pin 19
    To MCP3008 DOUT ────────│  MISO ●  ○ GPIO25   │ ← Pin 21
     To MCP3008 CLK ────────│  SCLK ●  ● CE0      │ ← Pin 23, Pin 24
                            │GPIO12 ○  ○ GPIO12   │     ↑
                            │   ... etc ...       │     └── To MCP3008 CS
                            └─────────────────────┘


    SIGNAL FLOW:
    
    ┌─────────┐      ┌─────────────┐      ┌─────────┐      ┌──────────┐
    │  HB100  │ IF   │   LM358     │ OUT  │ MCP3008 │ SPI  │ Pi 5     │
    │  Radar  │─────→│   Amp       │─────→│   ADC   │─────→│          │
    │         │      │  (100x)     │      │  (CH0)  │      │          │
    └─────────┘      └─────────────┘      └─────────┘      └──────────┘
        │                  │                  │
        │ VCC              │ VCC              │ VDD/VREF
        ↓                  ↓                  ↓
    ┌─────────────────────────────────────────────────────────────────┐
    │                    5V POWER RAIL                                 │
    └─────────────────────────────────────────────────────────────────┘
                                              ↑
                                         3.3V ONLY!
                                     (separate from 5V rail)
```

---

## Enable SPI on Raspberry Pi

Before running the software, you must enable SPI:

```bash
sudo raspi-config
```

Navigate to:
1. Interface Options
2. SPI
3. Enable

Then reboot:
```bash
sudo reboot
```

---

## Test Your Connections

After wiring, run this test script to verify the ADC is working:

```python
#!/usr/bin/env python3
import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000

def read_adc(channel):
    cmd = [1, (8 + channel) << 4, 0]
    reply = spi.xfer2(cmd)
    value = ((reply[1] & 0x03) << 8) | reply[2]
    return value

print("Reading ADC Channel 0 (should show ~500-512 at rest)")
print("Wave your hand in front of HB100 to see values change")
print("Press Ctrl+C to exit\n")

try:
    while True:
        value = read_adc(0)
        bar = '█' * (value // 20)
        print(f"CH0: {value:4d} |{bar}")
        time.sleep(0.1)
except KeyboardInterrupt:
    spi.close()
    print("\nDone!")
```

Save this as `test_adc.py` and run with:
```bash
python3 test_adc.py
```

**Expected behavior:**
- At rest: Values around 500-512 (mid-range)
- When waving hand near HB100: Values oscillate

---

## Troubleshooting

### ADC reads all zeros or all 1023:
- Check 3.3V connection to MCP3008 VDD and VREF
- Verify ground connections
- Make sure MCP3008 is oriented correctly (notch = pin 1)

### ADC reads constant value, no change when moving:
- Check HB100 IF → LM358 IN connection
- Verify HB100 has 5V power
- LM358 might need adjustment (if using adjustable module)

### Random values / noise:
- Ensure all ground wires are connected
- Keep HB100 away from Pi (RF interference)
- Add a small capacitor (0.1µF) between signal and ground

### SPI not working:
- Run `ls /dev/spi*` - should show spidev0.0
- If not visible, SPI is not enabled (re-run raspi-config)
- Check all 4 SPI wires (MOSI, MISO, SCLK, CE0)

---

## Next Steps

Once your wiring is verified and the test script shows changing values:

1. Run the main `launch_monitor.py` script
2. Position the HB100 facing the ball/tee area
3. Calibrate by comparing readings to known speeds
4. Consider adding the camera system (Phase 2)

Good luck! 🏌️
