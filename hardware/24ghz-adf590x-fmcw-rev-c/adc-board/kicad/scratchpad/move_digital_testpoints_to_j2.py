from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path


FOOTPRINT_RE = re.compile(r"\t\(footprint .*?\n\t\)", re.S)


MOVES = {
    "TP9": (51.0, 19.7),
    "TP10": (42.7, 50.18),
    "TP11": (51.0, 52.72),
    "TP14": (51.0, 24.78),
}


STUBS = [
    ("I2S_BCLK", (48.26, 19.7), (51.0, 19.7)),
    ("I2S_LRCLK", (45.72, 50.18), (42.7, 50.18)),
    ("I2S_DIN", (48.26, 52.72), (51.0, 52.72)),
    ("ADC_SHDNZ", (48.26, 24.78), (51.0, 24.78)),
]


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(net: str, start: tuple[float, float], end: tuple[float, float]) -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        "\t\t(width 0.2)\n"
        '\t\t(layer "F.Cu")\n'
        f'\t\t(net "{net}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def move_footprint(block: str, ref: str, at: tuple[float, float]) -> str:
    if f'(property "Reference" "{ref}"' not in block:
        return block

    moved = re.sub(
        r"\n\t\t\(at [^)]+\)",
        f"\n\t\t(at {fmt(at[0])} {fmt(at[1])})",
        block,
        count=1,
    )
    if moved == block:
        raise RuntimeError(f"could not move {ref}")
    return moved


def insert_routes(text: str, routes: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(routes) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: move_digital_testpoints_to_j2.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()

    seen: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        block = match.group(0)
        for ref, at in MOVES.items():
            if f'(property "Reference" "{ref}"' in block:
                seen.add(ref)
                return move_footprint(block, ref, at)
        return block

    text = FOOTPRINT_RE.sub(replace, text)
    missing = sorted(set(MOVES) - seen)
    if missing:
        raise RuntimeError(f"missing testpoint footprints: {missing}")

    routes = [segment(net, start, end) for net, start, end in STUBS]
    board.write_text(insert_routes(text, routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
