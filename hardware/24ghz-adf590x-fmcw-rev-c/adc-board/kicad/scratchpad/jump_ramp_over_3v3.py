from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE, VIA_RE


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(net: str, start: tuple[float, float], end: tuple[float, float], layer: str) -> str:
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
        if match.group(7) == "RAMP_SYNC":
            text = text.replace(match.group(0), "")
            removed_segments += 1
    if removed_segments != 7:
        raise RuntimeError(f"expected 7 RAMP_SYNC segments, removed {removed_segments}")

    removed_vias = 0
    for match in list(VIA_RE.finditer(text)):
        if match.group(7) == "RAMP_SYNC":
            text = text.replace(match.group(0), "")
            removed_vias += 1
    if removed_vias != 2:
        raise RuntimeError(f"expected 2 RAMP_SYNC vias, removed {removed_vias}")
    return text


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: jump_ramp_over_3v3.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    routes = [
        via("RAMP_SYNC", (6.95, 38.89)),
        segment("RAMP_SYNC", (6.95, 38.89), (10.0, 38.89), "B.Cu"),
        segment("RAMP_SYNC", (10.0, 38.89), (10.0, 18.5), "B.Cu"),
        segment("RAMP_SYNC", (10.0, 18.5), (29.0, 18.5), "B.Cu"),
        via("RAMP_SYNC", (29.0, 18.5)),
        segment("RAMP_SYNC", (29.0, 18.5), (32.0, 18.5), "In1.Cu"),
        via("RAMP_SYNC", (32.0, 18.5)),
        segment("RAMP_SYNC", (32.0, 18.5), (37.5, 18.5), "B.Cu"),
        segment("RAMP_SYNC", (37.5, 18.5), (37.5, 16.0), "B.Cu"),
        via("RAMP_SYNC", (37.5, 16.0)),
        segment("RAMP_SYNC", (37.5, 18.5), (50.0, 18.5), "B.Cu"),
        segment("RAMP_SYNC", (50.0, 18.5), (50.0, 27.32), "B.Cu"),
        segment("RAMP_SYNC", (50.0, 27.32), (48.26, 27.32), "B.Cu"),
    ]
    board.write_text(insert_routes(remove_old(board.read_text()), routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
