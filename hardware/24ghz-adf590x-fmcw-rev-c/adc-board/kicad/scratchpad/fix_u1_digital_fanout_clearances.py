from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE, VIA_RE


NETS = {
    "ADDR0",
    "ADDR1",
    "GPIO1_NC",
    "I2S_LRCLK",
    "I2S_BCLK",
    "I2S_DIN",
    "DREG",
}

EXPECTED_SEGMENTS = {
    "ADDR0": 3,
    "ADDR1": 3,
    "GPIO1_NC": 4,
    "I2S_LRCLK": 4,
    "I2S_BCLK": 5,
    "I2S_DIN": 4,
    "DREG": 4,
}

EXPECTED_VIAS = {
    "ADDR0": 2,
    "ADDR1": 2,
    "GPIO1_NC": 2,
    "I2S_LRCLK": 1,
    "I2S_BCLK": 1,
    "I2S_DIN": 1,
}


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


def remove_old(text: str) -> str:
    removed_segments = {net: 0 for net in NETS}
    for match in list(SEGMENT_RE.finditer(text)):
        net = match.group(7)
        if net in NETS:
            text = text.replace(match.group(0), "")
            removed_segments[net] += 1

    if removed_segments != EXPECTED_SEGMENTS:
        raise RuntimeError(f"unexpected segment counts: {removed_segments}")

    removed_vias = {net: 0 for net in NETS}
    for match in list(VIA_RE.finditer(text)):
        net = match.group(7)
        if net in NETS:
            text = text.replace(match.group(0), "")
            removed_vias[net] += 1

    expected_vias = {net: EXPECTED_VIAS.get(net, 0) for net in NETS}
    if removed_vias != expected_vias:
        raise RuntimeError(f"unexpected via counts: {removed_vias}")

    return text


def build_routes() -> list[str]:
    routes: list[str] = []

    routes.extend(
        [
            segment("ADDR0", (31.7, 29.75), (32.3, 29.55)),
            via("ADDR0", (32.3, 29.55)),
            segment("ADDR0", (32.3, 29.55), (31.7, 29.55), layer="B.Cu"),
            segment("ADDR0", (31.7, 29.55), (31.7, 33.01), layer="B.Cu"),
            segment("ADDR0", (31.7, 33.01), (32.8, 33.01), layer="B.Cu"),
            via("ADDR0", (32.8, 33.01)),
            segment("ADDR0", (32.8, 33.01), (34.5, 33.01)),
            segment("ADDR1", (31.7, 30.25), (32.45, 30.25)),
            via("ADDR1", (32.45, 30.25)),
            segment("ADDR1", (32.45, 30.25), (32.45, 29.4), layer="In1.Cu"),
            segment("ADDR1", (32.45, 29.4), (35.8, 29.4), layer="In1.Cu"),
            segment("ADDR1", (35.8, 29.4), (35.8, 33.01), layer="In1.Cu"),
            segment("ADDR1", (35.8, 33.01), (35.6, 33.01), layer="In1.Cu"),
            via("ADDR1", (35.6, 33.01)),
            segment("ADDR1", (35.6, 33.01), (36.5, 33.01)),
        ]
    )

    routes.extend(
        [
            segment("GPIO1_NC", (30.75, 28.3), (30.75, 27.8)),
            via("GPIO1_NC", (30.75, 27.8)),
            segment("GPIO1_NC", (30.75, 27.8), (33.75, 27.8), layer="B.Cu"),
            segment("GPIO1_NC", (33.75, 27.8), (33.75, 35.01), layer="B.Cu"),
            via("GPIO1_NC", (33.75, 35.01)),
            segment("GPIO1_NC", (33.75, 35.01), (34.5, 35.01)),
        ]
    )

    routes.extend(
        [
            segment("I2S_LRCLK", (29.25, 28.3), (29.25, 26.2)),
            via("I2S_LRCLK", (29.25, 26.2)),
            segment("I2S_LRCLK", (29.25, 26.2), (43.6, 26.2), layer="In1.Cu"),
            segment("I2S_LRCLK", (43.6, 26.2), (43.6, 50.18), layer="In1.Cu"),
            segment("I2S_LRCLK", (43.6, 50.18), (45.72, 50.18), layer="In1.Cu"),
            segment("I2S_BCLK", (29.75, 28.3), (29.75, 26.8)),
            via("I2S_BCLK", (29.75, 26.8)),
            segment("I2S_BCLK", (29.75, 26.8), (29.75, 26.2), layer="In2.Cu"),
            segment("I2S_BCLK", (29.75, 26.2), (50.4, 26.2), layer="In2.Cu"),
            segment("I2S_BCLK", (50.4, 26.2), (50.4, 19.7), layer="In2.Cu"),
            segment("I2S_BCLK", (50.4, 19.7), (48.26, 19.7), layer="In2.Cu"),
            segment("I2S_DIN", (30.25, 28.3), (30.25, 26.8)),
            segment("I2S_DIN", (30.25, 26.8), (30.0, 25.7)),
            via("I2S_DIN", (30.0, 25.7)),
            segment("I2S_DIN", (30.0, 25.7), (34.0, 25.7), layer="B.Cu"),
            segment("I2S_DIN", (34.0, 25.7), (34.0, 31.3), layer="B.Cu"),
            segment("I2S_DIN", (34.0, 31.3), (52.8, 31.3), layer="B.Cu"),
            segment("I2S_DIN", (52.8, 31.3), (52.8, 52.72), layer="B.Cu"),
            segment("I2S_DIN", (52.8, 52.72), (48.26, 52.72), layer="B.Cu"),
        ]
    )

    routes.extend(
        [
            segment("DREG", (28.75, 28.3), (27.8, 27.7)),
            segment("DREG", (27.8, 27.7), (27.8, 24.35)),
            segment("DREG", (27.8, 24.35), (37.0, 24.35)),
            segment("DREG", (34.52, 24.35), (34.52, 25.0)),
            segment("DREG", (37.0, 24.35), (37.0, 25.0)),
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
        print("usage: fix_u1_digital_fanout_clearances.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = remove_old(board.read_text())
    board.write_text(insert_routes(text, build_routes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
