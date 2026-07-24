#!/usr/bin/env python3
"""Minimal KiCad-Gerber F.Cu renderer for expert-review comparison.

Handles FSLAX46Y46 mm format, C/R apertures, RoundRect macro, D01/D02/D03,
G36/G37 regions. Enough for KiCad 10 exports of this board.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon, Rectangle

HERE = Path(__file__).resolve().parent
GERBERS = HERE.parent.parent / "rf-board" / "gerbers"


def parse_gerber(path: Path):
    apertures: dict[int, tuple] = {}
    draws = []  # (x0, y0, x1, y1, width)
    shapes = []  # matplotlib patches
    regions = []  # list of point lists
    current_aperture = None
    x = y = 0.0
    in_region = False
    region_points: list[tuple[float, float]] = []

    macro_roundrect: dict[int, list[float]] = {}

    lines = path.read_text().splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line:
            continue
        if line.startswith("%AM"):
            # Aperture macro: collect until % — only RoundRect used by KiCad here
            name = line[3:].rstrip("*")
            params: list[float] = []
            while index < len(lines):
                macro_line = lines[index]
                index += 1
                if macro_line.endswith("%"):
                    break
            continue
        match = re.match(r"%ADD(\d+)([A-Za-z]+)(?:,(.*?))?\*%", line)
        if match:
            code = int(match.group(1))
            kind = match.group(2)
            params = [float(p) for p in match.group(3).split("X")] if match.group(3) else []
            if kind == "C":
                apertures[code] = ("C", params[0])
            elif kind == "R":
                apertures[code] = ("R", params[0], params[1])
            elif kind == "RoundRect":
                # macro args: 8 corner coords; treat as rect bounding box
                xs = params[0::2]
                ys = params[1::2]
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                apertures[code] = ("R", width, height)
            else:
                apertures[code] = ("C", params[0] if params else 0.1)
            continue
        if line.startswith("%"):
            continue
        d_match = re.match(r"D(\d+)\*$", line)
        if d_match:
            current_aperture = apertures.get(int(d_match.group(1)))
            continue
        coord_match = re.match(
            r"X(-?\d+)Y(-?\d+)(?:I(-?\d+)J(-?\d+))?D0([123])\*$", line
        )
        if coord_match:
            new_x = int(coord_match.group(1)) / 1e6
            new_y = -int(coord_match.group(2)) / 1e6
            op = coord_match.group(5)
            if line.startswith("G36"):
                in_region = True
                region_points = [(new_x, new_y)]
            elif line.startswith("G37"):
                if region_points:
                    regions.append(region_points)
                in_region = False
                region_points = []
            elif op == "1":
                if in_region:
                    region_points.append((new_x, new_y))
                elif current_aperture:
                    width = (
                        current_aperture[1]
                        if current_aperture[0] == "C"
                        else min(current_aperture[1], current_aperture[2])
                    )
                    draws.append((x, y, new_x, new_y, width))
            elif op == "2" and in_region and not region_points:
                region_points.append((new_x, new_y))
            elif op == "3" and current_aperture:
                if current_aperture[0] == "C":
                    shapes.append(
                        Circle((new_x, new_y), current_aperture[1] / 2, color="red")
                    )
                else:
                    width, height = current_aperture[1], current_aperture[2]
                    shapes.append(
                        Rectangle(
                            (new_x - width / 2, new_y - height / 2),
                            width,
                            height,
                            color="red",
                        )
                    )
            x, y = new_x, new_y
            continue
        if line.startswith("G36"):
            in_region = True
            region_points = []
        elif line.startswith("G37"):
            if region_points:
                regions.append(region_points)
            in_region = False
            region_points = []
    return draws, shapes, regions


def render(path: Path, out: Path, title: str) -> None:
    draws, shapes, regions = parse_gerber(path)
    fig, ax = plt.subplots(figsize=(24, 15))
    for polygon in regions:
        ax.add_patch(Polygon(polygon, closed=True, facecolor="red", edgecolor="none"))
    for patch in shapes:
        ax.add_patch(patch)
    for x0, y0, x1, y1, width in draws:
        ax.plot([x0, x1], [y0, y1], color="red", lw=width * 3.0, solid_capstyle="butt")
    ax.set_xlim(-1, 83)
    ax.set_ylim(51, -1)
    ax.set_aspect("equal")
    ax.set_facecolor("white")
    ax.set_title(title)
    ax.axis("off")
    fig.savefig(out, dpi=40, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    print(f"wrote {out}")


def main() -> int:
    for flavor in ("production", "review"):
        render(
            GERBERS
            / f"openflight-24ghz-fmcw-rf-rev-c-{flavor}"
            / "openflight-24ghz-fmcw-rf-rev-c-F_Cu.gtl",
            HERE / f"gerber-fcu-{flavor}.png",
            flavor,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
