from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


BB_NETS = {
    "BB1_P",
    "BB1_N",
    "BB2_P",
    "BB2_N",
    "BB3_P",
    "BB3_N",
    "BB4_P",
    "BB4_N",
}


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(
    net: str,
    start: tuple[float, float],
    end: tuple[float, float],
    layer: str = "F.Cu",
) -> str:
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
    counts = {net: 0 for net in BB_NETS}
    for match in list(SEGMENT_RE.finditer(text)):
        net = match.group(7)
        if net in BB_NETS:
            text = text.replace(match.group(0), "")
            counts[net] += 1
    expected = {net: 3 for net in BB_NETS}
    if counts != expected:
        raise RuntimeError(f"unexpected BB segment counts: {counts}")
    return text


def build_routes() -> list[str]:
    specs = [
        ("BB1_P", (3.05, 23.65), (4.2, 23.65), (10.6, 37.0), (11.49, 37.0)),
        ("BB1_N", (6.95, 23.65), (8.4, 23.65), (10.6, 39.0), (11.49, 39.0)),
        ("BB2_P", (3.05, 26.19), (4.2, 26.19), (10.6, 43.0), (11.49, 43.0)),
        ("BB2_N", (6.95, 26.19), (8.4, 26.19), (10.6, 45.0), (11.49, 45.0)),
        ("BB3_P", (3.05, 28.73), (4.2, 28.73), (10.6, 49.0), (11.49, 49.0)),
        ("BB3_N", (6.95, 28.73), (8.4, 28.73), (10.6, 51.0), (11.49, 51.0)),
        ("BB4_P", (3.05, 31.27), (4.2, 31.27), (10.6, 55.0), (11.49, 55.0)),
        ("BB4_N", (6.95, 31.27), (8.4, 31.27), (10.6, 57.0), (11.49, 57.0)),
    ]

    routes: list[str] = []
    for net, source_pad, source_via, target_via, target_pad in specs:
        routes.append(segment(net, source_pad, source_via))
        routes.append(via(net, source_via))
        routes.append(segment(net, source_via, target_via, layer="In2.Cu"))
        routes.append(via(net, target_via))
        routes.append(segment(net, target_via, target_pad))
    return routes


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: reroute_bb_bundle_in2.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    board.write_text(insert_routes(remove_old(board.read_text()), build_routes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
