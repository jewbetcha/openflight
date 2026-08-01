# IWR6843 Firmware Developer Guide

OpenFlight uses custom firmware on the TI IWR6843LEVM to preserve a short radar
movie around impact in the chip's on-board L3 RAM. The firmware continuously
processes chirps, stores selected complex range bins in a circular frame ring,
and streams that ring to the Raspberry Pi after the shared sound trigger.

Most builders do **not** need to compile firmware. A validated flashable image is
checked into the repository. Build the firmware only when changing capture
geometry, range windows, HWA/EDMA processing, or the binary dump contract.

For hardware wiring, mounting, geometry, calibration, and normal OpenFlight
startup, use the [IWR6843 Operator Guide](../docs/iwr6843/README.md).

## Current Validated Release

Use this firmware and runtime configuration together:

| Component | Current value |
|---|---|
| Flash image | `firmware/releases/l3_dump_vTX2_hwa_window53_12loops_18frames_4ms_temperature_report_20260731.bin` |
| Previous rollback image | `firmware/releases/l3_dump_vTX2_hwa_window53_12loops_18frames_4ms_v2.bin` |
| Runtime config | `config/iwr6843_l3dump_vTX2_window53_12l18f.cfg` |
| Reference calibration | `config/iwr6843_calibration_reference.json` |
| Build target | `make -C firmware build-native` |
| Flash image size | 339,780 bytes |
| Flash SHA-256 | `8a87593954fd5ae2b7adf709c78626f81a87b8988b8dc28f2b2be7b5c99eac12` |
| Dump format | Version 5, windowed complex range-FFT snapshots plus temperature report |
| Complete dump size | 549,566 bytes |

Verify the checked-in image before flashing:

```bash
sha256sum firmware/releases/l3_dump_vTX2_hwa_window53_12loops_18frames_4ms_temperature_report_20260731.bin
```

The current image retains the validated capture geometry while fixing repeated
application startup and shutdown. It stops the
RF front end only after the active HWA frame reaches a safe boundary, then
disables HWA and EDMA.

Release filenames track build iteration separately from the dump wire-format
version. The `_v2.bin` image remains checked in as the last validated rollback
artifact (`3045bb2f087b40c228bf1dd5190cf3fac6dbde50682c7927e86714314b0e7fcb`);
the dated `temperature_report_20260731` image is the current supported release
and emits dump format v5.

## What The Current Firmware Captures

### Capture Geometry

| Setting | Value |
|---|---|
| Transmitters | 3 |
| Receivers | 4 |
| Loops per frame | 12 |
| Chirps per frame | 36 (`3 TX x 12 loops`) |
| Frames in the ring | 18 |
| Frame spacing | 4 ms |
| Frames before trigger | 6 |
| Frames after trigger | 12 |
| Acquired ADC samples per chirp | 128 |
| Stored range bins per chirp/RX | 53 complex bins |

All three transmitters are retained. The outer transmitter pair is used by the
vertical launch estimator, while the remaining transmitter provides the
experimental horizontal aperture. Each transmitter is fired once per TDM loop;
the four receivers sample every chirp simultaneously.

### On-Chip Data Path

```text
RF chirp
  -> ADCBUF
  -> HWA 128-point range FFT
  -> EDMA copies 53 selected complex bins
  -> 18-frame circular ring in L3 RAM
  -> Pi sends "l3dump" at the sound-trigger edge
  -> firmware keeps 12 completed post-trigger frames
  -> freeze at a completed-frame boundary
  -> stream header, frame-window metadata, and IQ payload over UARTA
  -> restart the frame ring for the next shot
```

HWA performs the range FFT before storage, but the saved bins remain complex
I/Q. That phase information is required for vertical and horizontal direction
of arrival; this is not a magnitude-only detection list.

### Dynamic Range Windows

The firmware stores 53 contiguous bins per frame but moves that window outward
as the ball travels away from the radar:

