from __future__ import annotations

import sys
import uuid
from pathlib import Path


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


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: connect_digital_testpoints.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    routes = [
        via("I2S_BCLK", (37.5, 10.0)),
        segment("I2S_BCLK", (37.5, 10.0), (47.0, 10.0), "In2.Cu"),
        segment("I2S_BCLK", (47.0, 10.0), (47.0, 19.7), "In2.Cu"),
        via("I2S_LRCLK", (40.1, 10.0)),
        segment("I2S_LRCLK", (40.1, 10.0), (43.6, 10.0), "In1.Cu"),
        segment("I2S_LRCLK", (43.6, 10.0), (43.6, 26.2), "In1.Cu"),
        via("I2S_DIN", (42.7, 10.0)),
        segment("I2S_DIN", (42.7, 10.0), (52.8, 10.0), "B.Cu"),
        segment("I2S_DIN", (52.8, 10.0), (52.8, 31.3), "B.Cu"),
        via("ADC_SHDNZ", (42.7, 13.0)),
        segment("ADC_SHDNZ", (42.7, 13.0), (51.0, 13.0), "In2.Cu"),
        segment("ADC_SHDNZ", (51.0, 13.0), (51.0, 24.78), "In2.Cu"),
    ]
    board.write_text(insert_routes(board.read_text(), routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
