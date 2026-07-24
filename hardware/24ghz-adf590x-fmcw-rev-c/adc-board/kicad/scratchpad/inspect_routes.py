from __future__ import annotations

import re
import sys
from pathlib import Path


SEGMENT_RE = re.compile(
    r'\(segment\s+'
    r'\(start ([^ ]+) ([^)]+)\)\s+'
    r'\(end ([^ ]+) ([^)]+)\)\s+'
    r'\(width ([^)]+)\)\s+'
    r'\(layer "([^"]+)"\)\s+'
    r'\(net "([^"]+)"\)\s+'
    r'\(uuid "([^"]+)"\)\s*'
    r'\)',
    re.S,
)

VIA_RE = re.compile(
    r'\(via\s+'
    r'\(at ([^ ]+) ([^)]+)\)\s+'
    r'\(size ([^)]+)\)\s+'
    r'\(drill ([^)]+)\)\s+'
    r'\(layers "([^"]+)" "([^"]+)"\)\s+'
    r'\(net "([^"]+)"\)\s+'
    r'\(uuid "([^"]+)"\)\s*'
    r'\)',
    re.S,
)


def parse(path: Path):
    text = path.read_text()
    segments = []
    for match in SEGMENT_RE.finditer(text):
        sx, sy, ex, ey, width, layer, net, uuid = match.groups()
        segments.append(
            {
                "start": (float(sx), float(sy)),
                "end": (float(ex), float(ey)),
                "width": float(width),
                "layer": layer,
                "net": net,
                "uuid": uuid,
                "raw": match.group(0),
            }
        )

    vias = []
    for match in VIA_RE.finditer(text):
        x, y, size, drill, layer_a, layer_b, net, uuid = match.groups()
        vias.append(
            {
                "at": (float(x), float(y)),
                "size": float(size),
                "drill": float(drill),
                "layers": (layer_a, layer_b),
                "net": net,
                "uuid": uuid,
                "raw": match.group(0),
            }
        )

    return segments, vias


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: inspect_routes.py <board.kicad_pcb> [net ...]", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    nets = sys.argv[2:] or [
        "IN1P",
        "IN1M",
        "IN2P",
        "IN2M",
        "IN3P",
        "IN3M",
        "IN4P",
        "IN4M",
        "+3V3",
        "DREG",
        "ADC_SHDNZ",
        "I2S_BCLK",
        "I2S_DIN",
        "I2S_LRCLK",
        "I2C_SCL",
        "I2C_SDA",
        "RAMP_SYNC",
        "+5V",
        "MICBIAS",
        "GND",
    ]

    segments, vias = parse(board)
    print(f"segments {len(segments)} vias {len(vias)}")
    for net in nets:
        net_segments = [segment for segment in segments if segment["net"] == net]
        net_vias = [via for via in vias if via["net"] == net]
        if not net_segments and not net_vias:
            continue

        print(f"\nNET {net} segments {len(net_segments)} vias {len(net_vias)}")
        for segment in net_segments:
            print(
                " seg",
                segment["layer"],
                segment["start"],
                "->",
                segment["end"],
                "w",
                segment["width"],
                segment["uuid"][:8],
            )
        for via in net_vias:
            print(" via", via["at"], "size", via["size"], via["uuid"][:8])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
