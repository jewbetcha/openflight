from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE, VIA_RE


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(
    net: str,
    start: tuple[float, float],
    end: tuple[float, float],
    layer: str = "F.Cu",
    width: float = 0.2,
) -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        f"\t\t(width {fmt(width)})\n"
        f'\t\t(layer "{layer}")\n'
        f'\t\t(net "{net}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def via(net: str, at: tuple[float, float], size: float = 0.5, drill: float = 0.3) -> str:
    return (
        "\t(via\n"
        f"\t\t(at {fmt(at[0])} {fmt(at[1])})\n"
        f"\t\t(size {fmt(size)})\n"
        f"\t\t(drill {fmt(drill)})\n"
        '\t\t(layers "F.Cu" "B.Cu")\n'
        f'\t\t(net "{net}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def remove_net(text: str, net: str, expected_segments: int, expected_vias: int) -> str:
    removed_segments = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) == net:
            text = text.replace(match.group(0), "")
            removed_segments += 1
    if removed_segments != expected_segments:
        raise RuntimeError(f"expected {expected_segments} {net} segments, removed {removed_segments}")

    removed_vias = 0
    for match in list(VIA_RE.finditer(text)):
        if match.group(7) == net:
            text = text.replace(match.group(0), "")
            removed_vias += 1
    if removed_vias != expected_vias:
        raise RuntimeError(f"expected {expected_vias} {net} vias, removed {removed_vias}")
    return text


def build_routes() -> list[str]:
    routes: list[str] = []

    routes.extend(
        [
            segment("I2C_SCL", (31.7, 29.25), (32.4, 28.8), width=0.15),
            via("I2C_SCL", (32.4, 28.8)),
            segment("I2C_SCL", (32.4, 28.8), (34.5, 29.99), width=0.15),
            segment("I2C_SCL", (32.4, 28.8), (28.5, 28.8), layer="In1.Cu"),
            segment("I2C_SCL", (28.5, 28.8), (28.5, 13.0), layer="In1.Cu"),
            segment("I2C_SCL", (28.5, 13.0), (37.5, 13.0), layer="In1.Cu"),
            via("I2C_SCL", (37.5, 13.0)),
            segment("I2C_SCL", (37.5, 13.0), (37.5, 12.08), layer="In1.Cu"),
            segment("I2C_SCL", (37.5, 12.08), (45.72, 12.08), layer="In1.Cu"),
            segment("I2C_SDA", (31.7, 28.75), (32.15, 27.55), width=0.15),
            segment("I2C_SDA", (32.15, 27.55), (34.5, 27.99), width=0.15),
            segment("I2C_SDA", (34.5, 27.99), (35.3, 27.4), width=0.15),
            via("I2C_SDA", (35.3, 27.4)),
            segment("I2C_SDA", (35.3, 27.4), (31.4, 27.4), layer="In2.Cu"),
            segment("I2C_SDA", (31.4, 27.4), (31.4, 28.4), layer="In2.Cu"),
            segment("I2C_SDA", (31.4, 28.4), (28.0, 28.4), layer="In2.Cu"),
            segment("I2C_SDA", (28.0, 28.4), (28.0, 14.0), layer="In2.Cu"),
            segment("I2C_SDA", (28.0, 14.0), (40.1, 14.0), layer="In2.Cu"),
            segment("I2C_SDA", (40.1, 14.0), (40.1, 13.0), layer="In2.Cu"),
            via("I2C_SDA", (40.1, 13.0)),
            segment("I2C_SDA", (40.1, 13.0), (40.1, 9.54), layer="In2.Cu"),
            segment("I2C_SDA", (40.1, 9.54), (45.72, 9.54), layer="In2.Cu"),
            segment("I2S_DIN", (30.25, 28.3), (30.25, 26.8)),
            segment("I2S_DIN", (30.25, 26.8), (30.0, 25.7)),
            via("I2S_DIN", (30.0, 25.7)),
            segment("I2S_DIN", (30.0, 25.7), (36.0, 25.7), layer="B.Cu"),
            segment("I2S_DIN", (36.0, 25.7), (36.0, 31.3), layer="B.Cu"),
            segment("I2S_DIN", (36.0, 31.3), (52.8, 31.3), layer="B.Cu"),
            segment("I2S_DIN", (52.8, 31.3), (52.8, 52.72), layer="B.Cu"),
            segment("I2S_DIN", (52.8, 52.72), (48.26, 52.72), layer="B.Cu"),
        ]
    )

    return routes


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fix_i2c_sda_and_din.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = remove_net(text, "I2C_SCL", expected_segments=7, expected_vias=2)
    text = remove_net(text, "I2C_SDA", expected_segments=8, expected_vias=2)
    text = remove_net(text, "I2S_DIN", expected_segments=7, expected_vias=1)
    board.write_text(insert_routes(text, build_routes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
