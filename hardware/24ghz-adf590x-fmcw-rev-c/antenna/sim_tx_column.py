#!/usr/bin/env python3
r"""openEMS TX 1x4 series-fed patch column, 24.2 GHz (RO4350B, h=0.254 mm).

Design intent (Rev C, Task 7)
-----------------------------
Four identical rectangular patches stacked vertically (along +y) and joined,
radiating-edge to radiating-edge, by high-impedance series links. The column is
fed at the bottom by a 50 ohm inset feed into the bottom patch (the validated
element inset from results/patch_element.json applies only to how the BOTTOM
feed attaches). The inter-patch links attach at the radiating-edge *centres*
(the point of maximum edge current / voltage antinode) and carry the travelling
wave up the column.

Series-fed phasing
------------------
A rectangular patch is a half-wave (lambda_g/2) resonator: the voltage/current
at its two radiating edges are 180 deg out of phase along the patch. To make all
four patches radiate in phase (broadside beam), the connecting link between the
top edge of patch n and the bottom edge of patch n+1 must add another 180 deg,
i.e. link electrical length ~= lambda_g/2 on the LINK line. Equivalently the
patch-centre-to-patch-centre spacing along the feed axis is ~= lambda_g so the
excitation phase repeats every element. Here:

  * The patch itself contributes ~180 deg (edge-to-edge).
  * A LINK_LG_FRAC * lambda_g(link) connecting line contributes the rest.

We size the link so the total per-element phase is ~360 deg (in-phase stacking).
Because the patch resonant length is fixed (~lambda_g_patch/2) and the link runs
on a narrow high-Z line (different er_eff, hence different lambda_g), the link
physical length is computed from the link-line lambda_g, not the patch's.

The links are HIGH impedance (~100 ohm, w ~= 0.14-0.16 mm) so they present a
large series impedance relative to the ~radiating-edge resistance, minimising
their loading/radiation and keeping each patch near resonance. The bottom feed
is a standard 50 ohm inset (reused element geometry) so the port sees ~50 ohm
when the four-patch travelling-wave load transforms through the bottom inset.

Frequency scanning
-------------------
Series-fed columns beam-scan with frequency: the progressive phase per element
is 360 deg only at the design frequency, and drifts +/- with f, squinting the
beam off broadside. Acceptance is broadside +/- 3 deg at 24.2 GHz; the band-edge
squint (24.15 / 24.25 GHz) is reported as data, not gated.

EIRP check
----------
EIRP = ADF5901 PA output power + simulated column gain. PA output = +8 dBm typ
(min 2, max 10 dBm), 50 ohm single-ended -- adf5901.md line 67/97, Table 1 p.3.
Flagged if EIRP > +20 dBm (FCC 15.245/15.249 check).

Acceptance (Task 7 brief)
-------------------------
  * |S11| <= -10 dB across 24.150-24.250 GHz
  * broadside gain ~= 10-12 dBi
  * main beam within broadside +/- 3 deg at 24.2 GHz
Also reports S11 at 24.140 GHz and beam angle at band edges.

Port / mesh / excitation conventions copied from sim_patch.py & sim_subarray.py:
openEMS(EndCriteria) energy stop, SetGaussExcite, PML_8 on the bottom-feed
(propagation, -y) ends + MUR elsewhere + PEC ground at zmin, lambda/20 dielectric
mesh with thirds-rule edge refinement, MSL bottom port with FeedShift /
MeasPlaneShift de-embedding, NF2FF box for gain + beam angle.

Invocation (from repo root):
    docker run --rm -v "$PWD":/work -w /work openems-local \
        python3 hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_tx_column.py
Optional overrides: SIM_OUT_DIR, MESH_DIV (outer-mesh coarsening), END_CRIT,
L_TRIM_MM (uniform patch-length trim), LINK_LG_FRAC (link length in lambda_g of
the link line), LINK_Z (link impedance ohm), SKIP_SIM (post-process only).
"""

import json
import os
import sys

import numpy as np

from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0, EPS0

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_design import microstrip_width, eff_permittivity  # noqa: E402
from subarray_geometry import (  # noqa: E402
    assess_far_field,
    build_nf2ff_domain,
    gain_dbi_from_directivity,
    nf2ff_angles_deg,
    pattern_metrics,
)

HERE = os.path.dirname(os.path.abspath(__file__))
DATASHEET = os.path.join(
    os.path.dirname(HERE), "datasheets", "extracted", "adf5901.md")


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


