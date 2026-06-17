# TV Remote Control (kiosk on a TV via HDMI / DisplayPort)

When the Raspberry Pi drives a TV over HDMI or DisplayPort, you can navigate the
OpenFlight kiosk with a remote - the TV's own remote, or any universal/IR remote.
You need only **navigation + select**: a D-pad (Up/Down/Left/Right), OK/Select,
and Back.

## How it works

Every input path converges on the same thing the web UI understands - **arrow
keys + Enter**:

```
                      ┌─ HDMI-CEC ───────────┐
TV remote ───IR──► TV ┤ (TV's own remote      ├─► Pi: cec_remote.py ─┐
                      └  down the HDMI cable)  ┘     → ydotool        │
                                                                     ├─► Chromium kiosk
Any IR remote ───IR──► FLIRC USB dongle ──► Pi: USB keyboard ────────┘     (Arrow keys / Enter)
                       (HDMI *or* DisplayPort)                              → useSpatialNavigation
```

The web layer ([ui/src/state/useSpatialNavigation.ts](../ui/src/state/useSpatialNavigation.ts))
moves focus to the nearest control in the pressed direction and shows a large
focus ring (the `.tv` styles). Focused buttons activate on **Enter** natively.

> **Choosing Interactive vs Scoreboard.** On first run, larger external screens
> show a one-time chooser - **Interactive** (full controls, 10-foot + remote) or
> **Scoreboard** (passive stats display). The small 7" kiosk panel defaults to
> Interactive and skips the chooser. `start-kiosk.sh` auto-detects the connected
> screen (EDID/CEC) to pre-highlight the likely option; force it with
> `--interactive` / `--scoreboard` (or the `--tv` / `--monitor` aliases), or skip
> detection with `--no-view-detect`. The choice is saved per device and applied
> **live, switchable anytime in Settings → View mode** (no reload). Samsung/LG TV
> browsers still auto-suggest Interactive, and `?tv=1` still seeds Interactive.

## Button map

| Remote button | Key sent | Effect in the kiosk |
|---------------|----------|---------------------|
| D-pad Up/Down/Left/Right | Arrow keys | Move focus to the nearest control |
| OK / Select | Enter | Activate the focused control |
| Back / Exit | Esc | Close the settings panel / dialog |

---

## Path 1 - HDMI-CEC (recommended for HDMI, no extra hardware)

CEC is built into the HDMI cable. The TV's own remote sends D-pad/OK presses to
the Pi. Every major brand supports it under a marketing name - enable it on the
TV once:

| Brand | CEC setting name |
|-------|------------------|
| Samsung | Anynet+ (HDMI-CEC) |
| LG | SimpLink |
| Sony | Bravia Sync |
| Philips | EasyLink |
| Panasonic | VIERA Link |
| Vizio | CEC |
| TCL / Hisense (Android TV) | CEC / T-Link / HDMI-CEC |

### Pi setup

```bash
sudo apt install cec-utils python3-cec ydotool
sudo systemctl enable --now ydotool          # uinput key injection (Wayland)

# Confirm the TV is visible on the CEC bus:
cec-client -l                                 # lists adapters
echo 'scan' | cec-client -s -d 1              # should list the TV

# Install the bridge service:
sudo cp scripts/tv-remote/openflight-cec.service /etc/systemd/system/
#   edit User= and the ExecStart path in the unit to match your install
sudo systemctl daemon-reload
sudo systemctl enable --now openflight-cec.service
journalctl -u openflight-cec -f               # watch button events
```

The bridge is [scripts/tv-remote/cec_remote.py](../scripts/tv-remote/cec_remote.py):
it listens for CEC keypresses and injects the mapped key with `ydotool`. It runs
as its own systemd service ([openflight-cec.service](../scripts/tv-remote/openflight-cec.service),
independent of the kiosk) so it survives kiosk restarts and starts on boot.

---

## Path 2 - FLIRC USB-IR (universal; required for DisplayPort)

**DisplayPort has no CEC channel**, so a DP-connected TV/monitor cannot forward
its remote to the Pi. It's also the simplest brand-agnostic option for HDMI.

