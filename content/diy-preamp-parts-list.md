# DIY High-Gain Preamp for CDM324/HB100 Radar

Based on [limpkin's CDM324 backpack design](https://github.com/limpkin/cdm324_backpack) - a proven 84dB gain amplifier specifically designed for Doppler radar speed sensing.

## Why This Design?

Your dual LM358 setup didn't work because:
1. **Wrong gain curve** - Generic LM358 modules aren't tuned for Doppler frequencies
2. **No filtering** - Amplifies everything including interference
3. **Poor noise performance** - LM358 has high input noise

This design uses:
- **OPA2365** - Low noise, high bandwidth op-amp
- **Bandpass filtering** - Only amplifies 3.4Hz to 999Hz (the Doppler range)
- **84dB total gain** - Two stages of 125.5x each = 15,758x total
- **Rail-to-rail output** - Full 0-5V swing for ADC

---

## Parts List

### Active Components

| Ref | Part | Value | Package | DigiKey | ~Price |
|-----|------|-------|---------|---------|--------|
| U1 | OPA2365AIDR | Dual Op-Amp | SOIC-8 | 296-31704-1-ND | $4.50 |
| U2 | MAX9031AUK+T | Comparator | SOT-23-5 | MAX9031AUK+TCT-ND | $2.80 |
| Q1 | SI2301CDS | P-MOSFET | SOT-23 | SI2301CDS-T1-GE3CT-ND | $0.50 |
| D1 | S1B | Schottky | SMA | S1BFSCT-ND | $0.40 |
| FB1 | HZ0805D102R-10 | Ferrite Bead | 0805 | 240-2397-1-ND | $0.30 |

### Resistors (all 0805, 1%)

| Ref | Value | Qty | DigiKey | ~Price |
|-----|-------|-----|---------|--------|
| R1, R2, R3, R10, R11 | 10kΩ | 5 | 311-10.0KCRCT-ND | $0.50 |
| R4, R5, R6 | 4.7kΩ | 3 | 311-4.70KCRCT-ND | $0.30 |
| R7, R8 | 590kΩ | 2 | 311-590KCRCT-ND | $0.20 |
| R9 | 8.2kΩ | 1 | 311-8.20KCRCT-ND | $0.10 |

### Capacitors (all 0805)

| Ref | Value | Qty | DigiKey | ~Price |
|-----|-------|-----|---------|--------|
| C1-C5, C8-C11 | 10µF | 9 | 1276-2872-1-ND | $1.80 |
| C6, C7 | 270pF | 2 | 311-1123-1-ND | $0.20 |

### Connectors & Misc

| Ref | Part | DigiKey | ~Price |
|-----|------|---------|--------|
| P1 | 1x5 pin header | S1011EC-05-ND | $0.50 |
| P2 | 1x3 pin header | S1011EC-03-ND | $0.30 |

---

## Total Estimated Cost

| Category | Cost |
|----------|------|
| Active components | ~$8.50 |
| Resistors | ~$1.10 |
| Capacitors | ~$2.00 |
| Connectors | ~$0.80 |
| PCB (OSHPark or JLCPCB) | ~$5-10 |
| **Total** | **~$18-22** |

*Prices from DigiKey, buying minimum quantities. Bulk or AliExpress alternatives could be cheaper.*

---

## Simplified Breadboard Version

If you don't want to make a PCB, here's a minimal breadboard-friendly version:

### Core Components Only

| Part | Value | Through-hole Alternative |
|------|-------|-------------------------|
| U1 | OPA2365 | Use DIP-8 socket + SOIC adapter, OR substitute **OPA2134PA** (DIP-8) |
| R (gain) | 590kΩ | 2x 300kΩ in series |
| R (bias) | 10kΩ | Standard 1/4W |
| R (input) | 4.7kΩ | Standard 1/4W |
| C (coupling) | 10µF | Electrolytic, 16V+ |
| C (filter) | 270pF | Ceramic disc |

### Breadboard-Friendly Op-Amp Alternatives

| Op-Amp | Package | GBW | Notes |
|--------|---------|-----|-------|
| **OPA2134PA** | DIP-8 | 8MHz | Good substitute, easy to find |
| **TL072** | DIP-8 | 3MHz | Very common, lower performance |
| **NE5532** | DIP-8 | 10MHz | Audio-grade, good noise |
| **AD822** | DIP-8 | 1.8MHz | Rail-to-rail, single supply |

*The OPA2365's 50MHz bandwidth is overkill for Doppler frequencies - any of these will work.*

---

## Circuit Overview

```
                     +5V
                      │
                      ├──[FB1]──┬──────────────────────┐
                      │         │                      │
                     ┌┴┐       ═══ C1                  │
                R1   │ │ 10k    │ 10µF                 │
               10k   └┬┘        │                      │
                      │         │                      │
CDM324    ┌───────────┼─────────┴───────┐              │
  IF ─────┤           │                 │              │
          │  ┌────────┴────────┐        │              │
          │  │     STAGE 1     │        │              │
        ──┴──│  OPA2365 (1/2)  │────────┼──────────────┤
   C2        │   Gain: 125.5x  │        │              │
  10µF       │   BPF: 3-999Hz  │        │              │
             └────────┬────────┘        │              │
                      │                 │              │
                      │    ┌────────────┴────────┐     │
                      │    │      STAGE 2        │     │
                      └────│  OPA2365 (2/2)      │─────┘
                           │   Gain: 125.5x      │
                           │   BPF: 3-999Hz      │
                           └────────┬────────────┘
                                    │
                                    ▼
                              To MCP3008 CH0
                           (0-5V analog signal)
```

**Total Gain: 125.5 × 125.5 = 15,758x (84dB)**

---

## Key Design Points

### Why 590kΩ and 4.7kΩ?
- Gain = R_feedback / R_input = 590k / 4.7k = **125.5x per stage**

### Why 270pF capacitors?
- Sets the high-frequency cutoff: f = 1/(2π × 590k × 270p) ≈ **999Hz**
- 999Hz ÷ 71.7 Hz/mph = **~14 mph** max speed with this design
- **For golf, you'll need to change C6/C7 to ~27pF for 150+ mph!**

### Why 10µF coupling caps?
- Sets the low-frequency cutoff: f = 1/(2π × 4.7k × 10µ) ≈ **3.4Hz**
- Blocks DC, passes Doppler frequencies

---

## Modification for Golf Speeds

The original design tops out at ~14 mph. For golf (150+ mph), modify:

| Component | Original | For Golf | Calculation |
|-----------|----------|----------|-------------|
| C6, C7 | 270pF | **27pF** | 150 mph × 71.7 = 10,755 Hz cutoff |

This extends the bandwidth to detect speeds up to ~150 mph while still filtering out high-frequency noise.

---

## Where to Get PCBs

If you want the proper PCB:

1. **Download KiCad files** from [limpkin's GitHub](https://github.com/limpkin/cdm324_backpack/tree/master/kicad)
2. Export Gerbers
3. Upload to:
   - [JLCPCB](https://jlcpcb.com) - ~$2 for 5 boards
   - [OSHPark](https://oshpark.com) - ~$5 for 3 boards
   - [PCBWay](https://pcbway.com) - ~$5 for 10 boards

---

## Alternative: Buy Pre-Made

If this seems like too much, the [Infineon SENSE2GOL PULSE](https://www.digikey.com/en/products/detail/infineon-technologies/DEMOSENSE2GOLPULSETOBO1/12179194) at ~$139 is a complete solution that skips all of this.

---

## Sources

- [limpkin's CDM324 backpack GitHub](https://github.com/limpkin/cdm324_backpack)
- [Original blog post](https://www.limpkin.fr/index.php?post/2017/02/22/Making-the-Electronics-for-a-24GHz-Doppler-Motion-Sensor)
- [Hackaday article](https://hackaday.com/2017/03/31/the-right-circuit-turns-doppler-module-into-a-sensor/)
- [Instructables simple HB100 amp](https://www.instructables.com/Easy-HB100-Amplifier/)
