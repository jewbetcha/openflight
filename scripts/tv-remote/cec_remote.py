#!/usr/bin/env python3
"""HDMI-CEC -> keyboard bridge for the OpenFlight TV kiosk.

When the Raspberry Pi drives a TV over HDMI, the TV's own remote (and most
universal remotes programmed to that TV) sends D-pad + OK presses *down the
HDMI cable* via HDMI-CEC. This daemon listens for those CEC button events and
injects the matching key into the Wayland kiosk with `ydotool`, so the web UI
sees plain Arrow keys + Enter (handled by ui/src/state/useSpatialNavigation.ts).

Every major brand implements the same HDMI-CEC spec under a marketing name
(Samsung Anynet+, LG SimpLink, Sony Bravia Sync, Philips EasyLink, Panasonic
VIERA Link, ...). Enable "CEC" on the TV once and the remote just works.

Requirements (Raspberry Pi OS Bookworm):
    sudo apt install cec-utils python3-cec ydotool
    # ydotool needs its daemon + uinput access:
    sudo systemctl enable --now ydotool    # or run `ydotoold` yourself

NOTE: HDMI-CEC is an HDMI feature only. A TV connected by DisplayPort has no
CEC channel — use the FLIRC USB receiver instead (see docs/tv-remote-control.md).

This runs as a long-lived system service (see openflight-cec.service); it uses
the system `cec` bindings (python3-cec), not the project's uv venv.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time

log = logging.getLogger("openflight-cec")

try:
    import cec  # python3-cec (libcec bindings)
except ImportError:  # pragma: no cover - hardware/runtime dependency
    sys.stderr.write(
        "python3-cec not found. Install it with: sudo apt install python3-cec cec-utils\n"
    )
    raise SystemExit(1)

# CEC user-control codes (HDMI-CEC spec, CEC_USER_CONTROL_CODE_*) -> Linux
# input event key names understood by `ydotool key` via the codes below.
# ydotool uses Linux input-event-codes (KEY_*). We map to those numbers.
KEY_UP = 103
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_DOWN = 108
KEY_ENTER = 28
KEY_ESC = 1

# libcec keypress codes (cec.CEC_USER_CONTROL_CODE_*) we care about.
CEC_TO_KEY = {
    0x01: KEY_UP,        # UP
    0x02: KEY_DOWN,      # DOWN
    0x03: KEY_LEFT,      # LEFT
    0x04: KEY_RIGHT,     # RIGHT
    0x00: KEY_ENTER,     # SELECT / OK
    0x0D: KEY_ESC,       # EXIT
    0x48: KEY_ESC,       # ROOT MENU / Back on some remotes
}

# Debounce repeated keypress callbacks libcec may emit for one physical press.
_REPEAT_GUARD_S = 0.06
_last_emit: dict[int, float] = {}


def _press(keycode: int) -> None:
    """Emit a single key press+release via ydotool."""
    now = time.monotonic()
    if now - _last_emit.get(keycode, 0.0) < _REPEAT_GUARD_S:
        return
    _last_emit[keycode] = now
    # `ydotool key <code>:1 <code>:0` => press then release.
    result = subprocess.run(
        ["ydotool", "key", f"{keycode}:1", f"{keycode}:0"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        # A silent ydotool failure (dead ydotoold, wrong YDOTOOL_SOCKET, uinput
        # perms) looks identical to "remote not working" — surface it.
        log.warning(
            "ydotool exit %s for key %s — check ydotoold/YDOTOOL_SOCKET/uinput perms: %s",
            result.returncode,
            keycode,
            result.stderr.decode(errors="replace").strip(),
        )


def _on_keypress(*args: int) -> None:
    # Logged at DEBUG so the real callback signature can be confirmed on the
    # device (`journalctl -u openflight-cec -f` after setting level to DEBUG).
    log.debug("CEC keypress callback args=%r", args)
    # python-cec invokes the EVENT_KEYPRESS callback with the keypress payload.
    # Different libcec binding versions pass either (keycode, duration) or
    # (event, keycode, duration); the last two are always (keycode, duration),
    # so read from the tail to stay compatible with both. VERIFY ON DEVICE with
    # `journalctl -u openflight-cec -f` and adjust if your binding differs.
    if len(args) < 2:
        return
    code, duration = args[-2], args[-1]
    # libcec fires on both press (duration==0) and release (duration>0). Act on
    # the press edge only.
    if duration:
        return
    keycode = CEC_TO_KEY.get(code)
    if keycode is not None:
        _press(keycode)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if shutil.which("ydotool") is None:
        log.error("ydotool not found. Install it: sudo apt install ydotool")
        return 1

    # Initialise libcec as a passive device so the TV forwards remote keypresses
    # to us without us becoming the active source. Init fails when there is no
    # CEC adapter — the exact DisplayPort-only case the FLIRC path exists for.
    try:
        cec.init()
        cec.add_callback(_on_keypress, cec.EVENT_KEYPRESS)
    except Exception as exc:  # libcec surfaces adapter errors as various types
        log.error(
            "Could not initialise HDMI-CEC (%s). If this Pi drives the display "
            "over DisplayPort there is no CEC bus — use the FLIRC USB receiver "
            "instead (see docs/tv-remote-control.md).",
            exc,
        )
        return 1

    log.info("OpenFlight CEC remote bridge running. Press TV remote keys.")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