| Time region | Frames | Start bin | Stored bins | Purpose |
|---|---:|---:|---:|---|
| Rolling history plus active trigger frame | 7 | 20 | 20-72 | Keep six pre-trigger frames and the frame already active when the request arrives |
| Middle post-trigger flight | 5 | 32 | 32-84 | Follow the ball away from the tee |
| Late post-trigger flight | 6 | 47 | 47-99 | Retain farther flight and the net-side region |

Each frame's start bin is written into the dump. The host therefore knows the
absolute range represented by every local bin and never has to infer which
window the firmware used.

### L3 Memory Budget

The IWR6843 provides 768 KiB (786,432 bytes) of L3 RAM for the capture ring. The
current payload is:

```text
3 TX x 12 loops x 18 frames x 4 RX x 53 bins x 4 bytes
= 549,504 bytes
```

The transfer adds a 20-byte header, a 24-byte temperature report, and 18
one-byte frame-window entries:

```text
549,504 + 20 + 24 + 18 = 549,566 bytes
```

For comparison, retaining all 128 complex range bins with the same TX, loop,
and frame counts would require 1,327,104 bytes. On-chip range FFT plus selected
range windows is what makes the denser 18-frame capture fit.

## Firmware And Host Contract

The wire format is defined in two places that must stay synchronized:

- Firmware: [`iwr6843/dump_format.h`](iwr6843/dump_format.h)
- Host parser: [`../src/openflight/iwr6843/dump.py`](../src/openflight/iwr6843/dump.py)

The current version 5 transfer contains:

1. A packed 20-byte little-endian `l3_dump_header_t`.
2. A packed 24-byte `l3_temperature_report_t` captured immediately before streaming.
3. One unsigned start-bin byte for each frame.
4. Complex int16 samples ordered by frame, chirp, RX, and local range bin.
5. Each complex sample in TI's native imaginary-then-real order.

The header carries:

| Field | Meaning |
|---|---|
| `magic` | `ILD1` synchronization marker |
| `version` | Dump contract version |
| `n_frames` | Number of ring frames |
| `chirps_per_frame` | `n_tx x loops` |
| `n_tx`, `n_rx` | Virtual-array geometry |
| `n_samples` | Stored bins per chirp/RX for snapshot formats |
| `sample_fmt` | Raw ADC, fixed range snapshot, or windowed range snapshot |
| `trigger_frame` | Oldest circular-ring slot for chronological rotation |
| `frame_period_us` | Frame spacing used by trajectory fitting |

Changing the header, sample order, frame metadata, or sample format requires a
matching host-parser change and regression tests in the same commit.

## Repository Layout

| Path | Responsibility |
|---|---|
| `firmware/iwr6843/l3_dump.c` | RF control, HWA/EDMA pipeline, circular ring, freeze/rearm, CLI, and dump streaming |
| `firmware/iwr6843/dump_format.h` | Packed firmware-side wire contract |
| `firmware/iwr6843/makefile` | TI mmWave SDK application build and meta-image generation |
| `firmware/iwr6843/mss.cfg` | SYS/BIOS configuration |
| `firmware/iwr6843/mss_linker.cmd` | Places the ring and optional scratch buffers in L3 RAM |
| `firmware/Makefile` | Toolchain setup and production firmware build target |
| `firmware/releases/` | The single checked-in, validated flash image |
| `firmware/flash_iwr6843.py` | Pi-compatible IWR6843 ROM bootloader client |
| `config/iwr6843_l3dump_vTX2_window53_12l18f.cfg` | Runtime RF configuration matching the current firmware |
| `src/openflight/iwr6843/dump.py` | Python decoder and executable format reference |

## Where To Build, Flash, And Run

