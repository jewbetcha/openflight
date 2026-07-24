# Support-Part Datasheet Extraction — TCXO_CWX113, ADP7104, ADP150

Ground-truth pin tables for the three support-part symbols in
`library/openflight-revc.kicad_sym`, cited to primary datasheets. Package/variant
choice follows the EV-RADAR-MMIC2 (UG-866) reference design BOM
(`datasheets/extracted/ev-radar-mmic2.md`).

---

## 1. TCXO_CWX113 — Connor-Winfield CWX113-100.0M

**Source:** `datasheets/CWX113_SM118.pdf` — Connor-Winfield Bulletin **Sm118**, Rev. 13,
31 July 2018, "Surface Mount LVCMOS Clock Oscillator Series" (the **Xxxx-Series**
family; X113 = ±25 ppm, 3.3 Vdc, 0–70°C temperature-range variant of this family, per
the family's own Model Matrix on p.3). Downloaded from `conwin.com/datasheets/sm/sm118.pdf`
(direct from Connor-Winfield; reachable without a mirror).

**Important naming note:** UG-866 (EV-RADAR-MMIC2 reference design, p.5 "INPUT
SIGNALS") calls Y1 a "100 MHz temperature compensated crystal oscillator (TCXO)" and
the BOM lists it as **CWX113-100.0M**, but Connor-Winfield's own literature classifies
the X1xx/X2xx/X3xx/X4xx family (bulletin Sm118) as an **LVCMOS clock oscillator (XO)**
series, not their dedicated TCXO/VCTCXO product line (which uses different bulletin
series like TX/D-series, e.g. tx350.pdf). No public Connor-Winfield datasheet exists
under the literal string "CWX113" — Sm118 documents the "Xxxx-Series" family
generically, and the ordering-code breakdown on p.3 confirms **X113 = LVCMOS Clock
Series, 0–70°C, ±25 ppm, 3.3 Vdc** is a member of this exact family (the "CW" prefix is
Connor-Winfield's part-family marking convention, confirmed by the identical pinout
and package on the closely related CWX813/CWX823 bulletins Sm126/Sm112, which are
electrically and mechanically identical 5x7mm 4-pad packages). Sm118 is the correct,
matching source for CWX113's package, pinout, and electrical behavior; there is no
more specific "CWX113"-titled PDF to supersede it. (p.1, p.3 Ordering Information/Model
Matrix)

**Package:** 5.0 x 7.0 mm surface-mount ceramic, 4-pad, "Xxxx-Series" (Sm118 Fig. Package
Outline, p.2). No exposed pad / thermal pad on this package.
- D (length) 4.85–5.15 mm (nom 5.0), E (width) 6.86–7.16 mm (nom 7.00) — pads on the
  5.0 mm-wide edges, consistent with "5.0x7.0mm" naming. (p.2 Package Outline table)
- Suggested pad layout: 4 pads, pitch (e) 5.08 mm, pad width (b) 1.40 mm, pad length
  (L) 1.20 mm. (p.2 Suggested Pad Layout)

**Pin table (Sm118 p.2, "Pad Connections"):**
| Pin | Name | Function |
|-----|------|----------|
| 1 | OE (Enable/Disable) | High or open = enabled; low = disabled (output high-Z) |
| 2 | GND (Cover) | Ground |
| 3 | Output | LVCMOS output |
| 4 | Vcc | Supply voltage |

**Electrical:** LVCMOS output, 3.3 Vdc supply (X1x**3** = 3.3 V code, p.3 Ordering
Information), ±25 ppm frequency tolerance (X**1**1x code), 0–70°C (X**1**xx code).
Output frequency range spec'd 20–225 MHz for the general family table (p.1
Operating Specifications) — the 100 MHz CWX113-100.0M is a custom/ordered frequency
within that family, consistent with UG-866's ordering of a 100 MHz version. Enable
time 2 ms max, disable time 200 ns max (p.2 OE Input Characteristics). Duty cycle
45–55% (p.2 CMOS Output Characteristics).

**Application circuit / bypass (Sm118 p.4, Test Circuit):** 0.01 µF ceramic bypass
capacitor from Vcc to GND, placed close to the package (labeled "C-by" on the closely
related Sm112/Sm126 pad-layout diagrams which share this package/pinout family).

**Symbol verdict:** verified-clean, no correction needed. Symbol pinout (1=EN, 2=GND,
3=OUT, 4=VDD) and pin electrical types (input/power_in/output/power_in) exactly match
Sm118's Pad Connections table above. Footprint field `TCXO_CWX113_SMD4` (4-pad SMD, no
EP) is consistent with the package having no exposed pad.

