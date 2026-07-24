#!/usr/bin/env python3
"""Build the four-channel RX aperture from a validated subarray geometry."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from geometry_to_footprint import Rectangle, subarray_rectangles  # noqa: E402

GRID_PITCH_MM = 12.5


def merge_close_mesh_lines(
    lines: list[float], *, min_spacing_mm: float
) -> list[float]:
    """Merge sub-threshold line clusters without chaining across the threshold."""
    if min_spacing_mm < 0:
        raise ValueError("minimum mesh spacing must be non-negative")
    clusters: list[list[float]] = []
    for line in sorted(set(float(value) for value in lines)):
        if clusters and line - clusters[-1][0] < min_spacing_mm:
            clusters[-1].append(line)
        else:
            clusters.append([line])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def translated_mesh_lines(
    local_lines: list[float], placements: list[dict], axis: str
) -> list[float]:
    """Translate a local mesh into one sorted, deduplicated global axis."""
    if axis not in {"x", "y"}:
        raise ValueError(f"unsupported mesh axis {axis}")

    translated = set()
    coordinate_key = f"{axis}_mm"
    for placement in placements:
        rotation_deg = int(placement["rotation_deg"])
        if rotation_deg not in {0, 180}:
            raise ValueError(f"unsupported grid rotation {rotation_deg}")
        sign = 1.0 if rotation_deg == 0 else -1.0
        center = float(placement[coordinate_key])
        translated.update(center + sign * float(value) for value in local_lines)
    return sorted(translated)


def simulation_port_extent(root: dict, placement: dict) -> dict:
    """Return an ordered MSL-port box and its outward wave component."""
    x_local = float(root["x_port_mm"])
    y_port_local = float(root["y_port_mm"])
    y_inner_local = float(root["y_qw_end_mm"])
    rotation_deg = int(placement["rotation_deg"])
    if rotation_deg == 180:
        x_local = -x_local
        y_port_local = -y_port_local
        y_inner_local = -y_inner_local
    elif rotation_deg != 0:
        raise ValueError(f"unsupported grid rotation {rotation_deg}")

    x_mm = float(placement["x_mm"]) + x_local
    y_port_mm = float(placement["y_mm"]) + y_port_local
    y_inner_mm = float(placement["y_mm"]) + y_inner_local
    feed_direction = 1 if y_inner_mm > y_port_mm else -1
    return {
        "x_mm": x_mm,
        "y_port_mm": y_port_mm,
        "y_inner_mm": y_inner_mm,
        "y_start_mm": min(y_port_mm, y_inner_mm),
        "y_stop_mm": max(y_port_mm, y_inner_mm),
        "span_mm": abs(y_inner_mm - y_port_mm),
        "feed_direction": feed_direction,
        "outgoing_wave": "uf_ref" if feed_direction > 0 else "uf_inc",
    }


def simulation_subarray_rectangles(subarray: dict) -> list[Rectangle]:
    """Return board copper with robust feed-to-patch overlap for openEMS."""
    overlap_mm = float(subarray["patch"]["feed_w_mm"]) / 4.0
    rectangles = []
    for rectangle in subarray_rectangles(subarray):
        if rectangle.tag.startswith(("feed_left_", "feed_right_")):
            rectangle = Rectangle(
                rectangle.tag,
                rectangle.x_mm + overlap_mm / 2.0,
                rectangle.y_mm,
                rectangle.width_mm + overlap_mm,
                rectangle.height_mm,
            )
        rectangles.append(rectangle)
    return rectangles


def split_simulation_rectangles(subarray: dict, placements: list[dict]):
    """Separate shared array copper from the feed strips owned by MSL ports."""
    shared_copper: list[Rectangle] = []
    port_feeds: dict[str, Rectangle] = {}
    for placement in placements:
        for rectangle in simulation_subarray_rectangles(subarray):
            transformed = transform_rectangle(
                rectangle,
                center_x_mm=placement["x_mm"],
                center_y_mm=placement["y_mm"],
                rotation_deg=placement["rotation_deg"],
            )
            if rectangle.tag == "root_feed_50":
                port_feeds[placement["channel"]] = transformed
            else:
                shared_copper.append(transformed)
    if set(port_feeds) != {placement["channel"] for placement in placements}:
        raise ValueError("each grid channel must have exactly one root feed rectangle")
    return shared_copper, port_feeds


def apply_coupling_result(grid: dict, coupling_db_by_port: dict[str, list[float]]) -> dict:
    """Attach a fail-closed worst-case coupling gate to frozen grid geometry."""
    if not coupling_db_by_port or any(not values for values in coupling_db_by_port.values()):
        raise ValueError("coupling results must include at least one sample per port")
    samples = [float(value) for values in coupling_db_by_port.values() for value in values]
    if any(not math.isfinite(value) for value in samples):
        raise ValueError("coupling samples must be finite")

    coupling_db_max = max(samples)
    result = dict(grid)
    result["coupling_db_by_port"] = coupling_db_by_port
    result["coupling_db_max"] = coupling_db_max
    result["acceptance"] = dict(grid.get("acceptance", {}))
    result["acceptance"]["coupling"] = coupling_db_max <= -20.0
    return result


def compare_grid_results(
    reference: dict, candidate: dict, *, max_delta_db: float
) -> dict:
    """Compare accepted-band S11 and coupling points between two grid runs."""
    frequencies = ("24.15", "24.20", "24.25")
    reference_channels = set(reference["coupling_db_by_port"])
    candidate_channels = set(candidate["coupling_db_by_port"])
    if reference_channels != candidate_channels:
        raise ValueError("grid convergence runs must contain the same channels")

    s11_deltas = [
        abs(
            float(candidate["port_s11_db"][frequency])
            - float(reference["port_s11_db"][frequency])
        )
        for frequency in frequencies
    ]
    coupling_deltas = [
        abs(
            float(candidate["coupling_db_by_port"][channel][frequency])
            - float(reference["coupling_db_by_port"][channel][frequency])
        )
        for channel in sorted(reference_channels)
        for frequency in frequencies
    ]
    if any(not math.isfinite(value) for value in s11_deltas + coupling_deltas):
        raise ValueError("grid convergence deltas must be finite")

    s11_max_delta_db = max(s11_deltas)
    coupling_max_delta_db = max(coupling_deltas)
    return {
        "s11_max_delta_db": s11_max_delta_db,
        "coupling_max_delta_db": coupling_max_delta_db,
        "max_delta_db": max_delta_db,
        "acceptance": max(s11_max_delta_db, coupling_max_delta_db) <= max_delta_db,
    }


def transform_rectangle(
    rectangle: Rectangle,
    *,
    center_x_mm: float,
    center_y_mm: float,
    rotation_deg: int,
) -> Rectangle:
    if rotation_deg == 0:
        x_mm = center_x_mm + rectangle.x_mm
        y_mm = center_y_mm + rectangle.y_mm
    elif rotation_deg == 180:
        x_mm = center_x_mm - rectangle.x_mm
        y_mm = center_y_mm - rectangle.y_mm
    else:
        raise ValueError(f"unsupported grid rotation {rotation_deg}")
    return Rectangle(
        rectangle.tag,
        x_mm,
        y_mm,
        rectangle.width_mm,
        rectangle.height_mm,
    )


def rectangles_overlap(first: Rectangle, second: Rectangle, clearance_mm: float = 0.0) -> bool:
    first_x0, first_y0, first_x1, first_y1 = first.bounds
    second_x0, second_y0, second_x1, second_y1 = second.bounds
    return not (
        first_x1 + clearance_mm <= second_x0
        or second_x1 + clearance_mm <= first_x0
        or first_y1 + clearance_mm <= second_y0
        or second_y1 + clearance_mm <= first_y0
    )


def build_grid_geometry(subarray: dict, clearance_mm: float = 0.2) -> dict:
    half_pitch = GRID_PITCH_MM / 2.0
    placements = [
        {"channel": "RX1", "x_mm": -half_pitch, "y_mm": -half_pitch, "rotation_deg": 0},
        {"channel": "RX2", "x_mm": half_pitch, "y_mm": -half_pitch, "rotation_deg": 0},
        {"channel": "RX3", "x_mm": -half_pitch, "y_mm": half_pitch, "rotation_deg": 180},
        {"channel": "RX4", "x_mm": half_pitch, "y_mm": half_pitch, "rotation_deg": 180},
    ]
    local_rectangles = subarray_rectangles(subarray)
    transformed: dict[str, list[Rectangle]] = {}
    for placement in placements:
        transformed[placement["channel"]] = [
            transform_rectangle(
                rectangle,
                center_x_mm=placement["x_mm"],
                center_y_mm=placement["y_mm"],
                rotation_deg=placement["rotation_deg"],
            )
            for rectangle in local_rectangles
        ]

    collisions: list[dict] = []
    for first_index, first in enumerate(placements):
        for second in placements[first_index + 1 :]:
            for first_rectangle in transformed[first["channel"]]:
                for second_rectangle in transformed[second["channel"]]:
                    if rectangles_overlap(first_rectangle, second_rectangle, clearance_mm):
                        collisions.append(
                            {
                                "first": f"{first['channel']}:{first_rectangle.tag}",
                                "second": f"{second['channel']}:{second_rectangle.tag}",
                            }
                        )
    if collisions:
        raise ValueError(f"grid copper overlaps at {clearance_mm} mm clearance: {collisions[:5]}")

    root = subarray["root"]
    ports = []
    for placement in placements:
        extent = simulation_port_extent(root, placement)
        ports.append(
            {
                "channel": placement["channel"],
                "x_mm": extent["x_mm"],
                "y_mm": extent["y_port_mm"],
            }
        )

    return {
        "architecture": "four_2x2_subarrays_outward_feeds",
        "pitch_mm": GRID_PITCH_MM,
        "phase_centers": placements,
        "feed_ports": ports,
        "minimum_copper_clearance_mm": clearance_mm,
        "coupling_db_max": None,
        "acceptance": {"geometry": True, "coupling": False},
    }


def main() -> int:
    source = HERE / "results" / "subarray.json"
    output = HERE / "results" / "grid.json"
    subarray = json.loads(source.read_text(encoding="utf-8"))
    result = build_grid_geometry(subarray)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote provisional geometry -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
