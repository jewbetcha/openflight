from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE, VIA_RE


BB_ROUTES = {
    "BB1_P": {"j1": (3.05, 23.65), "entry": (1.2, 23.65), "exit": (10.8, 37.0), "filter": (11.49, 37.0)},
    "BB1_N": {"j1": (6.95, 23.65), "entry": (8.7, 23.65), "exit": (10.8, 39.0), "filter": (11.49, 39.0)},
    "BB2_P": {"j1": (3.05, 26.19), "entry": (1.2, 26.19), "exit": (10.8, 43.0), "filter": (11.49, 43.0)},
    "BB2_N": {"j1": (6.95, 26.19), "entry": (8.7, 26.19), "exit": (10.8, 45.0), "filter": (11.49, 45.0)},
    "BB3_P": {"j1": (3.05, 28.73), "entry": (1.2, 28.73), "exit": (10.8, 49.0), "filter": (11.49, 49.0)},
    "BB3_N": {"j1": (6.95, 28.73), "entry": (8.7, 28.73), "exit": (10.8, 51.0), "filter": (11.49, 51.0)},
    "BB4_P": {"j1": (3.05, 31.27), "entry": (1.2, 31.27), "exit": (10.8, 55.0), "filter": (11.49, 55.0)},
    "BB4_N": {"j1": (6.95, 31.27), "entry": (8.7, 31.27), "exit": (10.8, 57.0), "filter": (11.49, 57.0)},
}


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(net: str, start: tuple[float, float], end: tuple[float, float], layer: str = "F.Cu") -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        "\t\t(width 0.2)\n"
        f'\t\t(layer "{layer}")\n'
        f'\t\t(net "{net}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def via(net: str, at: tuple[float, float]) -> str:
    return (
        "\t(via\n"
        f"\t\t(at {fmt(at[0])} {fmt(at[1])})\n"
        "\t\t(size 0.5)\n"
        "\t\t(drill 0.3)\n"
        '\t\t(layers "F.Cu" "B.Cu")\n'
        f'\t\t(net "{net}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def remove_old(text: str) -> str:
    removed_segments = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) in BB_ROUTES:
            text = text.replace(match.group(0), "")
            removed_segments += 1
    if removed_segments != 24:
        raise RuntimeError(f"expected to remove 24 BB segments, removed {removed_segments}")

    removed_vias = 0
    for match in list(VIA_RE.finditer(text)):
        if match.group(7) in BB_ROUTES:
            text = text.replace(match.group(0), "")
            removed_vias += 1
    if removed_vias != 0:
        raise RuntimeError(f"expected to remove 0 BB vias, removed {removed_vias}")
    return text


def build_routes() -> list[str]:
    routes: list[str] = []
    for net, route in BB_ROUTES.items():
        j1 = route["j1"]
        entry = route["entry"]
        exit_ = route["exit"]
        filt = route["filter"]
        routes.extend(
            [
                segment(net, j1, entry),
                via(net, entry),
                segment(net, entry, exit_, layer="In2.Cu"),
                via(net, exit_),
                segment(net, exit_, filt),
            ]
        )
    return routes


def insert_segments(text: str, segments: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(segments) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: reroute_bb_in2.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = remove_old(text)
    text = insert_segments(text, build_routes())
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
