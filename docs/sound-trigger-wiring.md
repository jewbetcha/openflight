# Sound Trigger Wiring Guide

This guide provides step-by-step instructions for wiring the hardware sound trigger circuit that enables ultra-low-latency triggering of the OPS243-A radar in rolling buffer mode.

## Overview

The sound trigger detects the impact of a golf club hitting a ball and triggers the radar to dump its I/Q buffer. This captured data is then analyzed for spin rate estimation.

### The Problem

The SparkFun SEN-14262 sound detector outputs ~2.5V on its GATE pin when triggered. However, the OPS243-A HOST_INT pin has:
- A high input threshold (~3.0V required)
- Very low input impedance (~27Ω)

This means the SEN-14262 cannot directly drive HOST_INT - it needs a circuit that can output 3.3V with enough current (~100mA+).

### The Solution

Use two IRLZ44N N-channel MOSFETs configured as a **double-inverter** with a strong pull-up resistor. This provides:
- Full 3.3V output voltage
- High current drive capability (~700mA with 4.7Ω pull-up)
- Ultra-low latency (~1μs switching time)
- Non-inverted output (GATE HIGH → HOST_INT HIGH)

---

## Parts Required

| Part | Quantity | Notes |
|------|----------|-------|
| IRLZ44N MOSFET | 2 | Logic-level N-channel, TO-220 package |
| 4.7Ω resistor | 1 | Strong pull-up for HOST_INT (1/4W or higher) |
| 10kΩ resistor | 1 | Weak pull-up for first stage |
| 1kΩ resistor | 1 | Gate protection (optional but recommended) |
| Breadboard | 1 | Standard solderless breadboard |
| Jumper wires | Several | For connections |

