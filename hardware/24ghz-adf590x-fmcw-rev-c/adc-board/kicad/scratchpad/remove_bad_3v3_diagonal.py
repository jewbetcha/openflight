from __future__ import annotations

import sys
from pathlib import Path

from inspect_routes import SEGMENT_RE


BAD_SEGMENT_UUID = "fb54d5f1-1c5a-4a58-a350-3b067b21924c"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: remove_bad_3v3_diagonal.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    removed = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(8) == BAD_SEGMENT_UUID:
            text = text.replace(match.group(0), "")
            removed += 1
    if removed != 1:
        raise RuntimeError(f"expected to remove one +3V3 diagonal, removed {removed}")
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