| Operation | Supported environment |
|---|---|
| Build | Native x86_64 Linux or an x86_64 Debian VM |
| Build on Apple Silicon | UTM emulating x86_64 Debian |
| Build on Raspberry Pi 5 | Not currently reliable because TI's x86/i386 installer stubs can fail under QEMU and a 16 KiB host page size |
| Flash | Raspberry Pi using `flash_iwr6843.py`, or TI UniFlash as a fallback |
| Run | Raspberry Pi through OpenFlight |

The recommended open-source, no-cloud path for an Apple Silicon Mac is an
x86_64 Debian VM in UTM. The Pi can flash and run the image, but it should not
be treated as the canonical compiler host.

## Build On Apple Silicon With UTM

### 1. Create An x86_64 Debian VM

In UTM:

1. Select **Create a New Virtual Machine**.
2. Select **Emulate**, not Virtualize.
3. Select **Linux** and an amd64 Debian netinst ISO.
4. Use `Intel ICH9 based PC (2009, x86_64)`.
5. Allocate at least 4 GB RAM and 30 GB storage.
6. Install `SSH server` and `standard system utilities`; a desktop is optional.
7. Eject the installer ISO before the first reboot into the installed system.

Confirm the guest architecture and page size:

```bash
uname -m
getconf PAGE_SIZE
```

Expected output is `x86_64` and `4096`.

### 2. Put OpenFlight In The VM

Clone the repository inside the VM or copy your existing worktree with `rsync`:

```bash
sudo apt-get update
sudo apt-get install -y git rsync openssh-server
git clone https://github.com/jewbetcha/openflight.git
cd openflight
```

To copy an existing worktree from the Mac instead:

```bash
rsync -av --exclude '.venv' ~/Projects/openflight/ \
  openflight@VM_ADDRESS:~/openflight/
```

Find the VM address with `ip addr` inside Debian.

### 3. Supply The TI Installers

TI's installers are large and license-gated, so they are intentionally ignored
by git. Download them from TI and place these exact files under
`firmware/ti_installers/` inside the VM:

```text
mmwave_sdk_03_06_02_00-LTS-Linux-x86-Install.bin
ti_cgt_tms470_20.2.7.LTS_linux-x64_installer.bin
bios_6_73_01_01.run
sysconfig-1.10.0_2163-setup.run
xdctools_3_61_00_16_core_linux.zip
```

The application is MSS/R4F-only; it does not require the C674x DSP compiler or
DSP libraries.

Verify the installer set:

```bash
make -C firmware check-installers
```

### 4. Install The Build Environment

Install Debian packages, probe every installer stub, and install the TI tools
under `/opt/ti`:

```bash
make -C firmware install-ti-deps-native
make -C firmware probe-installers-native
make -C firmware install-ti-tools-native
```

The resulting layout is:

```text
/opt/ti/sdk/mmwave_sdk_03_06_02_00-LTS
/opt/ti/cgt-arm/ti-cgt-arm_20.2.7.LTS
/opt/ti/bios/bios_6_73_01_01
/opt/ti/xdc/xdctools_3_61_00_16_core
/opt/ti/sysconfig
```

### 5. Build The Current Firmware

From the repository root inside the VM:

```bash
make -C firmware build-native
```

The target performs the application build, generates the flashable TI
meta-image, and copies the production image into `firmware/releases/`:

```text
firmware/releases/l3_dump_vTX2_hwa_window53_12loops_18frames_4ms_temperature_report_20260731.bin
```

Generated `.xer4f`, `.map`, and intermediate `.bin` files stay under
`firmware/iwr6843/` and are ignored by Git. Current production images and
intentional rollback images live under `releases/`.

### 6. Copy Artifacts Out Of The VM

From the Mac:

```bash
mkdir -p artifacts/firmware_build
rsync -av \
  openflight@VM_ADDRESS:~/openflight/firmware/releases/ \
  artifacts/firmware_build/
```

## Build On Native x86_64 Linux

Use the same installer files and Make targets as the UTM VM. Confirm `uname -m`
reports `x86_64`, then start at **Supply The TI Installers** above.

