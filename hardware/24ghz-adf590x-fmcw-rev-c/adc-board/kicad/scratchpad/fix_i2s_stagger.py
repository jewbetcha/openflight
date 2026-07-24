from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE, VIA_RE


NETS = {"I2S_LRCLK", "I2S_BCLK", "I2S_DIN"}


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
        if match.group(7) in NETS:
            text = text.replace(match.group(0), "")
            removed_segments += 1
    if removed_segments != 14:
        raise RuntimeError(f"expected to remove 14 I2S segments, removed {removed_segments}")

    removed_vias = 0
    for match in list(VIA_RE.finditer(text)):
        if match.group(7) in NETS:
            text = text.replace(match.group(0), "")
            removed_vias += 1
    if removed_vias != 3:
        raise RuntimeError(f"expected to remove 3 I2S vias, removed {removed_vias}")
    return text


def build_routes() -> list[str]:
    return [
        segment("I2S_LRCLK", (29.25, 28.3), (28.7, 27.4)),
        segment("I2S_LRCLK", (28.7, 27.4), (28.7, 26.2)),
        via("I2S_LRCLK", (28.7, 26.2)),
        segment("I2S_LRCLK", (28.7, 26.2), (28.7, 25.6), layer="In2.Cu"),
        segment("I2S_LRCLK", (28.7, 25.6), (43.6, 25.6), layer="In2.Cu"),
        segment("I2S_LRCLK", (43.6, 25.6), (43.6, 50.18), layer="In2.Cu"),
        segment("I2S_LRCLK", (43.6, 50.18), (45.72, 50.18), layer="In2.Cu"),
        segment("I2S_BCLK", (29.75, 28.3), (29.75, 26.2)),
        via("I2S_BCLK", (29.75, 26.2)),
        segment("I2S_BCLK", (29.75, 26.2), (29.75, 26.8), layer="In2.Cu"),
        segment("I2S_BCLK", (29.75, 26.8), (50.4, 26.8), layer="In2.Cu"),
        segment("I2S_BCLK", (50.4, 26.8), (50.4, 19.7), layer="In2.Cu"),
        segment("I2S_BCLK", (50.4, 19.7), (48.26, 19.7), layer="In2.Cu"),
        segment("I2S_DIN", (30.25, 28.3), (31.4, 27.4)),
        segment("I2S_DIN", (31.4, 27.4), (31.4, 26.2)),
        via("I2S_DIN", (31.4, 26.2)),
        segment("I2S_DIN", (31.4, 26.2), (31.4, 27.4), layer="In2.Cu"),
        segment("I2S_DIN", (31.4, 27.4), (52.8, 27.4), layer="In2.Cu"),
        segment("I2S_DIN", (52.8, 27.4), (52.8, 52.72), layer="In2.Cu"),
        segment("I2S_DIN", (52.8, 52.72), (48.26, 52.72), layer="In2.Cu"),
    ]


def insert_segments(text: str, segments: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(segments) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fix_i2s_stagger.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = remove_old(text)
    text = insert_segments(text, build_routes())
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
