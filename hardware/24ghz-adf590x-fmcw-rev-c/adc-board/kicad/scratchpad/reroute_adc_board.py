from __future__ import annotations

import sys
import uuid
from pathlib import Path

from inspect_routes import SEGMENT_RE


CD_ROTATIONS = {
    "(at 15 38 90)": "(at 15 38 270)",
    "(at 15 44 90)": "(at 15 44 270)",
    "(at 15 50 90)": "(at 15 50 270)",
    "(at 15 56 90)": "(at 15 56 270)",
}

POWER_REMOVE_UUIDS = {
    "42b43c16-dd94-4f23-9950-f1bb5ec59ae2",
    "51bcf81e-e13a-4933-ae5f-990e937f1238",
    "86fc808b-31d4-4bc2-872c-cc7fb6c6471d",
    "9490274d-eafd-4c96-bff1-e70db89494bd",
    "9e760613-31ec-42fb-9085-98a00975277c",
    "cc9ceed8-6c34-4a57-9af0-6646698fa7e3",
    "f69ad152-feb2-4093-bede-d5d559b31693",
}


ANALOG_ROUTES = {
    "IN1P": {
        "source": (12.51, 37.0),
        "shunt": (17.52, 37.0),
        "cd": (15.0, 37.52),
        "offset_y": 36.35,
        "tp": (21.5, 36.9),
        "u1": (28.3, 31.25),
    },
    "IN1M": {
        "source": (12.51, 39.0),
        "shunt": (17.52, 39.0),
        "cd": (15.0, 38.48),
        "offset_y": 39.65,
        "tp": (24.0, 39.1),
        "u1": (28.75, 31.7),
    },
    "IN2P": {
        "source": (12.51, 43.0),
        "shunt": (17.52, 43.0),
        "cd": (15.0, 43.52),
        "offset_y": 42.35,
        "tp": (21.5, 42.9),
        "u1": (29.25, 31.7),
    },
    "IN2M": {
        "source": (12.51, 45.0),
        "shunt": (17.52, 45.0),
        "cd": (15.0, 44.48),
        "offset_y": 45.65,
        "tp": (24.0, 45.1),
        "u1": (29.75, 31.7),
    },
    "IN3P": {
        "source": (12.51, 49.0),
        "shunt": (17.52, 49.0),
        "cd": (15.0, 49.52),
        "offset_y": 48.35,
        "tp": (21.5, 48.9),
        "u1": (30.25, 31.7),
    },
    "IN3M": {
        "source": (12.51, 51.0),
        "shunt": (17.52, 51.0),
        "cd": (15.0, 50.48),
        "offset_y": 51.65,
        "tp": (24.0, 51.1),
        "u1": (30.75, 31.7),
    },
    "IN4P": {
        "source": (12.51, 55.0),
        "shunt": (17.52, 55.0),
        "cd": (15.0, 55.52),
        "offset_y": 54.35,
        "tp": (21.5, 54.9),
        "u1": (31.25, 31.7),
    },
    "IN4M": {
        "source": (12.51, 57.0),
        "shunt": (17.52, 57.0),
        "cd": (15.0, 56.48),
        "offset_y": 57.65,
        "tp": (24.0, 57.1),
        "u1": (31.7, 31.25),
    },
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


def build_analog_segments() -> list[str]:
    segments: list[str] = []
    for net, route in ANALOG_ROUTES.items():
        source = route["source"]
        shunt = route["shunt"]
        cd = route["cd"]
        offset_y = route["offset_y"]
        tp = route["tp"]
        u1 = route["u1"]
        u1_escape = (u1[0], offset_y)

        segments.extend(
            [
                segment(net, source, shunt),
                segment(net, source, cd),
                segment(net, shunt, (shunt[0], offset_y)),
                segment(net, (shunt[0], offset_y), u1_escape),
                segment(net, u1_escape, u1),
                segment(net, (tp[0], offset_y), tp),
            ]
        )
    return segments


def build_power_segments() -> list[str]:
    return [
        # C7 was rotated so its +3V3 pad faces C6; keep this local rail segment clear
        # of the decoupler ground pads.
        segment("+3V3", (29.48, 25.0), (30.52, 25.0), width=0.25),
        # Feed U1 DVDD from the C6/+3V3 entry point without crossing the old C7 GND pad
        # or the U1 GPIO1_NC pad.
        segment("+3V3", (30.52, 25.0), (30.52, 26.8), width=0.2),
        segment("+3V3", (30.52, 26.8), (31.25, 28.3), width=0.2),
        # Feed the two I2C pullup supply pads from the right side instead of through
        # the I2C signal pads.
        segment("+3V3", (34.5, 29.01), (35.35, 29.01), width=0.2),
        segment("+3V3", (35.35, 29.01), (35.35, 31.01), width=0.2),
        segment("+3V3", (35.35, 31.01), (34.5, 31.01), width=0.2),
        segment("+3V3", (30.52, 25.0), (35.35, 25.0), width=0.2).replace(
            '(layer "F.Cu")', '(layer "B.Cu")'
        ),
        segment("+3V3", (35.35, 25.0), (35.35, 31.01), width=0.2).replace(
            '(layer "F.Cu")', '(layer "B.Cu")'
        ),
        via("+3V3", (35.35, 31.01)),
    ]


def remove_analog_segments(text: str) -> str:
    removed = 0
    for match in list(SEGMENT_RE.finditer(text)):
        if match.group(7) in ANALOG_ROUTES:
            text = text.replace(match.group(0), "")
            removed += 1

    if removed not in {40, 48}:
        raise RuntimeError(f"expected to remove 40 or 48 analog segments, removed {removed}")
    return text


def remove_power_segments(text: str) -> str:
    found = {match.group(8): match.group(0) for match in SEGMENT_RE.finditer(text)}
    missing = sorted(POWER_REMOVE_UUIDS - set(found))
    if missing:
        raise RuntimeError(f"missing expected power segment UUIDs: {missing}")

    for segment_uuid in POWER_REMOVE_UUIDS:
        text = text.replace(found[segment_uuid], "")
    return text


def rotate_cd_footprints(text: str) -> str:
    for old, new in CD_ROTATIONS.items():
        if old in text:
            text = text.replace(old, new, 1)
        elif new in text:
            continue
        else:
            raise RuntimeError(f"missing footprint rotation marker {old}")
    return text


def rotate_c7(text: str) -> str:
    old = "\t\t(at 29 25)\n"
    new = "\t\t(at 29 25 180)\n"
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError("missing C7 rotation marker")


def insert_segments(text: str, segments: list[str]) -> str:
    marker = "\t(zone\n"
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("could not find first zone insertion point")
    return text[:index] + "\n".join(segments) + "\n" + text[index:]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: reroute_adc_board.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text = board.read_text()
    text = rotate_cd_footprints(text)
    text = rotate_c7(text)
    text = remove_analog_segments(text)
    text = remove_power_segments(text)
    text = insert_segments(text, build_analog_segments() + build_power_segments())
    board.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
