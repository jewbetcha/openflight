from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


REMOVE = {
    ((32.4, 28.8), (28.5, 28.8), "In1.Cu"),
    ((28.5, 28.8), (28.5, 13.0), "In1.Cu"),
    ((28.5, 13.0), (37.5, 13.0), "In1.Cu"),
}


ADD = [
    ((32.4, 28.8), (27.0, 28.8), "In1.Cu"),
    ((27.0, 28.8), (27.0, 13.0), "In1.Cu"),
    ((27.0, 13.0), (37.5, 13.0), "In1.Cu"),
]


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def same_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    expected: tuple[tuple[float, float], tuple[float, float], str],
    layer: str,
) -> bool:
    a, b, expected_layer = expected
    return layer == expected_layer and ((start == a and end == b) or (start == b and end == a))


def segment(start: tuple[float, float], end: tuple[float, float], layer: str) -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        "\t\t(width 0.2)\n"
        f'\t\t(layer "{layer}")\n'
        '\t\t(net "I2C_SCL")\n'
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
        print("usage: move_i2c_scl_left_for_c7_gnd.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    removed = 0
    for match in list(SEGMENT_RE.finditer(text)):
        sx, sy, ex, ey, _width, layer, net, _uuid = match.groups()
        if net != "I2C_SCL":
            continue
        start = (float(sx), float(sy))
        end = (float(ex), float(ey))
        if any(same_segment(start, end, expected, layer) for expected in REMOVE):
            text = text.replace(match.group(0), "")
            removed += 1
    if removed != len(REMOVE):
        raise RuntimeError(f"expected to remove {len(REMOVE)} I2C_SCL segments, removed {removed}")

    routes = [segment(start, end, layer) for start, end, layer in ADD]
    board.write_text(insert_routes(text, routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