---

## 2. ADP7104 — Analog Devices ADP7104ARDZ-3.3

**Source:** `datasheets/ADP7104.pdf` — Analog Devices Data Sheet, **Rev. I**, 25 pages,
"20 V, 500 mA, Low Noise, CMOS LDO." Downloaded via Octopart's datasheet mirror
(`datasheet.octopart.com/ADP7104ARDZ-R7-Analog-Devices-datasheet-140480630.pdf`) after
`analog.com` and the Farnell PDF-ID guesses both failed/served wrong content in this
environment (analog.com resets the HTTP/2 stream before responding; a naive Farnell
doc-ID guess actually returned the ADP7112 datasheet, and another Farnell ID guess for
"ADP150" briefly returned an unrelated connector-shell 3D-model PDF — both discarded).

**Package variant used by the reference design:** EV-RADAR-MMIC2 BOM specifies
**ADP7104ARDZ-3.3** (U6, U7). Per the datasheet's Ordering Guide (p.25), the
**ARDZ** suffix (not ACPZ) maps to package option **RD-8-2 = 8-Lead SOIC_N_EP,
Narrow Body** (JEDEC MS-012-AA), i.e. a narrow SOIC-8 with an exposed pad on the
underside — **not** the 8-lead LFCSP_WD (CP-8-5, "ACPZ" suffix, 3mm×3mm QFN-style).
These are two distinct, non-interchangeable packages with different pinouts.
(Ordering Guide p.25)

**Package/EP dimensions (RD-8-2, Fig. 81, p.24):**
- Body: JEDEC MS-012-AA narrow-body SOIC-8, standard 1.27 mm lead pitch.
- Exposed pad (bottom view): 3.098 mm x 2.41 mm (per Fig.81's EP callouts), centered
  on the package underside, exposed on the bottom (not a top-side/side-wettable pad).
- EPAD is internally bonded to GND (see pin table below) — datasheet explicitly
  recommends connecting the EPAD to the board's ground plane. (p.6 Table 5, Pin No.
  "EPAD" row)

**Pin table — 8-Lead SOIC_N_EP, RD-8-2 (Fig. 4 + Table 5, p.6):**
| Pin | Name | Function |
|-----|------|----------|
| 1 | VOUT | Regulated output. Bypass to GND with >=1 µF. |
| 2 | SENSE/ADJ | SENSE (fixed-voltage parts): output-voltage feedback sense, connect close to load. ADJ (adjustable parts only): resistor-divider input. |
| 3 | GND | Ground |
| 4 | NC | Do not connect |
| 5 | EN/UVLO | Enable (drive high to turn on; tie to VIN for auto-start) / programmable UVLO threshold input |
| 6 | GND | Ground |
| 7 | PG | Power Good, open-drain, needs external pull-up to VIN or VOUT |
| 8 | VIN | Regulator input. Bypass to GND with >=1 µF. |
| EPAD | GND | Exposed pad, internally bonded to GND; recommend connecting to board ground plane |

**This is a materially different pinout from the LFCSP (CP-8-5) pin map** — the two
packages do NOT share a pin-for-pin layout (confirmed by comparing Fig.3 LFCSP and
Fig.4 SOIC_N_EP pin diagrams on p.6 of the datasheet, which are drawn side-by-side and
are identical to each other pin-for-pin in this particular case — both show
VOUT(1)/SENSE-ADJ(2)/GND(3)/NC(4)/EN-UVLO(5)/GND(6)/PG(7)/VIN(8) with EPAD=GND on both
packages). So while the *package* (LFCSP vs SOIC-EP) differs, the *pin numbering and
function* are identical between the two ADP7104 package options — only the physical
footprint/land pattern changes.

