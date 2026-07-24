from __future__ import annotations

import sys
from pathlib import Path

from inspect_routes import VIA_RE


REMOVE_UUIDS = {
    "0f2250f1-f50e-4d61-bae2-3cf8237a2bb8",
    "25cb6542-c044-41bb-9b46-01c66e235253",
    "a8d8ce60-7136-4d36-afb3-9ce0e3a0432d",
    "c1182dcd-fed3-40a1-8594-5a4f7b8e2ba5",
    "d6341193-f4f2-4d84-9a6d-e4b1326ccfd5",
}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: remove_bad_gnd_vias.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    found = {match.group(8): match.group(0) for match in VIA_RE.finditer(text)}
    missing = sorted(REMOVE_UUIDS - set(found))
    if missing:
        raise RuntimeError(f"missing expected GND via UUIDs: {missing}")

    for via_uuid in REMOVE_UUIDS:
        text = text.replace(found[via_uuid], "")
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
