#!/usr/bin/env python3
r"""openEMS 2x2 RX subarray using the direct-column fallback feed.

This is the fallback from SIM-STATUS.md:

* retune each patch feed target to approximately 100 ohm,
* parallel the two patches in each 1x2 column directly to approximately 50 ohm,
* combine the two 50-ohm columns at the root through one 35.4-ohm quarter-wave
  transformer.

The script consumes the pure geometry from subarray_geometry.py, draws the same
copper in openEMS, and writes the canonical results/subarray.json when the run
finishes.
"""

import json
import os
import sys

import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0, EPS0
from openEMS.ports import UI_data

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subarray_geometry import (  # noqa: E402
    assess_far_field,
    build_nf2ff_domain,
    build_fallback_geometry,
    gain_dbi_from_directivity,
    load_default_element,
    nf2ff_angles_deg,
    pattern_metrics,
)


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


HERE = os.path.dirname(os.path.abspath(__file__))
UNIT = 1e-3

ELEM = load_default_element(HERE)
L_TRIM_MM = float(os.environ.get("L_TRIM_MM", "-0.05"))
PATCH_INSET_MM = os.environ.get("PATCH_INSET_MM")
PATCH_INSET = None if PATCH_INSET_MM is None else float(PATCH_INSET_MM)
GEOM = build_fallback_geometry(
    ELEM,
    l_trim_mm=L_TRIM_MM,
    inset_mm=PATCH_INSET,
)

SUB_EPS_R = float(ELEM["substrate"]["er"])
SUB_TAN_D = float(ELEM["substrate"]["tand"])
SUB_H = float(ELEM["substrate"]["h_mm"])
SUB_KAPPA = SUB_TAN_D * 2 * np.pi * 24.2e9 * EPS0 * SUB_EPS_R

PATCH = GEOM["patch"]
PATCH_W = PATCH["W_mm"]
PATCH_L = PATCH["L_mm"]
INSET_DEPTH = PATCH["inset_mm"]
FEED_W = PATCH["feed_w_mm"]
INSET_GAP = PATCH["inset_gap_mm"]
PITCH = GEOM["pitch_mm"]

F_START = 22.0e9
F_STOP = 26.0e9
F0 = 24.2e9
FC = 8e9
F_PHASE = 24.2e9

MESH_DIV = float(os.environ.get("MESH_DIV", "20"))
MESH_RES = C0 / (F_STOP * np.sqrt(SUB_EPS_R)) / UNIT / MESH_DIV
EDGE_RES = FEED_W / 4.0
END_CRIT = float(os.environ.get("END_CRIT", "1e-4"))

QW_W = GEOM["transformer"]["w_mm"]
QW_LEN = GEOM["transformer"]["lambda_g_qw_mm"] / 4.0
Z_QW = GEOM["transformer"]["z_qw_ohm"]
ER_EFF_QW = GEOM["transformer"]["er_eff_qw"]
X_ROOT = GEOM["root"]["x_mm"]
Y_ROOT = GEOM["root"]["y_mm"]
X_PORT = GEOM["root"]["x_port_mm"]
Y_ROOT_QW_END = GEOM["root"]["y_qw_end_mm"]
Y_PORT = GEOM["root"]["y_port_mm"]
ROOT_QW_ROUTE = GEOM["root"]["qw_route"]
ROOT_BRANCH_ROUTES = GEOM["root_branch_routes"]
X_CL = GEOM["column_junctions"]["left"]["x_mm"]
X_CR = GEOM["column_junctions"]["right"]["x_mm"]
YC = PITCH / 2.0
X_BASE_L = GEOM["patches"]["TL"]["x_inset_end"]
X_BASE_R = GEOM["patches"]["TR"]["x_inset_end"]

AIR_ABOVE = 3.0
MARGIN = 3.0


def add_patch(metal, e):
    y_feed = FEED_W / 2.0
    y_notch = y_feed + INSET_GAP
    yc = e["yc"]
    lo = e["x_feed_edge"]
    hi = e["x_inset_end"]
    metal.AddBox([hi, e["y_min"], SUB_H], [e["x_max"], e["y_max"], SUB_H], priority=10)
    metal.AddBox([lo, yc + y_notch, SUB_H], [hi, e["y_max"], SUB_H], priority=10)
    metal.AddBox([lo, e["y_min"], SUB_H], [hi, yc - y_notch, SUB_H], priority=10)


def hline(metal, x0, x1, y, w):
    metal.AddBox([min(x0, x1), y - w / 2.0, SUB_H], [max(x0, x1), y + w / 2.0, SUB_H], priority=10)


def vline(metal, y0, y1, x, w):
    metal.AddBox([x - w / 2.0, min(y0, y1), SUB_H], [x + w / 2.0, max(y0, y1), SUB_H], priority=10)


