# EV-RADAR-MMIC2 — Reference Evaluation Board (ADF5901 + ADF5904 + ADF4159), UG-866

**Source PDF:** `datasheets/EV-RADAR-MMIC2_UG-866.pdf` (ADI UG-866, Rev. A, 2/2017, 28 pages). Downloaded from Farnell mirror (farnell.com/datasheets/2334747.pdf) after analog.com media host timed out.
**What it is:** ADI's reference FMCW-radar chipset eval board. Contains the full production-quality reference schematic + BOM for the exact three-MMIC front end Rev C is cloning, plus the EV-ADAR-D2S baseband differential-amplifier daughter board. This is the authoritative source for **application-circuit component values** (loop filter, reference oscillator, LDOs, decoupling, RF/LO coupling, baseband stage). (p.1)

---

## Reference architecture (p.1, p.5; schematics Fig.10–14)
- Reference oscillator: on-board **100 MHz TCXO** → ADF4159 REFIN and ADF5901 REFIN. (p.5 Input Signals; Fig.16 Y1)
- ADF4159 CP → passive loop filter → ADF5901 VTUNE.
- ADF5901 AUX/AUX (÷2 = 12 GHz) → ADF4159 RFinA/RFinB feedback.
- **ADF5901 LOOUT → ADF5904 LO_IN** (LO chain; ac-coupled).
- ADF5901 TXOUT1/TXOUT2 (J8/J9 SMA) → Tx antennas; **Tx outputs carry dc bias, must be ac-coupled.** (p.5 RF Output Signals)
- ADF5904 RX1–RX4_RF inputs (J2/J3/J4/J6 SMA), **dc-biased, must be ac-coupled.** (p.5 RF Input Signals)
- ADF5904 differential baseband → **EV-ADAR-D2S** board (AD8130 diff amps) → single-ended → SDP / instrumentation. Production path (datasheet Fig.21/31) uses ADAR7251 Σ-Δ ADC; Rev C substitutes the TLV320ADC3140. (p.1)
- Programming: SDP-S/SDP-B (SPI) via level shifters; on-board EEPROM. (p.6)

## Power supplies (p.5; Fig.14 page 5 of schematic)
- Board input: single **+5 V** to VSUPPLY (P3 red banana), GND (P2 black banana). ADAR-D2S: +9 V (VPOS) and −9 V (VNEG). (p.4–5)
- Input protection on 5 V rail: **D1 = 1N4001** (Multicomp), **D2 = MBR0520LT1G Schottky** (ON Semi), **E1 = ferrite bead** (Würth 7427-92642). (BOM Table 2; Fig.14)
- **Four regulators off the 5 V (AVDD) rail (Fig.14, BOM Table 2):**
  | Ref | Part | Output | Feeds |
  |-----|------|--------|-------|
  | U6 | **ADP7104ARDZ-3.3** (ultralow-noise LDO, 20 V/500 mA) | 3.3 V | AVDD_TX (ADF5901 Tx MMIC rails) |
  | U7 | **ADP7104ARDZ-3.3** | 3.3 V | AVDD_RX (ADF5904 Rx MMIC AVDD) |
  | U4 | **ADP150AUJZ-3.0** | 3.0 V | AVDD_PLL (ADF4159 analog) |
  | U5 | **ADP150AUJZ-1.8** | 1.8 V | DVDD_PLL (ADF4159 digital / Σ-Δ) |
  - ADP7104 uses SENSE pin (point-of-load sense) with 0 Ω series resistor to each MMIC rail; per-output 1 µF caps and 0 Ω series option resistors (R23–R34, R37–R39). (Fig.14)
- ⚠ ADF4159 analog rail on the eval board is **3.0 V** (ADP150-3.0), not 3.3 V — within ADF4159 AVDD range 2.7–3.45 V. Rev C may use 3.3 V (also in range) or match the reference 3.0 V.

