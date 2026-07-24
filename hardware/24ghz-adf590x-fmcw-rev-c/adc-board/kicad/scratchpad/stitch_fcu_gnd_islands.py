from __future__ import annotations

import sys
import uuid
from pathlib import Path


GND_STITCHES = [
    (20.0, 56.0),
    (20.0, 50.0),
    (20.0, 44.0),
    (20.0, 38.0),
    (24.0, 33.3),
    (24.0, 31.3),
    (23.5, 29.3),
    (30.0, 30.0),
    (28.52, 25.0),
]


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def via(at: tuple[float, float]) -> str:
    return (
        "\t(via\n"
        f"\t\t(at {fmt(at[0])} {fmt(at[1])})\n"
        "\t\t(size 0.5)\n"
        "\t\t(drill 0.3)\n"
        '\t\t(layers "F.Cu" "B.Cu")\n'
        '\t\t(net "GND")\n'
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
        print("usage: stitch_fcu_gnd_islands.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    routes = [via(point) for point in GND_STITCHES]
    board.write_text(insert_routes(board.read_text(), routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