**Application circuit (p.1 Fig.1, "Fixed Output Voltage" typical circuit):**
- CIN = 1 µF (VIN to GND), COUT = 1 µF (VOUT to GND) — ceramic.
- PG pull-up resistor RPG = 100 kΩ to VIN (or VOUT).
- EN/UVLO resistor divider (if using programmable UVLO): R1 = 100 kΩ, R2 = 100 kΩ
  (values shown in the typical application circuit; exact UVLO threshold values are
  design-specific — Rev C should size these for its own VIN sequencing needs, this is
  just the datasheet's example).
- Matches ev-radar-mmic2.md's independently-noted "per-output 1 µF caps" for U6/U7.

**Symbol verdict: CORRECTED — pin numbers/names were wrong, AND the footprint field
named the wrong package variant.** See "Corrections made" below.

---

## 3. ADP150 — Analog Devices ADP150AUJZ-3.0 / ADP150AUJZ-1.8

**Source:** `datasheets/ADP150.pdf` — Analog Devices Data Sheet, **Rev. C**, 20 pages,
"Ultralow Noise, 150 mA CMOS Linear Regulator." Downloaded from Mouser's static
datasheet mirror (`mouser.com/datasheet/2/609/ADP150-773560.pdf`) after `analog.com`
direct fetch timed out in this environment.

**Package variant used by the reference design:** EV-RADAR-MMIC2 BOM specifies
**ADP150AUJZ-3.0** (U4, VDD_PLL) and **ADP150AUJZ-1.8** (U5, DVDD_PLL). Per the
datasheet's Ordering Guide (p.19–20), the **AUJZ** suffix maps to package option
**UJ-5 = 5-Lead Thin Small Outline Transistor (TSOT)** — this matches the symbol's
existing `ADP150_TSOT5` footprint name; no package correction needed.

**Package dimensions (UJ-5, Fig. 49, p.18):** JEDEC MO-193-AB (with datasheet-noted
exceptions on package height/thickness). Body 2.90 mm x 2.80 mm BSC, pitch 0.95 mm
BSC, no exposed pad.

**Pin table — 5-Lead TSOT, UJ-5 (Fig. 3 + Table 5, p.6):**
| Pin | Name | Function |
|-----|------|----------|
| 1 | VIN | Regulator input. Bypass to GND with >=1 µF. |
| 2 | GND | Ground |
| 3 | EN | Enable. Drive high to turn on; tie to VIN for auto-start. |
| 4 | NC | Not connected internally |
| 5 | VOUT | Regulated output. Bypass to GND with >=1 µF. |

**Application circuit (p.1 Fig. "Typical Application Circuit," VIN=2.3V/VOUT=1.8V
example):** CIN = 1 µF, COUT = 1 µF, ceramic, both to GND. No additional noise-bypass
capacitor required (ADP150's key differentiating feature vs. competing ultralow-noise
LDOs). (p.1 Features, "No additional noise bypass capacitor required")

**Symbol verdict: CORRECTED — pin numbers 1 and 2 were swapped relative to the
datasheet.** See "Corrections made" below. Package/footprint was already correct
(TSOT-5, UJ-5) — no footprint change needed.

---

## Corrections made (summary — see kicad_sym diff for exact edits)

### ADP7104 (`library/openflight-revc.kicad_sym`, symbol "ADP7104")
Previous symbol pinout did not match either ADP7104 package option in the datasheet at
all (pin count, names, and numbers were fabricated/from-memory, not from an ADI pin
table). Corrected in place to the RD-8-2 (SOIC_N_EP) pin table above:
- Pin 1: was `EN` (input) -> now `VOUT` (power_out)
- Pin 2: was `NC` -> now `SENSE/ADJ` (passive, feedback sense)
- Pin 3: was `NC` -> now `GND` (power_in)
- Pin 4: was `OUT` (power_out) -> now `NC` (no_connect)
- Pin 5: was `OUT` (power_out) -> now `EN/UVLO` (input)
- Pin 6: was `SENSE` (passive) -> now `GND` (power_in)
- Pin 7: was `IN` (power_in) -> now `PG` (open-drain output)
- Pin 8: was `IN` (power_in) -> now `VIN` (power_in)
- Pin 9 (EP): kept as `EP`, power_in, tied to GND — this matches the datasheet's EPAD=GND function, only the pin *number* context changes (was miscounted against a wrong 8-pin map; still correct as "the 9th/EP pin, function=GND").
- **Footprint field was WRONG PACKAGE VARIANT and has been corrected**: was
  `openflight-revc:ADP7104_LFCSP8` (LFCSP/QFN-style land pattern), corrected to
  `openflight-revc:ADP7104_SOIC8_EP` (narrow-body SOIC-8 with exposed pad, RD-8-2) to
  match the ARDZ-3.3 part number actually specified by the EV-RADAR-MMIC2 reference
  BOM. **THIS IS A FOOTPRINT NAME CHANGE, FLAGGED FOR THE FOOTPRINT-OWNING AGENT** —
  the previous LFCSP footprint name implied the wrong package family entirely (ACPZ,
  not ARDZ); a new `ADP7104_SOIC8_EP` footprint (8-pin narrow SOIC + exposed pad,
  JEDEC MS-012-AA body outward dims, ~3.098mm x 2.41mm thermal pad per Fig.81) needs to
  be authored/renamed to match, since `library/openflight-revc.pretty/` is out of scope
  for this task.

### ADP150 (`library/openflight-revc.kicad_sym`, symbol "ADP150")
Pin numbers 1 and 2 were swapped versus the datasheet's Table 5:
- Pin was `GND` numbered `1` -> corrected to `GND` numbered `2`
- Pin was `IN` numbered `2` -> corrected to `VIN`("IN") numbered `1`
- Pins 3 (EN), 4 (NC), 5 (OUT/VOUT) were already correct.
- Footprint field `openflight-revc:ADP150_TSOT5` is correct (UJ-5 = TSOT-5) — no
  change.

### TCXO_CWX113 (`library/openflight-revc.kicad_sym`, symbol "TCXO_CWX113")
No corrections. Pin map (1=EN, 2=GND, 3=OUT, 4=VDD) and footprint
(`TCXO_CWX113_SMD4`) both verified-clean against Connor-Winfield Sm118.

---

## 4. SN74AVC4T245 — TI 4-bit dual-supply level shifter / bus transceiver

**Source:** `datasheets/SN74AVC4T245.pdf` — Texas Instruments **SCES576I**, JUNE 2004 –
REVISED FEBRUARY 2025, "SN74AVC4T245 Dual-Bit Bus Transceiver with Configurable
Voltage Translation and 3-State Outputs" (title is historical; the part is the 4-bit
AVC4T245). Downloaded directly from `ti.com/lit/ds/symlink/sn74avc4t245.pdf`.