# ----------------------------------------------------------------------------
# Validated element geometry (never hardcode)
# ----------------------------------------------------------------------------
with open(os.path.join(HERE, "results", "patch_element.json"),
          encoding="utf-8") as _f:
    ELEM = json.load(_f)

UNIT = 1e-3
SUB_EPS_R = ELEM["substrate"]["er"]
SUB_TAN_D = ELEM["substrate"]["tand"]
SUB_H = ELEM["substrate"]["h_mm"]

# Uniform patch-length trim (in-array resonance sits slightly below standalone
# due to the series links loading the radiating edges). Default 0.0; tunable.
L_TRIM_MM = float(os.environ.get("L_TRIM_MM", "0.0"))
PATCH_W = ELEM["W_mm"]                    # non-resonant edge (x extent here)
PATCH_L = ELEM["L_mm"] + L_TRIM_MM        # resonant length (y extent, feed axis)
INSET_DEPTH = float(os.environ.get("INSET_MM", str(ELEM["inset_mm"])))  # notch
FEED_W = ELEM["feed_w_mm"]                # 50 ohm feed width
INSET_GAP = ELEM["inset_gap_mm"]

# ----------------------------------------------------------------------------
# Frequency setup
# ----------------------------------------------------------------------------
F_START = 22.0e9
F_STOP = 26.0e9
F0 = 24.2e9
FC = 8e9

SUB_KAPPA = SUB_TAN_D * 2 * np.pi * F0 * EPS0 * SUB_EPS_R

MESH_DIV = float(os.environ.get("MESH_DIV", "20"))
MESH_RES = C0 / (F_STOP * np.sqrt(SUB_EPS_R)) / UNIT / MESH_DIV
EDGE_RES = FEED_W / 4.0
END_CRIT = float(os.environ.get("END_CRIT", "1e-4"))

# ----------------------------------------------------------------------------
# Series link (high-Z) sizing -- script-computed
# ----------------------------------------------------------------------------
LINK_Z = float(os.environ.get("LINK_Z", "100.0"))          # ohm
LINK_W = microstrip_width(LINK_Z, SUB_EPS_R, SUB_H * 1e-3) * 1e3  # mm
ER_EFF_LINK = eff_permittivity(SUB_EPS_R, LINK_W * 1e-3, SUB_H * 1e-3)
LAMBDA_G_LINK = (C0 / F0) / np.sqrt(ER_EFF_LINK) * 1e3     # mm

# Link electrical length in units of lambda_g(link). A patch contributes ~180
# deg edge-to-edge; the link must add the remaining ~180 deg for in-phase
# stacking -> ~lambda_g/2. Default 0.5; tunable to co-phase the column.
LINK_LG_FRAC = float(os.environ.get("LINK_LG_FRAC", "0.5"))
LINK_LEN = LINK_LG_FRAC * LAMBDA_G_LINK                    # mm

N_PATCH = 4

# ----------------------------------------------------------------------------
# Layout: column runs along +y; patches centred on x=0. Fed at the bottom
# (-y) by a 50 ohm inset feed into the bottom patch's -y radiating edge.
# Each patch occupies PATCH_L in y (resonant) and PATCH_W in x (non-resonant).
# Link connects a patch's +y edge centre to the next patch's -y edge centre.
# ----------------------------------------------------------------------------
# Patch n (0=bottom): its -y radiating edge sits at y_edge_lo[n].
# Bottom patch -y edge at y=0. Successive patches: +PATCH_L (this patch) then
# +LINK_LEN (link) to reach the next patch's -y edge.
PITCH = PATCH_L + LINK_LEN                                 # centre-to-centre, mm

Y_EDGE_LO = [n * PITCH for n in range(N_PATCH)]            # -y edge of patch n
Y_EDGE_HI = [ylo + PATCH_L for ylo in Y_EDGE_LO]          # +y edge of patch n

# bottom feed: inset into the bottom patch -y edge, then a 50 ohm feed to port.
Y_BOT_EDGE = Y_EDGE_LO[0]                                  # = 0
Y_INSET_END = Y_BOT_EDGE + INSET_DEPTH                     # notch base
FEED_LEN = 5.0                                             # 50R feed to port, mm
Y_PORT = Y_BOT_EDGE - FEED_LEN

AIR_ABOVE = 3.0
MARGIN = 3.0


def hbox(metal, x0, x1, y0, y1):
    metal.AddBox([min(x0, x1), min(y0, y1), SUB_H],
                 [max(x0, x1), max(y0, y1), SUB_H], priority=10)


