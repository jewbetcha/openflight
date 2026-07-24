from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


REMOVE = {
    ((8.0, 54.0), (3.05, 54.0), "B.Cu"),
    ((3.05, 63.5), (54.2, 63.5), "B.Cu"),
    ((3.05, 54.0), (3.05, 21.11), "B.Cu"),
    ((3.05, 21.11), (3.05, 63.5), "B.Cu"),
}


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(start: tuple[float, float], end: tuple[float, float], width: float) -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        f"\t\t(width {fmt(width)})\n"
        '\t\t(layer "B.Cu")\n'
        '\t\t(net "+5V")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def remove_old(text: str) -> str:
    removed = 0
    for match in list(SEGMENT_RE.finditer(text)):
        sx, sy, ex, ey, _width, layer, net, _uuid = match.groups()
        if net != "+5V":
            continue
        start = (float(sx), float(sy))
        end = (float(ex), float(ey))
        key = (start, end, layer)
        reverse_key = (end, start, layer)
        if key in REMOVE or reverse_key in REMOVE:
            text = text.replace(match.group(0), "")
            removed += 1
    if removed != len(REMOVE):
        raise RuntimeError(f"expected {len(REMOVE)} +5V segments, removed {removed}")
    return text


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fix_5v_mount_hole_clearance.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    routes = [
        segment((3.05, 21.11), (5.8, 21.11), 0.4),
        segment((5.8, 21.11), (5.8, 63.5), 0.4),
        segment((5.8, 63.5), (54.2, 63.5), 0.4),
        segment((8.0, 54.0), (5.8, 54.0), 0.2),
    ]
    board.write_text(insert_routes(remove_old(board.read_text()), routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