## Reference oscillator (Fig.16 page 7; BOM)
- **Y1 = CWX113-100.0M (Connor-Winfield), 100 MHz TCXO** (BOM Table 2). (Datasheet Fig.16 labels a CWX823-100.0M8Z footprint; BOM lists CWX113-100.0M as fitted.)
- Distribution: TCXO OUT buffered → REF net → ADF4159 REFIN (R45) and ADF5901 REFIN, with R41 (1.0k), R42/R44 (do-not-insert options), MCLK tap. C40 = 22 µF, C41 = 10 pF on TCXO supply. (Fig.16)

## ADF4159 loop filter — CPOUT → VTUNE (Fig.12 page 3; BOM Table 2)
Passive 3rd-order:
| Ref | Value | Position |
|-----|-------|----------|
| R19 | **1 kΩ** (0805) | series from CP |
| C12 | **220 pF** | shunt (fast pole) |
| R18 | **510 Ω** | series (middle) |
| C13 | **3.3 nF** | shunt (main) |
| C14 | **100 pF** | shunt (final pole) |
| R20 | **0 Ω** | series to VTUNE |
- Tuned for a ~200 MHz chirp using the 12 GHz AUX feedback path, ~5 ms ramp, per the eval default. **Rev C must re-run ADIsimPLL for its own chirp BW / ramp time and PFD frequency before adopting these values.** (UG-866 p.9–10; ADF4159 datasheet p.34)
- Phase-detector polarity = positive for this passive filter (negative only for inverting active filter). (p.9)

## ADF5901 support parts (Fig.13 page 4; BOM)
- **RSET R22 = 5.1 kΩ** to AGND. (Fig.13)
- REFIN ac-coupling C1 = 1 nF, C2 = 1 nF (RF1 = TBD0805 option). (Fig.13)
- Per-rail decoupling triads **0.1 µF + 1 nF + 10 pF** on TX_AHI (C19/C21), AHI (C22/C28... ), VCO_AHI (C25/C27), etc. VREG/C1-pin/C2-pin caps per datasheet pin table (47 nF / 220 nF). (Fig.13)
- Tx and LO outputs ac-coupled off-board (K-connectors). (p.5)

## ADF4159 support parts (Fig.11 page 2; BOM)
- **RSET R17 = 5.1 kΩ** → I_CP_MAX = 4.8 mA. (Fig.11)
- REFIN ac-coupling: C17 = 1 nF, C19 = 1 nF, series R96 (option). (Fig.11)
- Rail decoupling: AVDD (C3/C4/C5), DVDD (C6/C7), VP (C10/C11) — 0.1 µF/1 nF/10 pF classes. RFinB decoupled ~100 pF per datasheet. (Fig.11)

## ADF5904 support parts (Fig.23 page 14; BOM)
- Per-rail AVDD decoupling triads 0.1 µF + 1 nF + 10 pF: RX12_AHI (C58/C61/C64), RX34_AHI (C59/C62/C65), LO_AHI (C60/C63/C66). (Fig.23)
- RXx_RF and LO_IN ac-coupled with dc bias. Baseband differential outputs to P1 → ADAR-D2S. (Fig.23, p.5)

## Level-shift / digital glue (Fig.15–21; BOM)
- **U8–U11 = SN74AVC4T245PW** (4-bit bus transceivers, 3.3 V↔1.8 V level shift between SDP and ADF4159 1.8 V digital / SPI).
- **U12 = SN74AVC2T245RSWR** (dual bus transceiver).
- **U13 = SN74LVC1G08DCKR** (single AND gate — DOUT select logic).
- **U3 = 24LC32A-I/MS** (Microchip 32 kΩ... 32 kbit I²C serial EEPROM — board ID).
- SPI signals routed through these to ADF5901/ADF5904/ADF4159 CLK/DATA/LE/CE. (Fig.15–21, BOM)

