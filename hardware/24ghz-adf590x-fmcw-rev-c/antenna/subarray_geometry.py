#!/usr/bin/env python3
"""Pure geometry helpers for the Rev C 2x2 RX subarray.

This module intentionally has no openEMS dependency.  The EM scripts consume
these coordinates, and the unit tests use them to keep the feed topology honest
before a long FDTD run starts.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from patch_design import eff_permittivity, microstrip_width  # noqa: E402

F0 = 24.2e9
C0 = 299_792_458.0
PITCH_MM = 6.2
Z0_OHM = 50.0
ELEMENT_TARGET_Z_OHM = 100.0
ROOT_SPLIT_Z_OHM = 25.0
ROOT_QW_Z_OHM = (Z0_OHM * ROOT_SPLIT_Z_OHM) ** 0.5
DEFAULT_COLUMN_CLEARANCE_MM = 0.6
DEFAULT_ROOT_FEED_LEN_MM = 5.0
DEFAULT_ROOT_BRANCH_CLEARANCE_MM = 1.0
MIN_PLAUSIBLE_RADIATION_EFFICIENCY = 1e-6
MAX_PLAUSIBLE_RADIATION_EFFICIENCY = 1.05


def assess_far_field(
    *,
    radiated_power_w: float,
    accepted_power_w: float,
    directivity_linear: float,
    angular_grid_complete: bool,
) -> dict:
    """Reject numerically invalid far-field results before gain acceptance."""
    reasons = []
    if not angular_grid_complete:
        reasons.append("far-field angular grid must cover the full sphere")
    if not math.isfinite(accepted_power_w) or accepted_power_w <= 0.0:
        reasons.append("accepted power must be finite and positive")
        efficiency = 0.0
    else:
        efficiency = radiated_power_w / accepted_power_w

    if (
        not math.isfinite(radiated_power_w)
        or efficiency < MIN_PLAUSIBLE_RADIATION_EFFICIENCY
    ):
        reasons.append("radiated power is effectively zero relative to accepted power")
    elif efficiency > MAX_PLAUSIBLE_RADIATION_EFFICIENCY:
        reasons.append("radiated power exceeds accepted power")

    if not math.isfinite(directivity_linear) or directivity_linear <= 0.0:
        reasons.append("directivity must be finite and positive")

    return {
        "valid": not reasons,
        "radiated_power_w": radiated_power_w,
        "accepted_power_w": accepted_power_w,
        "radiation_efficiency": efficiency,
        "directivity_linear": directivity_linear,
        "angular_grid_complete": angular_grid_complete,
        "reason": "; ".join(reasons),
    }


def phase_center_m(x_mm: float, y_mm: float, z_mm: float) -> tuple[float, float, float]:
    """Convert an NF2FF phase center from drawing millimeters to meters."""
    millimeters_to_meters = 1e-3
    return (
        x_mm * millimeters_to_meters,
        y_mm * millimeters_to_meters,
        z_mm * millimeters_to_meters,
    )


def build_nf2ff_domain(
    *,
    structure_start_mm: tuple[float, float, float],
    structure_stop_mm: tuple[float, float, float],
    air_clearance_mm: float,
    nf2ff_clearance_mm: float,
) -> dict:
    """Place a finite structure inside an NF2FF surface and an outer air box."""
    if air_clearance_mm <= 0.0 or not math.isfinite(air_clearance_mm):
        raise ValueError("air clearance must be finite and positive")
    if nf2ff_clearance_mm <= 0.0 or not math.isfinite(nf2ff_clearance_mm):
        raise ValueError("NF2FF clearance must be finite and positive")
    if nf2ff_clearance_mm >= air_clearance_mm:
        raise ValueError("NF2FF clearance must be smaller than the air clearance")

    start = tuple(float(value) for value in structure_start_mm)
    stop = tuple(float(value) for value in structure_stop_mm)
    if len(start) != 3 or len(stop) != 3:
        raise ValueError("structure bounds must have three coordinates")
    if any(
        not math.isfinite(lo) or not math.isfinite(hi) or lo >= hi
        for lo, hi in zip(start, stop, strict=True)
    ):
        raise ValueError("structure start must be finite and below structure stop")

    simulation_start = tuple(value - air_clearance_mm for value in start)
    simulation_stop = tuple(value + air_clearance_mm for value in stop)
    nf2ff_start = tuple(value - nf2ff_clearance_mm for value in start)
    nf2ff_stop = tuple(value + nf2ff_clearance_mm for value in stop)
    center_mm = tuple((lo + hi) / 2.0 for lo, hi in zip(start, stop, strict=True))

    return {
        "structure_start_mm": start,
        "structure_stop_mm": stop,
        "simulation_start_mm": simulation_start,
        "simulation_stop_mm": simulation_stop,
        "nf2ff_start_mm": nf2ff_start,
        "nf2ff_stop_mm": nf2ff_stop,
        "phase_center_m": phase_center_m(*center_mm),
    }


def nf2ff_angles_deg(*, step_deg: float = 2.0) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return a full-sphere angular grid in the degrees expected by Python openEMS."""
    if not math.isfinite(step_deg) or step_deg <= 0.0:
        raise ValueError("NF2FF angular step must be finite and positive")
    theta_steps = round(180.0 / step_deg)
    phi_steps = round(360.0 / step_deg)
    if not math.isclose(theta_steps * step_deg, 180.0, abs_tol=1e-9):
        raise ValueError("NF2FF angular step must divide 180 degrees")
    theta = tuple(index * step_deg for index in range(theta_steps + 1))
    phi = tuple(-180.0 + index * step_deg for index in range(phi_steps + 1))
    return theta, phi