[FLIRC](https://flirc.tv) is a ~$25 USB dongle that learns *any* IR remote and
presents to the Pi as a normal USB keyboard - no driver, works on HDMI or DP,
works with cheap universal remotes.

```bash
sudo apt install flirc            # or the official .deb from flirc.tv
scripts/tv-remote/flirc_setup.sh  # press each requested remote button once
```

The helper ([flirc_setup.sh](../scripts/tv-remote/flirc_setup.sh)) maps six buttons
to Up/Down/Left/Right/Enter/Esc. Because FLIRC *is* a keyboard, nothing else is
needed - no CEC service, no `ydotool`.

> Universal remotes: either program the universal remote to your TV brand (then
> use Path 1 / the TV's CEC), or point any of its IR buttons at the FLIRC and
> record them with the script above.

---

## Path 3 - Phone / tablet web-remote (universal, no hardware)

The most brand-independent fallback, and the one that needs no CEC, no IR, and no
extra hardware. Open the web-remote page on any phone/tablet on the same network:

```
http://<pi-ip>:8080/remote
```

It shows a D-pad + OK + Back. Each press is relayed over the existing Socket.IO
connection to the display, which moves focus via the same spatial-navigation
engine the physical remotes drive. Requirements:

- The display must be in TV mode (`/scoreboard?tv=1` or `/?tv=1`) so navigation +
  the 10-foot focus ring are active.
- Both devices on the same LAN. Nav-only (no auth): the relayed keys move focus,
  activate the focused control, or dismiss a dialog - destructive actions (e.g.
  shutdown) still require their on-screen confirmation.

## Path 4 - GPIO / USB IR via `ir-keytable` (cheap IR alternative to FLIRC)

Same brand-agnostic result as FLIRC (any IR remote) but with a ~$2 IR receiver
(e.g. TSOP38238) on the Pi's GPIO instead of a USB dongle - at the cost of some
kernel config.

```bash
# 1. Enable the GPIO IR overlay (receiver on GPIO17 here) in /boot/firmware/config.txt:
#    dtoverlay=gpio-ir,gpio_pin=17
sudo apt install ir-keytable
# 2. Find the scancodes your remote sends:
sudo ir-keytable -t          # press buttons, note the scancodes
# 3. Write a keymap mapping those scancodes to the keys the kiosk needs:
#    /etc/rc_keymaps/openflight.toml
#    [[protocols]]
#    name = "openflight"
#    protocol = "nec"          # whatever -t reported
#    [protocols.scancodes]
#    0x40bf01 = "KEY_UP"
#    0x40bf02 = "KEY_DOWN"
#    0x40bf03 = "KEY_LEFT"
#    0x40bf04 = "KEY_RIGHT"
#    0x40bf05 = "KEY_ENTER"   # OK
#    0x40bf06 = "KEY_ESC"     # Back
sudo ir-keytable -w /etc/rc_keymaps/openflight.toml
```

`ir-keytable` injects the mapped `KEY_*` events straight into the input layer -
no `ydotool` needed, and the kiosk receives arrows/Enter/Esc directly.

## Path 5 - Bluetooth HID remote / air-mouse (no line-of-sight)

Many cheap "Android TV" remotes and air-mice are Bluetooth HID keyboards. Pair
once and they present arrows/Enter to the Pi with no bridge at all:

```bash
bluetoothctl
# power on / agent on / scan on / pair <MAC> / trust <MAC> / connect <MAC>
```

Then they behave exactly like a USB keyboard - same as Path 2/4 from the UI's
point of view.

## Native smart-TV browser (zero setup, brand-native)

If you load the kiosk in the **TV's own browser** (Samsung Tizen, LG webOS,
Android TV) rather than on the Pi over HDMI, the TV's remote drives the UI
directly: those browsers map the D-pad to JS arrow keys and OK to Enter, and the
app auto-detects Tizen/webOS to turn on TV mode. Nothing to install.

## Choosing a path

| Situation | Use |
|-----------|-----|
| TV on **HDMI**, want to use the TV's own remote | **CEC** (Path 1) |
| TV/monitor on **DisplayPort** | **FLIRC** (Path 2) |
| Want one dedicated remote, brand-independent | **FLIRC** (Path 2) |
| CEC missing/disabled on the panel | **FLIRC** (Path 2) |

You can run both at once (CEC + FLIRC) - they both just produce key events.

## Troubleshooting

- **Nothing moves:** confirm the kiosk URL has `?tv=1` (spatial nav is off
  otherwise). Press an arrow with a USB keyboard to confirm the web side works.
- **CEC scan finds nothing:** enable CEC on the TV (table above); some TVs only
  pass CEC on specific HDMI ports.
- **`ydotool` does nothing:** ensure `ydotoold` is running and the
  `YDOTOOL_SOCKET` in the service unit matches it; the user needs uinput access.
- **Wrong buttons:** re-run `flirc_setup.sh`, or check `flirc_util settings`.
- **DisplayPort + expecting CEC:** not possible - use FLIRC.

## Verifying on a device

These paths depend on hardware that CI can't exercise. Step-by-step manual test
plans - what you need, what success looks like, and how to record a failure -
live in [test-plans/](test-plans/) (CEC, FLIRC, GPIO-IR, Bluetooth, the phone
web-remote, spatial navigation, screen readers, the no-camera visualizer, TV
scaling, and the camera stream).
