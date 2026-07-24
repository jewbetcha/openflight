from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE, VIA_RE


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def same_point(actual: tuple[float, float], expected: tuple[float, float]) -> bool:
    return abs(actual[0] - expected[0]) < 1e-6 and abs(actual[1] - expected[1]) < 1e-6


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


def remove_selected_3v3(text: str) -> str:
    remove_segments = {
        ((30.52, 25.0), (30.52, 26.8), "F.Cu"),
        ((30.52, 26.8), (31.25, 28.3), "F.Cu"),
        ((30.52, 25.0), (35.35, 25.0), "B.Cu"),
        ((35.35, 25.0), (35.35, 31.01), "B.Cu"),
    }
    removed_segments = 0
    for match in list(SEGMENT_RE.finditer(text)):
        sx, sy, ex, ey, _width, layer, net, _uuid = match.groups()
        if net != "+3V3":
            continue
        start = (float(sx), float(sy))
        end = (float(ex), float(ey))
        key = (start, end, layer)
        reverse_key = (end, start, layer)
        if key in remove_segments or reverse_key in remove_segments:
            text = text.replace(match.group(0), "")
            removed_segments += 1
    if removed_segments != len(remove_segments):
        raise RuntimeError(f"expected to remove {len(remove_segments)} +3V3 segments, removed {removed_segments}")

    removed_vias = 0
    for match in list(VIA_RE.finditer(text)):
        x, y, _size, _drill, _la, _lb, net, _uuid = match.groups()
        if net == "+3V3" and same_point((float(x), float(y)), (35.35, 31.01)):
            text = text.replace(match.group(0), "")
            removed_vias += 1
    if removed_vias != 1:
        raise RuntimeError(f"expected to remove 1 +3V3 via, removed {removed_vias}")
    return text


def build_routes() -> list[str]:
    routes: list[str] = []

    routes.extend(
        [
            segment("+3V3", (30.52, 25.0), (31.25, 25.0)),
            segment("+3V3", (31.25, 25.0), (31.25, 28.3)),
            segment("+3V3", (30.52, 25.0), (37.0, 25.0), layer="B.Cu"),
            segment("+3V3", (37.0, 25.0), (37.0, 29.01), layer="B.Cu"),
            segment("+3V3", (37.0, 29.01), (35.35, 29.01), layer="B.Cu"),
            via("+3V3", (35.35, 29.01)),
        ]
    )

    routes.extend(
        [
            segment("DREG", (28.75, 28.3), (27.8, 27.7)),
            segment("DREG", (27.8, 27.7), (27.8, 24.35)),
            segment("DREG", (27.8, 24.35), (37.0, 24.35)),
            segment("DREG", (32.52, 24.35), (32.52, 25.0)),
            segment("DREG", (34.52, 24.35), (34.52, 25.0)),
            segment("DREG", (37.0, 24.35), (37.0, 25.0)),
        ]
    )

    routes.extend(
        [
            segment("ADDR1", (31.7, 30.25), (32.45, 30.25)),
            via("ADDR1", (32.45, 30.25)),
            segment("ADDR1", (32.45, 30.25), (33.0, 30.25), layer="In1.Cu"),
            segment("ADDR1", (33.0, 30.25), (33.0, 29.4), layer="In1.Cu"),
            segment("ADDR1", (33.0, 29.4), (35.8, 29.4), layer="In1.Cu"),
            segment("ADDR1", (35.8, 29.4), (35.8, 33.01), layer="In1.Cu"),
            segment("ADDR1", (35.8, 33.01), (35.6, 33.01), layer="In1.Cu"),
            via("ADDR1", (35.6, 33.01)),
            segment("ADDR1", (35.6, 33.01), (36.5, 33.01)),
        ]
    )

    routes.extend(
        [
            segment("I2S_DIN", (30.25, 28.3), (30.25, 26.8)),
            segment("I2S_DIN", (30.25, 26.8), (30.0, 25.7)),
            via("I2S_DIN", (30.0, 25.7)),
            segment("I2S_DIN", (30.0, 25.7), (34.6, 25.7), layer="B.Cu"),
            segment("I2S_DIN", (34.6, 25.7), (34.6, 31.3), layer="B.Cu"),
            segment("I2S_DIN", (34.6, 31.3), (52.8, 31.3), layer="B.Cu"),
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
        print("usage: fix_u1_power_addr_din.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = remove_selected_3v3(text)
    text = remove_net(text, "DREG", expected_segments=5, expected_vias=0)
    text = remove_net(text, "ADDR1", expected_segments=6, expected_vias=2)
    text = remove_net(text, "I2S_DIN", expected_segments=7, expected_vias=1)
    board.write_text(insert_routes(text, build_routes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
