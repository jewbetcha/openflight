#!/usr/bin/env python3
"""openEMS canary simulation: 50 ohm microstrip through-line at 24 GHz.

Purpose
-------
Validate the openEMS toolchain and the port/excitation/mesh pattern that the
Rev C patch-antenna sims (tasks 5-8) copy. Models a straight 50 ohm microstrip
line and checks that it is well matched and low loss across 20-28 GHz.

Structure (RO4350B design values)
---------------------------------
  substrate:  h = 0.254 mm, eps_r = 3.66, tan_d = 0.0037
  trace:      10 mm between measurement planes, width 0.55 mm (~50 ohm)
  ground:     PEC boundary at z = 0 (bottom face of the substrate)
  ports:      two MSL ports (port 1 = excited feed, port 2 = passive through)
  sweep:      20-28 GHz, acceptance evaluated at 24.2 GHz

Acceptance
----------
  |S21| > -1 dB   AND   |S11| < -15 dB  at 24.2 GHz  -> PASS

Environment (which path worked)
-------------------------------
openEMS here is the thliebig FDTD electromagnetics engine (NOT the Java
"OpenEMS" energy-management project of the same name on Docker Hub).

Install attempts on this machine (macOS arm64, Apple Silicon, 2026-07-01):

  1. brew install micromamba                       -> OK (2.8.1)
  2. micromamba create -y -n openems -c conda-forge python=3.11 openems csxcad
     -> FAIL: "openems/csxcad does not exist". Verified via micromamba search
     (osx-arm64, osx-64, linux-64) and api.anaconda.org: these packages were
     never published to conda-forge or any anaconda.org channel, so the
     python=3.10 and CONDA_SUBDIR=osx-64 retries were moot.
  3. docker pull ghcr.io/thliebig/openems:latest   -> FAIL: manifest denied
     (no such public image on GHCR).
  4. docker pull mwolleben/openems:2 (Docker Hub)  -> pulled, but Octave-only:
     `import openEMS` raises ModuleNotFoundError. Discarded.
  5. PyPI: no openEMS FDTD package published.
  6. Build from source in Docker (WORKING PATH): see
     hardware/24ghz-adf590x-fmcw-rev-c/antenna/docker/Dockerfile, which builds
     thliebig/openEMS-Project (CSXCAD + engine + Python bindings) on Ubuntu
     22.04, native linux/arm64 under OrbStack.

Invocation for all sim tasks (4-8), run from the repo root:

    docker build -t openems-local hardware/24ghz-adf590x-fmcw-rev-c/antenna/docker
    docker run --rm -v "$PWD":/work -w /work openems-local \
        python3 hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_canary.py

The image build is one-time; only the `docker run` line is needed per sim.

Port/mesh pattern for tasks 5-8 to copy
---------------------------------------
  - openEMS(EndCriteria=1e-4) (-40 dB energy stop), SetGaussExcite(f0, fc)
    with the sweep band well inside f0 +/- fc.
  - Boundaries: PML_8 on the propagation-axis ends, MUR on the sides/top,
    PEC at zmin acting as the microstrip ground plane.
  - Mesh: lambda/20 in the dielectric at f_max, thirds-rule refinement at the
    trace edges, >= 4 cells through the substrate thickness.
  - Ports via FDTD.AddMSLPort() with the port box spanning strip (z = h) down
    to ground (z = 0); FeedShift moves the excitation out of the PML and
    MeasPlaneShift de-embeds the reference plane into the line.
  - S-params from Port.CalcPort(sim_path, freq, ref_impedance=50), then
    s11 = P1.uf_ref/P1.uf_inc, s21 = P2.uf_ref/P1.uf_inc (port 2 faces -x, so
    the transmitted +x wave lands in its "reflected" decomposition -- same
    convention as the official openEMS MSL tutorial).
"""

import os
import sys

import numpy as np

from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0, EPS0

# ----------------------------------------------------------------------------
# Geometry / stackup (drawing unit = 1 mm)
# ----------------------------------------------------------------------------
UNIT = 1e-3

SUB_EPS_R = 3.66
SUB_TAN_D = 0.0037
SUB_H = 0.254            # substrate height, mm

MSL_W = 0.55             # trace width, mm (~50 ohm on this stackup)
MSL_LEN = 20.0           # total modeled strip length, mm
MEAS_SHIFT = 5.0         # meas-plane inset from each end -> 10 mm DUT
SUB_W = 15 * MSL_W       # half-width of substrate/air region in y, mm
AIR_ABOVE = 3.0          # air above the substrate, mm

# ----------------------------------------------------------------------------
# Frequency setup
# ----------------------------------------------------------------------------
F_START = 20e9
F_STOP = 28e9
F_TARGET = 24.2e9
F0 = 24e9                # Gauss center
FC = 8e9                 # 20 dB band edges at 16/32 GHz -> sweep well inside

# dielectric loss as conductivity at band center
SUB_KAPPA = SUB_TAN_D * 2 * np.pi * F0 * EPS0 * SUB_EPS_R  # S/m