**Where to buy IRLZ44N:** [Amazon - IRLZ44N 10-pack](https://www.amazon.com/dp/B0CBKH4XGL)

---

## IRLZ44N Pin Identification

Hold the MOSFET with the **metal tab facing away from you** and **pins pointing down**:

```
      ┌─────────────┐
      │  (metal)    │  ← Metal heatsink tab
      │    tab      │
      └──────┬──────┘
             │
      ┌──────┴──────┐
      │             │
     ┌┴┐   ┌───┐   ┌┴┐
     │1│   │ 2 │   │3│
     └─┘   └───┘   └─┘
    GATE  DRAIN  SOURCE
     (G)   (D)     (S)
```

- **Pin 1 (left)** = GATE (G) - Control input
- **Pin 2 (middle)** = DRAIN (D) - Current input
- **Pin 3 (right)** = SOURCE (S) - Current output (to ground)

---

## Circuit Diagram

```
                SEN-14262                    BREADBOARD                         OPS243-A
              ┌───────────┐                                                   ┌──────────┐
              │           │                    3.3V RAIL                      │          │
  Pi 3.3V ────┼── VCC     │         ════════════╤═══════════════════          │          │
              │           │                     │                             │          │
              │           │                   [10kΩ]          [4.7Ω]          │          │
              │           │                     │               │             │          │
              │   GATE ───┼──[1kΩ]──►Gate      Drain           Drain ────────►│ HOST_INT │
              │           │                   ┌─┴─┐    wire   ┌─┴─┐           │ (J3 P3)  │
              │           │                   │Q1 │ ─────────►│Q2 │           │          │
              │           │                   └─┬─┘  (G to D) └─┬─┘           │          │
              │           │                     │               │             │          │
  Pi GND ─────┼── GND     │         ════════════╧═══════════════╧═════════════┼── GND    │
              │           │                   GND RAIL                        │ (J3 P1)  │
              └───────────┘                                                   └──────────┘
```

---

## Step-by-Step Wiring Instructions

### Step 1: Set Up Power Rails

1. Connect **Pi 3.3V** (physical pin 1) to the **red (+) power rail** on the breadboard
2. Connect **Pi GND** (physical pin 6) to the **blue (-) ground rail** on the breadboard

```
Raspberry Pi                    Breadboard
┌────────────┐                 ┌─────────────────┐
│ Pin 1 (3.3V)│ ──────────────►│ Red rail (+)    │
│ Pin 6 (GND) │ ──────────────►│ Blue rail (-)   │
└────────────┘                 └─────────────────┘
```

---

### Step 2: Insert First MOSFET (Q1)

1. Insert **MOSFET Q1** into the breadboard
2. Orient it with the metal tab facing away from you
3. Each pin should be in a different row

```
Breadboard (example rows):
Row 5:  Q1 Gate (pin 1)
Row 6:  Q1 Drain (pin 2)
Row 7:  Q1 Source (pin 3)
```

---

### Step 3: Wire First MOSFET (Q1)

**3a. Connect Q1 Source to Ground:**
- Run a jumper from **Q1 Source (pin 3)** to the **blue GND rail**

**3b. Connect 10kΩ Pull-up to Q1 Drain:**
- Connect the **10kΩ resistor** between **Q1 Drain (pin 2)** and the **red 3.3V rail**

**3c. Connect 1kΩ Gate Protection:**
- Connect the **1kΩ resistor** to **Q1 Gate (pin 1)**
- The other end goes to a free row (we'll connect GATE here in Step 5)

After Step 3:
```
         3.3V (red rail)
           │
         [10kΩ]
           │
           ├────────── (junction for Q2 gate - Step 4)
           │
          ┌┴┐
    1kΩ ──┤ │ Q1
          └┬┘
           │
         GND (blue rail)
```

---

### Step 4: Insert and Wire Second MOSFET (Q2)

**4a. Insert Q2:**
- Insert **MOSFET Q2** a few rows below Q1
- Same orientation (metal tab away from you)

**4b. Connect Q2 Source to Ground:**
- Run a jumper from **Q2 Source (pin 3)** to the **blue GND rail**

**4c. Connect Q2 Gate to Q1 Drain:**
- Run a jumper wire from **Q1 Drain (pin 2)** to **Q2 Gate (pin 1)**

**4d. Connect 4.7Ω Pull-up to Q2 Drain:**
- Connect the **4.7Ω resistor** between **Q2 Drain (pin 2)** and the **red 3.3V rail**
- This is the strong pull-up that provides high current to HOST_INT

After Step 4:
```
         3.3V (red rail)
           │
         [4.7Ω]  ← Strong pull-up!
           │
           ├─────────► (to HOST_INT - Step 6)
           │
          ┌┴┐
From Q1 ──┤ │ Q2
Drain     └┬┘
           │
         GND (blue rail)
```

---

### Step 5: Connect SEN-14262 Sound Detector

**5a. Connect VCC:**
- Connect **SEN-14262 VCC** to the **red 3.3V rail**

**5b. Connect GND:**
- Connect **SEN-14262 GND** to the **blue GND rail**

**5c. Connect GATE:**
- Connect **SEN-14262 GATE** to the free end of the **1kΩ resistor** (from Step 3c)

```
SEN-14262              Breadboard
┌─────────┐           ┌─────────────────┐
│ VCC     │ ─────────►│ Red rail (3.3V) │
│ GND     │ ─────────►│ Blue rail (GND) │
│ GATE    │ ─────────►│ 1kΩ → Q1 Gate   │
└─────────┘           └─────────────────┘
```

---

### Step 6: Connect to OPS243-A Radar

**6a. Connect HOST_INT:**
- Run a wire from **Q2 Drain (pin 2)** to **OPS243-A HOST_INT (J3 Pin 3)**

**6b. Connect GND:**
- Run a wire from the **blue GND rail** to **OPS243-A GND (J3 Pin 1)**

```
OPS243-A J3 Header Pin Layout:
┌───┬───┬───┬───┬───┬───┐
│ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │
│GND│   │INT│   │   │   │
└───┴───┴───┴───┴───┴───┘
  ▲       ▲
  │       └── HOST_INT (connect to Q2 Drain)
  └────────── GND (connect to blue rail)
```

---

## Wiring Checklist

Use this checklist to verify your connections:

- [ ] Pi 3.3V (pin 1) → breadboard red rail
- [ ] Pi GND (pin 6) → breadboard blue rail
- [ ] SEN-14262 VCC → red 3.3V rail
- [ ] SEN-14262 GND → blue GND rail
- [ ] SEN-14262 GATE → 1kΩ resistor → Q1 Gate (pin 1)
- [ ] Q1 Source (pin 3) → blue GND rail
- [ ] Q1 Drain (pin 2) → 10kΩ resistor → red 3.3V rail
- [ ] Q1 Drain (pin 2) → wire → Q2 Gate (pin 1)
- [ ] Q2 Source (pin 3) → blue GND rail
- [ ] Q2 Drain (pin 2) → 4.7Ω resistor → red 3.3V rail
- [ ] Q2 Drain (pin 2) → OPS243-A HOST_INT (J3 Pin 3)
- [ ] Blue GND rail → OPS243-A GND (J3 Pin 1)

---

## How It Works

The double-inverter provides a non-inverted, high-current output:

| State | GATE | Q1 | Q1 Drain | Q2 | Q2 Drain (HOST_INT) |
|-------|------|----|---------|----|---------------------|
| Quiet | LOW (~0V) | OFF | HIGH (3.3V) | ON | **LOW (~0V)** |
| Sound | HIGH (~2.5V) | ON | LOW (~0V) | OFF | **HIGH (~3.3V)** |

**When sound is detected:**
1. SEN-14262 GATE goes HIGH (~2.5V)
2. Q1 turns ON, pulling Q1 Drain LOW
3. Q2 turns OFF, allowing 4.7Ω resistor to pull Q2 Drain HIGH
4. HOST_INT receives 3.3V with ~700mA current capability
5. Radar triggers and dumps its I/Q buffer

---

## Testing the Circuit

### Test 1: Voltage Measurement

1. Power on the Pi and radar
2. Measure voltage at **Q2 Drain** (the HOST_INT connection point) with a multimeter
3. **When quiet:** Should read **~0V**
4. **When you clap:** Should briefly spike to **~3.3V** then return to ~0V

### Test 2: Software Verification

Run the hardware trigger test script:

```bash
uv run python scripts/test_sound_trigger_hardware.py
```

Expected output:
```
======================================================================
  Direct Hardware Sound Trigger Test
  (SEN-14262 GATE → MOSFET Driver → HOST_INT)
======================================================================

Connecting to radar...
  Connected on: /dev/ttyACM0
  Firmware: 1.3.2

Configuring rolling buffer mode (S#12)...

----------------------------------------------------------------------
Ready for hardware sound triggers!
  Pre-trigger: S#12

Make a sound near the sensor... (Ctrl+C to quit)
----------------------------------------------------------------------

[1] Waiting for hardware trigger (timeout=60s)...
  TRIGGER RECEIVED after 0.02s!
  Response size: 12847 bytes
  I/Q samples: 4096 I, 4096 Q
  Total readings: 23
  Outbound: 15 (peak: 78.3 mph)
  Inbound: 8 (peak: 12.1 mph)
  SWING DETECTED: 12 readings >= 15 mph, peak 78.3 mph
  Re-arming buffer...
```

---

## Troubleshooting

### No trigger received

1. **Check GATE signal:** Measure SEN-14262 GATE with multimeter. Should go from ~0V to ~2.5V on sound.
2. **Check Q1 switching:** Measure Q1 Drain. Should go from ~3.3V (quiet) to ~0V (sound).
3. **Check Q2 output:** Measure Q2 Drain. Should go from ~0V (quiet) to ~3.3V (sound).
4. **Verify GND connections:** All grounds must be connected together.

### Voltage at Q2 Drain is always 0V

- Check that 4.7Ω resistor is connected between Q2 Drain and 3.3V rail
- Verify Q2 Gate is connected to Q1 Drain (not Q1 Gate)

### Voltage at Q2 Drain is always 3.3V

- Check that Q2 Source is connected to GND
- Verify SEN-14262 GATE is connected through the 1kΩ to Q1 Gate

### Radar triggers but no I/Q data

- Verify radar is in rolling buffer mode (GC command)
- Check USB serial connection
- Try running `uv run python scripts/test_sound_trigger_hardware.py --timeout 120`

---

## Alternative: GPIO Passthrough Method

If you don't have MOSFETs, you can use the Pi's GPIO as a software-controlled trigger. This has higher latency (~10μs with lgpio callbacks) but requires no additional components.

See [PARTS.md](PARTS.md) for GPIO passthrough wiring, or use:

```bash
scripts/start-kiosk.sh --mode rolling-buffer --trigger sound-passthrough
```

---

## Running the Launch Monitor

Once wiring is complete and tested, start the launch monitor with hardware sound triggering:

```bash
scripts/start-kiosk.sh --mode rolling-buffer --trigger sound
```

This uses the hardware trigger path: SEN-14262 → MOSFET Driver → HOST_INT → Radar buffer dump.