def add_patch(metal, y_lo, y_hi, inset=False):
    """One patch spanning y in [y_lo, y_hi], x in [-W/2, +W/2].

    If inset, cut a notch from the -y edge (the bottom-feed patch only) so the
    50 ohm feed can inset. Otherwise a solid rectangle; series links attach at
    the edge centres.
    """
    x_min, x_max = -PATCH_W / 2.0, PATCH_W / 2.0
    if not inset:
        hbox(metal, x_min, x_max, y_lo, y_hi)
        return
    # inset notch on the -y edge around the feed width
    x_feed = FEED_W / 2.0
    x_notch = x_feed + INSET_GAP
    y_base = y_lo + INSET_DEPTH
    # main body from notch base to +y edge
    hbox(metal, x_min, x_max, y_base, y_hi)
    # side strips flanking the notch over [y_lo, y_base]
    hbox(metal, x_notch, x_max, y_lo, y_base)
    hbox(metal, x_min, -x_notch, y_lo, y_base)


def add_link(metal, y0, y1):
    """High-Z series link along y at x=0, connecting two radiating-edge centres.

    Overlap one edge-cell into each patch so the link and patches share metal
    cells regardless of mesh snapping at the junctions.
    """
    over = EDGE_RES
    hbox(metal, -LINK_W / 2.0, LINK_W / 2.0, y0 - over, y1 + over)


def build(sim_path):
    fdtd = openEMS(EndCriteria=END_CRIT,
                   NrTS=int(os.environ.get("NRTS", "800000")))
    fdtd.SetGaussExcite(F0, FC)
    fdtd.SetBoundaryCond(["MUR"] * 6)

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(UNIT)

    x_sub_min = -PATCH_W / 2.0 - MARGIN
    x_sub_max = PATCH_W / 2.0 + MARGIN
    y_sub_min = Y_PORT - MARGIN
    y_sub_max = Y_EDGE_HI[-1] + MARGIN
    domain = build_nf2ff_domain(
        structure_start_mm=(x_sub_min, y_sub_min, 0.0),
        structure_stop_mm=(x_sub_max, y_sub_max, SUB_H),
        air_clearance_mm=AIR_ABOVE,
        nf2ff_clearance_mm=2.0 * MESH_RES,
    )

    third = np.array([-EDGE_RES / 3.0, 2.0 * EDGE_RES / 3.0])

    # --- mesh: x (transverse) ------------------------------------------------
    mesh.AddLine(
        "x",
        [
            domain["simulation_start_mm"][0],
            x_sub_min,
            0.0,
            x_sub_max,
            domain["simulation_stop_mm"][0],
        ],
    )
    x_edges = {-PATCH_W / 2.0, PATCH_W / 2.0,
               -FEED_W / 2.0, FEED_W / 2.0,
               -LINK_W / 2.0, LINK_W / 2.0}
    x_feed = FEED_W / 2.0
    x_notch = x_feed + INSET_GAP
    x_edges.update([x_notch, -x_notch])
    for xe in x_edges:
        mesh.AddLine("x", xe + third)
        mesh.AddLine("x", xe - third[::-1])
    mesh.SmoothMeshLines("x", MESH_RES, 1.4)

    # --- mesh: y (feed propagation axis) -------------------------------------
    mesh.AddLine(
        "y",
        [
            domain["simulation_start_mm"][1],
            y_sub_min,
            Y_PORT,
            y_sub_max,
            domain["simulation_stop_mm"][1],
        ],
    )
    y_edges = set()
    for ylo, yhi in zip(Y_EDGE_LO, Y_EDGE_HI):
        y_edges.update([ylo, yhi])
    y_edges.update([Y_INSET_END])
    for ye in y_edges:
        mesh.AddLine("y", ye + third)
        mesh.AddLine("y", ye - third[::-1])
    mesh.SmoothMeshLines("y", MESH_RES, 1.4)

    # --- mesh: z -------------------------------------------------------------
    mesh.AddLine("z", np.linspace(0, SUB_H, 5))
    mesh.AddLine(
        "z",
        [domain["simulation_start_mm"][2], domain["simulation_stop_mm"][2]],
    )
    mesh.SmoothMeshLines("z", MESH_RES, 1.4)

    # --- substrate -----------------------------------------------------------
    substrate = csx.AddMaterial("RO4350B", epsilon=SUB_EPS_R, kappa=SUB_KAPPA)
    substrate.AddBox([x_sub_min, y_sub_min, 0], [x_sub_max, y_sub_max, SUB_H])

    ground = csx.AddMetal("ground")
    ground.AddBox([x_sub_min, y_sub_min, 0], [x_sub_max, y_sub_max, 0], priority=10)

    # --- patches + links -----------------------------------------------------
    metal = csx.AddMetal("column")
    for n in range(N_PATCH):
        add_patch(metal, Y_EDGE_LO[n], Y_EDGE_HI[n], inset=(n == 0))
    for n in range(N_PATCH - 1):
        add_link(metal, Y_EDGE_HI[n], Y_EDGE_LO[n + 1])

    # --- bottom 50 ohm feed into the inset notch -----------------------------
    # The MSL port draws its own metal from Y_PORT to Y_BOT_EDGE; extend the
    # feed metal into the notch so it contacts the patch body at Y_INSET_END.
    feed = csx.AddMetal("feed")
    hbox(feed, -FEED_W / 2.0, FEED_W / 2.0,
         Y_BOT_EDGE, Y_INSET_END + EDGE_RES)

    # --- MSL bottom port (excited) -------------------------------------------
    port = fdtd.AddMSLPort(
        1, csx.AddMetal("feed_port"),
        [-FEED_W / 2.0, Y_PORT, SUB_H],
        [FEED_W / 2.0, Y_BOT_EDGE, 0],
        "y", "z",
        excite=-1,
        FeedShift=8 * MESH_RES,
        MeasPlaneShift=3.5,   # > FeedShift, on the 50R feed before the patch
        priority=10,
    )

    # --- NF2FF box for gain + beam scan --------------------------------------
    nf2ff = fdtd.CreateNF2FFBox(
        "nf2ff",
        domain["nf2ff_start_mm"],
        domain["nf2ff_stop_mm"],
    )
    return fdtd, port, nf2ff, domain


