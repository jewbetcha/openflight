# PDF Schematic Analysis & Extraction

How to analyze schematics provided as PDF files — reference designs, dev board schematics, eval board docs, application notes — and extract useful information for incorporation into KiCad projects.

## Table of Contents

1. [Common Sources of PDF Schematics](#common-sources-of-pdf-schematics)
2. [Reading PDF Schematics](#reading-pdf-schematics)
3. [Extraction Workflow](#extraction-workflow)
4. [Component Extraction](#component-extraction)
5. [Net and Connectivity Extraction](#net-and-connectivity-extraction)
6. [Subcircuit Extraction](#subcircuit-extraction)
7. [Translating to KiCad](#translating-to-kicad)
8. [Validation Against Datasheets](#validation-against-datasheets)
9. [Common Pitfalls](#common-pitfalls)

---

## Common Sources of PDF Schematics

| Source | What You Get | Example |
|--------|-------------|---------|
| **Dev board schematics** | Complete board design — power, MCU, peripherals, connectors | ESP32-DevKitC, STM32 Nucleo, Arduino, Raspberry Pi Pico |
| **Eval board / reference designs** | Manufacturer's recommended circuit for a specific IC | TI EVM boards, Analog Devices eval boards |
| **Application notes** | Focused subcircuits solving specific problems | AN-XXX from TI, Maxim, NXP, etc. |
| **Chip datasheets** | Typical application circuit (usually 1-2 pages) | "Typical Application" section of any IC datasheet |
| **Open-source hardware** | Full designs shared as PDFs (when source files aren't available) | Adafruit, SparkFun, community projects |

These PDFs are invaluable because they represent tested, working circuits — often designed by the IC manufacturer's own application engineers.

---

## Reading PDF Schematics

Read specific pages of the PDF using page range selection. Schematics are visual — multimodal LLMs can interpret the circuit diagrams directly from the rendered PDF pages.

### Strategy for multi-page schematics

1. **Read the first page** — usually a title block or table of contents. Note the page count and sheet names.
2. **Read the table of contents or sheet index** — many reference designs list sheets by function (Power, MCU, Connectivity, IO, etc.)
3. **Read pages by functional area** — focus on the subcircuits relevant to your design goal.
4. **Read the BOM page** (if included) — some PDFs include a BOM table on the last pages.

### Tips for reading

- Request 2-4 pages at a time to keep context manageable
- For complex pages, focus on one area at a time (e.g., "the voltage regulator in the top-left quadrant")
- If text is small or blurry, note component values you can't read clearly and cross-reference with the BOM or datasheet
- Schematic PDFs from manufacturers are usually high-quality vector graphics — they render well

---

## Extraction Workflow

### Step 1: Understand the purpose

Before extracting, clarify what you're taking from the PDF and why:
- **Whole design**: recreating the entire board in KiCad (e.g., cloning a dev board)
- **Specific subcircuit**: borrowing a power supply, USB interface, or sensor circuit
- **Component selection**: seeing what parts the manufacturer chose and why
- **Value verification**: checking your own design against a known-good reference

### Step 2: Read and catalog

Read through the schematic pages. For each page/sheet, note:
- Sheet title and function
- Key ICs and their part numbers
- Power rails and voltages
- Connectors and interfaces
- Any notes or comments on the schematic (designers often annotate important decisions)

### Step 3: Extract what you need

Depending on your goal, extract:
- Full BOM (all components with designators, values, footprints, part numbers)
- Subcircuit topology (which components connect to which, net names)
- Component values and their rationale
- Design decisions (why certain values/parts were chosen)

### Step 4: Translate to KiCad

Recreate the extracted circuit in your KiCad schematic with proper symbols, values, and properties.

### Step 5: Validate

Cross-reference the extracted circuit against the IC datasheets to confirm correctness. PDF schematics can contain errors (even from manufacturers), and your application conditions may differ.

---

## Component Extraction

When reading a PDF schematic, extract a structured BOM.

### What to capture per component

| Field | Source in PDF | Notes |
|-------|--------------|-------|
| Reference | Printed next to symbol (R1, C5, U3) | May follow different convention than your project |
| Value | Printed on or near symbol | "100n", "10K", "4.7u" — note the notation style |
| Part number / MPN | In the BOM table, or printed on the symbol | Not always visible on the schematic itself |
| Package / Footprint | Sometimes in BOM, sometimes from context | "0402", "0603", "SOT-23-5" |
| Voltage rating | Sometimes annotated, often only in BOM | Critical for caps — "16V", "25V" |
| Tolerance | Rarely on schematic, usually in BOM | "1%", "5%", "10%" |
| Notes | Designer annotations near the component | "DNP", "Optional", "Select for 3.3V" |

### Notation conventions in PDF schematics

Different manufacturers use different shorthand:

| PDF Notation | Meaning |
|-------------|---------|
| `100n`, `0.1u`, `100nF` | 100 nanofarads |
| `4R7`, `4.7R` | 4.7 ohms (R marks decimal point) |
| `10K`, `10k` | 10 kilohms |
| `2M2` | 2.2 megohms |
| `4u7`, `4.7u` | 4.7 microfarads |
| `22p` | 22 picofarads |
| `NF`, `NP`, `NC` | Not fitted / Not populated / No connect |
| `DNP`, `DNS` | Do Not Populate / Do Not Stuff |

### Handling missing information

PDF schematics often omit details that KiCad needs:
- **No MPN shown**: search the value + package on DigiKey/Mouser to find a suitable part
- **No footprint shown**: infer from context (dev boards typically use 0402 or 0603 for passives) or check the BOM if included
- **No voltage rating on caps**: check the rail voltage and select appropriate rating (1.5-2x)
- **Generic part numbers**: "100nF" without MPN — select a specific part during your own BOM enrichment

---

## Net and Connectivity Extraction

### Reading connections from PDF schematics

PDF schematics show connectivity through:
- **Wires** — lines connecting component pins
- **Net labels** — text labels on wires (same label = same net, even across pages)
- **Power symbols** — VCC, GND, +3V3, +5V, VBAT, etc.
- **Port/off-page connectors** — arrows or symbols indicating connections to other sheets
- **Bus notation** — thick lines with slash labels (D[0:7], A[0:15])

### Multi-page connectivity

For multi-page schematics, track inter-sheet connections:
1. Note all port/off-page connector labels on each page
2. Match labels across pages — same label = same net
3. Power rails (VCC, GND, etc.) are typically global across all pages
4. Some designs use hierarchical labels — note the hierarchy

### Creating a net map

For complex extractions, build a net map:

```
Net Name: USB_DP
  Page 2: U1 pin 33 (MCU USB_DP)
  Page 2: R5 pin 1 (22R series resistor)
  Page 3: J1 pin A6/B6 (USB-C connector D+)
  Page 3: U4 pin 3 (ESD protection)

Net Name: +3V3
  Page 1: U2 VOUT (3.3V LDO output)
  Page 1: C3, C4 (output decoupling)
  Page 2: U1 VDD pins (MCU power)
  Page 3: R8, R9 (I2C pull-ups)
```

This map becomes the basis for recreating the schematic in KiCad.

---

## Subcircuit Extraction

The most common use case — extracting a specific subcircuit from a reference design to use in your own project.

### What makes a good subcircuit to extract

- **Power supply circuits** — LDO, buck, boost, battery charger. These are the most commonly borrowed subcircuits because getting them wrong is consequential and the reference design is known to work.
- **Interface circuits** — USB, Ethernet, CAN, RS-485. Protocol-specific circuits with precise component requirements.
- **Sensor front-ends** — amplifier, filter, and ADC input stages from eval boards.
- **Wireless module circuits** — antenna matching, crystal, bypass caps for WiFi/BT/LoRa modules.
- **Protection circuits** — ESD, reverse polarity, overcurrent. Safety-critical, better to copy a proven design.

### Extraction checklist

For each subcircuit you extract:

- [ ] All components identified with values
- [ ] All connections traced (including power and ground)
- [ ] Net names recorded (use the PDF's names or create your own)
- [ ] Any notes or annotations from the original designer captured
- [ ] IC datasheet cross-referenced to verify the subcircuit
- [ ] Any components shared with other subcircuits identified (e.g., bulk cap shared between regulators)
- [ ] Board-specific components identified and excluded (e.g., test points, debug headers you don't need)
- [ ] Voltage rails and current requirements documented

### Adapting extracted subcircuits

Rarely can you copy a subcircuit verbatim. Common adaptations:

| Adaptation | When Needed | How |
|-----------|-------------|-----|
| **Different input voltage** | Your power source differs from the reference | Recalculate input caps, voltage ratings, feedback dividers |
| **Different output current** | Your load is lighter or heavier | Check regulator rating, adjust inductor/cap sizing |
| **Different package** | You want a different footprint (e.g., larger for hand soldering) | Find same MPN in different package, or equivalent part |
| **Removing unused features** | Reference has features you don't need | Identify which components are optional (check datasheet) |
| **Adding features** | Reference is minimal, you want power-good or soft-start | Add components per datasheet |
| **Different component availability** | Original parts hard to source | Find equivalents using DigiKey/Mouser/LCSC (match key specs) |

---

## Translating to KiCad

### Mapping PDF components to KiCad symbols

| PDF Symbol | KiCad Library | Notes |
|-----------|--------------|-------|
| Resistor (rectangle or zigzag) | `Device:R` | Add MPN, value, footprint |
| Capacitor (two lines) | `Device:C` or `Device:C_Polarized` | Polarized for electrolytic/tantalum |
| Inductor (coil) | `Device:L` | Check if shielded version needed |
| Diode (triangle) | `Device:D` or `Device:D_Schottky` or `Device:D_Zener` | Match type to function |
| LED | `Device:LED` | Note color for correct VF |
| N-FET | `Device:Q_NMOS_GDS` | Check pin order matches |
| P-FET | `Device:Q_PMOS_GDS` | Check pin order matches |
| NPN/PNP | `Device:Q_NPN_BCE` / `Device:Q_PNP_BCE` | Check pin order |
| Generic IC | Search KiCad library by MPN | If not in library, create custom symbol |
| Connector | `Connector_Generic:Conn_01xNN` or specific | Match pin count and type |
| Crystal | `Device:Crystal` | Two-pin or four-pin (with ground) |
| TVS diode | `Device:D_TVS` or `Device:D_TVS_bidir` | Uni vs bidirectional |
| Ferrite bead | `Device:FerriteBead` | Value in ohms at 100MHz |

### Symbol not in KiCad library?

If the IC from the PDF isn't in KiCad's default libraries:
1. **Check manufacturer libraries** — many vendors provide KiCad symbols (TI, STMicro, Espressif, etc.)
2. **Search online** — SnapEDA, Ultra Librarian, Component Search Engine offer free KiCad symbols
3. **Create a custom symbol** — use the pin descriptions from the IC datasheet to create a new symbol in KiCad's Symbol Editor

### Recreating the schematic

1. **Place ICs first** — the main active components anchor the layout
2. **Add passive components** — resistors, caps, inductors connected to each IC
3. **Add power symbols** — VCC, GND, named power nets
4. **Wire everything** — follow the PDF's connectivity
5. **Add net labels** — for connections between subcircuits or across pages
6. **Annotate** — set reference designators (can reuse PDF's or use KiCad's auto-annotate)
7. **Fill in symbol properties** — Value, Footprint, MPN, Datasheet URL
8. **Run ERC** — KiCad's Electrical Rules Check catches basic wiring errors

### Organizing multi-sheet schematics

If the PDF has multiple pages, consider mirroring that structure in KiCad with hierarchical sheets:
- One sheet per functional block (Power, MCU, Connectivity, IO)
- Use hierarchical labels for inter-sheet connections
- Keep power rails as global power symbols (they connect across all sheets automatically)

---

## Validation Against Datasheets

Never blindly trust a PDF schematic. Always cross-reference against datasheets.

### Why PDF schematics can be wrong

- **Errata not applied** — the PDF may predate a silicon revision or app note correction
- **Transcription errors** — someone redrew the schematic and made mistakes
- **Version mismatch** — the PDF shows rev A but the datasheet has been updated for rev C
- **Board-specific workarounds** — the reference design may include bodge fixes that aren't appropriate for your design
- **Different operating conditions** — the reference design may target conditions different from yours (temperature, voltage range, load)

### Validation steps

1. **Get the current datasheet** for every IC — don't rely on the PDF's embedded info
2. **Compare pin connections** — verify every pin in the PDF matches the datasheet's pin table
3. **Check the "Typical Application" circuit** in the datasheet — compare against the PDF
4. **Verify component values** against datasheet recommendations (use `schematic-analysis.md` methodology)
5. **Check for errata** — look for errata documents or app notes that supersede the reference design
6. **Verify footprints** — the PDF's component packages may not match what's currently available

### Red flags in PDF schematics

- Component values that seem unusual (e.g., a 47nF where you'd expect 100nF)
- Pins connected that the datasheet says should be left floating (or vice versa)
- Missing decoupling caps on IC power pins
- Net labels that don't match the IC datasheet pin names
- Annotations like "TBD", "check", "verify" — the design may not be finalized
- Very old revision dates — circuit may predate important errata

---

## Common Pitfalls

### Pin numbering differences

Different schematic tools number pins differently. A PDF from Altium, OrCAD, or Eagle may show pin numbers or names that don't match KiCad's symbol. Always cross-reference against the IC datasheet — the datasheet is the authority on pin numbering.

### Passive component notation

PDF schematics may use inconsistent notation. On the same page you might see "100n", "0.1uF", and "100nF" — these are all the same value. Normalize when entering into KiCad (pick one convention: "100nF" is clearest).

### Ground symbol variants

PDFs may use multiple ground symbols (chassis ground, digital ground, analog ground, signal ground). Understand which are connected and which are separate in the original design. In KiCad, each distinct ground net needs its own power symbol.

### Copied circuits need adaptation

The reference design's operating conditions may differ from yours:
- Different input voltage → recalculate feedback dividers, check voltage ratings
- Different load current → verify regulator capacity, adjust inductor sizing
- Different temperature range → check component ratings
- Different PCB stackup → impedance-controlled traces may need different widths

### Don't copy what you don't understand

If you can't explain why a component is there and what value it should be, research it before including it. Copying cargo-cult components from reference designs is a common source of problems — you'll have mysterious parts on your board that you can't debug because you don't know their purpose.
