# OpenFlight Parts List

Hardware components for building the OpenFlight golf launch monitor.

## Core Components

| Part | Description | Link | ~Price |
|------|-------------|------|--------|
| **OPS243-A Radar** | Doppler radar for ball/club speed detection | [OmniPreSense](https://omnipresense.com/product/ops243-a-doppler-radar-sensor/) | $249 |
| **Raspberry Pi 5** | Main compute unit (4GB+ recommended) | [Adafruit](https://www.adafruit.com/product/5812) | $60 |
| **Raspberry Pi HQ Camera** | 12.3MP camera for launch angle detection | [Adafruit](https://www.adafruit.com/product/4561) | $50 |
| **Arducam 4mm CS-Mount Lens** | Wide angle lens for HQ Camera | [Amazon](https://www.amazon.com/dp/B088GWZPL1) | $20 |
| **7" Touchscreen Display** | HMTECH 7" 1024x600 IPS display | [Amazon](https://www.amazon.com/dp/B0D3QB7X4Z) | $46 |

## IR Illumination (for camera)

| Part | Description | Link | ~Price |
|------|-------------|------|--------|
| **IR LED Camera Module** | OV5647 camera with 2x 3W 850nm IR LEDs (use LEDs only) | [Amazon](https://www.amazon.com/MELIFE-Raspberry-Camera-Adjustable-Focus-Infrared/dp/B08RHZ5BJM) | $16 |

### Alternative IR Options

| Part | Description | Link | ~Price |
|------|-------------|------|--------|
| 5W IR LED Module (2-pack) | Higher power, direct Pi connection | [Amazon](https://www.amazon.com/Infrared-Raspberry-Illuminator-Adjustable-Resistor/dp/B0D39S5RLW) | $12 |
| 3W IR LED Module (2-pack) | Standard power, direct Pi connection | [Amazon](https://www.amazon.com/Infrared-Illuminator-Adjustable-Resistor-Raspberry/dp/B07FM6LL3V) | $10 |
| 10W IR LED Chip | For outdoor use (requires 12V driver setup) | [Amazon](https://www.amazon.com/dp/B01DBZK4EM) | $8 |

### 10W LED Driver Setup (if needed for outdoor)

| Part | Description | Link | ~Price |
|------|-------------|------|--------|
| 12V 3A Power Supply | Powers Pi + LED | Search "12V 3A barrel jack adapter" | $8 |
| 12V to 5V Buck Converter | Powers Pi from 12V supply | Search "12V to 5V 3A buck converter" | $6 |
| XL4015 CC/CV Module | Constant current driver for 10W LED | [Amazon](https://www.amazon.com/Organizer-Adjustable-Step-Down-Voltmeter-Constant/dp/B07VDKD5YQ) | $8 |
| Heatsink (40x40mm) | Required for 10W LED | Search "aluminum heatsink 40mm" | $3 |

## Power & Accessories

| Part | Description | Link | ~Price |
|------|-------------|------|--------|
| **27W USB-C Power Supply** | Official Pi 5 power supply (5V 5A) | [Adafruit](https://www.adafruit.com/product/5974) | $12 |
| MicroSD Card (32GB+) | For Pi OS and software | Any Class 10 | $10 |
| USB-A to Micro-USB Cable | For OPS243-A radar connection | Any | $5 |

## Optional

| Part | Description | Link | ~Price |
|------|-------------|------|--------|
| Pi Case with Camera Mount | Enclosure for Pi + HQ Camera | Various | $15-30 |
| Tripod Mount | For positioning the unit | 1/4"-20 mount | $10 |
| **850nm IR Pass Filter** | For outdoor use - blocks visible light, only passes IR | [Kurokesu](https://www.kurokesu.com/shop/D19x1_NIR_SCREWIN) | ~$20 |

---

## Notes

### IR LED Connection
The IR LED modules connect to the Pi's GPIO:
- **5V**: Pin 2 or Pin 4
- **GND**: Pin 6, 9, 14, 20, 25, 30, 34, or 39

### Camera IR Filter
The Raspberry Pi HQ Camera does **not** have a built-in IR filter, making it suitable for IR illumination without modification. Verify your lens doesn't have an IR-cut filter by pointing a TV remote at the camera - you should see the IR LED flash.

### Power Budget
When powering IR LEDs from Pi's 5V GPIO:
- Pi 5 uses ~2-3A under load (more powerful than Pi 4)
- With 5A power supply (official Pi 5 PSU recommended), ~2A available for accessories
- 6W of IR LEDs @ 5V = 1.2A (safe with good power supply)