def analyze_far_field(nf2ff, sim_path, frequencies_hz, port_freq, port_pacc, center):
    """Calculate gain and beam direction from one full-sphere NF2FF result."""
    theta_deg, phi_deg = nf2ff_angles_deg(step_deg=2.0)
    nf = nf2ff.CalcNF2FF(
        sim_path,
        np.asarray(frequencies_hz),
        np.asarray(theta_deg),
        np.asarray(phi_deg),
        center=center,
        read_cached=False,
    )

    results = []
    for index, frequency_hz in enumerate(frequencies_hz):
        directivity_linear = float(nf.Dmax[index])
        far_field = assess_far_field(
            radiated_power_w=float(nf.Prad[index]),
            accepted_power_w=float(np.interp(frequency_hz, port_freq, port_pacc)),
            directivity_linear=directivity_linear,
            angular_grid_complete=True,
        )
        pattern = pattern_metrics(
            theta_deg=theta_deg,
            phi_deg=phi_deg,
            e_norm=nf.E_norm[index],
            directivity_linear=directivity_linear,
        )
        peak_gain_dbi = None
        broadside_gain_dbi = None
        if far_field["valid"]:
            peak_gain_dbi = gain_dbi_from_directivity(
                directivity_linear=pattern["peak_directivity_linear"],
                radiation_efficiency=far_field["radiation_efficiency"],
            )
            broadside_gain_dbi = gain_dbi_from_directivity(
                directivity_linear=pattern["broadside_directivity_linear"],
                radiation_efficiency=far_field["radiation_efficiency"],
            )
        results.append(
            {
                "frequency_hz": float(frequency_hz),
                "far_field": far_field,
                "pattern": pattern,
                "peak_gain_dbi": peak_gain_dbi,
                "broadside_gain_dbi": broadside_gain_dbi,
            }
        )
    return results


