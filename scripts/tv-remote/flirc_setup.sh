#!/usr/bin/env bash
# Program a FLIRC USB receiver for the OpenFlight TV kiosk.
#
# FLIRC is a brand-agnostic USB-IR dongle: it learns ANY infrared remote
# (a TV remote, a cheap universal remote, a media remote) and presents to the
# Pi as an ordinary USB keyboard. Use this when:
#   - the TV is connected by DisplayPort (no HDMI-CEC), or
#   - you want a single dedicated remote independent of the TV brand, or
#   - HDMI-CEC is unavailable/disabled on the panel.
#
# It maps six buttons to exactly the keys the kiosk needs:
#   D-pad Up/Down/Left/Right -> arrow keys (spatial navigation)
#   OK/Select                -> enter      (activates the focused control)
#   Back/Exit                -> escape     (closes overlays/dialogs)
#
# Requires the FLIRC CLI:  sudo apt install flirc   (or the official .deb)
# Run it, then press the requested remote button when prompted for each line.
#
# See docs/tv-remote-control.md for the full setup.
set -euo pipefail

if ! command -v flirc_util >/dev/null 2>&1; then
    echo "flirc_util not found. Install the FLIRC software first:" >&2
    echo "  https://flirc.tv/pages/download  (or: sudo apt install flirc)" >&2
    exit 1
fi

echo "FLIRC detected:"
flirc_util version || true
echo

# key name as flirc_util understands it : human prompt
mappings=(
    "up:D-pad UP"
    "down:D-pad DOWN"
    "left:D-pad LEFT"
    "right:D-pad RIGHT"
    "enter:OK / SELECT"
    "escape:BACK / EXIT"
)

echo "You will be asked to press six remote buttons. Aim the remote at the FLIRC."
echo

for entry in "${mappings[@]}"; do
    key="${entry%%:*}"
    label="${entry#*:}"
    echo "--> Press your remote's [$label] button now (maps to '$key')..."
    flirc_util record "$key"
    echo
done

echo "Done. Verify the mapping any time with:  flirc_util settings"
echo "Test it: focus the kiosk window and press the remote D-pad — focus should move."
