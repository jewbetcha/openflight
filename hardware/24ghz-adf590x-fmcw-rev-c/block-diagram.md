# Rev C Active FMCW Radar — Two-Board Block Diagram

System-level block diagram of the Rev C design (spec:
`docs/superpowers/specs/2026-07-01-adf590x-active-fmcw-rev-c-design.md`).
Renders on GitHub and in any Mermaid viewer.

Key relationships: the ADF5901's VCO output is simultaneously the TX chirp and
the ADF5904's LO (coherence by construction); the ADF4159 closes the PLL loop
and generates the FMCW ramps; the OPS243 has no electrical connection — it
coexists ≥25 MHz below the chirp band.

```mermaid
flowchart LR
    OPS["OPS243-A Doppler radar<br/>CW 24.125 GHz<br/>(existing, untouched)"]

    subgraph RF["RF Board — hybrid RO4350B/FR4, 4-layer, ~70×50 mm"]
        direction LR
        TXANT["TX antenna<br/>1×4 series-fed patch column<br/>~10–11 dBi"]
        RXANT["RX array<br/>4× 2×2 patch subarrays<br/>2×2 grid @ 12.5 mm (1λ)"]
        COUPON["VNA coupon strip<br/>(2×2 subarray + 50 Ω line)"]

        ADF5901["ADF5901<br/>24 GHz VCO + PA + LO out"]
        ADF5904["ADF5904<br/>4-ch 24 GHz RX downconverter"]
        ADF4159["ADF4159<br/>PLL + FMCW ramp generator"]
        TCXO["CWX113 TCXO<br/>reference"]
        SHIFT["SN74AVC4T245 / 2T245<br/>3.3 V ↔ 1.8 V level shifters"]
        PWR1["ADP7104 ×2 → 3V3_TX, 3V3_RX<br/>ADP150 → 1V8_DIG"]

        ADF5901 -- "TX 24.15–24.25 GHz chirp" --> TXANT
        ADF5901 -- "LO 24 GHz" --> ADF5904
        ADF5901 -- "÷ divider RF" --> ADF4159
        ADF4159 -- "VTUNE (loop filter)" --> ADF5901
        TCXO --> ADF4159
        SHIFT -- "SPI @ 1.8 V" --> ADF4159
        RXANT -- "RX1–RX4" --> ADF5904
    end

    subgraph ADC["ADC/Pi Board — FR4, 4-layer, ~55×65 mm"]
        direction LR
        AA["Anti-alias filters ×4<br/>1 kΩ + 820 pF, ~97 kHz corner"]
        TLV["TLV320ADC3140<br/>4-ch ADC, 384 kHz, 32-bit"]
        TP["22 test points"]
        AA --> TLV
    end

    PI["Raspberry Pi<br/>raw 4-ch capture (ALSA hw)<br/>→ range-Doppler + MUSIC AoA"]

    OPS -. "coexists ≥25 MHz away<br/>(no RF connection)" .- RF
    ADF5904 == "BB1–BB4 differential<br/>via 2×15 1.27 mm header (J1)" ==> AA
    PI -- "SPI + CE/TX_EN via J1" --> SHIFT
    ADF4159 -- "RAMP_SYNC (MUXOUT)" --> PI
    TLV -- "I2S/TDM + I2C" --> PI
    PI -- "5 V" --> PWR1

    BALL(("golf ball"))
    TXANT -. "illuminate" .-> BALL
    BALL -. "reflect" .-> RXANT
```
