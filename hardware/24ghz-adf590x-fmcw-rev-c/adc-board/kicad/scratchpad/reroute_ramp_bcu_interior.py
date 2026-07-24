from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(start: tuple[float, float], end: tuple[float, float]) -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        "\t\t(width 0.2)\n"
        '\t\t(layer "B.Cu")\n'
        '\t\t(net "RAMP_SYNC")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def remove_old(text: str) -> str:
    removed = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) == "RAMP_SYNC":
            text = text.replace(match.group(0), "")
            removed += 1
    if removed != 7:
        raise RuntimeError(f"expected 7 RAMP_SYNC segments, removed {removed}")
    return text


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: reroute_ramp_bcu_interior.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    routes = [
        segment((6.95, 38.89), (10.0, 38.89)),
        segment((10.0, 38.89), (10.0, 18.5)),
        segment((10.0, 18.5), (37.5, 18.5)),
        segment((37.5, 18.5), (37.5, 16.0)),
        segment((37.5, 18.5), (50.0, 18.5)),
        segment((50.0, 18.5), (50.0, 27.32)),
        segment((50.0, 27.32), (48.26, 27.32)),
    ]
    board.write_text(insert_routes(remove_old(board.read_text()), routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
