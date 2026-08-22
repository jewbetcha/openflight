# OpenFlight Parts List

Hardware components for building the OpenFlight golf launch monitor.

> **Ordering shortcut:** A shared **[OpenFlight Mouser project](https://www.mouser.com/en/Tools/Project/Share?AccessID=4c97a00bbc)** is available for the parts Mouser stocks — open it, save it to your own Mouser account, and add the whole list to your cart in one step instead of searching for each item. Check it against the tables below before you order: anything Mouser does not carry has a direct vendor link here.

> **Next step after gathering parts:** See the [Raspberry Pi Setup Guide](raspberry-pi-setup.md) for assembly and software installation.

> **Prices:** USD figures are the vendor's own list price. CAD figures are either a
> Canadian distributor's list price (where one stocks the part) or the USD price
> converted at the Bank of Canada daily rate of **1.3760 USD/CAD (2026-08-21)**.
> Converted figures are marked `~` and **exclude shipping, duty, customs brokerage,
> GST/HST/PST**. See [Buying in Canada](#buying-in-canada) before ordering.

## Core Components

| Part | Description | Link | ~USD | ~CAD |
|------|-------------|------|------|------|
| **OPS243 Radar** | Doppler radar for ball/club speed detection | [OmniPreSense](https://omnipresense.com/product/ops243-doppler-radar-sensor/) | $224 | ~$308 |
| **Raspberry Pi 5** | Main compute unit (4GB+ recommended) | [Adafruit](https://www.adafruit.com/product/5812) · CA [PiShop.ca](https://www.pishop.ca/product/raspberry-pi-5-4gb/) | $130 | $154 |
| **7" Touchscreen Display** | HMTECH 7" 1024x600 IPS display | [Amazon](https://www.amazon.com/dp/B0D3QB7X4Z) · CA [equivalent](https://www.amazon.ca/dp/B0CRRB1GFN) | $46 | $56 |

> **NOTE on OPS243-A-W (WiFi version):** The standard **OPS243-A** (USB only) is strongly recommended. The WiFi module on the OPS243-A-W drives the internal UART receive line, preventing direct connection to the Raspberry Pi GPIO UART (Layout A). However, if you already have the WiFi version, it can still be used over USB with a powered USB hub (Layout B) when paired with the IWR6843 angle radar.

> **Display alternative:** The [Raspberry Pi Touch Display 2](https://www.raspberrypi.com/products/touch-display-2/) (7" 720x1280, MIPI DSI) also works with the Pi 5. If you use it, print the `Touch_Display2_backplate.stl` and `Touch_Display2_shell.stl` from the IARC case instead of `monitor_shell.stl` — see the [IARC case instructions](../cad/IARC_case/README.md).

## Sound Trigger (for Rolling Buffer Mode)

The sound trigger detects club impact to precisely time radar captures. Essential for spin detection via rolling buffer mode.

| Part | Description | Link | ~USD | ~CAD |
|------|-------------|------|------|------|
| **SparkFun SEN-14262** | Sound Detector with envelope/gate outputs | [SparkFun](https://www.sparkfun.com/products/14262) · CA [DigiKey.ca](https://www.digikey.ca/en/products/detail/sparkfun-electronics/14262/7725299) | $12 | $21 |
| **Through-hole resistor** | For R17 pad on SEN-14262 to reduce sensitivity (see note) | Any electronics supplier | $1 | $1 |
| **Jumper Wires** | 3 wires: GATE → HOST_INT, VCC → 3.3V, GND → GND | Any | $5 | $7 |

> **R17 resistor:** The SEN-14262 is rated for 5V but runs at 3.3V in this setup, which can cause the GATE output to stick high. Soldering a resistor into the R17 through-hole position (in parallel with the onboard 100kΩ R3) reduces preamp gain and fixes this. Start with 47kΩ; use a lower value (e.g. 33kΩ) if the sensor is still too sensitive for your environment.

### Sound Trigger Wiring

```
SEN-14262               Raspberry Pi           OPS243
┌───────────┐          ┌──────────┐          ┌──────────┐
│ VCC ──────┼──────────┤ 3.3V     │          │          │
│           │          │          │          │          │
│ GATE ─────┼──────────┼──────────┼──────────┤ HOST_INT │
│           │          │          │          │ (J3 P3)  │
│ GND ──────┼──────────┤ GND      ├──────────┤ GND      │
│           │          │          │          │ (J3 P1)  │
└───────────┘          └──────────┘          └──────────┘
```

See [sound-trigger-wiring.md](sound-trigger-wiring.md) for detailed instructions and troubleshooting.

## Angle Radar (TI IWR6843) — CURRENT

This is the supported angle radar. It measures vertical and horizontal launch
angle, and supplies the pre-impact frames club path is derived from.

| Part | Description | Link | ~USD | ~CAD |
|------|-------------|------|------|------|
| **TI IWR6843LEVM** | 60 GHz mmWave evaluation board, 4 RX × 3 TX | [TI](https://www.ti.com/tool/IWR6843LEVM) | $156 | ~$215 |
| **USB cable (data-capable)** | Connects the LEVM's CP2105 serial bridge to the Pi. Charge-only cables will not enumerate — check the connector on your board revision | Any | $5 | $8 |
| **Jumper wire** | 1 wire: detector `GATE` → Pi BCM17 / physical pin 11, alongside the existing `GATE` → OPS `HOST_INT` | Any | $1 | $1 |

> **Canadian buyers: order the LEVM from TI directly.** TI ships to Canada and lists it
> at $156.45 USD (~$215 CAD). DigiKey Canada stocks the same board at **$297.83 CAD**,
> roughly $80 more than TI direct even after shipping and brokerage.

The board needs **custom firmware** — it does not work out of the box. The
stock TI demo does not expose the raw radar cube OpenFlight needs. A validated
prebuilt image ships in `firmware/releases/`, so you do not need the TI
toolchain to flash it.

You also need physical access to the board's **boot-mode switch (S1.1)** and
**RESET button** to flash. Both are on the LEVM itself; nothing to buy.

### IWR6843 Setup

Two connection layouts are supported, and which one you can use depends on your
OPS243 variant:

| Layout | OPS243 connection | Extra parts needed |
|--------|-------------------|--------------------|
| **A (validated)** | Pi GPIO UART header | 4 jumper wires (5V, GND, TX, RX) |
| **B** | Powered USB hub | [Powered USB hub](https://www.amazon.com/dp/B0CN3F9Y1Z) (~$20 USD / ~$28 CAD) |

> [!CAUTION]
> The hub must have its **own power adapter**. Layout B exists because the Pi cannot
> supply both radars, so a bus-powered hub will not solve the problem it is there to
> solve. Note that the `.com` ASIN above resolves to a **different, bus-powered** hub on
> Amazon.ca, so Canadian buyers should search for an *externally powered* USB 3.0 hub
> rather than following that link.

Layout A keeps the TI board on USB and moves the OPS243 to the Pi's GPIO
header, which is what the power budget requires — the Pi cannot supply both
radars over USB.

> [!WARNING]
> Layout A does **not** work with a **WiFi-equipped OPS243-A**. Its onboard WiFi
> module already drives the radar's UART receive line, so the Pi cannot send it
> commands. WiFi OPS boards must use Layout B with a powered hub.

Full instructions: **[IWR6843 Operator Guide](iwr6843/README.md)** for wiring,
flashing, mounting, and geometry; **[Moving the OPS243 to the Pi GPIO
UART](ops243-uart-migration.md)** for the OPS side of Layout A.

### Optional Enclosure Inclinometer

An LIS3DH mounted to the enclosure base lets OpenFlight compensate the IWR6843
tilt when the rig is placed on uneven ground.

| Part | Description | Link | ~USD | ~CAD |
|------|-------------|------|------|------|
| **Adafruit LIS3DH breakout** | Triple-axis accelerometer with STEMMA QT connectors | [Adafruit product 2809](https://www.adafruit.com/product/2809) · CA [Elmwood](https://elmwoodelectronics.ca/search?q=LIS3DH) | $5 | $8 |
| **JST-SH cable kit** | Solderless STEMMA QT/Qwiic to female Dupont wiring used in the validated build | [Amazon](https://www.amazon.com/Connector-Compatible-Development-Sensors-Drivers/dp/B0GJPRX4YT) · CA [Elmwood](https://elmwoodelectronics.ca/search?q=STEMMA+QT+JST+SH+cable) | ~$10 | $2 |

See the **[LIS3DH Inclinometer Setup Guide](inclinometer/README.md)** for wiring,
mounting, calibration, startup flags, and troubleshooting.

---

## Angle Radar (K-LD7) — DEPRECATED

> **⚠️ DEPRECATED — do not buy for new builds.** The K-LD7 angle radars have been superseded by a more capable radar chip. K-LD7 support remains in the software for existing builds but will not receive further development. The parts below are listed for reference only.

Two K-LD7 modules measure launch angle (vertical) and club path / aim direction (horizontal). The OPS243 handles speed; the K-LD7s provide **angle and distance only** (speed data aliases above 62 mph).

| Part | Description | Link | ~Price |
|------|-------------|------|--------|
| **RFbeam K-LD7 (×2)** | 24 GHz FMCW radar for angle + distance | [RFbeam](https://rfbeam.ch/product/k-ld7-radar-transceiver/) | ~$60 ea |
| **FTDI USB-to-Serial adapter (×2)** | 3.3V FTDI board for K-LD7 UART (e.g. FT232RL) | [Amazon](https://www.amazon.com/s?k=ftdi+3.3v+usb+serial) | ~$10 |

> **EVAL board not required.** The K-LD7 bare module communicates over 3.3V UART (TX, RX, VCC, GND). Any 3.3V FTDI USB-to-serial adapter works. The official K-LD7 EVAL board (~$120 each) is only needed if you want the RFbeam GUI software for configuration — OpenFlight configures the radar over serial automatically.

### K-LD7 Connection

Each K-LD7 connects via a 3.3V FTDI adapter, appearing as `/dev/ttyUSB*` on Linux.

```
K-LD7 Module (UART) → FTDI 3.3V Adapter → USB → Raspberry Pi
```

One unit is mounted vertically (launch angle), one horizontally (club path / aim direction). A `--kld7-angle-offset` parameter corrects for mounting geometry — see the [setup guide](raspberry-pi-setup.md) for calibration.

## Power & Accessories

| Part | Description | Link | ~USD | ~CAD |
|------|-------------|------|------|------|
| **27W USB-C Power Supply** | Official Pi 5 power supply (5V 5A) | [Adafruit](https://www.adafruit.com/product/5814) · CA [PiShop.ca](https://www.pishop.ca/product/raspberry-pi-27w-usb-c-power-supply-black-us/) | $14 | $17 |
| MicroSD Card (32GB+) | For Pi OS and software | Any Class 10 · CA [PiShop.ca](https://www.pishop.ca/product-category/raspberry-pi/sd-cards/) | $10 | $29 |
| USB-A to Micro-USB Cable | For OPS243 radar connection | Any | $5 | $8 |

## Optional

| Part | Description | Link | ~USD | ~CAD |
|------|-------------|------|------|------|
| Tripod Mount | For positioning the unit | 1/4"-20 mount | $10 | $14 |
| **Geekworm X1202 UPS HAT** | Rechargeable Pi 5 power using four matching flat-top 18650 Li-ion cells. Cells are not included | [Geekworm](https://geekworm.com/products/x1202) | ~$48 + cells | ~$66 + cells |
| **Geekworm X1206 UPS HAT** | Larger rechargeable Pi 5 power option using four matching 21700 Li-ion cells, advertised up to 20,000mAh total. Cells are not included | [Geekworm](https://geekworm.com/products/x1206) | Varies + cells | Varies + cells |
| **InnoMaker OV9281 global-shutter camera** | High-speed monochrome camera for experimental vision work. Camera software is not enabled in the production kiosk path | [Amazon](https://www.amazon.com/dp/B09WTP5GZH?th=1) | ~$30 | ~$41 |

See [Camera and YOLO Experiments](yolo-performance-tuning.md) before buying the
camera; the standard setup does not install its optional software dependencies.

---

## Cost Summary

| Category | ~USD | ~CAD |
|----------|------|------|
| Core (OPS243, Pi 5, Display) | $400 | $518 |
| Sound Trigger (SEN-14262 + resistor + wires) | $18 | $29 |
| Power & Accessories | $29 | $54 |
| **Subtotal, no angle radar** | **~$447** | **~$601** |
| Angle Radar (IWR6843LEVM + cable + wire) — **current** | $162 | $224 |
| **Total with angle radar** | **~$609** | **~$825** |
| Angle Radar (2× K-LD7 + FTDI adapters) — **deprecated** | $140 | n/a |

CAD totals assume the LEVM is ordered from TI direct and exclude shipping, duty,
brokerage, and sales tax.

OpenFlight works without any angle radar: you get ball speed, club speed, smash
factor, spin rate, and estimated carry. The angle radar adds measured launch
angle (vertical and horizontal) and is what club path is derived from.

If you are building new, buy the **IWR6843**, not the K-LD7s. It costs about the
same as the two K-LD7s plus their FTDI adapters ($162 vs $140) and replaces both
of them with one board. The K-LD7 path is **deprecated** and kept only so
existing builds keep working.

---

## Buying in Canada

Most of the build can be sourced from Canadian distributors, which avoids customs
brokerage fees that often exceed the duty itself on low-value shipments.

| Part | Canadian source | ~CAD |
|------|-----------------|------|
| Raspberry Pi 5 (4GB) | [PiShop.ca](https://www.pishop.ca/product/raspberry-pi-5-4gb/) | $153.95 |
| 27W USB-C PSU | [PiShop.ca](https://www.pishop.ca/product/raspberry-pi-27w-usb-c-power-supply-black-us/) | $16.95 |
| microSD 32GB (official, blank) | [PiShop.ca](https://www.pishop.ca/product-category/raspberry-pi/sd-cards/) | $28.95 |
| SparkFun SEN-14262 | [DigiKey.ca](https://www.digikey.ca/en/products/detail/sparkfun-electronics/14262/7725299) | $20.76 |
| Adafruit LIS3DH (optional) | [Elmwood Electronics](https://elmwoodelectronics.ca/search?q=LIS3DH) | $7.99 |
| STEMMA QT / JST-SH cable (optional) | [Elmwood Electronics](https://elmwoodelectronics.ca/search?q=STEMMA+QT+JST+SH+cable) | $1.99 |
| 7" 1024x600 IPS touchscreen | [Amazon.ca](https://www.amazon.ca/dp/B0CRRB1GFN) (equivalent, not the identical HMTECH unit) | ~$55.64 |

Two parts have **no Canadian distributor** and must be imported:

- **OPS243-A**: order direct from [OmniPreSense](https://omnipresense.com/product/ops243-doppler-radar-sensor/)
  ($224 USD). As of 2026-08-22 it is listed **"Available on backorder"**, so order this
  first: it is both the long pole and the single most expensive item.
- **IWR6843LEVM**: order direct from [TI](https://www.ti.com/tool/IWR6843LEVM)
  ($156.45 USD). TI ships to Canada. Do **not** buy it from DigiKey Canada at
  $297.83 CAD unless you need it same-week.

### Notes for Canadian orders

- **Amazon `.com` ASINs do not map to Amazon.ca.** Every Amazon link in this document
  is a `.com` listing, and the two that were checked both resolve to a different product
  on the Canadian store: the display link lands on an 800x480 MIPI DSI panel rather than
  a 1024x600 unit, and the hub link lands on a bus-powered hub. Match on
  *specification*, not on the linked listing.
- **DigiKey Canada** ships free on orders over $100 CAD and clears customs itself, so
  batching the SEN-14262 with other DigiKey parts is usually worth it.
- **Elmwood Electronics** (Toronto) stocks most Adafruit and SparkFun parts domestically
  and is materially cheaper than importing them: the STEMMA QT cable is $1.99 CAD there
  versus a ~$10 USD Amazon kit.
- Prices captured **2026-08-22**; converted figures use the Bank of Canada daily rate of
  **1.3760 USD/CAD (2026-08-21)**.

The deprecated K-LD7 table is intentionally left in USD only, since those parts should
not be bought for new builds.
