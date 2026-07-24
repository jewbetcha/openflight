#!/usr/bin/env python3
"""Generate KiCad antenna footprints from the openEMS geometry result."""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_RESULT = HERE / "results" / "subarray.json"
DEFAULT_LIBRARY = HERE.parent / "library" / "openflight-revc.pretty"
MASK_MARGIN_MM = 0.08
COURTYARD_MARGIN_MM = 1.0


@dataclass(frozen=True)
class Rectangle:
    tag: str
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (
            self.x_mm - self.width_mm / 2.0,
            self.y_mm - self.height_mm / 2.0,
            self.x_mm + self.width_mm / 2.0,
            self.y_mm + self.height_mm / 2.0,
        )


def fmt(value: float) -> str:
    rounded = round(value, 6)
    if abs(rounded) < 0.5e-6:
        rounded = 0.0
    return f"{rounded:.6f}".rstrip("0").rstrip(".")


def horizontal(tag: str, x0: float, x1: float, y: float, width: float) -> Rectangle:
    if abs(x1 - x0) < 1e-9:
        raise ValueError(f"zero-length horizontal segment {tag}")
    return Rectangle(tag, (x0 + x1) / 2.0, y, abs(x1 - x0), width)


def vertical(tag: str, x: float, y0: float, y1: float, width: float) -> Rectangle:
    if abs(y1 - y0) < 1e-9:
        raise ValueError(f"zero-length vertical segment {tag}")
    return Rectangle(tag, x, (y0 + y1) / 2.0, width, abs(y1 - y0))


def route_rectangles(tag: str, points: list[list[float]], width: float) -> list[Rectangle]:
    rectangles: list[Rectangle] = []
    for index, ((x0, y0), (x1, y1)) in enumerate(zip(points, points[1:])):
        segment_tag = f"{tag}_{index}"
        if abs(x0 - x1) < 1e-9:
            rectangles.append(vertical(segment_tag, x0, y0, y1, width))
        elif abs(y0 - y1) < 1e-9:
            rectangles.append(horizontal(segment_tag, x0, x1, y0, width))
        else:
            raise ValueError(f"non-orthogonal route {segment_tag}: {(x0, y0)} -> {(x1, y1)}")
    return rectangles


def subarray_rectangles(result: dict) -> list[Rectangle]:
    patch = result["patch"]
    feed_w = float(patch["feed_w_mm"])
    inset_gap = float(patch["inset_gap_mm"])
    notch_half_width = feed_w / 2.0 + inset_gap
    rectangles: list[Rectangle] = []

    for name, element in result["patches"].items():
        x_feed = float(element["x_feed_edge"])
        x_inset = float(element["x_inset_end"])
        x_max = float(element["x_max"])
        y_min = float(element["y_min"])
        y_max = float(element["y_max"])
        y_center = float(element["yc"])
        rectangles.extend(
            [
                Rectangle(
                    f"patch_{name}_body",
                    (x_inset + x_max) / 2.0,
                    y_center,
                    x_max - x_inset,
                    y_max - y_min,
                ),
                Rectangle(
                    f"patch_{name}_notch_top",
                    (x_feed + x_inset) / 2.0,
                    (y_center + notch_half_width + y_max) / 2.0,
                    x_inset - x_feed,
                    y_max - (y_center + notch_half_width),
                ),
                Rectangle(
                    f"patch_{name}_notch_bottom",
                    (x_feed + x_inset) / 2.0,
                    (y_min + y_center - notch_half_width) / 2.0,
                    x_inset - x_feed,
                    (y_center - notch_half_width) - y_min,
                ),
            ]
        )

    left_x = float(result["column_junctions"]["left"]["x_mm"])
    right_x = float(result["column_junctions"]["right"]["x_mm"])
    row_y = float(result["pitch_mm"]) / 2.0
    for row_tag, y in (("top", row_y), ("bottom", -row_y)):
        rectangles.extend(
            [
                horizontal(
                    f"feed_left_{row_tag}",
                    left_x,
                    result["patches"]["TL"]["x_inset_end"],
                    y,
                    feed_w,
                ),
                vertical(f"trunk_left_{row_tag}", left_x, 0.0, y, feed_w),
                horizontal(
                    f"feed_right_{row_tag}",
                    right_x,
                    result["patches"]["TR"]["x_inset_end"],
                    y,
                    feed_w,
                ),
                vertical(f"trunk_right_{row_tag}", right_x, 0.0, y, feed_w),
            ]
        )

    for side, route in result["root_branch_routes"].items():
        rectangles.extend(route_rectangles(f"root_branch_{side}", route, feed_w))

    transformer_w = float(result["transformer"]["w_mm"])
    rectangles.extend(
        route_rectangles("root_transformer", result["root"]["qw_route"], transformer_w)
    )
    root = result["root"]
    rectangles.append(
        vertical(
            "root_feed_50",
            float(root["x_port_mm"]),
            float(root["y_port_mm"]),
            float(root["y_qw_end_mm"]),
            feed_w,
        )
    )

    for rectangle in rectangles:
        if rectangle.width_mm <= 0.0 or rectangle.height_mm <= 0.0:
            raise ValueError(f"invalid rectangle {rectangle}")
    return rectangles