# mesh resolution: lambda/20 in the dielectric at the top frequency (mm)
MESH_RES = C0 / (F_STOP * np.sqrt(SUB_EPS_R)) / UNIT / 20.0
EDGE_RES = MSL_W / 8.0   # fine mesh at the trace edges


def build_sim():
    """Construct the FDTD problem; return (fdtd, ports)."""
    fdtd = openEMS(EndCriteria=1e-4, NrTS=400000)
    fdtd.SetGaussExcite(F0, FC)
    # PML on the x (propagation) ends; MUR sides/top; PEC ground at zmin.
    fdtd.SetBoundaryCond(["PML_8", "PML_8", "MUR", "MUR", "PEC", "MUR"])

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(UNIT)

    # --- mesh: propagation axis (x) ------------------------------------------
    mesh.AddLine("x", [-MSL_LEN / 2, 0, MSL_LEN / 2])
    mesh.SmoothMeshLines("x", MESH_RES, 1.4)

    # --- mesh: transverse (y), thirds rule at the trace edges ----------------
    third = np.array([-EDGE_RES / 3, 2 * EDGE_RES / 3])
    mesh.AddLine("y", 0)
    mesh.AddLine("y", MSL_W / 2 + third)
    mesh.AddLine("y", -MSL_W / 2 - third)
    mesh.AddLine("y", [-SUB_W, SUB_W])
    mesh.SmoothMeshLines("y", MESH_RES, 1.4)

    # --- mesh: vertical (z), 4 cells through the substrate + air above -------
    mesh.AddLine("z", np.linspace(0, SUB_H, 5))
    mesh.AddLine("z", SUB_H + AIR_ABOVE)
    mesh.SmoothMeshLines("z", MESH_RES, 1.4)

    # --- substrate ------------------------------------------------------------
    substrate = csx.AddMaterial("RO4350B", epsilon=SUB_EPS_R, kappa=SUB_KAPPA)
    substrate.AddBox([-MSL_LEN / 2, -SUB_W, 0], [MSL_LEN / 2, SUB_W, SUB_H])

    # --- MSL ports (each draws its half of the strip metal) -------------------
    # The port box spans the strip width in y and strip-to-ground in z.
    # Port 1 points +x from the left end (excited); port 2 points -x from the
    # right end (passive). FeedShift keeps the excitation clear of the PML;
    # MeasPlaneShift de-embeds the reference planes 5 mm in from each end.
    pec = csx.AddMetal("PEC_strip")
    ports = [None, None]
    ports[0] = fdtd.AddMSLPort(
        1, pec,
        [-MSL_LEN / 2, -MSL_W / 2, SUB_H], [0, MSL_W / 2, 0],
        "x", "z",
        excite=-1,
        FeedShift=10 * MESH_RES,
        MeasPlaneShift=MEAS_SHIFT,
        priority=10,
    )
    ports[1] = fdtd.AddMSLPort(
        2, pec,
        [MSL_LEN / 2, -MSL_W / 2, SUB_H], [0, MSL_W / 2, 0],
        "x", "z",
        MeasPlaneShift=MEAS_SHIFT,
        priority=10,
    )
    return fdtd, ports


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    sim_path = os.environ.get("SIM_OUT_DIR",
                              os.path.join(here, "results", "canary"))
    os.makedirs(sim_path, exist_ok=True)

    fdtd, ports = build_sim()
    fdtd.Run(sim_path, verbose=1, cleanup=True)

    freq = np.linspace(F_START, F_STOP, 401)  # 20 MHz step; hits 24.2 exactly
    for port in ports:
        port.CalcPort(sim_path, freq, ref_impedance=50)

    s11 = ports[0].uf_ref / ports[0].uf_inc
    s21 = ports[1].uf_ref / ports[0].uf_inc
    s11_db = 20 * np.log10(np.abs(s11))
    s21_db = 20 * np.log10(np.abs(s21))

    out_csv = os.path.join(sim_path, "canary_sparams.csv")
    np.savetxt(out_csv, np.column_stack([freq, s11_db, s21_db]),
               delimiter=",", header="freq_hz,s11_db,s21_db", comments="")

    s11_at = float(np.interp(F_TARGET, freq, s11_db))
    s21_at = float(np.interp(F_TARGET, freq, s21_db))

    print()
    print(f"S11 @ {F_TARGET / 1e9:.2f} GHz = {s11_at:7.2f} dB")
    print(f"S21 @ {F_TARGET / 1e9:.2f} GHz = {s21_at:7.2f} dB")
    print(f"S-parameter sweep written to {out_csv}")

    s21_ok = s21_at > -1.0
    s11_ok = s11_at < -15.0
    print(f"  criterion |S21| > -1 dB : {s21_at:7.2f} dB -> "
          f"{'ok' if s21_ok else 'FAIL'}")
    print(f"  criterion |S11| < -15 dB: {s11_at:7.2f} dB -> "
          f"{'ok' if s11_ok else 'FAIL'}")
    print("RESULT:", "PASS" if (s21_ok and s11_ok) else "FAIL")
    sys.exit(0 if (s21_ok and s11_ok) else 1)


if __name__ == "__main__":
    main()
