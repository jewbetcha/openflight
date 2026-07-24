from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE, VIA_RE


NET = "ADC_SHDNZ"


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(start: tuple[float, float], end: tuple[float, float], layer: str = "F.Cu") -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        "\t\t(width 0.2)\n"
        f'\t\t(layer "{layer}")\n'
        f'\t\t(net "{NET}")\n'
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
        f'\t\t(net "{NET}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def remove_old(text: str) -> str:
    removed_segments = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) == NET:
            text = text.replace(match.group(0), "")
            removed_segments += 1
    if removed_segments != 4:
        raise RuntimeError(f"expected to remove 4 ADC_SHDNZ segments, removed {removed_segments}")

    removed_vias = 0
    for match in list(VIA_RE.finditer(text)):
        if match.group(7) == NET:
            text = text.replace(match.group(0), "")
            removed_vias += 1
    if removed_vias != 1:
        raise RuntimeError(f"expected to remove 1 ADC_SHDNZ via, removed {removed_vias}")
    return text


def build_routes() -> list[str]:
    return [
        segment((31.7, 30.75), (33.2, 30.75)),
        via((33.2, 30.75)),
        segment((33.2, 30.75), (33.2, 28.6), layer="In2.Cu"),
        segment((33.2, 28.6), (51.0, 28.6), layer="In2.Cu"),
        segment((51.0, 28.6), (51.0, 24.78), layer="In2.Cu"),
        segment((51.0, 24.78), (48.26, 24.78), layer="In2.Cu"),
    ]


def insert_segments(text: str, segments: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(segments) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fix_adc_shdnz_lane.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = remove_old(text)
    text = insert_segments(text, build_routes())
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
