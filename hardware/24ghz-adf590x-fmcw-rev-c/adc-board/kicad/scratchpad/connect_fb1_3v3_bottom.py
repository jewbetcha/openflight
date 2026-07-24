from __future__ import annotations

import sys
import uuid
from pathlib import Path


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(
    start: tuple[float, float],
    end: tuple[float, float],
    layer: str,
    width: float = 0.25,
) -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        f"\t\t(width {fmt(width)})\n"
        f'\t\t(layer "{layer}")\n'
        '\t\t(net "+3V3")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def via(at: tuple[float, float]) -> str:
    return (
        "\t(via\n"
        f"\t\t(at {fmt(at[0])} {fmt(at[1])})\n"
        "\t\t(size 0.5)\n"
        "\t\t(drill 0.3)\n"
        '\t\t(layers "F.Cu" "B.Cu")\n'
        '\t\t(net "+3V3")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: connect_fb1_3v3_bottom.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    stitch = (21.0, 23.2)
    routes = [
        via(stitch),
        segment((21.0, 22.0), stitch, "F.Cu", width=0.25),
        segment(stitch, (25.0, 23.2), "B.Cu", width=0.25),
        segment((25.0, 23.2), (30.52, 25.0), "B.Cu", width=0.25),
    ]
    board.write_text(insert_routes(board.read_text(), routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