The tool paths can be overridden when a machine does not use `/opt/ti`:

```bash
make -C firmware build-native \
  TI_ROOT=/custom/ti
```

## Supported Build Target

`make -C firmware build-native` is the only supported target. It builds the
validated 3 TX, 12-loop, 18-frame, 4 ms configuration with dynamic 53-bin
windows. Use Git history for earlier experiments rather than distributing
those images or targets as installation choices.

## Flash From The Raspberry Pi

The checked-in Python flasher uses the IWR6843 ROM UART bootloader and does not
require TI Cloud Agent. Flash over the CP2105 **Enhanced/UARTA** interface,
normally interface `00` and `/dev/ttyUSB0`. Do not use the Standard interface,
normally `/dev/ttyUSB1`.

### 1. Stop Serial Users

Stop OpenFlight and any calibration or test process using the TI port:

```bash
pgrep -af 'openflight|calibrate|shot_test'
sudo fuser -v /dev/ttyUSB0
```

### 2. Enter Flash Mode And Probe

Set the IWR6843LEVM switches to:

```text
S1.1 ON, S1.2 OFF, S1.3 ON, S1.4 ON, S1.5 OFF
```

Start the non-destructive probe:

```bash
uv run python firmware/flash_iwr6843.py \
  --probe \
  --port /dev/ttyUSB0
```

Follow the prompts exactly:

1. Type `READY` so the script opens UART and settles the control lines.
2. Press and release RESET only when requested.
3. Wait one second.
4. Type `PROBE`.

Do not continue until the ROM bootloader handshake passes.

### 3. Flash The Current Image

Leave the board in flash mode and run:

```bash
uv run python firmware/flash_iwr6843.py \
  firmware/releases/l3_dump_vTX2_hwa_window53_12loops_18frames_4ms_temperature_report_20260731.bin \
  --port /dev/ttyUSB0
```

Type `READY`, press RESET when prompted, wait one second, and type `FLASH`. The
default workflow erases SFLASH, writes acknowledged chunks, closes the image,
and verifies the final ROM bootloader status.

Expected completion:

```text
Erasing existing SFLASH...
Opening firmware image...
Writing firmware...
Writing: 100% (339,780/339,780 bytes)
Closing and verifying firmware...

Flash verified by the IWR6843 ROM bootloader.
```

Do not reset, disconnect, or remove power while erase or write is active. A
failed write is recoverable because the ROM bootloader is not stored in SFLASH.
Leave the board in flash mode and rerun the complete command.

### 4. Return To Functional Mode

Set the switches to:

```text
S1.1 OFF, S1.2 OFF, S1.3 ON, S1.4 ON, S1.5 OFF
```

Press and release RESET. The firmware CLI and binary dumps now share the
Enhanced UART at 1,041,667 baud. Flashing itself always uses the ROM
bootloader's 115,200-baud protocol.

