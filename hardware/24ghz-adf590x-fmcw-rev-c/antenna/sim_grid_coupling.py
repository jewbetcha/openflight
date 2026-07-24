#!/usr/bin/env python3
"""openEMS mutual-coupling simulation for the four-channel RX aperture."""

from __future__ import annotations

import json
import os
import sys

import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0, EPS0

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_subarray_fallback as standalone_reference  # noqa: E402
from grid_geometry import (  # noqa: E402
    apply_coupling_result,
    build_grid_geometry,
    compare_grid_results,
    merge_close_mesh_lines,
    simulation_port_extent,
    split_simulation_rectangles,
    translated_mesh_lines,
)

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT = 1e-3
F_START = 22.0e9
F_STOP = 26.0e9
F0 = 24.2e9
FC = 8.0e9
AIR_CLEARANCE = 3.0
MIN_MESH_SPACING_MM = 0.0035

with open(os.path.join(HERE, "results", "subarray.json"), encoding="utf-8") as file:
    SUBARRAY = json.load(file)

GRID = build_grid_geometry(SUBARRAY)
SUB_EPS_R = float(SUBARRAY["element"]["substrate"]["er"])
SUB_TAN_D = float(SUBARRAY["element"]["substrate"]["tand"])
SUB_H = float(SUBARRAY["element"]["substrate"]["h_mm"])
SUB_KAPPA = SUB_TAN_D * 2.0 * np.pi * F0 * EPS0 * SUB_EPS_R
FEED_W = float(SUBARRAY["patch"]["feed_w_mm"])
MESH_DIV = float(os.environ.get("MESH_DIV", "20"))
MESH_RES = C0 / (F_STOP * np.sqrt(SUB_EPS_R)) / UNIT / MESH_DIV
END_CRIT = float(os.environ.get("END_CRIT", "1e-4"))
MAX_TIMESTEPS = int(os.environ.get("NRTS", "800000"))


def build():
    fdtd = openEMS(
        EndCriteria=END_CRIT,
        NrTS=MAX_TIMESTEPS,
    )
    fdtd.SetGaussExcite(F0, FC)
    fdtd.SetBoundaryCond(["MUR"] * 6)

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(UNIT)

    placements = GRID["phase_centers"]
    rectangles, _port_feeds = split_simulation_rectangles(SUBARRAY, placements)
    reference_fdtd, _, _, _, reference_domain = standalone_reference.build(HERE)
    reference_mesh = reference_fdtd.GetCSX().GetGrid()
    local_x_lines = reference_mesh.GetLines("x")
    local_y_lines = reference_mesh.GetLines("y")
    local_z_lines = reference_mesh.GetLines("z")

    structure_corners = []
    local_x0, local_y0, _ = reference_domain["structure_start_mm"]
    local_x1, local_y1, _ = reference_domain["structure_stop_mm"]
    for placement in placements:
        sign = 1.0 if int(placement["rotation_deg"]) == 0 else -1.0
        for local_x, local_y in (
            (local_x0, local_y0),
            (local_x0, local_y1),
            (local_x1, local_y0),
            (local_x1, local_y1),
        ):
            structure_corners.append(
                (
                    float(placement["x_mm"]) + sign * local_x,
                    float(placement["y_mm"]) + sign * local_y,
                )
            )
    x_sub_min = min(point[0] for point in structure_corners)
    y_sub_min = min(point[1] for point in structure_corners)
    x_sub_max = max(point[0] for point in structure_corners)
    y_sub_max = max(point[1] for point in structure_corners)
    simulation_start = (
        x_sub_min - AIR_CLEARANCE,
        y_sub_min - AIR_CLEARANCE,
        -AIR_CLEARANCE,
    )
    simulation_stop = (
        x_sub_max + AIR_CLEARANCE,
        y_sub_max + AIR_CLEARANCE,
        SUB_H + AIR_CLEARANCE,
    )

    mesh.AddLine(
        "x",
        merge_close_mesh_lines(
            translated_mesh_lines(local_x_lines, placements, "x"),
            min_spacing_mm=MIN_MESH_SPACING_MM,
        ),
    )
    mesh.AddLine(
        "y",
        merge_close_mesh_lines(
            translated_mesh_lines(local_y_lines, placements, "y"),
            min_spacing_mm=MIN_MESH_SPACING_MM,
        ),
    )
    mesh.AddLine("z", local_z_lines)

    substrate = csx.AddMaterial("RO4350B", epsilon=SUB_EPS_R, kappa=SUB_KAPPA)
    substrate.AddBox([x_sub_min, y_sub_min, 0], [x_sub_max, y_sub_max, SUB_H])
    ground = csx.AddMetal("ground")
    ground.AddBox([x_sub_min, y_sub_min, 0], [x_sub_max, y_sub_max, 0], priority=10)

    top = csx.AddMetal("rx_grid")
    for rectangle in rectangles:
        x0, y0, x1, y1 = rectangle.bounds
        top.AddBox([x0, y0, SUB_H], [x1, y1, SUB_H], priority=10)

    root = SUBARRAY["root"]
    ports = []
    for index, placement in enumerate(placements):
        extent = simulation_port_extent(root, placement)
        x_port = extent["x_mm"]
        y_start = extent["y_start_mm"]
        y_stop = extent["y_stop_mm"]
        port = fdtd.AddMSLPort(
            index + 1,
            csx.AddMetal(f"port_{placement['channel']}"),
            [x_port - FEED_W / 2.0, y_start, SUB_H],
            [x_port + FEED_W / 2.0, y_stop, 0],
            "y",
            "z",
            excite=-1 if index == 0 else 0,
            FeedShift=8.0 * MESH_RES,
            MeasPlaneShift=3.5,
            priority=10,
        )
        ports.append(port)

    domain = {
        "substrate_start_mm": [x_sub_min, y_sub_min, 0.0],
        "substrate_stop_mm": [x_sub_max, y_sub_max, SUB_H],
        "simulation_start_mm": simulation_start,
        "simulation_stop_mm": simulation_stop,
    }
    return fdtd, ports, domain


