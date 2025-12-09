# DigiKey Bill of Materials - CDM324 Preamp PCB

Complete parts list for the limpkin CDM324 amplification backpack, modified for golf speed detection.

## Quick Order Links

**DigiKey Cart Link:** Create your cart by searching each part number below, or use the CSV at the bottom for bulk upload.

---

## Active Components

| Qty | Reference | Description | DigiKey Part # | Unit Price | Ext Price |
|-----|-----------|-------------|----------------|------------|-----------|
| 1 | U1 | OPA2365AIDR - Dual Op-Amp, 50MHz, SOIC-8 | [296-31704-1-ND](https://www.digikey.com/en/products/detail/texas-instruments/OPA2365AIDR/1572255) | $2.54 | $2.54 |
| 1 | U2 | MAX9031AUK+T - Comparator, SOT-23-5 | [MAX9031AUK+TCT-ND](https://www.digikey.com/en/products/detail/analog-devices-inc-maxim-integrated/MAX9031AUK-T/774090) | $2.17 | $2.17 |
| 1 | Q1 | SI2301CDS-T1-GE3 - P-Ch MOSFET, SOT-23 | [SI2301CDS-T1-GE3CT-ND](https://www.digikey.com/en/products/detail/vishay-siliconix/SI2301CDS-T1-GE3/1978876) | $0.69 | $0.69 |
| 1 | D1 | S1B-13-F - Schottky Diode, SMA | [S1B-FDICT-ND](https://www.digikey.com/en/products/detail/diodes-incorporated/S1B-13-F/804869) | $0.46 | $0.46 |
| 1 | FB1 | BLM21PG221SN1D - Ferrite Bead, 0805 | [490-1037-1-ND](https://www.digikey.com/en/products/detail/murata-electronics/BLM21PG221SN1D/526227) | $0.10 | $0.10 |

---

## Resistors (0805, 1%, 1/8W)

| Qty | Reference | Value | DigiKey Part # | Unit Price | Ext Price |
|-----|-----------|-------|----------------|------------|-----------|
| 5 | R1,R2,R3,R10,R11 | 10kΩ | [311-10.0KCRCT-ND](https://www.digikey.com/en/products/detail/yageo/RC0805FR-0710KL/730482) | $0.10 | $0.50 |
| 3 | R4,R5,R6 | 4.7kΩ | [311-4.70KCRCT-ND](https://www.digikey.com/en/products/detail/yageo/RC0805FR-074K7L/728304) | $0.10 | $0.30 |
| 2 | R7,R8 | 590kΩ | [311-590KCRCT-ND](https://www.digikey.com/en/products/detail/yageo/RC0805FR-07590KL/727756) | $0.10 | $0.20 |
| 1 | R9 | 8.2kΩ | [311-8.20KCRCT-ND](https://www.digikey.com/en/products/detail/yageo/RC0805FR-078K2L/728440) | $0.10 | $0.10 |

---

## Capacitors

| Qty | Reference | Value | DigiKey Part # | Unit Price | Ext Price |
|-----|-----------|-------|----------------|------------|-----------|
| 9 | C1-C5,C8-C11 | 10µF, 0805, 16V | [1276-1096-1-ND](https://www.digikey.com/en/products/detail/samsung-electro-mechanics/CL21A106KAYNNNE/3889152) | $0.10 | $0.90 |
| 2 | C6,C7 | **27pF**, 0805, 50V ⚠️ | [311-1103-1-ND](https://www.digikey.com/en/products/detail/yageo/CC0805JRNPO9BN270/302864) | $0.10 | $0.20 |

> ⚠️ **IMPORTANT:** The original design uses 270pF for C6/C7, which limits max speed to ~14 mph. For golf (150+ mph), use **27pF** instead. This extends the high-frequency cutoff to ~10kHz.

---

## Connectors

| Qty | Reference | Description | DigiKey Part # | Unit Price | Ext Price |
|-----|-----------|-------------|----------------|------------|-----------|
| 1 | P1 | 1x5 Pin Header, 0.1" | [S1011EC-05-ND](https://www.digikey.com/en/products/detail/sullins-connector-solutions/PRPC005SAAN-RC/2775278) | $0.52 | $0.52 |
| 1 | P2 | 1x3 Pin Header, 0.1" | [S1011EC-03-ND](https://www.digikey.com/en/products/detail/sullins-connector-solutions/PRPC003SAAN-RC/2775276) | $0.42 | $0.42 |

---

## Order Summary

| Category | Cost |
|----------|------|
| Active Components | $5.96 |
| Resistors | $1.10 |
| Capacitors | $1.10 |
| Connectors | $0.94 |
| **Subtotal** | **$9.10** |
| Shipping (est.) | ~$5.00 |
| **Total** | **~$14.10** |

---

## DigiKey Bulk Upload CSV

Copy this into a `.csv` file and use DigiKey's "Upload a List" feature:

```csv
Quantity,Part Number
1,296-31704-1-ND
1,MAX9031AUK+TCT-ND
1,SI2301CDS-T1-GE3CT-ND
1,S1B-FDICT-ND
1,490-1037-1-ND
5,311-10.0KCRCT-ND
3,311-4.70KCRCT-ND
2,311-590KCRCT-ND
1,311-8.20KCRCT-ND
9,1276-1096-1-ND
2,311-1103-1-ND
1,S1011EC-05-ND
1,S1011EC-03-ND
```

---

## Also Needed (Not from DigiKey)

| Item | Source | Cost |
|------|--------|------|
| PCBs (5 boards) | [JLCPCB](https://jlcpcb.com) | ~$2 |
| PCB Shipping | JLCPCB | ~$5-8 |
| CDM324 Radar Module | Amazon/AliExpress (you have this) | $0 |

---

## Total Project Cost

| Item | Cost |
|------|------|
| DigiKey components | ~$14 |
| PCBs + shipping | ~$8 |
| **Total** | **~$22** |

---

## Assembly Notes

1. **Solder order:** Start with smallest components (resistors, caps), then ICs, then connectors
2. **U1 (OPA2365):** Note pin 1 orientation (dot on chip matches dot on PCB)
3. **U2 (MAX9031):** Very small SOT-23-5, use fine tip and flux
4. **Test before connecting radar:** Apply 5V, measure ~2.5V at op-amp outputs

---

## Alternative Cheaper Sources

If DigiKey shipping is too much for small orders, consider:

| Source | Pros | Cons |
|--------|------|------|
| **Mouser** | Similar to DigiKey | Similar pricing |
| **LCSC** | Cheap, ships with JLCPCB | Limited selection |
| **AliExpress** | Very cheap | Slow shipping, possible counterfeits |
| **Amazon** | Fast shipping | Limited SMD selection |

For just the OPA2365 and MAX9031, AliExpress can save ~$3-4 but takes 2-4 weeks.