def deterministic_uuid(name: str, tag: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"openflight-revc:{name}:{tag}"))


def render_footprint(name: str, result: dict) -> str:
    rectangles = subarray_rectangles(result)
    x_min = min(rectangle.bounds[0] for rectangle in rectangles) - COURTYARD_MARGIN_MM
    y_min = min(rectangle.bounds[1] for rectangle in rectangles) - COURTYARD_MARGIN_MM
    x_max = max(rectangle.bounds[2] for rectangle in rectangles) + COURTYARD_MARGIN_MM
    y_max = max(rectangle.bounds[3] for rectangle in rectangles) + COURTYARD_MARGIN_MM

    lines = [
        f'(footprint "{name}"',
        "\t(version 20260206)",
        '\t(generator "openflight-geometry-to-footprint")',
        '\t(generator_version "1.0")',
        '\t(layer "F.Cu")',
        '\t(descr "Rev C 24 GHz 2x2 patch subarray generated 1:1 from openEMS geometry")',
        '\t(tags "24GHz patch antenna generated openEMS")',
        '\t(property "Reference" "REF**"',
        f"\t\t(at {fmt((x_min + x_max) / 2.0)} {fmt(y_min - 0.8)} 0)",
        '\t\t(layer "F.SilkS")',
        f'\t\t(uuid "{deterministic_uuid(name, "reference")}")',
        "\t\t(effects (font (size 0.8 0.8) (thickness 0.12)))",
        "\t)",
        f'\t(property "Value" "{name}"',
        f"\t\t(at {fmt((x_min + x_max) / 2.0)} {fmt(y_max + 0.8)} 0)",
        '\t\t(layer "F.Fab")',
        "\t\t(hide yes)",
        f'\t\t(uuid "{deterministic_uuid(name, "value")}")',
        "\t\t(effects (font (size 0.8 0.8) (thickness 0.12)))",
        "\t)",
        "\t(attr smd)",
        "\t(duplicate_pad_numbers_are_jumpers no)",
    ]
    for rectangle in rectangles:
        lines.extend(
            [
                '\t(pad "1" smd rect',
                f"\t\t(at {fmt(rectangle.x_mm)} {fmt(rectangle.y_mm)})",
                f"\t\t(size {fmt(rectangle.width_mm)} {fmt(rectangle.height_mm)})",
                '\t\t(layers "F.Cu" "F.Mask")',
                f"\t\t(solder_mask_margin {fmt(MASK_MARGIN_MM)})",
                "\t\t(zone_connect 2)",
                f'\t\t(uuid "{deterministic_uuid(name, rectangle.tag)}")',
                "\t)",
            ]
        )
    lines.append(")")
    return "\n".join(lines) + "\n"


def validate_result(result: dict) -> None:
    acceptance = result.get("acceptance", {})
    failures = sorted(name for name in ("s11", "phase", "gain") if not acceptance.get(name))
    if failures:
        raise RuntimeError(f"antenna result has failing acceptance gates: {', '.join(failures)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()

    result = json.loads(args.input.read_text(encoding="utf-8"))
    if not args.allow_unverified:
        validate_result(result)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("RX_SUBARRAY_2X2", "TX_ARRAY_2X2"):
        output = args.output_dir / f"{name}.kicad_mod"
        output.write_text(render_footprint(name, result), encoding="utf-8")
        print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