def draw_polyline(feed, points, width):
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if abs(x0 - x1) < 1e-9:
            vline(feed, y0, y1, x0, width)
        elif abs(y0 - y1) < 1e-9:
            hline(feed, x0, x1, y0, width)
        else:
            raise ValueError(f"Only orthogonal routes are supported: {(x0, y0)} -> {(x1, y1)}")


def build(sim_path):
    fdtd = openEMS(EndCriteria=END_CRIT, NrTS=int(os.environ.get("NRTS", "800000")))
    fdtd.SetGaussExcite(F0, FC)
    fdtd.SetBoundaryCond(["MUR"] * 6)

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(UNIT)

    patches = GEOM["patches"]
    x_values = [X_ROOT, X_PORT, X_CL, X_CR]
    y_values = [Y_ROOT, Y_PORT, Y_ROOT_QW_END]
    for point in ROOT_QW_ROUTE:
        x_values.append(point[0])
        y_values.append(point[1])
    for route in ROOT_BRANCH_ROUTES.values():
        for point in route:
            x_values.append(point[0])
            y_values.append(point[1])
    for e in patches.values():
        x_values.extend([e["x_min"], e["x_max"], e["x_inset_end"]])
        y_values.extend([e["y_min"], e["y_max"], e["yc"]])

    x_sub_min = min(x_values) - MARGIN
    x_sub_max = max(x_values) + MARGIN
    y_sub_min = min(y_values) - MARGIN
    y_sub_max = max(y_values) + MARGIN
    domain = build_nf2ff_domain(
        structure_start_mm=(x_sub_min, y_sub_min, 0.0),
        structure_stop_mm=(x_sub_max, y_sub_max, SUB_H),
        air_clearance_mm=AIR_ABOVE,
        nf2ff_clearance_mm=2.0 * MESH_RES,
    )

    third = np.array([-EDGE_RES / 3.0, 2.0 * EDGE_RES / 3.0])

    mesh.AddLine(
        "x",
        [
            domain["simulation_start_mm"][0],
            x_sub_min,
            X_ROOT,
            x_sub_max,
            domain["simulation_stop_mm"][0],
        ],
    )
    x_edges = set(x_values)
    x_edges.update(
        [
            X_ROOT - QW_W / 2.0,
            X_ROOT + QW_W / 2.0,
            X_PORT - QW_W / 2.0,
            X_PORT + QW_W / 2.0,
            X_PORT - FEED_W / 2.0,
            X_PORT + FEED_W / 2.0,
        ]
    )
    for x in (X_ROOT, X_PORT, X_CL, X_CR):
        x_edges.update([x - FEED_W / 2.0, x + FEED_W / 2.0])
    for route in ROOT_BRANCH_ROUTES.values():
        for (x0, y0), (x1, y1) in zip(route, route[1:]):
            if abs(x0 - x1) < 1e-9:
                x_edges.update([x0 - FEED_W / 2.0, x0 + FEED_W / 2.0])
    for xe in x_edges:
        mesh.AddLine("x", xe + third)
        mesh.AddLine("x", xe - third[::-1])
    mesh.SmoothMeshLines("x", MESH_RES, 1.4)

    mesh.AddLine(
        "y",
        [
            domain["simulation_start_mm"][1],
            y_sub_min,
            Y_PORT,
            0.0,
            y_sub_max,
            domain["simulation_stop_mm"][1],
        ],
    )
    y_edges = set(y_values)
    y_edges.update(
        [
            Y_ROOT_QW_END,
            Y_ROOT_QW_END - QW_W / 2.0,
            Y_ROOT_QW_END + QW_W / 2.0,
            QW_W / 2.0,
            -QW_W / 2.0,
            FEED_W / 2.0,
            -FEED_W / 2.0,
        ]
    )
    y_feed = FEED_W / 2.0
    y_notch = y_feed + INSET_GAP
    for row_y in (+YC, -YC):
        for ye in (row_y + y_feed, row_y - y_feed, row_y + y_notch, row_y - y_notch):
            y_edges.add(ye)
    for route in ROOT_BRANCH_ROUTES.values():
        for (x0, y0), (x1, y1) in zip(route, route[1:]):
            if abs(y0 - y1) < 1e-9:
                y_edges.update([y0 - FEED_W / 2.0, y0 + FEED_W / 2.0])
    for ye in y_edges:
        mesh.AddLine("y", ye + third)
        mesh.AddLine("y", ye - third[::-1])
    mesh.SmoothMeshLines("y", MESH_RES, 1.4)

    mesh.AddLine("z", np.linspace(0, SUB_H, 5))
    mesh.AddLine(
        "z",
        [domain["simulation_start_mm"][2], domain["simulation_stop_mm"][2]],
    )
    mesh.SmoothMeshLines("z", MESH_RES, 1.4)

    substrate = csx.AddMaterial("RO4350B", epsilon=SUB_EPS_R, kappa=SUB_KAPPA)
    substrate.AddBox([x_sub_min, y_sub_min, 0], [x_sub_max, y_sub_max, SUB_H])

    ground = csx.AddMetal("ground")
    ground.AddBox([x_sub_min, y_sub_min, 0], [x_sub_max, y_sub_max, 0], priority=10)

    patch_metal = csx.AddMetal("patches")
    for e in patches.values():
        add_patch(patch_metal, e)

    feed = csx.AddMetal("feed")
    over = EDGE_RES
    for row_y in (+YC, -YC):
        hline(feed, X_CL, X_BASE_L + over, row_y, FEED_W)
        vline(feed, 0.0, row_y, X_CL, FEED_W)
        hline(feed, X_CR, X_BASE_R + over, row_y, FEED_W)
        vline(feed, 0.0, row_y, X_CR, FEED_W)

    for route in ROOT_BRANCH_ROUTES.values():
        draw_polyline(feed, route, FEED_W)
    draw_polyline(feed, ROOT_QW_ROUTE, QW_W)

    port = fdtd.AddMSLPort(
        1,
        csx.AddMetal("feed_port"),
        [X_PORT - FEED_W / 2.0, Y_PORT, SUB_H],
        [X_PORT + FEED_W / 2.0, Y_ROOT_QW_END, 0],
        "y",
        "z",
        excite=-1,
        FeedShift=8 * MESH_RES,
        MeasPlaneShift=3.5,
        priority=10,
    )

    probes = {}
    for tag, e in patches.items():
        pr = csx.AddProbe(f"vp_{tag}", 0)
        pr.SetFrequency([F_PHASE])
        pr.AddBox([e["x_inset_end"], e["yc"], 0.0], [e["x_inset_end"], e["yc"], SUB_H])
        probes[tag] = pr

    nf2ff = fdtd.CreateNF2FFBox(
        "nf2ff",
        domain["nf2ff_start_mm"],
        domain["nf2ff_stop_mm"],
    )

    return fdtd, port, nf2ff, probes, domain


