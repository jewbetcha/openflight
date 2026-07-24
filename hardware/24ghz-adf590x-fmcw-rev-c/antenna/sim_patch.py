#!/usr/bin/env python3
"""openEMS element simulation: inset-fed rectangular patch at 24.2 GHz.

Reuses the port / mesh / excitation conventions established by sim_canary.py
on the same RO4350B stackup (h=0.254 mm, er=3.66, tan_d=0.0037):

  - openEMS(EndCriteria=1e-4) energy stop, SetGaussExcite(f0, fc).
  - PML_8 on the feed (x) propagation ends, MUR on the other faces, PEC ground
    at zmin.
  - MSL port via FDTD.AddMSLPort() spanning strip (z=h) to ground (z=0), with
    FeedShift clear of the PML and MeasPlaneShift de-embedding the reference
    plane into the feed line.
  - lambda/20 dielectric mesh at f_max with thirds-rule refinement at the feed
    and patch edges; >= 4 cells through the substrate.

Geometry comes from patch_design.py; L is iterated (env var PATCH_L_MM) to
center resonance within 24.20 +/- 0.05 GHz. Acceptance: |S11| <= -10 dB across
24.150-24.250 GHz. Reports S11 at 24.140/24.150/24.200/24.250 GHz.

Invocation (from repo root):
    docker run --rm -v "$PWD":/work -w /work openems-local \
        python3 hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_patch.py
Optional overrides: PATCH_L_MM, PATCH_W_MM, PATCH_INSET_MM, SIM_OUT_DIR.
"""

import json
import os
import sys

import numpy as np

from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0, EPS0

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subarray_geometry import (  # noqa: E402
    assess_far_field,
    build_nf2ff_domain,
    gain_dbi_from_directivity,
    nf2ff_angles_deg,
)

# ----------------------------------------------------------------------------
# Geometry / stackup (drawing unit = 1 mm)
# ----------------------------------------------------------------------------
UNIT = 1e-3

SUB_EPS_R = 3.66
SUB_TAN_D = 0.0037
SUB_H = 0.254            # substrate height, mm

# Patch geometry (closed-form defaults from patch_design.py; L is the knob).
# Final tuned geometry (FDTD-iterated from the patch_design.py starting point).
# Closed-form gave W=4.058, L=3.152, inset=1.235; FDTD centered resonance at
# 24.19 GHz with W=4.058, L=2.970, inset=0.850 (see sim_patch iteration table
# in task-5-report.md). The closed-form L was ~6% long and inset ~45% too deep.
PATCH_W = float(os.environ.get("PATCH_W_MM", "4.058"))   # non-resonant edge
PATCH_L = float(os.environ.get("PATCH_L_MM", "2.970"))   # resonant length
INSET_DEPTH = float(os.environ.get("PATCH_INSET_MM", "0.850"))  # notch depth
FEED_W = 0.556          # 50 ohm feed width, mm
INSET_GAP = 0.20        # notch clearance each side of the feed, mm (>=0.127)
FEED_LEN = 6.0          # feed line length from patch edge to port, mm

# Substrate / air extents. Patch sits centred in x; feed runs -x to the port.
AIR_ABOVE = 3.0         # air above the substrate, mm (~ >2 lambda0 at 24 GHz)
MARGIN = 3.0            # substrate margin around metal footprint, mm

# ----------------------------------------------------------------------------
# Frequency setup
# ----------------------------------------------------------------------------
F_START = float(os.environ.get("F_START_GHZ", "22.0")) * 1e9
F_STOP = float(os.environ.get("F_STOP_GHZ", "26.0")) * 1e9
F0 = 24.2e9             # Gauss center
FC = 8e9                # 20 dB edges ~16/32 GHz -> wide search band

SUB_KAPPA = SUB_TAN_D * 2 * np.pi * F0 * EPS0 * SUB_EPS_R  # S/m

# mesh: lambda/20 in the dielectric at the top frequency (mm)
MESH_RES = C0 / (F_STOP * np.sqrt(SUB_EPS_R)) / UNIT / 20.0
EDGE_RES = FEED_W / 4.0  # fine mesh at feed/patch edges
FAR_FIELD = os.environ.get("FAR_FIELD", "0") == "1"