def at(frequency_hz, frequencies_hz, values):
    return float(np.interp(frequency_hz, frequencies_hz, values))


def main() -> int:
    sim_path = os.environ.get(
        "SIM_OUT_DIR",
        os.path.join(HERE, "results", "grid_coupling"),
    )
    os.makedirs(sim_path, exist_ok=True)

    fdtd, ports, domain = build()
    if not os.environ.get("SKIP_SIM"):
        fdtd.Run(sim_path, verbose=1, cleanup=True)

    freq = np.linspace(F_START, F_STOP, 401)
    for port in ports:
        port.CalcPort(sim_path, freq, ref_impedance=50)
    incident = ports[0].uf_inc
    s11_db = 20.0 * np.log10(np.abs(ports[0].uf_ref / incident))
    band = (freq >= 24.150e9) & (freq <= 24.250e9)
    band_max_s11 = float(np.max(s11_db[band]))

    coupling_db_by_port = {}
    coupling_summary = {}
    channels = [placement["channel"] for placement in GRID["phase_centers"]]
    for channel, port, placement in zip(channels[1:], ports[1:], GRID["phase_centers"][1:]):
        extent = simulation_port_extent(SUBARRAY["root"], placement)
        outgoing = getattr(port, extent["outgoing_wave"])
        coupling_db = 20.0 * np.log10(np.abs(outgoing / incident))
        coupling_db_by_port[channel] = [float(value) for value in coupling_db[band]]
        coupling_summary[channel] = {
            "24.15": round(at(24.15e9, freq, coupling_db), 2),
            "24.20": round(at(24.20e9, freq, coupling_db), 2),
            "24.25": round(at(24.25e9, freq, coupling_db), 2),
            "band_max_24.15_24.25": round(float(np.max(coupling_db[band])), 2),
        }

    result = apply_coupling_result(GRID, coupling_db_by_port)
    result["coupling_db_by_port"] = coupling_summary
    result["port_s11_db"] = {
        "24.15": round(at(24.15e9, freq, s11_db), 2),
        "24.20": round(at(24.20e9, freq, s11_db), 2),
        "24.25": round(at(24.25e9, freq, s11_db), 2),
        "band_max_24.15_24.25": round(band_max_s11, 2),
    }
    result["simulation"] = {
        "excited_port": "RX1",
        "symmetry_basis": "RX1 spans adjacent, opposed, and diagonal relationships; reciprocity covers reverse pairs",
        "mesh_method": "translated validated standalone-subarray mesh",
        "mesh_div": MESH_DIV,
        "minimum_merged_spacing_mm": MIN_MESH_SPACING_MM,
        "end_criteria": END_CRIT,
        "max_timesteps": MAX_TIMESTEPS,
        "domain": domain,
    }
    result["acceptance"]["source_subarray"] = all(
        bool(SUBARRAY.get("acceptance", {}).get(key)) for key in ("s11", "phase", "gain")
    )
    result["acceptance"]["s11"] = band_max_s11 <= -10.0
    convergence_reference = os.environ.get("CONVERGENCE_REFERENCE_JSON")
    if convergence_reference:
        with open(convergence_reference, encoding="utf-8") as file:
            reference_result = json.load(file)
        result["convergence"] = compare_grid_results(
            reference_result,
            result,
            max_delta_db=3.0,
        )
        result["convergence"]["reference"] = os.path.relpath(
            convergence_reference,
            HERE,
        )
        result["acceptance"]["convergence"] = result["convergence"]["acceptance"]
    result["acceptance"]["overall"] = all(result["acceptance"].values())

    output = os.path.join(HERE, "results", "grid.json")
    with open(output, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(f"RX-grid S11 worst-band = {band_max_s11:.2f} dB")
    for channel, summary in coupling_summary.items():
        print(f"RX1 -> {channel} coupling worst-band = {summary['band_max_24.15_24.25']:.2f} dB")
    print(f"coupling acceptance = {result['acceptance']['coupling']}")
    print(f"results -> {output}")
    return 0 if result["acceptance"]["overall"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
