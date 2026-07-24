from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


NETS = {"+3V3_A", "AREG", "VREF", "MICBIAS"}
REMOVE_3V3_UUIDS = {"0e10ae05-38f4-4b63-a4a5-97e662647b87"}


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


def remove_old(text: str) -> str:
    removed_signal = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) in NETS:
            text = text.replace(match.group(0), "")
            removed_signal += 1

    if removed_signal != 23:
        raise RuntimeError(f"expected to remove 23 signal segments, removed {removed_signal}")

    found = {match.group(8): match.group(0) for match in SEGMENT_RE.finditer(text)}
    missing = sorted(REMOVE_3V3_UUIDS - set(found))
    if missing:
        raise RuntimeError(f"missing expected stale +3V3 segment UUIDs: {missing}")
    for segment_uuid in REMOVE_3V3_UUIDS:
        text = text.replace(found[segment_uuid], "")
    return text


def build_routes() -> list[str]:
    return [
        segment("+3V3_A", (24.51, 22.0), (24.48, 24.0), width=0.25),
        segment("+3V3_A", (24.48, 24.0), (24.48, 26.0), width=0.25),
        segment("+3V3_A", (24.48, 26.0), (24.48, 28.0), width=0.25),
        segment("+3V3_A", (24.48, 28.0), (26.3, 28.0), width=0.2),
        segment("+3V3_A", (26.3, 28.0), (26.3, 28.75), width=0.2),
        segment("+3V3_A", (26.3, 28.75), (28.3, 28.75), width=0.2),
        segment("+3V3_A", (24.48, 28.0), (24.48, 28.65), width=0.2),
        segment("+3V3_A", (24.48, 28.65), (21.0, 28.65), width=0.2),
        segment("+3V3_A", (21.0, 28.65), (21.0, 28.0), width=0.2),
        segment("AREG", (24.48, 30.0), (26.3, 30.0), width=0.2),
        segment("AREG", (26.3, 30.0), (26.3, 29.25), width=0.2),
        segment("AREG", (26.3, 29.25), (28.3, 29.25), width=0.2),
        segment("AREG", (24.48, 30.0), (24.48, 30.65), width=0.2),
        segment("AREG", (24.48, 30.65), (21.0, 30.65), width=0.2),
        segment("AREG", (21.0, 30.65), (21.0, 30.0), width=0.2),
        segment("VREF", (24.48, 32.0), (26.7, 32.0), width=0.2),
        segment("VREF", (26.7, 32.0), (26.7, 29.75), width=0.2),
        segment("VREF", (26.7, 29.75), (28.3, 29.75), width=0.2),
        segment("VREF", (24.48, 32.0), (24.48, 32.65), width=0.2),
        segment("VREF", (24.48, 32.65), (21.0, 32.65), width=0.2),
        segment("VREF", (21.0, 32.65), (21.0, 32.0), width=0.2),
        segment("MICBIAS", (24.48, 34.0), (27.1, 34.0), width=0.2),
        segment("MICBIAS", (27.1, 34.0), (27.1, 30.75), width=0.2),
        segment("MICBIAS", (27.1, 30.75), (28.3, 30.75), width=0.2),
        segment("MICBIAS", (24.48, 34.0), (24.48, 34.65), width=0.2),
        segment("MICBIAS", (24.48, 34.65), (21.0, 34.65), width=0.2),
        segment("MICBIAS", (21.0, 34.65), (21.0, 34.0), width=0.2),
    ]


def insert_segments(text: str, segments: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(segments) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fix_supply_ref_lanes.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = remove_old(text)
    text = insert_segments(text, build_routes())
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