def pattern_metrics(
    *,
    theta_deg,
    phi_deg,
    e_norm,
    directivity_linear: float,
) -> dict:
    """Extract peak direction and broadside directivity from a full-sphere pattern."""
    if not math.isfinite(directivity_linear) or directivity_linear <= 0.0:
        raise ValueError("directivity must be finite and positive")
    if len(theta_deg) == 0 or len(phi_deg) == 0 or len(e_norm) != len(theta_deg):
        raise ValueError("pattern dimensions must match the angular grid")
    if any(len(row) != len(phi_deg) for row in e_norm):
        raise ValueError("pattern dimensions must match the angular grid")

    peak_theta_index = 0
    peak_phi_index = 0
    peak_field = -math.inf
    for theta_index, row in enumerate(e_norm):
        for phi_index, value in enumerate(row):
            field = abs(float(value))
            if not math.isfinite(field):
                raise ValueError("pattern field values must be finite")
            if field > peak_field:
                peak_field = field
                peak_theta_index = theta_index
                peak_phi_index = phi_index
    if peak_field <= 0.0:
        raise ValueError("pattern field must contain a positive value")

    broadside_index = min(range(len(theta_deg)), key=lambda index: abs(theta_deg[index]))
    broadside_field = max(abs(float(value)) for value in e_norm[broadside_index])
    broadside_directivity = directivity_linear * (broadside_field / peak_field) ** 2
    theta_peak = float(theta_deg[peak_theta_index])
    phi_peak = float(phi_deg[peak_phi_index])
    y_sign = 1.0 if math.sin(math.radians(phi_peak)) >= 0.0 else -1.0

    return {
        "beam_offset_deg": theta_peak,
        "signed_y_beam_deg": y_sign * theta_peak,
        "phi_peak_deg": phi_peak,
        "peak_directivity_linear": directivity_linear,
        "broadside_directivity_linear": broadside_directivity,
    }


def gain_dbi_from_directivity(
    *,
    directivity_linear: float,
    radiation_efficiency: float,
) -> float:
    """Convert directivity and radiation efficiency into antenna gain."""
    gain_linear = directivity_linear * radiation_efficiency
    if not math.isfinite(gain_linear) or gain_linear <= 0.0:
        raise ValueError("gain must be finite and positive")
    return 10.0 * math.log10(gain_linear)


def load_default_element(antenna_dir: str | Path = HERE) -> dict:
    """Load the validated standalone patch element JSON."""
    path = Path(antenna_dir) / "results" / "patch_element.json"
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _patch_edges(xc: float, yc: float, patch_l: float, patch_w: float, inset: float) -> dict:
    x_min = xc - patch_l / 2.0
    return {
        "xc": xc,
        "yc": yc,
        "x_min": x_min,
        "x_max": xc + patch_l / 2.0,
        "y_min": yc - patch_w / 2.0,
        "y_max": yc + patch_w / 2.0,
        "x_feed_edge": x_min,
        "x_inset_end": x_min + inset,
    }


def _x_ranges_overlap(a_min: float, a_max: float, b_min: float, b_max: float) -> bool:
    return max(a_min, b_min) < min(a_max, b_max)


def _vertical_segment_intersects_patch(
    *,
    x_center: float,
    width: float,
    y0: float,
    y1: float,
    patch: dict,
) -> bool:
    x_min = x_center - width / 2.0
    x_max = x_center + width / 2.0
    y_min = min(y0, y1)
    y_max = max(y0, y1)
    return _x_ranges_overlap(x_min, x_max, patch["x_min"], patch["x_max"]) and _x_ranges_overlap(
        y_min, y_max, patch["y_min"], patch["y_max"]
    )