def main():
    sim_path = os.environ.get("SIM_OUT_DIR",
                              os.path.join(HERE, "results", "tx_column"))
    os.makedirs(sim_path, exist_ok=True)

    fdtd, port, nf2ff, domain = build(sim_path)
    if not os.environ.get("SKIP_SIM"):
        fdtd.Run(sim_path, verbose=1, cleanup=True)

    # --- S11 -----------------------------------------------------------------
    freq = np.linspace(F_START, F_STOP, 401)
    port.CalcPort(sim_path, freq, ref_impedance=50)
    s11 = port.uf_ref / port.uf_inc
    s11_db = 20 * np.log10(np.abs(s11))
    zin = port.uf_tot / port.if_tot

    def at(fg):
        return float(np.interp(fg * 1e9, freq, s11_db))

    # Zin diagnostic table (helps distinguish transformer mistune from
    # near-short/near-open traps).
    print("f(GHz)  |S11|dB   Zin(Re+jIm)")
    for fg in (23.5, 24.0, 24.14, 24.2, 24.25, 25.0):
        i = int(np.argmin(np.abs(freq - fg * 1e9)))
        print(f"{fg:6.2f}  {s11_db[i]:7.2f}   "
              f"{zin[i].real:8.2f} {zin[i].imag:+8.2f}j")

    s_140, s_150, s_200, s_250 = at(24.14), at(24.15), at(24.20), at(24.25)
    band = (freq >= 24.150e9) & (freq <= 24.250e9)
    band_max = float(np.max(s11_db[band]))
    s11_accept = bool(band_max <= -10.0)
    i_min = int(np.argmin(s11_db))
    f_res = float(freq[i_min] / 1e9)

    # --- full-sphere gain + beam angle vs frequency --------------------------
    ff_150, ff_200, ff_250 = analyze_far_field(
        nf2ff,
        sim_path,
        (24.15e9, 24.20e9, 24.25e9),
        freq,
        port.P_acc,
        domain["phase_center_m"],
    )
    far_field_accept = all(item["far_field"]["valid"] for item in (ff_150, ff_200, ff_250))
    gain_dbi = ff_200["peak_gain_dbi"]
    gain_bs_dbi = ff_200["broadside_gain_dbi"]
    th_150 = ff_150["pattern"]["signed_y_beam_deg"]
    th_200 = ff_200["pattern"]["signed_y_beam_deg"]
    th_250 = ff_250["pattern"]["signed_y_beam_deg"]
    gain_accept = bool(
        far_field_accept and gain_dbi is not None and 10.0 <= gain_dbi <= 12.0
    )
    beam_accept = bool(
        far_field_accept and ff_200["pattern"]["beam_offset_deg"] <= 3.0
    )

    def ang(th):
        return round(float(th), 2)

    # --- EIRP check ----------------------------------------------------------
    # ADF5901 PA output +8 dBm typ (min 2, max 10), 50 ohm single-ended.
    # adf5901.md line 67 / line 97, Table 1 p.3.
    PA_DBM = 8.0
    eirp_dbm = None if gain_dbi is None else PA_DBM + gain_dbi
    eirp_flag = bool(eirp_dbm is not None and eirp_dbm > 20.0)

    # --- assemble results JSON ----------------------------------------------
    result = {
        "element": ELEM,
        "pitch_mm": round(PITCH, 4),
        "feed_topology": (
            "1x4 series-fed patch column. Four identical patches stacked along "
            "+y, joined radiating-edge-centre to radiating-edge-centre by "
            f"high-Z ({LINK_Z:.0f} ohm, w={LINK_W:.4f} mm) series links of "
            f"length {LINK_LEN:.4f} mm (~{LINK_LG_FRAC:.3f} lambda_g on the link "
            "line). Each patch is a lambda_g/2 resonator contributing ~180 deg "
            "edge-to-edge; the ~lambda_g/2 link adds the remaining ~180 deg so "
            "all four patches excite in phase (broadside). Fed at the bottom by "
            "a 50 ohm inset feed into the bottom patch's -y radiating edge "
            "(element inset reused). Series-fed columns beam-scan with frequency: "
            "the beam squints off broadside as f moves; broadside is targeted at "
            "24.2 GHz."
        ),
        "feed_tree": [
            {"seg": "series_link", "w_mm": round(LINK_W, 4),
             "l_mm": round(LINK_LEN, 4), "z_ohm": round(LINK_Z, 2),
             "count": N_PATCH - 1},
            {"seg": "bottom_feed_50", "w_mm": round(FEED_W, 4),
             "l_mm": round(FEED_LEN, 4), "z_ohm": 50.0},
        ],
        "link": {
            "z_ohm": round(LINK_Z, 3),
            "w_mm": round(LINK_W, 4),
            "len_mm": round(LINK_LEN, 4),
            "lg_frac": round(LINK_LG_FRAC, 4),
            "lambda_g_link_mm": round(LAMBDA_G_LINK, 4),
            "er_eff_link": round(ER_EFF_LINK, 4),
        },
        "port_s11_db": {
            "24.14": round(s_140, 2), "24.15": round(s_150, 2),
            "24.20": round(s_200, 2), "24.25": round(s_250, 2),
            "band_max_24.15_24.25": round(band_max, 2),
        },
        "f_res_ghz": round(f_res, 4),
        "gain_dbi_est": None if gain_dbi is None else round(gain_dbi, 2),
        "gain_broadside_dbi": (
            None if gain_bs_dbi is None else round(gain_bs_dbi, 2)
        ),
        "beam_angle_deg": {
            "24.15": ang(th_150), "24.20": ang(th_200), "24.25": ang(th_250),
        },
        "beam_peak_dbi": {
            "24.15": None if ff_150["peak_gain_dbi"] is None else round(ff_150["peak_gain_dbi"], 2),
            "24.20": None if gain_dbi is None else round(gain_dbi, 2),
            "24.25": None if ff_250["peak_gain_dbi"] is None else round(ff_250["peak_gain_dbi"], 2),
        },
        "far_field": {
            "24.15": ff_150,
            "24.20": ff_200,
            "24.25": ff_250,
        },
        "far_field_domain": domain,
        "extent_mm": [round(PATCH_W, 3),
                      round(Y_EDGE_HI[-1] - Y_PORT, 3)],
        "eirp_check": {
            "pa_dbm": PA_DBM,
            "pa_citation": ("ADF5901 Tx output power +8 dBm typ (min 2, max 10),"
                            " 50 ohm single-ended -- datasheets/extracted/"
                            "adf5901.md line 67 & 97, Table 1 p.3"),
            "gain_dbi": None if gain_dbi is None else round(gain_dbi, 2),
            "eirp_dbm": None if eirp_dbm is None else round(eirp_dbm, 2),
            "exceeds_20dbm": eirp_flag,
        },
        "acceptance": {
            "s11": s11_accept,
            "far_field": far_field_accept,
            "gain": gain_accept,
            "beam": beam_accept,
        },
    }
    if L_TRIM_MM != 0.0:
        result["L_trim_mm"] = round(L_TRIM_MM, 4)

    # --- report --------------------------------------------------------------
    print()
    print(f"Link: Z={LINK_Z:.1f}R  w={LINK_W:.4f} mm  len={LINK_LEN:.4f} mm "
          f"(~{LINK_LG_FRAC:.3f} lg_link; lg_link={LAMBDA_G_LINK:.4f})")
    print(f"pitch (centre-centre) = {PITCH:.4f} mm  (patch_L={PATCH_L:.4f} + "
          f"link={LINK_LEN:.4f})")
    print(f"resonance f_res = {f_res:.4f} GHz")
    print(f"S11 @24.14={s_140:.2f} @24.15={s_150:.2f} "
          f"@24.20={s_200:.2f} @24.25={s_250:.2f} dB")
    print(f"worst |S11| 24.15-24.25 = {band_max:.2f} dB -> "
          f"{'PASS' if s11_accept else 'FAIL'}")
    if far_field_accept:
        print(f"broadside gain @24.2 = {gain_bs_dbi:.2f} dBi; "
              f"peak = {gain_dbi:.2f} dBi @ theta={th_200:.2f} deg")
        print(
            f"radiation efficiency @24.2 = "
            f"{ff_200['far_field']['radiation_efficiency']:.3f}"
        )
    else:
        print(f"far field = INVALID: {ff_200['far_field']['reason']}")
    print(f"gain 10-12 dBi -> {'PASS' if gain_accept else 'FAIL'}; "
          f"beam +/-3 deg -> {'PASS' if beam_accept else 'FAIL'}")
    print(f"beam angle: @24.15={th_150:.2f}  @24.20={th_200:.2f}  "
          f"@24.25={th_250:.2f} deg (frequency scan)")
    if eirp_dbm is not None:
        print(f"EIRP = PA {PA_DBM:.1f} dBm + gain {gain_dbi:.2f} dBi = "
              f"{eirp_dbm:.2f} dBm  {'[>20 dBm FLAG]' if eirp_flag else ''}")
    print("SUMMARY_JSON:" + json.dumps({
        "band_max_db": band_max, "s11_accept": s11_accept,
        "far_field_accept": far_field_accept,
        "gain_dbi": gain_dbi, "gain_accept": gain_accept,
        "beam_deg": th_200, "beam_accept": beam_accept,
        "f_res_ghz": f_res, "eirp_dbm": eirp_dbm, "eirp_flag": eirp_flag,
    }))

    out_json = os.path.join(HERE, "results", "tx_column.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=_json_default)
    print(f"results -> {out_json}")

    ok = s11_accept and far_field_accept and gain_accept and beam_accept
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