## EV-ADAR-D2S baseband board (Fig.24–28; BOM Table 3)
- **U1–U8 = AD8130ARZ** — 270 MHz differential (difference) receiver amplifiers, one per channel/complement. Converts ADF5904 differential baseband to single-ended.
- Stated gain configs (schematic notes): **Gain 1: RF = 0 Ω, RG = NC. Gain 10: RF = 560 Ω, RG = 62 Ω.** (UG-866 p.1 states "20 dB gain" for the D2S board.)
- Coupling/decoupling: 1 nF and 1 µF ac-coupling (Murata GRM188R61E105KA12D 1 µF, GRM1555C1H101JD01D 100 pF); 10 pF/100 pF/1 µF supply decoupling per amp. 0 Ω link resistors set gain/routing. Powered from ±9 V (VPOS/VNEG). (Fig.25–28, BOM Table 3)
- Rev C replaces this analog single-ended stage with a differential-in path straight to the TLV320ADC3140 (which prefers AC-coupled differential input) — see tlv320adc3140.md.

## Channel mapping (Table 1, p.5)
| EV-RADAR-MMIC2 conn | ADF5904 input | ADAR-D2S conn |
|---------------------|---------------|---------------|
| J2 | RX1_RFIN | O7 |
| J3 | RX2_RFIN | O8 |
| J4 | RX3_RFIN | O6 |
| J6 | RX4_RFIN | O5 |

## Key BOM parts (Table 2 & Table 3)
- MMICs: **ADF5901WCCPZ-U6** (Tx), **ADF5904WCCPZ-U4** (Rx), **ADF4159CCPZ** (PLL).
- LDOs: **ADP7104ARDZ-3.3** ×2, **ADP150AUJZ-3.0**, **ADP150AUJZ-1.8**.
- TCXO: **CWX113-100.0M** (Connor-Winfield), 100 MHz.
- EEPROM: **24LC32A-I/MS**. Level shifters: **SN74AVC4T245PW** ×4, **SN74AVC2T245RSWR**, **SN74LVC1G08DCKR**.
- Diodes: **1N4001** (D1), **MBR0520LT1G** (D2). Ferrite: Würth **7427-92642** (E1).
- Loop filter: R19 1 kΩ, R18 510 Ω, R20 0 Ω, C12 220 pF, C13 3.3 nF, C14 100 pF.
- RSET (R17, R22) 5.1 kΩ. Decoupling classes: 0.1 µF, 1 nF, 10 pF, 100 pF, 47 nF, 0.22 µF, 1 µF, 22 µF.
- Baseband amps: **AD8130ARZ** (D2S board).

---

## Spec deltas
- **Two-LDO / "both 3.3 V" assumption is incomplete.** The reference design uses **four** regulators from the 5 V rail: two ADP7104-3.3 (one per MMIC — Tx and Rx), an ADP150-3.0 (ADF4159 analog), and an ADP150-1.8 (ADF4159 digital 1.8 V). The ADF4159 needs a distinct 1.8 V digital rail; a two-rail "both 3.3 V" plan omits it. Recommend Rev C keep at least: 3.3 V (MMICs, from low-noise ADP7104-class), 3.0–3.3 V (ADF4159 AVDD/VP), and 1.8 V (ADF4159 DVDD/SDVDD). (Fig.14, BOM)
- **Current budget:** ADF5901 170 mA + ADF5904 170 mA + ADF4159 (~26+7.5+5.5 ≈ 39 mA) ≈ **379 mA typ** of MMIC/PLL device current at 3.3/3.0/1.8 V. Plus TLV320ADC3140 (~21 mA), level shifters, TCXO, and any baseband amps. Total from 5 V (accounting for linear LDO current = output current, near 1:1 for LDOs) is on the order of ~430–480 mA typ, rising over temperature/max — the spec's **~600 mA from 5 V** is a reasonable upper-bound budget with headroom, not contradicted. (Currents cross-referenced from adf5901.md, adf5904.md, adf4159.md, tlv320adc3140.md.)
- **LO chain:** ADF5901 LOOUT (−7/−1/+5 dBm) directly drives ADF5904 LO_IN (−8 to +5 dBm). Reference board routes this as an on-board 24 GHz trace — Rev C must keep LOOUT→LO_IN interconnect loss under ~1 dB so the LO stays above the ADF5904 −8 dBm minimum at the ADF5901 low corner. (adf5901.md / adf5904.md Spec deltas)
- **ADF4159 analog rail is 3.0 V on the reference board**, not 3.3 V. Both are in-range (2.7–3.45 V); note the deviation from a uniform-3.3 V assumption.

