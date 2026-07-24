from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


BB_ROUTES = {
    "BB1_P": {"j1": (3.05, 23.65), "bus_x": 1.2, "filter": (11.49, 37.0)},
    "BB1_N": {"j1": (6.95, 23.65), "bus_x": 12.0, "filter": (11.49, 39.0)},
    "BB2_P": {"j1": (3.05, 26.19), "bus_x": 1.2, "filter": (11.49, 43.0)},
    "BB2_N": {"j1": (6.95, 26.19), "bus_x": 12.0, "filter": (11.49, 45.0)},
    "BB3_P": {"j1": (3.05, 28.73), "bus_x": 1.2, "filter": (11.49, 49.0)},
    "BB3_N": {"j1": (6.95, 28.73), "bus_x": 12.0, "filter": (11.49, 51.0)},
    "BB4_P": {"j1": (3.05, 31.27), "bus_x": 1.2, "filter": (11.49, 55.0)},
    "BB4_N": {"j1": (6.95, 31.27), "bus_x": 12.0, "filter": (11.49, 57.0)},
}


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(net: str, start: tuple[float, float], end: tuple[float, float], width: float = 0.2) -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        f"\t\t(width {fmt(width)})\n"
        '\t\t(layer "F.Cu")\n'
        f'\t\t(net "{net}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def remove_old_bb(text: str) -> str:
    removed = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) in BB_ROUTES:
            text = text.replace(match.group(0), "")
            removed += 1

    if removed not in {24, 28}:
        raise RuntimeError(f"expected to remove 24 or 28 BBx segments, removed {removed}")
    return text


def build_segments() -> list[str]:
    segments: list[str] = []
    for net, route in BB_ROUTES.items():
        j1 = route["j1"]
        bus_x = route["bus_x"]
        filt = route["filter"]
        bus_at_j1 = (bus_x, j1[1])
        bus_at_filter = (bus_x, filt[1])
        segments.extend(
            [
                segment(net, j1, bus_at_j1),
                segment(net, bus_at_j1, bus_at_filter),
                segment(net, bus_at_filter, filt),
            ]
        )
    return segments


def insert_segments(text: str, segments: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(segments) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: reroute_bb_escapes.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = remove_old_bb(text)
    text = insert_segments(text, build_segments())
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