def _horizontal_segment_intersects_patch(
    *,
    y_center: float,
    width: float,
    x0: float,
    x1: float,
    patch: dict,
) -> bool:
    x_min = min(x0, x1)
    x_max = max(x0, x1)
    y_min = y_center - width / 2.0
    y_max = y_center + width / 2.0
    return _x_ranges_overlap(x_min, x_max, patch["x_min"], patch["x_max"]) and _x_ranges_overlap(
        y_min, y_max, patch["y_min"], patch["y_max"]
    )


def _route_intersects_patch(points: list[list[float]], width: float, patch: dict) -> bool:
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if abs(x0 - x1) < 1e-9:
            if _vertical_segment_intersects_patch(
                x_center=x0,
                width=width,
                y0=y0,
                y1=y1,
                patch=patch,
            ):
                return True
        elif abs(y0 - y1) < 1e-9:
            if _horizontal_segment_intersects_patch(
                y_center=y0,
                width=width,
                x0=x0,
                x1=x1,
                patch=patch,
            ):
                return True
        else:
            raise ValueError(f"only orthogonal routes are supported: {(x0, y0)} -> {(x1, y1)}")
    return False


def build_fallback_geometry(
    element: dict,
    *,
    l_trim_mm: float = -0.05,
    inset_mm: float | None = None,
    column_clearance_mm: float = DEFAULT_COLUMN_CLEARANCE_MM,
    root_x_mm: float | None = None,
    root_y_mm: float | None = None,
) -> dict:
    """Build the direct-column fallback topology.

    Topology:
    - Every patch remains co-oriented and fed on its -x edge.
    - Each 1x2 column directly parallels two retuned ~100-ohm element inputs,
      so the column junction is approximately 50 ohm.
    - The two 50-ohm column outputs are combined at the root and transformed
      once through a 35.4-ohm quarter-wave section.
    - Each column output leaves its junction horizontally before dropping below
      the patch copper. The left drop runs outside the array and the right drop
      runs through the gap between patch columns, so neither root branch shares
      copper with an element trunk.
    - The root x-coordinate is solved from the two physical Manhattan route
      lengths, preserving identical electrical lengths without overlapping
      primitives.
    - The 35.4-ohm transformer and 50-ohm launch continue vertically downward.
    """
    patch_w = float(element["W_mm"])
    patch_l = float(element["L_mm"]) + l_trim_mm
    inset = float(element["inset_mm"] if inset_mm is None else inset_mm)
    feed_w = float(element["feed_w_mm"])
    substrate = element["substrate"]
    er = float(substrate["er"])
    h_m = float(substrate["h_mm"]) * 1e-3

    qw_w = microstrip_width(ROOT_QW_Z_OHM, er, h_m) * 1e3
    er_eff_qw = eff_permittivity(er, qw_w * 1e-3, h_m)
    lambda_g_qw = (C0 / F0) / (er_eff_qw**0.5) * 1e3
    qw_len = lambda_g_qw / 4.0

    xc = PITCH_MM / 2.0
    yc = PITCH_MM / 2.0
    patches = {
        "TL": _patch_edges(-xc, +yc, patch_l, patch_w, inset),
        "TR": _patch_edges(+xc, +yc, patch_l, patch_w, inset),
        "BL": _patch_edges(-xc, -yc, patch_l, patch_w, inset),
        "BR": _patch_edges(+xc, -yc, patch_l, patch_w, inset),
    }

    x_edge_l = patches["TL"]["x_feed_edge"]
    x_edge_r = patches["TR"]["x_feed_edge"]
    x_base_l = patches["TL"]["x_inset_end"]
    x_base_r = patches["TR"]["x_inset_end"]
    x_cl = x_edge_l - column_clearance_mm
    x_cr = x_edge_r - column_clearance_mm
    horizontal_branch_l = x_base_l - x_cl
    horizontal_branch_r = x_base_r - x_cr

    left_drop_x = min(patches["TL"]["x_min"], patches["BL"]["x_min"]) - (
        feed_w / 2.0 + DEFAULT_ROOT_BRANCH_CLEARANCE_MM
    )
    right_drop_x = (patches["TL"]["x_max"] + patches["TR"]["x_min"]) / 2.0
    left_departure = abs(x_cl - left_drop_x)
    right_departure = abs(x_cr - right_drop_x)
    if root_x_mm is None:
        root_x_mm = (right_departure + right_drop_x + left_drop_x - left_departure) / 2.0
    if not left_drop_x < root_x_mm < right_drop_x:
        raise ValueError(
            "root x must lie between the two drop lanes for equal compact branches: "
            f"{left_drop_x} < {root_x_mm} < {right_drop_x}"
        )
    if root_y_mm is None:
        root_y_mm = min(patch["y_min"] for patch in patches.values()) - (
            feed_w / 2.0 + DEFAULT_ROOT_BRANCH_CLEARANCE_MM
        )
    x_qw_end = root_x_mm
    y_qw_end = root_y_mm - qw_len

    left_root_branch = left_departure + abs(root_y_mm) + abs(root_x_mm - left_drop_x)
    right_root_branch = right_departure + abs(root_y_mm) + abs(right_drop_x - root_x_mm)
    left_path = left_root_branch + yc + horizontal_branch_l
    right_path = right_root_branch + yc + horizontal_branch_r

    path_lengths = {
        "TL": left_path,
        "BL": left_path,
        "TR": right_path,
        "BR": right_path,
    }

    y_port = y_qw_end - DEFAULT_ROOT_FEED_LEN_MM
    root_branch_routes = {
        "left": [
            [x_cl, 0.0],
            [left_drop_x, 0.0],
            [left_drop_x, root_y_mm],
            [root_x_mm, root_y_mm],
        ],
        "right": [
            [x_cr, 0.0],
            [right_drop_x, 0.0],
            [right_drop_x, root_y_mm],
            [root_x_mm, root_y_mm],
        ],
    }
    root_qw_vertical_hits_patch = any(
        _vertical_segment_intersects_patch(
            x_center=root_x_mm,
            width=qw_w,
            y0=root_y_mm,
            y1=y_qw_end,
            patch=patch,
        )
        for patch in patches.values()
    )
    root_feed_hits_patch = any(
        _vertical_segment_intersects_patch(
            x_center=x_qw_end,
            width=feed_w,
            y0=y_qw_end,
            y1=y_port,
            patch=patch,
        )
        for patch in patches.values()
    )
    root_branch_hits_patch = any(
        _route_intersects_patch(route, feed_w, patch)
        for route in root_branch_routes.values()
        for patch in patches.values()
    )

    feed_tree = [
        {
            "seg": "root_qw",
            "w_mm": round(qw_w, 4),
            "l_mm": round(qw_len, 4),
            "z_ohm": round(ROOT_QW_Z_OHM, 2),
        },
        {
            "seg": "left_root_branch_50",
            "w_mm": round(feed_w, 4),
            "l_mm": round(left_root_branch, 4),
            "z_ohm": Z0_OHM,
        },
        {
            "seg": "right_root_branch_50",
            "w_mm": round(feed_w, 4),
            "l_mm": round(right_root_branch, 4),
            "z_ohm": Z0_OHM,
        },
        {
            "seg": "left_column_direct_parallel",
            "w_mm": round(feed_w, 4),
            "l_mm": round(yc + horizontal_branch_l, 4),
            "z_ohm": Z0_OHM,
            "load_ohm_each": ELEMENT_TARGET_Z_OHM,
        },
        {
            "seg": "right_column_direct_parallel",
            "w_mm": round(feed_w, 4),
            "l_mm": round(yc + horizontal_branch_r, 4),
            "z_ohm": Z0_OHM,
            "load_ohm_each": ELEMENT_TARGET_Z_OHM,
        },
    ]

    return {
        "topology": "symmetric_below_array_corporate_feed",
        "element_target_z_ohm": ELEMENT_TARGET_Z_OHM,
        "patch": {
            "W_mm": patch_w,
            "L_mm": patch_l,
            "inset_mm": inset,
            "feed_w_mm": feed_w,
            "inset_gap_mm": float(element["inset_gap_mm"]),
        },
        "pitch_mm": PITCH_MM,
        "column_junctions": {
            "left": {"x_mm": x_cl, "y_mm": 0.0},
            "right": {"x_mm": x_cr, "y_mm": 0.0},
        },
        "root": {
            "x_mm": root_x_mm,
            "y_mm": root_y_mm,
            "x_port_mm": x_qw_end,
            "y_qw_end_mm": y_qw_end,
            "y_port_mm": y_port,
            "qw_route": [
                [root_x_mm, root_y_mm],
                [root_x_mm, y_qw_end],
            ],
        },
        "patches": patches,
        "root_branch_routes": root_branch_routes,
        "feed_tree": feed_tree,
        "path_length_mm": path_lengths,
        "root_branch_length_mm": {
            "left": left_root_branch,
            "right": right_root_branch,
        },
        "clearance_checks": {
            "root_qw_clear_of_patch_copper": not root_qw_vertical_hits_patch,
            "root_feed_clear_of_patch_copper": not root_feed_hits_patch,
            "root_branches_clear_of_patch_copper": not root_branch_hits_patch,
        },
        "delay_routes": {
            "right_column": None,
        },
        "delay_scale": {
            "right_column": 0.0,
        },
        "transformer": {
            "z_qw_ohm": ROOT_QW_Z_OHM,
            "w_mm": qw_w,
            "lambda_g_qw_mm": lambda_g_qw,
            "er_eff_qw": er_eff_qw,
        },
    }
