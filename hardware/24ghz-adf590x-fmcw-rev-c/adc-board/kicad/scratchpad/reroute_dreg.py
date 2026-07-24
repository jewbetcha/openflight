from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


NET = "DREG"


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def segment(start: tuple[float, float], end: tuple[float, float]) -> str:
    return (
        "\t(segment\n"
        f"\t\t(start {fmt(start[0])} {fmt(start[1])})\n"
        f"\t\t(end {fmt(end[0])} {fmt(end[1])})\n"
        "\t\t(width 0.2)\n"
        '\t\t(layer "F.Cu")\n'
        f'\t\t(net "{NET}")\n'
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        "\t)"
    )


def remove_old(text: str) -> str:
    removed = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) == NET:
            text = text.replace(match.group(0), "")
            removed += 1
    if removed != 3:
        raise RuntimeError(f"expected to remove 3 DREG segments, removed {removed}")
    return text


def build_routes() -> list[str]:
    return [
        segment((28.75, 28.3), (28.75, 26.8)),
        segment((28.75, 26.8), (32.52, 26.8)),
        segment((32.52, 26.8), (32.52, 25.0)),
        segment((32.52, 25.0), (32.52, 24.35)),
        segment((32.52, 24.35), (37.0, 24.35)),
        segment((34.52, 24.35), (34.52, 25.0)),
        segment((37.0, 24.35), (37.0, 25.0)),
    ]


def insert_segments(text: str, segments: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(segments) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: reroute_dreg.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = remove_old(text)
    text = insert_segments(text, build_routes())
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