## Ordering suffixes (verified)

Verified directly against each datasheet's Ordering Guide (last page). Base MPN = tray-packed part used in the KiCad symbol `MPN` property; reel suffix = distributor `MPN_Reel` property for tape-and-reel quantities. All three confirmed in stock at DigiKey as of 2026-07-01.

- **ADF5901**: Only one grade exists — `ADF5901WCCPZ` (tray) / `ADF5901WCCPZ-RL7` (reel), −40°C to +105°C, CP-32-12. No non-"W" (automotive-qualified) grade is offered for this part. Source: ADF5901.pdf Rev. A, p.26 Ordering Guide. DigiKey listing: https://www.digikey.com/en/products/detail/analog-devices-inc/ADF5901WCCPZ-RL7/6056996 (1,180 units in stock).
  - Note: the BOM extraction's `ADF5901WCCPZ-U6` suffix does not appear in the datasheet's Ordering Guide; `-U6` is not a valid ADI order-code suffix (only `-RL7` reel exists) and was not carried into the symbol.
- **ADF5904**: Two grades exist — `ADF5904WCCPZ` (automotive-qualified) and `ADF5904ACPZ` (commercial), each with a `-RL7` reel variant, −40°C to +105°C, CP-32-12. The EV-RADAR-MMIC2 eval board BOM (this doc, line "MMICs:") specifies the automotive-qualified `ADF5904WCCPZ-U4` variant, so the symbol now uses the **W-grade** `ADF5904WCCPZ` (previously incorrectly `ADF5904ACPZ`, the commercial grade) to match the reference design. Source: ADF5904.pdf Rev. A, p.15 Ordering Guide. DigiKey: https://www.digikey.com/en/products/detail/analog-devices-inc/ADF5904WCCPZ-RL7/6490591 ; Mouser (A-grade comparison): https://www.mouser.com/ProductDetail/Analog-Devices/ADF5904ACPZ-RL7.
  - Note: `-U4` is not a valid ADI order-code suffix either (only `-RL7` reel exists); treated as a BOM-extraction artifact, not carried into `MPN`/`MPN_Reel`.
- **ADF4159**: Two grades exist — `ADF4159CCPZ` (commercial) and `ADF4159WCCPZ` (automotive), each with `-RL7` reel, −40°C to +125°C, CP-24-10. Reference design and current symbol use the commercial grade `ADF4159CCPZ`, confirmed correct — no change to `MPN`. Source: ADF4159.pdf Rev. E, p.36 Ordering Guide. DigiKey: https://www.digikey.com/en/products/detail/analog-devices-inc/ADF4159CCPZ-RL7/4916421 (ships today) and https://www.digikey.com/en/products/detail/analog-devices-inc/ADF4159CCPZ/4171703 (tray).

## Completeness checklist
- [x] Pin table — N/A for a board-level doc; per-IC pin tables are in adf5901.md / adf5904.md / adf4159.md.
- [x] EP size — N/A (board doc); per-IC EP sizes in the IC files.
- [x] Land pattern — N/A (board doc); ADI CSP land rule captured in adf4159.md.
- [x] Application circuit values present — loop filter R/C, RSET 5.1 kΩ, TCXO 100 MHz, four LDO part numbers, decoupling triads, RF/LO ac-coupling, baseband AD8130 gains, input protection. (Fig.11–14, Fig.16, Fig.24–28, BOM Table 2/3)
- [x] Power-up sequence present — board quick-start + per-IC init referenced (ADF5904 Initialize → ADF5901 Initialize → ADF4159 Write R0/ramp). (p.4 Quick Start; software p.7–10)
- Board doc — no single package lead count; component reference designators cross-checked against BOM Table 2/Table 3. ✓
