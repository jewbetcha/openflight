from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


ROUTE_NETS = {"+3V3_A", "AREG", "VREF", "MICBIAS"}

CAP_ROTATIONS = {
    "\t\t(at 24 24)\n": "\t\t(at 24 24 180)\n",
    "\t\t(at 24 26)\n": "\t\t(at 24 26 180)\n",
    "\t\t(at 24 28)\n": "\t\t(at 24 28 180)\n",
    "\t\t(at 24 30)\n": "\t\t(at 24 30 180)\n",
    "\t\t(at 24 32)\n": "\t\t(at 24 32 180)\n",
    "\t\t(at 24 34)\n": "\t\t(at 24 34 180)\n",
}


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(net: str, start: tuple[float, float], end: tuple[float, float], width: float = 0.2) -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        f"\t\t(width {fmt(width)})\n"
        '\t\t(layer "F.Cu")\n'
        f'\t\t(net "{net}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def rotate_caps(text: str) -> str:
    for old, new in CAP_ROTATIONS.items():
        if old in text:
            text = text.replace(old, new, 1)
        elif new in text:
            continue
        else:
            raise RuntimeError(f"missing cap rotation marker {old.strip()}")
    return text


def remove_old_routes(text: str) -> str:
    removed = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) in ROUTE_NETS:
            text = text.replace(match.group(0), "")
            removed += 1

    if removed != 12:
        raise RuntimeError(f"expected to remove 12 supply/reference segments, removed {removed}")
    return text


def build_routes() -> list[str]:
    routes: list[str] = []
    routes.extend(
        [
            # +3V3_A entry through the analog rail jumper, then C3/C2/C1 trunk.
            segment("+3V3_A", (24.51, 22.0), (24.48, 24.0), width=0.25),
            segment("+3V3_A", (24.48, 24.0), (24.48, 26.0), width=0.25),
            segment("+3V3_A", (24.48, 26.0), (24.48, 28.0), width=0.25),
            segment("+3V3_A", (24.48, 28.0), (27.0, 28.0), width=0.25),
            segment("+3V3_A", (27.0, 28.0), (28.3, 28.75), width=0.2),
            segment("+3V3_A", (24.48, 28.0), (24.48, 28.65), width=0.2),
            segment("+3V3_A", (24.48, 28.65), (21.0, 28.65), width=0.2),
            segment("+3V3_A", (21.0, 28.65), (21.0, 28.0), width=0.2),
            # AREG decoupler/test point.
            segment("AREG", (24.48, 30.0), (26.5, 30.0), width=0.2),
            segment("AREG", (26.5, 30.0), (28.3, 29.25), width=0.2),
            segment("AREG", (24.48, 30.0), (24.48, 30.65), width=0.2),
            segment("AREG", (24.48, 30.65), (21.0, 30.65), width=0.2),
            segment("AREG", (21.0, 30.65), (21.0, 30.0), width=0.2),
            # VREF decoupler/test point.
            segment("VREF", (24.48, 32.0), (26.0, 32.0), width=0.2),
            segment("VREF", (26.0, 32.0), (28.3, 29.75), width=0.2),
            segment("VREF", (24.48, 32.0), (24.48, 32.65), width=0.2),
            segment("VREF", (24.48, 32.65), (21.0, 32.65), width=0.2),
            segment("VREF", (21.0, 32.65), (21.0, 32.0), width=0.2),
            # MICBIAS decoupler/test point.
            segment("MICBIAS", (24.48, 34.0), (25.5, 34.0), width=0.2),
            segment("MICBIAS", (25.5, 34.0), (28.3, 30.75), width=0.2),
            segment("MICBIAS", (24.48, 34.0), (24.48, 34.65), width=0.2),
            segment("MICBIAS", (24.48, 34.65), (21.0, 34.65), width=0.2),
            segment("MICBIAS", (21.0, 34.65), (21.0, 34.0), width=0.2),
        ]
    )
    return routes


def insert_segments(text: str, segments: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(segments) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: reroute_supply_refs.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = rotate_caps(text)
    text = remove_old_routes(text)
    text = insert_segments(text, build_routes())
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