The flasher follows TI application note
[SWRA627, IWR6843 Bootloader Flow](https://www.ti.com/lit/an/swra627/swra627.pdf).

## Verify The Installed Firmware

Run OpenFlight with the matching config as described in the
[Operator Guide](../docs/iwr6843/README.md#start-openflight). With `--debug`, a
healthy capture reports:

```text
[IWR6843] Trigger #1: dumping firmware-frozen L3 ring
[IWR6843] Capture #1 complete: 549566 bytes
```

The firmware/config geometry is checked at `sensorStart`. A mismatch in TX
masks, loop count, frame count, or ADC samples is rejected rather than silently
capturing a differently shaped cube.

## Changing Capture Geometry

The following values are compile-time firmware geometry and must match the RF
config or dump parser:

| Firmware define | Matching runtime concept |
|---|---|
| `N_TX` | Number of `chirpCfg` TX masks and TDM chirps per loop |
| `LOOPS` | Loop count in `frameCfg` |
| `RING_FRAMES` | Number of frames carried in the dump |
| `HWA_POST_TRIGGER_FRAMES` | Post-trigger tail; must be less than `RING_FRAMES` |
| `N_SAMPLES` | ADC samples in `profileCfg` |
| `SNAPSHOT_BINS` | Complex range bins retained per chirp/RX |
| `SNAPSHOT_BIN_START` | Rolling pre-trigger range-window start |
| `SNAPSHOT_MIDDLE_BIN_START` | First post-trigger range-window start |
| `SNAPSHOT_LATE_BIN_START` | Final post-trigger range-window start |

Before increasing loops, frames, transmitters, or bins, calculate the ring:

```text
ring bytes = TX x loops x frames x RX x saved bins x 4
```

The result must fit within 786,432 L3 bytes along with any variant-specific L3
scratch sections. The linker places `.l3ring` and `.l3scratch` in `L3_RAM` and
fails the build if they overflow.

Do not reuse application objects after changing compile-time geometry. The
named targets in `firmware/Makefile` remove application objects before each
build; use those targets rather than invoking the lower-level makefile against
stale objects.

## Validation Before Flashing A New Variant

Run the firmware contract and host-pipeline tests:

```bash
uv run pytest \
  tests/test_iwr6843_firmware_rearm.py \
  tests/test_iwr6843_pipeline.py \
  tests/test_iwr6843_driver.py \
  tests/test_iwr6843_monitor.py \
  tests/test_iwr6843_bootloader.py
```

Also check:

1. The `.cfg` matches all compile-time capture geometry.
2. The map file keeps `.l3ring` and `.l3scratch` inside L3.
3. The first static capture has the expected version, dimensions, frame period,
   per-frame window table, and total byte count.
4. Repeated dump/rearm cycles work without resetting the board.
5. Vertical and horizontal estimators can replay the new format offline.
6. Source-of-truth testing is repeated if timing, loops, frame spacing, TX
   schedule, or saved range coverage changed.

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| TI installer exits immediately | Build host is ARM, installer lacks execute permission, or i386 compatibility is missing | Use x86_64 Debian, run `install-ti-deps-native`, then `probe-installers-native` |
| VM returns to the Debian installer | ISO remains attached | Eject the ISO from the UTM CD/DVD drive and reboot |
| `check-installers` reports missing files | Installer name or location differs | Use the exact filenames under `firmware/ti_installers/` |
| Build cannot find `/opt/ti/...` | Tool installation did not complete or uses a custom root | Run `install-ti-tools-native` or pass `TI_ROOT=/custom/ti` |
| Link fails with L3 overflow | Ring or scratch allocation exceeds 768 KiB | Reduce frames, loops, TX count, or saved bins and inspect the map file |
| Probe receives no ROM response | Wrong CP2105 interface or RESET timing | Use Enhanced/UARTA, type `READY`, then RESET only when prompted |
| Flash fails after erase | Image transfer was interrupted | Leave flash mode enabled and rerun the full flash command; the ROM bootloader remains available |
| No CLI after flashing | Board remains in flash mode or was not reset | Restore functional switches and press RESET |
| Server rejects the config | Firmware and `.cfg` geometry differ | Use the current release binary and `iwr6843_l3dump_vTX2_window53_12l18f.cfg` together |
| Dump is not 549,566 bytes | Wrong firmware format, interrupted UART transfer, or stale process | Verify SHA-256, use Enhanced/UARTA, stop serial owners, reset, and retry |
| First run works but restart hangs | Retired v1 image or incomplete shutdown | Flash the current release image and reset in functional mode |

## Historical Context

The [IWR6843 field report](../docs/iwr6843_field_report_2026-07.html) explains
why the project moved capture into on-chip L3 and how the estimator evolved.
The implementation has since advanced from full raw ADC rings to HWA-generated,
dynamically windowed complex range snapshots; this README is the authoritative
description of the current firmware.