**Role in Rev C:** U7 — 3.3 V→1.8 V level shifter between the Pi/IO 3.3 V control lines
(SPI_SCLK, SPI_SDATA, LE_4159, CE_RX) and the ADF4159's 1.8 V-domain digital inputs
(CLK, DATA, LE, CE; abs max +2.4 V per adf4159.md Table 4). Ports the reference
design's U8–U11 = SN74AVC4T245PW usage (ev-radar-mmic2.md "Level-shift / digital glue").

**Package used:** **PW = TSSOP-16, 4.4 mm × 5 mm body, 0.65 mm pitch** (Package
Information table, p.1: "PW (TSSOP, 16) — 5mm × 6.4mm" nominal incl. leads). Footprint:
stock KiCad `Package_SO:TSSOP-16_4.4x5mm_P0.65mm` (land pattern matches the TI PW
0.65 mm-pitch 16-lead TSSOP; authored footprint not required).

**Pin table — PW (TSSOP-16) package (Table 4-1 "Pin Functions", p.5):**
| Pin (PW) | Name | Type | Description |
|----------|------|------|-------------|
| 1 | VCCA | — | A-port power supply, 1.2–3.6 V (references control pins). |
| 2 | 1DIR | I | Direction control, '1' ports. |
| 3 | 2DIR | I | Direction control, '2' ports. |
| 4 | 1A1 | I/O | A-port bit, referenced to VCCA. |
| 5 | 1A2 | I/O | A-port bit, referenced to VCCA. |
| 6 | 2A1 | I/O | A-port bit, referenced to VCCA. |
| 7 | 2A2 | I/O | A-port bit, referenced to VCCA. |
| 8 | GND | — | Ground. |
| 9 | GND | — | Ground. |
| 10 | 2B2 | I/O | B-port bit, referenced to VCCB. |
| 11 | 2B1 | I/O | B-port bit, referenced to VCCB. |
| 12 | 1B2 | I/O | B-port bit, referenced to VCCB. |
| 13 | 1B1 | I/O | B-port bit, referenced to VCCB. |
| 14 | 2OE | I | Output enable, '2' ports (active low), referenced to VCCA. |
| 15 | 1OE | I | Output enable, '1' ports (active low), referenced to VCCA. |
| 16 | VCCB | — | B-port power supply, 1.2–3.6 V. |

**Function table (Table 7-1, p.16; each 2-bit section):** OE=L,DIR=L → B data to A bus;
OE=L,DIR=H → A data to B bus; OE=H,DIR=X → isolation (Hi-Z). Control pins (DIR, OE) are
referenced to VCCA. Abs max any supply/I/O 4.6 V; I/Os 4.6 V-tolerant. (p.6, p.16)