def main():
    sim_path = os.environ.get("SIM_OUT_DIR", os.path.join(HERE, "results", "subarray_fallback"))
    os.makedirs(sim_path, exist_ok=True)

    lengths = GEOM["path_length_mm"]
    spread = max(lengths.values()) - min(lengths.values())
    assert spread < 0.01, f"feed path lengths not equal: {lengths}"

    fdtd, port, nf2ff, probes, domain = build(sim_path)
    if not os.environ.get("SKIP_SIM"):
        fdtd.Run(sim_path, verbose=1, cleanup=True)

    freq = np.linspace(F_START, F_STOP, 401)
    port.CalcPort(sim_path, freq, ref_impedance=50)
    s11 = port.uf_ref / port.uf_inc
    s11_db = 20 * np.log10(np.abs(s11))

    def at(fg):
        return float(np.interp(fg * 1e9, freq, s11_db))

    s_140, s_150, s_200, s_250 = at(24.14), at(24.15), at(24.20), at(24.25)
    band = (freq >= 24.150e9) & (freq <= 24.250e9)
    band_max = float(np.max(s11_db[band]))
    s11_accept = bool(band_max <= -10.0)

    phases = {}
    for tag, pr in probes.items():
        ui = UI_data([f"vp_{tag}"], sim_path, np.array([F_PHASE]))
        val = ui.ui_f_val[0][0]
        phases[tag] = float(np.angle(val, deg=True))
    ph_arr = np.array(list(phases.values()))
    rel = ((ph_arr - ph_arr[0] + 180.0) % 360.0) - 180.0
    phase_imbalance = float(rel.max() - rel.min())
    phase_accept = bool(abs(phase_imbalance) <= 5.0)

    theta_deg, phi_deg = nf2ff_angles_deg(step_deg=2.0)
    theta = np.asarray(theta_deg)
    phi = np.asarray(phi_deg)
    nf = nf2ff.CalcNF2FF(
        sim_path,
        np.array([F0]),
        theta,
        phi,
        center=domain["phase_center_m"],
        read_cached=False,
    )
    directivity_linear = float(nf.Dmax[0])
    raw_directivity_dbi = float(10.0 * np.log10(directivity_linear))
    accepted_power_w = float(np.interp(F0, freq, port.P_acc))
    far_field = assess_far_field(
        radiated_power_w=float(nf.Prad[0]),
        accepted_power_w=accepted_power_w,
        directivity_linear=directivity_linear,
        angular_grid_complete=True,
    )
    pattern = pattern_metrics(
        theta_deg=theta_deg,
        phi_deg=phi_deg,
        e_norm=nf.E_norm[0],
        directivity_linear=directivity_linear,
    )
    gain_dbi = (
        gain_dbi_from_directivity(
            directivity_linear=directivity_linear,
            radiation_efficiency=far_field["radiation_efficiency"],
        )
        if far_field["valid"]
        else None
    )
    gain_accept = bool(far_field["valid"] and gain_dbi is not None and gain_dbi >= 9.0)

    result = {
        "element": ELEM,
        "topology": GEOM["topology"],
        "element_target_z_ohm": GEOM["element_target_z_ohm"],
        "pitch_mm": PITCH,
        "feed_tree": GEOM["feed_tree"],
        "port_s11_db": {
            "24.14": round(s_140, 2),
            "24.15": round(s_150, 2),
            "24.20": round(s_200, 2),
            "24.25": round(s_250, 2),
            "band_max_24.15_24.25": round(band_max, 2),
        },
        "phase_balance_deg_max": round(phase_imbalance, 3),
        "phase_deg_per_element": {k: round(v, 2) for k, v in phases.items()},
        "gain_dbi_est": None if gain_dbi is None else round(gain_dbi, 2),
        "directivity_dbi_est": (
            round(raw_directivity_dbi, 2) if far_field["valid"] else None
        ),
        "directivity_dbi_raw_untrusted": (
            None if far_field["valid"] else round(raw_directivity_dbi, 2)
        ),
        "far_field_validation": far_field,
        "far_field_domain": domain,
        "far_field_pattern": pattern,
        "path_length_mm": {k: round(v, 4) for k, v in lengths.items()},
        "delay_scale": GEOM["delay_scale"],
        "patch": GEOM["patch"],
        "patches": GEOM["patches"],
        "column_junctions": GEOM["column_junctions"],
        "root": GEOM["root"],
        "root_branch_routes": GEOM["root_branch_routes"],
        "clearance_checks": GEOM["clearance_checks"],
        "delay_routes": GEOM["delay_routes"],
        "transformer": {
            "z_qw_ohm": round(Z_QW, 3),
            "w_mm": round(QW_W, 4),
            "lambda_g_qw_mm": round(GEOM["transformer"]["lambda_g_qw_mm"], 4),
            "er_eff_qw": round(ER_EFF_QW, 4),
        },
        "acceptance": {
            "s11": s11_accept,
            "phase": phase_accept,
            "gain": gain_accept,
        },
    }
    if L_TRIM_MM != 0.0:
        result["L_trim_mm"] = round(L_TRIM_MM, 4)
    if PATCH_INSET is not None:
        result["patch_inset_override_mm"] = round(PATCH_INSET, 4)
    print()
    print("Symmetric topology: direct 100-ohm columns + below-array corporate root")
    print(f"Root QW: Z={Z_QW:.2f}R w={QW_W:.4f} l={QW_LEN:.4f} mm")
    print(f"path lengths (mm): {lengths} spread={spread:.5f}")
    print(f"S11 @24.14={s_140:.2f} @24.15={s_150:.2f} @24.20={s_200:.2f} @24.25={s_250:.2f} dB")
    print(f"worst |S11| 24.15-24.25 = {band_max:.2f} dB -> {'PASS' if s11_accept else 'FAIL'}")
    print(f"phases (deg): {phases}")
    print(f"phase imbalance = {phase_imbalance:.3f} deg -> {'PASS' if phase_accept else 'FAIL'}")
    if far_field["valid"]:
        print(f"peak directivity = {raw_directivity_dbi:.2f} dBi")
        print(f"peak gain = {gain_dbi:.2f} dBi -> {'PASS' if gain_accept else 'FAIL'}")
        print(
            f"beam peak = theta {pattern['beam_offset_deg']:.2f} deg, "
            f"phi {pattern['phi_peak_deg']:.2f} deg"
        )
    else:
        print(
            f"far field = INVALID (raw directivity {raw_directivity_dbi:.2f} dBi): "
            f"{far_field['reason']}"
        )
    print(
        "SUMMARY_JSON:"
        + json.dumps(
            {
                "band_max_db": band_max,
                "s11_accept": s11_accept,
                "phase_imbalance": phase_imbalance,
                "phase_accept": phase_accept,
                "gain_dbi": gain_dbi,
                "directivity_dbi": raw_directivity_dbi,
                "far_field_valid": far_field["valid"],
                "gain_accept": gain_accept,
            }
        )
    )

    out_json = os.path.join(HERE, "results", "subarray.json")
    with open(out_json, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, default=_json_default)
    print(f"results -> {out_json}")

    sys.exit(0 if (s11_accept and phase_accept and gain_accept) else 2)


if __name__ == "__main__":
    main()