def build_sim():
    """Construct the FDTD problem, optionally with a finite-ground NF2FF box."""
    fdtd = openEMS(EndCriteria=1e-4, NrTS=600000)
    fdtd.SetGaussExcite(F0, FC)
    if FAR_FIELD:
        fdtd.SetBoundaryCond(["MUR"] * 6)
    else:
        # PML on the feed ends; MUR elsewhere; PEC ground at zmin.
        fdtd.SetBoundaryCond(["PML_8", "PML_8", "MUR", "MUR", "PEC", "MUR"])

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(UNIT)

    # --- key x/y coordinates --------------------------------------------------
    # Patch occupies x in [x_patch_min, x_patch_max]; feed edge at x_feed_edge.
    x_patch_max = PATCH_L / 2.0
    x_patch_min = -PATCH_L / 2.0
    x_feed_edge = x_patch_min                 # feed attaches to -x radiating edge
    x_port = x_feed_edge - FEED_LEN           # port / substrate -x end
    x_sub_min = x_port - MARGIN
    x_sub_max = x_patch_max + MARGIN

    y_patch = PATCH_W / 2.0
    y_sub = y_patch + MARGIN

    domain = None
    if FAR_FIELD:
        domain = build_nf2ff_domain(
            structure_start_mm=(x_sub_min, -y_sub, 0.0),
            structure_stop_mm=(x_sub_max, y_sub, SUB_H),
            air_clearance_mm=AIR_ABOVE,
            nf2ff_clearance_mm=2.0 * MESH_RES,
        )

    # inset notch: feed penetrates INSET_DEPTH into the patch, notches on
    # either side of the feed line width.
    y_feed = FEED_W / 2.0
    y_notch = y_feed + INSET_GAP
    x_inset_end = x_patch_min + INSET_DEPTH   # deepest point of the notch

    # --- mesh: x (feed propagation axis) -------------------------------------
    third = np.array([-EDGE_RES / 3.0, 2.0 * EDGE_RES / 3.0])
    x_domain = (
        [domain["simulation_start_mm"][0], domain["simulation_stop_mm"][0]]
        if domain
        else []
    )
    mesh.AddLine("x", [x_sub_min, x_port, x_sub_max, *x_domain])
    for xe in (x_patch_min, x_patch_max, x_inset_end):
        mesh.AddLine("x", xe + third)
        mesh.AddLine("x", xe - third[::-1])
    mesh.SmoothMeshLines("x", MESH_RES, 1.4)

    # --- mesh: y (transverse), thirds rule at feed and patch edges -----------
    mesh.AddLine("y", 0)
    for ye in (y_feed, y_notch, y_patch):
        mesh.AddLine("y", ye + third)
        mesh.AddLine("y", -(ye + third))
        mesh.AddLine("y", ye - third[::-1])
        mesh.AddLine("y", -(ye - third[::-1]))
    y_domain = (
        [domain["simulation_start_mm"][1], domain["simulation_stop_mm"][1]]
        if domain
        else []
    )
    mesh.AddLine("y", [-y_sub, y_sub, *y_domain])
    mesh.SmoothMeshLines("y", MESH_RES, 1.4)

    # --- mesh: z, >=4 cells through substrate + air above --------------------
    mesh.AddLine("z", np.linspace(0, SUB_H, 5))
    mesh.AddLine("z", SUB_H + AIR_ABOVE)
    if domain:
        mesh.AddLine(
            "z",
            [domain["simulation_start_mm"][2], domain["simulation_stop_mm"][2]],
        )
    mesh.SmoothMeshLines("z", MESH_RES, 1.4)

    # --- substrate ------------------------------------------------------------
    substrate = csx.AddMaterial("RO4350B", epsilon=SUB_EPS_R, kappa=SUB_KAPPA)
    substrate.AddBox([x_sub_min, -y_sub, 0], [x_sub_max, y_sub, SUB_H])

    if FAR_FIELD:
        ground = csx.AddMetal("ground")
        ground.AddBox([x_sub_min, -y_sub, 0], [x_sub_max, y_sub, 0], priority=10)

    # --- patch metal with inset notch ----------------------------------------
    # Build the patch as three boxes so the notch (a rectangular slot cut from
    # the -x edge around the feed) is left as bare substrate:
    #   1) main body from x_inset_end .. x_patch_max (full width)
    #   2) two side strips from x_patch_min .. x_inset_end, outside the notch
    patch = csx.AddMetal("patch")
    patch.AddBox([x_inset_end, -y_patch, SUB_H],
                 [x_patch_max, y_patch, SUB_H], priority=10)
    patch.AddBox([x_patch_min, y_notch, SUB_H],
                 [x_inset_end, y_patch, SUB_H], priority=10)
    patch.AddBox([x_patch_min, -y_patch, SUB_H],
                 [x_inset_end, -y_notch, SUB_H], priority=10)

    # --- feed line: from port to the base of the inset notch -----------------
    # The MSL port draws its own metal from x_port to x_feed_edge; extend the
    # feed metal into the notch so it contacts the patch body at x_inset_end.
    # Overlap slightly into the patch body (one edge-cell) so the feed and
    # patch share metal cells regardless of mesh snapping at the junction.
    feed = csx.AddMetal("feed")
    feed.AddBox([x_feed_edge, -y_feed, SUB_H],
                [x_inset_end + EDGE_RES, y_feed, SUB_H], priority=10)

    # --- MSL port (excited feed) ---------------------------------------------
    port = fdtd.AddMSLPort(
        1, csx.AddMetal("feed_port"),
        [x_port, -y_feed, SUB_H], [x_feed_edge, y_feed, 0],
        "x", "z",
        excite=-1,
        FeedShift=8 * MESH_RES,
        MeasPlaneShift=5.0,   # de-embed reference plane ~1 mm from patch edge
        priority=10,
    )

    nf2ff = None
    if domain:
        nf2ff = fdtd.CreateNF2FFBox(
            "nf2ff",
            domain["nf2ff_start_mm"],
            domain["nf2ff_stop_mm"],
        )

    coords = {
        "x_patch": (x_patch_min, x_patch_max),
        "x_port": x_port,
        "x_inset_end": x_inset_end,
        "far_field_domain": domain,
    }
    return fdtd, port, nf2ff, coords


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    sim_path = os.environ.get(
        "SIM_OUT_DIR", os.path.join(here, "results", "patch"))
    os.makedirs(sim_path, exist_ok=True)

    fdtd, port, nf2ff, coords = build_sim()
    if not os.environ.get("SKIP_SIM"):
        fdtd.Run(sim_path, verbose=1, cleanup=True)

    freq = np.linspace(F_START, F_STOP, 601)  # 2.5 MHz step
    port.CalcPort(sim_path, freq, ref_impedance=50)
    s11 = port.uf_ref / port.uf_inc
    s11_db = 20 * np.log10(np.abs(s11))

    out_csv = os.path.join(sim_path, "patch_s11.csv")
    np.savetxt(out_csv, np.column_stack([freq, s11_db]),
               delimiter=",", header="freq_hz,s11_db", comments="")

    # resonance = frequency of minimum |S11|
    i_min = int(np.argmin(s11_db))
    f_res = float(freq[i_min])
    s11_min = float(s11_db[i_min])

    def at(fg):
        return float(np.interp(fg * 1e9, freq, s11_db))

    s_140, s_150, s_200, s_250 = at(24.14), at(24.15), at(24.20), at(24.25)

    # acceptance: |S11| <= -10 dB across 24.150-24.250 GHz
    band = (freq >= 24.150e9) & (freq <= 24.250e9)
    band_max = float(np.max(s11_db[band]))
    accept = band_max <= -10.0
    res_ok = abs(f_res - 24.20e9) <= 0.05e9

    print()
    print(f"Patch W={PATCH_W:.4f} L={PATCH_L:.4f} inset={INSET_DEPTH:.4f} "
          f"gap={INSET_GAP:.3f} mm")
    print(f"resonance f_res = {f_res / 1e9:.4f} GHz  (|S11|={s11_min:.2f} dB)")
    print(f"  centered 24.20 +/-0.05 : {'ok' if res_ok else 'OFF'}")
    print(f"S11 @ 24.140 GHz = {s_140:7.2f} dB")
    print(f"S11 @ 24.150 GHz = {s_150:7.2f} dB")
    print(f"S11 @ 24.200 GHz = {s_200:7.2f} dB")
    print(f"S11 @ 24.250 GHz = {s_250:7.2f} dB")
    print(f"worst |S11| in 24.150-24.250 = {band_max:7.2f} dB")
    print(f"S-parameter sweep written to {out_csv}")
    print("ACCEPTANCE:", "PASS" if accept else "FAIL",
          "(|S11| <= -10 dB across band)")

    far_field = None
    gain_dbi = None
    directivity_dbi = None
    if nf2ff is not None:
        theta_deg, phi_deg = nf2ff_angles_deg(step_deg=2.0)
        nf = nf2ff.CalcNF2FF(
            sim_path,
            np.array([F0]),
            np.asarray(theta_deg),
            np.asarray(phi_deg),
            center=coords["far_field_domain"]["phase_center_m"],
            read_cached=False,
        )
        directivity_linear = float(nf.Dmax[0])
        directivity_dbi = float(10.0 * np.log10(directivity_linear))
        far_field = assess_far_field(
            radiated_power_w=float(nf.Prad[0]),
            accepted_power_w=float(np.interp(F0, freq, port.P_acc)),
            directivity_linear=directivity_linear,
            angular_grid_complete=True,
        )
        if far_field["valid"]:
            gain_dbi = gain_dbi_from_directivity(
                directivity_linear=directivity_linear,
                radiation_efficiency=far_field["radiation_efficiency"],
            )
            print(f"peak directivity = {directivity_dbi:.2f} dBi")
            print(f"radiation efficiency = {far_field['radiation_efficiency']:.3f}")
            print(f"peak gain = {gain_dbi:.2f} dBi")
        else:
            print(f"far field = INVALID: {far_field['reason']}")

        with open(
            os.path.join(sim_path, "patch_farfield_canary.json"),
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                {
                    "s11_accept": accept,
                    "far_field": far_field,
                    "directivity_dbi": directivity_dbi,
                    "gain_dbi": gain_dbi,
                    "domain": coords["far_field_domain"],
                },
                file,
                indent=2,
            )

    # emit a compact machine-readable summary the driver can parse per-iter
    print("SUMMARY_JSON:" + json.dumps({
        "W_mm": PATCH_W, "L_mm": PATCH_L, "inset_mm": INSET_DEPTH,
        "f_res_ghz": f_res / 1e9, "s11_min_db": s11_min,
        "s11_24p14": s_140, "s11_24p15": s_150,
        "s11_24p20": s_200, "s11_24p25": s_250,
        "band_max_db": band_max, "accept": accept,
    }))
    far_field_accept = far_field is None or far_field["valid"]
    sys.exit(0 if accept and far_field_accept else 2)


if __name__ == "__main__":
    main()
