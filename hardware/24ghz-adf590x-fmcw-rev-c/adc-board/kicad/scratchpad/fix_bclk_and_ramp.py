from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(
    net: str,
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
        f'\t\t(net "{net}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def remove_segments(text: str, net: str, expected_segments: int) -> str:
    removed = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) == net:
            text = text.replace(match.group(0), "")
            removed += 1
    if removed != expected_segments:
        raise RuntimeError(f"expected {expected_segments} {net} segments, removed {removed}")
    return text


def build_routes() -> list[str]:
    return [
        segment("I2S_BCLK", (29.75, 28.3), (29.75, 26.8), "F.Cu"),
        segment("I2S_BCLK", (29.75, 26.8), (29.75, 26.2), "In2.Cu"),
        segment("I2S_BCLK", (29.75, 26.2), (47.0, 26.2), "In2.Cu"),
        segment("I2S_BCLK", (47.0, 26.2), (47.0, 19.7), "In2.Cu"),
        segment("I2S_BCLK", (47.0, 19.7), (48.26, 19.7), "In2.Cu"),
        segment("RAMP_SYNC", (6.95, 38.89), (20.0, 38.89), "In1.Cu"),
        segment("RAMP_SYNC", (20.0, 38.89), (20.0, 18.5), "In1.Cu"),
        segment("RAMP_SYNC", (20.0, 18.5), (37.5, 18.5), "In1.Cu"),
        segment("RAMP_SYNC", (37.5, 18.5), (37.5, 16.0), "In1.Cu"),
        segment("RAMP_SYNC", (37.5, 18.5), (48.26, 27.32), "In1.Cu"),
    ]


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fix_bclk_and_ramp.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = remove_segments(text, "I2S_BCLK", expected_segments=5)
    text = remove_segments(text, "RAMP_SYNC", expected_segments=6)
    board.write_text(insert_routes(text, build_routes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
