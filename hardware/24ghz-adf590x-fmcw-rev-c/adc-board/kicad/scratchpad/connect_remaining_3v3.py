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
    width: float = 0.2,
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


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: connect_remaining_3v3.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    routes = [
        segment((23.49, 22.0), (29.48, 25.0), "F.Cu"),
        segment((45.72, 27.32), (42.0, 27.32), "B.Cu"),
        segment((42.0, 27.32), (37.0, 30.5), "B.Cu"),
    ]
    board.write_text(insert_routes(board.read_text(), routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
