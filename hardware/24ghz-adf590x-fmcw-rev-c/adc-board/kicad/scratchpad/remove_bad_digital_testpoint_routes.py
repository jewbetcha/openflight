from __future__ import annotations

import sys
from pathlib import Path

from inspect_routes import SEGMENT_RE, VIA_RE


REMOVE_SEGMENTS = {
    ("I2S_BCLK", (37.5, 10.0), (47.0, 10.0), "In2.Cu"),
    ("I2S_BCLK", (47.0, 10.0), (47.0, 19.7), "In2.Cu"),
    ("I2S_LRCLK", (40.1, 10.0), (43.6, 10.0), "In1.Cu"),
    ("I2S_LRCLK", (43.6, 10.0), (43.6, 26.2), "In1.Cu"),
    ("I2S_DIN", (42.7, 10.0), (52.8, 10.0), "B.Cu"),
    ("I2S_DIN", (52.8, 10.0), (52.8, 31.3), "B.Cu"),
    ("ADC_SHDNZ", (42.7, 13.0), (51.0, 13.0), "In2.Cu"),
    ("ADC_SHDNZ", (51.0, 13.0), (51.0, 24.78), "In2.Cu"),
}

REMOVE_VIAS = {
    ("I2S_BCLK", (37.5, 10.0)),
    ("I2S_LRCLK", (40.1, 10.0)),
    ("I2S_DIN", (42.7, 10.0)),
    ("ADC_SHDNZ", (42.7, 13.0)),
}


def same_point(actual: tuple[float, float], expected: tuple[float, float]) -> bool:
    return abs(actual[0] - expected[0]) < 1e-6 and abs(actual[1] - expected[1]) < 1e-6


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: remove_bad_digital_testpoint_routes.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()

    removed_segments = 0
    for match in list(SEGMENT_RE.finditer(text)):
        sx, sy, ex, ey, _width, layer, net, _uuid = match.groups()
        start = (float(sx), float(sy))
        end = (float(ex), float(ey))
        key = (net, start, end, layer)
        reverse_key = (net, end, start, layer)
        if key in REMOVE_SEGMENTS or reverse_key in REMOVE_SEGMENTS:
            text = text.replace(match.group(0), "")
            removed_segments += 1
    if removed_segments != len(REMOVE_SEGMENTS):
        raise RuntimeError(f"expected {len(REMOVE_SEGMENTS)} segments, removed {removed_segments}")

    removed_vias = 0
    for match in list(VIA_RE.finditer(text)):
        x, y, _size, _drill, _la, _lb, net, _uuid = match.groups()
        point = (float(x), float(y))
        if any(net == via_net and same_point(point, via_point) for via_net, via_point in REMOVE_VIAS):
            text = text.replace(match.group(0), "")
            removed_vias += 1
    if removed_vias != len(REMOVE_VIAS):
        raise RuntimeError(f"expected {len(REMOVE_VIAS)} vias, removed {removed_vias}")

    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