**Decoupling (Sec 8.2 Fig 8-1 / Sec 8.4 layout, p.17–19):** bypass capacitor per supply
rail; TI's typical-application diagram shows 0.1 µF on VCCA and 0.1 µF (+1 µF bulk) on
VCCB. Rev C uses 100 nF per supply port (C47 on VCCA, C48 on VCCB). OE power-up note:
TI recommends OE pulled to VCCA through a resistor to hold Hi-Z until rails ramp; Rev C
ties OE to GND (always-enabled), acceptable for a non-sequence-critical Pi SPI bus.

**Rev C strapping (U7):** VCCA=+3V3_RX, VCCB=+1V8_DIG, 1DIR=2DIR=+3V3_RX (A→B,
3.3 V→1.8 V), 1OE=2OE=GND (enabled). A-port = 3.3 V control side, B-port → ADF4159.

---

## 5. SN74AVC2T245 — TI 2-bit dual-supply level shifter / bus transceiver

**Source:** `datasheets/SN74AVC2T245.pdf` — Texas Instruments **SCES692E**, JUNE 2008 –
REVISED SEPTEMBER 2024, "SN74AVC2T245 Dual-Bit Dual-Supply Bus Transceiver with
Configurable Level-Shifting / Voltage Translation and Tri-State Outputs." Downloaded
directly from `ti.com/lit/ds/symlink/sn74avc2t245.pdf`.

**Role in Rev C:** U8 — 1.8 V→3.3 V level shifter carrying ADF4159 MUXOUT (1.8 V
digital output) up to the 3.3 V RAMP_SYNC line for the Pi GPIO. Ports the reference
design's U12 = SN74AVC2T245RSWR usage.

**Package used:** **RSW = UQFN-10, 1.8 mm × 1.4 mm body, 0.4 mm pitch** (Device
Information, p.1: "PACKAGE UQFN (10), BODY SIZE (NOM) 1.80mm × 1.40mm"; Fig 4-1 "RSW
PACKAGE 10-PIN UQFN TOP VIEW", p.3). **Correction to the task brief:** the brief called
RSW "UQFN-12"; the datasheet definitively documents RSW as a **10-pin** UQFN. Footprint:
stock KiCad `Package_DFN_QFN:Texas_RSW0010A_UQFN-10_1.4x1.8mm_P0.4mm` (this is TI's own
RSW0010A land pattern; authored footprint not required).

**Pin table — RSW (UQFN-10) package (Table 4-1 "Pin Functions", p.3):**
| Pin (UQFN) | Name | Type | Description |
|------------|------|------|-------------|
| 1 | DIR2 | I | Direction pin ch2, connect to GND or VCCA. |
| 2 | OE | I | Output enable (active low), referenced to VCCA. |
| 3 | GND | — | Ground. |
| 4 | B2 | I/O | B-port bit 2, referenced to VCCB. |
| 5 | B1 | I/O | B-port bit 1, referenced to VCCB. |
| 6 | VCCB | — | B-port supply, 1.2–3.6 V. |
| 7 | VCCA | — | A-port supply, 1.2–3.6 V (references control pins). |
| 8 | A1 | I/O | A-port bit 1, referenced to VCCA. |
| 9 | A2 | I/O | A-port bit 2, referenced to VCCA. |
| 10 | DIR1 | I | Direction pin ch1, connect to GND or VCCA. |

**Function / direction:** Same convention as AVC4T245 — DIR=H → A→B, DIR=L → B→A;
OE=H → all outputs Hi-Z. Each channel has independent DIR. Control pins referenced to
VCCA. Abs max 4.6 V; I/Os 4.6 V-tolerant. (p.4, p.12)

**Unused-channel handling (Sec 5.3 note 3, p.5):** "All unused data inputs of the
device must be held at VCCI or GND." Rev C uses only channel 1 (MUXOUT→RAMP_SYNC); the
unused ch2 has **B2 (input side for B→A) tied to GND** and **A2 (output) left open**.

**Rev C strapping (U8):** VCCA=+3V3_RX, VCCB=+1V8_DIG, DIR1=DIR2=GND (B→A, 1.8→3.3 V),
OE=GND (enabled). B1←ADF4159 MUXOUT, A1→RAMP_SYNC. Decoupling 100 nF per supply port
(C50 on VCCA, C49 on VCCB) per Sec 9 Power Supply Recommendations.
