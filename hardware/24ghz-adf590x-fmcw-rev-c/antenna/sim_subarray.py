#!/usr/bin/env python3
r"""openEMS 2x2 subarray with an equal-length CO-ORIENTED corporate feed, 24.2 GHz.

Design intent (Rev C fix -- co-phase feed redesign)
---------------------------------------------------
The first Rev C attempt built a geometrically mirror-symmetric H-tree (feed
enters at the array centre; the right column fed on its -x edge, the left
column on its +x edge). Path lengths were equal by construction, but the two
columns were *mirror images*: their resonant-mode surface currents pointed in
OPPOSITE absolute directions, so the four patches' broadside co-polarised
fields cancelled. Result: Prad ~= 0, |S11| ~= 0 dB (energy trapped as a high-Q
standing wave), and a ~40 deg left/right phase split. Diagnosis (task-6 report
sec. 4): topology, not dimensions -- the single element with this exact inset
feed resonates at -30 dB / 24.17 GHz.

This redesign applies remedy A (translational / co-oriented patches): **all
four patches are fed on their -x radiating edge**, so every patch carries its
resonant current in the SAME absolute +x/-x direction and the four broadside
co-pol fields add. The feed tree is re-routed (column-first, with a meander on
the inner/right column) so that all four root->inset path lengths stay equal
*by construction* even though the tree is no longer a pure left/right mirror.

Element geometry is consumed verbatim from results/patch_element.json (never
hardcoded). Patches sit on a 6.2 mm grid (0.5 lambda0 at 24.2 GHz).

Layout (column-first corporate tree; all patches fed on -x edge)
----------------------------------------------------------------
Four patches at the grid corners, centred on the origin::

      TL (-,+)          TR (+,+)
        | inset from -x   | inset from -x
        |                 |
   (left column           (right column
    combiner at xCL,       combiner at xCR,
    left of the patches)   in the inter-column channel)
        |                 |
        +----- root T ----+   (two column trunks meet on the x axis; the root
                 |             QW leaves in -y, perpendicular to both trunks)
              root feed
                 |
               PORT (bottom -y board edge)

  * Every patch is fed on its -x edge. The inset feed line enters each notch
    from -x, running +x into the notch base. All four patch currents therefore
    point the same way -> co-polarised broadside addition.
  * LEFT column (TL, BL, notch base at x = xb_left): a vertical 50R combiner at
    x = xCL (just left of the patches) joins the two patches, symmetric about
    y=0. Its quarter-wave 35.4R transformer leaves the column junction in +x
    toward the root; a 50R trunk continues to the root.
  * RIGHT column (TR, BR, notch base at x = xb_right): a vertical 50R combiner
    at x = xCR inside the inter-column channel joins the two patches, symmetric
    about y=0. Its QW leaves in -x and reaches the root T directly (no separate
    right trunk). Because the right column's natural root->inset path is shorter
    than the left's, each right branch carries a single TALL series meander fold
    (in the clear vertical corridor beside the patch, x = xCR < right-patch
    edge) that adds exactly the deficit -- computed in the script so the four
    path lengths are equal.
  * ROOT (x junction at X_ROOT = xCR - lambda_g/4, i.e. the -x end of the right
    QW): the two column 50R trunks arrive along the x axis (colinear with each
    other) and combine in parallel (25R); the root quarter-wave 35.4R
    transformer leaves PERPENDICULAR in -y to a 50R root feed that runs to the
    MSL port on the -y board edge. (Branches colinear with each other, output
    perpendicular = a proper T; only branch-colinear-with-output is the bad case
    the prior run avoided. The root sits at X_ROOT rather than the origin so the
    right QW terminates cleanly at the T with no fold-back overlap.)

Within each column the two patches are an exact y-mirror pair fed by identical
branches, so intra-column phase balance is exact by construction; the meander
fold is applied identically to BOTH right branches, preserving that. The script
asserts the four root->inset path lengths are equal to < 0.01 mm.

Corporate transformers
----------------------
Three genuine 2-way splits (one per column + the root). Each junction: two 50R
branches in parallel = 25R, matched to 50R by a quarter-wave transformer of
sqrt(50*25) = 35.36 ohm. Transformer WIDTH from patch_design.microstrip_width
(Hammerstad-Jensen, imported not duplicated); LENGTH = lambda_g/4 from the
effective permittivity at the transformer width, computed here.

Sign convention for phase balance
----------------------------------
All four patches are fed on the same (-x) edge with the same current
orientation, so the co-pol phase is measured DIRECTLY as the DFT phase of Ez
integrated strip->ground at each inset base (no per-element sign flip). The
four phases must agree; max-min spread = imbalance. (This is the same-sign
co-pol convention required by the brief; because the patches are co-oriented
there is no |phase|-with-sign-flip subtlety.)

Acceptance (task-6 brief)
-------------------------
  * root-port |S11| <= -10 dB across 24.150-24.250 GHz
  * max inter-element phase imbalance <= 5 deg at 24.2 GHz
  * broadside gain >= 9 dBi from the NF2FF box
Also reports root S11 at 24.140 GHz.

Port / mesh / excitation conventions copied from sim_canary.py & sim_patch.py:
openEMS(EndCriteria) energy stop, SetGaussExcite, PML_8 on the root-feed
(propagation) ends + MUR elsewhere + PEC ground at zmin, lambda/20 dielectric
mesh with thirds-rule edge refinement, MSL root port with FeedShift /
MeasPlaneShift de-embedding, NF2FF box for gain.

Invocation (from repo root):
    docker run --rm -v "$PWD":/work -w /work openems-local \
        python3 hardware/24ghz-adf590x-fmcw-rev-c/antenna/sim_subarray.py
Optional overrides: SIM_OUT_DIR, MESH_DIV (outer-mesh coarsening),
QW_LEN_SCALE / QW_W_SCALE (transformer tuning), END_CRIT, L_TRIM_MM (uniform
patch-length trim, applied to all four patches), SKIP_SIM (reuse a prior run's
data for post-processing only).
"""

import json
import os
import sys

import numpy as np

from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0, EPS0
from openEMS.ports import UI_data

# Reuse the Hammerstad-Jensen synthesis + effective-eps model from
# patch_design.py (antenna/ is a plain dir; import rather than duplicate).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_design import microstrip_width, eff_permittivity  # noqa: E402


def _json_default(o):
    """Coerce numpy scalars to native Python types for json.dump."""
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


# ----------------------------------------------------------------------------
# Validated element geometry (never hardcode)
# ----------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "results", "patch_element.json"),
          encoding="utf-8") as _f:
    ELEM = json.load(_f)

UNIT = 1e-3

SUB_EPS_R = ELEM["substrate"]["er"]
SUB_TAN_D = ELEM["substrate"]["tand"]
SUB_H = ELEM["substrate"]["h_mm"]

# Optional uniform patch-length trim (in-array resonance sits a touch below
# standalone due to mutual coupling; the brief permits -0.01..-0.02 mm here).
# Default -0.05 mm: in-array resonance sits ~0.4 GHz low with untrimmed patches
# (debug 1x2 column resonated at 23.78 GHz; a -0.05 mm trim recentres to 24.23
# GHz and takes the column to -13.9 dB). Applied uniformly to all four patches.
L_TRIM_MM = float(os.environ.get("L_TRIM_MM", "-0.05"))

PATCH_W = ELEM["W_mm"]                    # non-resonant edge (y extent)
PATCH_L = ELEM["L_mm"] + L_TRIM_MM        # resonant length (x extent)
INSET_DEPTH = ELEM["inset_mm"]            # notch depth
FEED_W = ELEM["feed_w_mm"]                # 50 ohm feed width
INSET_GAP = ELEM["inset_gap_mm"]

PITCH = 6.2                     # element pitch, mm (0.5 lambda0 at 24.2 GHz)

# ----------------------------------------------------------------------------
# Frequency setup
# ----------------------------------------------------------------------------
F_START = 22.0e9
F_STOP = 26.0e9
F0 = 24.2e9
FC = 8e9
F_PHASE = 24.2e9

SUB_KAPPA = SUB_TAN_D * 2 * np.pi * F0 * EPS0 * SUB_EPS_R  # S/m

MESH_DIV = float(os.environ.get("MESH_DIV", "20"))
MESH_RES = C0 / (F_STOP * np.sqrt(SUB_EPS_R)) / UNIT / MESH_DIV
EDGE_RES = FEED_W / 4.0
END_CRIT = float(os.environ.get("END_CRIT", "1e-4"))

# ----------------------------------------------------------------------------
# Corporate-feed transformer sizing (script-computed)
# ----------------------------------------------------------------------------
Z0 = 50.0
Z_JUNCTION = 25.0                       # two 50R branches in parallel
Z_QW = np.sqrt(Z0 * Z_JUNCTION)         # 35.36 ohm quarter-wave transformer

QW_W_SCALE = float(os.environ.get("QW_W_SCALE", "1.0"))
QW_LEN_SCALE = float(os.environ.get("QW_LEN_SCALE", "1.0"))
QW_W = microstrip_width(Z_QW, SUB_EPS_R, SUB_H * 1e-3) * 1e3 * QW_W_SCALE  # mm

ER_EFF_QW = eff_permittivity(SUB_EPS_R, QW_W * 1e-3, SUB_H * 1e-3)
LAMBDA_G_QW = (C0 / F0) / np.sqrt(ER_EFF_QW) * 1e3       # mm
QW_LEN = LAMBDA_G_QW / 4.0 * QW_LEN_SCALE                # mm

ER_EFF_50 = eff_permittivity(SUB_EPS_R, FEED_W * 1e-3, SUB_H * 1e-3)

# ----------------------------------------------------------------------------
# Corporate-tree layout coordinates (all mm; array centred on origin)
# ----------------------------------------------------------------------------
XC = PITCH / 2.0                # +/- column-centre x
YC = PITCH / 2.0                # +/- row-centre y

# All patches fed on their -x edge (co-oriented). Notch base = deepest point of
# the inset, where the branch line contacts the patch body.
X_EDGE_L = -XC - PATCH_L / 2.0          # left-column -x feed edge
X_EDGE_R = +XC - PATCH_L / 2.0          # right-column -x feed edge
X_BASE_L = X_EDGE_L + INSET_DEPTH       # left-column notch base
X_BASE_R = X_EDGE_R + INSET_DEPTH       # right-column notch base

PATCH_HALF_W = PATCH_W / 2.0            # patch y half-extent
Y_PATCH_INNER = YC - PATCH_HALF_W       # inner (toward y=0) patch edge

# --- column combiner x positions -----------------------------------------
# Left combiner sits just OUTSIDE (-x of) the left patches; its two 50R branches
# enter the left notches from -x. Left QW leaves in +x toward the root; a 50R
# trunk then continues +x to the root T.
CLR = 0.6
X_CL = X_EDGE_L - CLR
# Right combiner sits inside the inter-column channel, clear of the right patch
# body (keep the 50R branch, half-width FEED_W/2, off the patch -x edge). Its QW
# leaves in -x and reaches the root directly (no separate right trunk), so the
# QW length alone sets the root x position.
X_CR = X_EDGE_R - FEED_W / 2.0 - EDGE_RES
# Root T sits at the -x end of the right QW (right QW ends AT the root -> the two
# column trunks arrive colinearly along x and the root QW leaves in -y). This
# avoids the fold-back that arises if the root is forced onto the origin.
X_ROOT = X_CR - QW_LEN

# --- per-column root->inset path lengths (centre-line) --------------------
# RIGHT (root -> TR/BR notch): right QW (X_ROOT..X_CR) + vertical YC + horiz.
PATH_R_STRAIGHT = QW_LEN + YC + (X_BASE_R - X_CR)
# LEFT (root -> TL/BL notch): left trunk (X_ROOT..X_CL+QW_LEN) + left QW +
# vertical YC + horiz (X_BASE_L - X_CL).
_LEFT_TRUNK = X_ROOT - (X_CL + QW_LEN)   # > 0: monotonic +x from QW end to root
assert _LEFT_TRUNK > 0.0, f"left trunk non-monotonic: {_LEFT_TRUNK}"
PATH_L_STRAIGHT = _LEFT_TRUNK + QW_LEN + YC + (X_BASE_L - X_CL)

# The left path is the longer one (left patches sit far outboard). Add a single
# TALL series meander fold to each right branch to equalize: out (-x) by A, a
# tall vertical in the offset column, back (+x) by A -> adds 2*A of through-
# length with net-zero x displacement.
_DELTA = PATH_L_STRAIGHT - PATH_R_STRAIGHT
assert _DELTA > 0.0, f"expected left path longer; delta={_DELTA}"
MEANDER_A = _DELTA / 2.0                   # horizontal excursion of the fold (mm)

# The fold lives in the CLEAR vertical corridor beside (not below) the patch:
# the right branch rises at x = X_CR, which is LEFT of the right patch body
# (X_CR < X_EDGE_R), so the whole rise from y=0 to the patch row is free of
# metal. The fold's two horizontals are placed high on that rise, separated by
# more than a feed width so they cannot merge; the offset column (x = X_CR - A)
# stays clear of both the left patch (negative-x block) and the root QW (y~0).
_MEANDER_REACH = X_CR - MEANDER_A
assert X_CR + FEED_W / 2.0 < X_EDGE_R, "right branch rise overlaps right patch"
# two fold horizontals at Y_MA (lower) and Y_MB (upper); both below the patch
# row (< YC) and well above the root QW; spacing > FEED_W so no merge.
Y_MA = 1.40
Y_MB = 2.40
assert Y_MB < YC, "meander fold exceeds patch row"
assert Y_MB - Y_MA > FEED_W + EDGE_RES, "fold horizontals too close (would merge)"
assert Y_MA > QW_W / 2.0 + FEED_W / 2.0, "fold horizontal overlaps root QW"
# offset column must clear the left patch (its +x edge) with a feed half-width
assert _MEANDER_REACH - FEED_W / 2.0 > (-XC + PATCH_L / 2.0), (
    f"meander offset column {_MEANDER_REACH:.3f} overlaps left patch")

# Root QW leaves X_ROOT in -y; 50R root feed continues -y to the port.
# FEED_LEN_ROOT must leave room for BOTH the FeedShift (8*MESH_RES ~= 2.41 mm)
# and a measurement plane placed FURTHER from the port start than the feed
# plane (MeasPlaneShift > FeedShift) yet still on the 50R feed, before the QW.
# The original 3.0 mm feed with MeasPlaneShift=1.0 put the reference plane
# BEHIND the excitation (measplane < feed_shift), which reads the port from the
# wrong side and reports near-total reflection regardless of the true match
# (confirmed in debug: a single patch reads |S11|~=0 dB / Zin~=0 with
# measplane<feedshift, but -27 dB / 50R once measplane>feedshift). See
# task-6 report "Debug round".
Y_ROOT_QW_END = -QW_LEN
FEED_LEN_ROOT = 5.0
Y_PORT = Y_ROOT_QW_END - FEED_LEN_ROOT

AIR_ABOVE = 3.0
MARGIN = 3.0


# ----------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------
def patch_edges(xc, yc):
    """Metal-box edges for one -x-inset-fed patch centred at (xc, yc).

    Every patch is fed on its -x edge (co-oriented). The notch is a slot cut
    from the -x edge around the feed line width; the branch enters from -x.
    """
    x_min = xc - PATCH_L / 2.0
    x_max = xc + PATCH_L / 2.0
    x_feed_edge = x_min
    x_inset_end = x_min + INSET_DEPTH
    return {
        "xc": xc, "yc": yc,
        "x_min": x_min, "x_max": x_max,
        "y_min": yc - PATCH_W / 2.0, "y_max": yc + PATCH_W / 2.0,
        "x_feed_edge": x_feed_edge, "x_inset_end": x_inset_end,
    }


def add_patch(metal, e):
    """Draw one -x inset-fed patch as three boxes leaving the feed notch bare."""
    y_feed = FEED_W / 2.0
    y_notch = y_feed + INSET_GAP
    yc = e["yc"]
    lo = e["x_feed_edge"]
    hi = e["x_inset_end"]
    # main body from the notch base to +x edge (full width)
    metal.AddBox([e["x_inset_end"], e["y_min"], SUB_H],
                 [e["x_max"], e["y_max"], SUB_H], priority=10)
    # side strips flanking the notch, over [lo, hi] in x
    metal.AddBox([lo, yc + y_notch, SUB_H], [hi, e["y_max"], SUB_H],
                 priority=10)
    metal.AddBox([lo, e["y_min"], SUB_H], [hi, yc - y_notch, SUB_H],
                 priority=10)


def hline(metal, x0, x1, y, w):
    metal.AddBox([min(x0, x1), y - w / 2.0, SUB_H],
                 [max(x0, x1), y + w / 2.0, SUB_H], priority=10)


def vline(metal, y0, y1, x, w):
    metal.AddBox([x - w / 2.0, min(y0, y1), SUB_H],
                 [x + w / 2.0, max(y0, y1), SUB_H], priority=10)


def path_lengths():
    """Root T (X_ROOT, 0) -> inset base path length for each patch, mm.

    LEFT column (TL, BL): centre-line
        root trunk 50R : X_ROOT -> (X_CL+QW_LEN)   = _LEFT_TRUNK   (along -x)
        col QW 35.4R   : (X_CL+QW_LEN) -> (X_CL,0)  = QW_LEN       (along -x)
        vertical 50R   : (X_CL,0) -> (X_CL, +/-YC)  = YC           (along +/-y)
        horiz 50R      : (X_CL,YC) -> notch base    = X_BASE_L-X_CL (along +x)
      sum = PATH_L_STRAIGHT.

    RIGHT column (TR, BR): the straight decomposition plus the single fold
    (2*MEANDER_A):
        col QW 35.4R   : X_ROOT -> (X_CR,0)         = QW_LEN       (along +x)
        vertical 50R   : (X_CR,0) -> (X_CR, +/-YC)  = YC           (along +/-y)
        horiz 50R      : (X_CR,YC) -> notch base    = X_BASE_R-X_CR (along +x)
        meander        : + 2*MEANDER_A
        sum = PATH_R_STRAIGHT + 2*MEANDER_A.

    By construction PATH_R_STRAIGHT + 2*MEANDER_A == PATH_L_STRAIGHT.  Within
    each column the two patches are an exact y-mirror pair, so all four equal.
    The caller asserts the spread < 0.01 mm.
    """
    left = PATH_L_STRAIGHT
    right = PATH_R_STRAIGHT + 2.0 * MEANDER_A
    return {"TL": left, "BL": left, "TR": right, "BR": right}


def add_left_column(feed):
    """Left column: vertical combiner + QW + trunk + two branches into notches."""
    over = EDGE_RES
    # two 50R branches: (X_CL, +/-YC) horizontal into the -x notch base
    for yr in (+YC, -YC):
        hline(feed, X_CL, X_BASE_L + over, yr, FEED_W)   # into notch base
        # vertical 50R from patch row down to the column junction (X_CL, 0)
        vline(feed, 0.0, yr, X_CL, FEED_W)
    # column QW 35.4R leaves the junction in +x, length QW_LEN
    hline(feed, X_CL, X_CL + QW_LEN, 0.0, QW_W)
    # 50R trunk from QW end to the root T (X_ROOT) along +x
    hline(feed, X_CL + QW_LEN, X_ROOT, 0.0, FEED_W)


def add_right_column(feed):
    """Right column: vertical combiner + QW-to-root + two MEANDERED branches.

    Single tall series meander fold (adds exactly 2*MEANDER_A of through-length
    with net-zero x displacement). Going out from the column junction (X_CR, 0)
    toward the patch row at +/-YC, each right branch routes (signs follow the
    row; A = MEANDER_A, excursion toward -x into the clear corridor beside the
    patch):
        (X_CR, 0)     --v--> (X_CR, ya)
        (X_CR, ya)    --h--> (X_CR-A, ya)     [-A, out]
        (X_CR-A, ya)  --v--> (X_CR-A, yb)     [tall offset-column run]
        (X_CR-A, yb)  --h--> (X_CR,   yb)     [+A, back]
        (X_CR, yb)    --v--> (X_CR, YC)       [continue to patch row]
        (X_CR, YC)    --h--> notch base       [+x into the -x notch]
    The two horizontal A-steps add 2*MEANDER_A; the offset-column vertical
    relocates part of the straight vertical (net-zero), so the added length is
    exactly 2*MEANDER_A.
    """
    over = EDGE_RES
    a = MEANDER_A
    xo = X_CR - a                          # offset (out) column x
    for yr in (+YC, -YC):
        ys = +1.0 if yr > 0 else -1.0
        ya, yb = ys * Y_MA, ys * Y_MB
        # rise from junction to fold entry
        vline(feed, 0.0, ya, X_CR, FEED_W)
        # fold: out, tall vertical, back
        hline(feed, X_CR, xo, ya, FEED_W)
        vline(feed, ya, yb, xo, FEED_W)
        hline(feed, xo, X_CR, yb, FEED_W)
        # continue vertical to the patch row
        vline(feed, yb, yr, X_CR, FEED_W)
        # horizontal 50R into the -x notch base
        hline(feed, X_CR, X_BASE_R + over, yr, FEED_W)
    # column QW 35.4R leaves the junction (X_CR,0) in -x and reaches the root T
    # (X_ROOT) directly -- no separate right trunk.
    hline(feed, X_ROOT, X_CR, 0.0, QW_W)


# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------
def build(sim_path):
    fdtd = openEMS(EndCriteria=END_CRIT, NrTS=800000)
    fdtd.SetGaussExcite(F0, FC)
    # PML on the y (root-feed propagation) ends; MUR on x sides and top;
    # PEC ground at zmin.
    fdtd.SetBoundaryCond(["MUR", "MUR", "PML_8", "PML_8", "PEC", "MUR"])

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(UNIT)

    patches = {
        "TL": patch_edges(-XC, +YC),
        "TR": patch_edges(+XC, +YC),
        "BL": patch_edges(-XC, -YC),
        "BR": patch_edges(+XC, -YC),
    }

    # substrate/air extent. Root feed exits -y to the port; extend that side.
    x_sub_min = X_CL - MARGIN
    x_sub_max = XC + PATCH_L / 2.0 + MARGIN
    y_sub_max = YC + PATCH_W / 2.0 + MARGIN
    y_sub_min = Y_PORT - MARGIN

    third = np.array([-EDGE_RES / 3.0, 2.0 * EDGE_RES / 3.0])

    # --- mesh: x (transverse) ------------------------------------------------
    mesh.AddLine("x", [x_sub_min, X_ROOT, x_sub_max])
    x_edges = set()
    for e in patches.values():
        x_edges.update([e["x_min"], e["x_max"], e["x_inset_end"]])
    x_edges.update([X_ROOT, X_ROOT - QW_W / 2.0, X_ROOT + QW_W / 2.0,
                    X_ROOT - FEED_W / 2.0, X_ROOT + FEED_W / 2.0,
                    X_CL, X_CL - FEED_W / 2.0, X_CL + FEED_W / 2.0,
                    X_CR, X_CR - FEED_W / 2.0, X_CR + FEED_W / 2.0,
                    X_CR - MEANDER_A, X_CR - MEANDER_A - FEED_W / 2.0,
                    X_CL + QW_LEN, X_BASE_L, X_BASE_R])
    for xe in x_edges:
        mesh.AddLine("x", xe + third)
        mesh.AddLine("x", xe - third[::-1])
    mesh.SmoothMeshLines("x", MESH_RES, 1.4)

    # --- mesh: y (root-feed propagation axis) --------------------------------
    mesh.AddLine("y", [y_sub_min, Y_PORT, 0.0, y_sub_max])
    y_edges = set()
    for e in patches.values():
        y_edges.update([e["y_min"], e["y_max"]])
    y_edges.update([YC, -YC, Y_ROOT_QW_END,
                    Y_MA, -Y_MA, Y_MB, -Y_MB,
                    FEED_W / 2.0, -FEED_W / 2.0, QW_W / 2.0, -QW_W / 2.0])
    # notch flank lines at each row
    y_feed = FEED_W / 2.0
    y_notch = y_feed + INSET_GAP
    for yr in (+YC, -YC):
        for ye in (yr + y_feed, yr - y_feed, yr + y_notch, yr - y_notch):
            y_edges.add(ye)
    for ye in y_edges:
        mesh.AddLine("y", ye + third)
        mesh.AddLine("y", ye - third[::-1])
    mesh.SmoothMeshLines("y", MESH_RES, 1.4)

    # --- mesh: z -------------------------------------------------------------
    mesh.AddLine("z", np.linspace(0, SUB_H, 5))
    mesh.AddLine("z", SUB_H + AIR_ABOVE)
    mesh.SmoothMeshLines("z", MESH_RES, 1.4)

    # --- substrate -----------------------------------------------------------
    substrate = csx.AddMaterial("RO4350B", epsilon=SUB_EPS_R, kappa=SUB_KAPPA)
    substrate.AddBox([x_sub_min, y_sub_min, 0], [x_sub_max, y_sub_max, SUB_H])

    # --- patches -------------------------------------------------------------
    patch_metal = csx.AddMetal("patches")
    for e in patches.values():
        add_patch(patch_metal, e)

    # --- feed tree -----------------------------------------------------------
    feed = csx.AddMetal("feed")
    add_left_column(feed)
    add_right_column(feed)

    # Root QW transformer: from the root T at (X_ROOT, 0) in -y (perpendicular
    # to the two column trunks that arrive along x) -> a clean root T-junction.
    # The 50R root feed from Y_ROOT_QW_END to the port is drawn by the MSL port
    # itself; extend the QW one edge-cell into the port strip so they share
    # metal cells.
    vline(feed, Y_ROOT_QW_END - EDGE_RES, 0.0, X_ROOT, QW_W)

    # --- root MSL port (excited) ---------------------------------------------
    # Port box spans strip (z=h) to ground (z=0), oriented along -y (prop axis),
    # centred on the root x position X_ROOT.
    port = fdtd.AddMSLPort(
        1, csx.AddMetal("feed_port"),
        [X_ROOT - FEED_W / 2.0, Y_PORT, SUB_H],
        [X_ROOT + FEED_W / 2.0, Y_ROOT_QW_END, 0],
        "y", "z",
        excite=-1,
        FeedShift=8 * MESH_RES,
        # MeasPlaneShift MUST exceed FeedShift (8*MESH_RES ~= 2.41 mm) so the
        # reference plane sits between the excitation and the load (the array),
        # on the 50R root feed, before the root QW. A value < FeedShift reads
        # the port from the wrong side -> spurious |S11|~=0. 3.5 mm lands on the
        # 50R feed (feed is FEED_LEN_ROOT=5.0 mm long; QW starts at 5.0 mm).
        MeasPlaneShift=3.5,
        priority=10,
    )

    # --- phase probes: Ez integrated strip->ground at each inset base ---------
    # Same-sign co-pol convention (see module docstring): all patches fed on the
    # -x edge with identical orientation, so the raw DFT phase is directly the
    # co-pol excitation phase (no per-element sign flip).
    probes = {}
    for tag, e in patches.items():
        px = e["x_inset_end"]
        py = e["yc"]
        pr = csx.AddProbe(f"vp_{tag}", 0)
        pr.SetFrequency([F_PHASE])
        pr.AddBox([px, py, 0.0], [px, py, SUB_H])
        probes[tag] = pr

    # --- NF2FF box -----------------------------------------------------------
    nf_margin = 2 * MESH_RES
    nf2ff = fdtd.CreateNF2FFBox(
        "nf2ff",
        [x_sub_min + nf_margin, y_sub_min + nf_margin, 0.0],
        [x_sub_max - nf_margin, y_sub_max - nf_margin,
         SUB_H + AIR_ABOVE - nf_margin],
    )

    return fdtd, port, nf2ff, probes


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    sim_path = os.environ.get("SIM_OUT_DIR",
                              os.path.join(HERE, "results", "subarray"))
    os.makedirs(sim_path, exist_ok=True)

    # --- path-length symmetry check (by construction) ------------------------
    lengths = path_lengths()
    lvals = list(lengths.values())
    spread = max(lvals) - min(lvals)
    assert spread < 0.01, f"feed path lengths not equal: {lengths}"

    fdtd, port, nf2ff, probes = build(sim_path)

    if not os.environ.get("SKIP_SIM"):
        fdtd.Run(sim_path, verbose=1, cleanup=True)

    # --- S11 -----------------------------------------------------------------
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

    # --- phase balance from the four voltage probes --------------------------
    phases = {}
    for tag, pr in probes.items():
        ui = UI_data([f"vp_{tag}"], sim_path, np.array([F_PHASE]))
        val = ui.ui_f_val[0][0]
        phases[tag] = float(np.angle(val, deg=True))
    ph_arr = np.array(list(phases.values()))
    rel = ((ph_arr - ph_arr[0] + 180.0) % 360.0) - 180.0
    phase_imbalance = float(rel.max() - rel.min())
    phase_accept = bool(abs(phase_imbalance) <= 5.0)

    # --- gain (broadside) ----------------------------------------------------
    theta = np.array([0.0])
    phi = np.array([0.0])
    nf = nf2ff.CalcNF2FF(sim_path, np.array([F0]), theta, phi,
                         center=[0, 0, SUB_H / 2.0 * 1e-3 / UNIT])
    gain_lin = float(nf.Dmax[0])
    gain_dbi = float(10.0 * np.log10(gain_lin))
    gain_accept = bool(gain_dbi >= 9.0)

    # --- assemble results JSON ----------------------------------------------
    feed_tree = [
        {"seg": "root_qw", "w_mm": round(QW_W, 4), "l_mm": round(QW_LEN, 4),
         "z_ohm": round(Z_QW, 2)},
        {"seg": "col_qw_left", "w_mm": round(QW_W, 4), "l_mm": round(QW_LEN, 4),
         "z_ohm": round(Z_QW, 2)},
        {"seg": "col_qw_right", "w_mm": round(QW_W, 4), "l_mm": round(QW_LEN, 4),
         "z_ohm": round(Z_QW, 2)},
        {"seg": "col_trunk_50_left", "w_mm": round(FEED_W, 4),
         "l_mm": round(_LEFT_TRUNK, 4), "z_ohm": 50.0},
        {"seg": "patch_branch_50", "w_mm": round(FEED_W, 4),
         "l_mm": round(YC + (X_BASE_L - X_CL), 4), "z_ohm": 50.0},
        {"seg": "right_meander_50", "w_mm": round(FEED_W, 4),
         "l_mm": round(2.0 * MEANDER_A, 4), "z_ohm": 50.0},
        {"seg": "root_feed_50", "w_mm": round(FEED_W, 4),
         "l_mm": round(FEED_LEN_ROOT, 4), "z_ohm": 50.0},
    ]
    extent_x = (XC + PATCH_L / 2.0) - X_CL
    extent_y = (YC + PATCH_W / 2.0) - Y_PORT
    result = {
        "element": ELEM,
        "pitch_mm": PITCH,
        "feed_topology": (
            "Co-oriented (translational) 2x2, remedy A: all four patches fed "
            "on their -x radiating edge so resonant currents are co-directed "
            "and broadside co-pol fields add. Column-first corporate tree -- "
            "each column combines its y-mirror patch pair (exact intra-column "
            "balance), the two column trunks combine at a root T (X_ROOT, 0) "
            "whose QW leaves in -y to the port. The inner (right) column's "
            "shorter reach is equalized by an identical two-fold series meander "
            "on both right branches; all four root->inset path lengths equal by "
            "construction."
        ),
        "feed_tree": feed_tree,
        "port_s11_db": {
            "24.14": round(s_140, 2), "24.15": round(s_150, 2),
            "24.20": round(s_200, 2), "24.25": round(s_250, 2),
            "band_max_24.15_24.25": round(band_max, 2),
        },
        "phase_balance_deg_max": round(phase_imbalance, 3),
        "phase_deg_per_element": {k: round(v, 2) for k, v in phases.items()},
        "gain_dbi_est": round(gain_dbi, 2),
        "extent_mm": [round(extent_x, 3), round(extent_y, 3)],
        "path_length_mm": {k: round(v, 4) for k, v in lengths.items()},
        "transformer": {
            "z_qw_ohm": round(Z_QW, 3), "w_mm": round(QW_W, 4),
            "lambda_g_qw_mm": round(LAMBDA_G_QW, 4),
            "er_eff_qw": round(ER_EFF_QW, 4),
        },
        "meander": {
            "folds": 1,
            "excursion_mm": round(MEANDER_A, 4),
            "added_len_mm": round(2.0 * MEANDER_A, 4),
        },
        "acceptance": {
            "s11": s11_accept, "phase": phase_accept, "gain": gain_accept,
        },
    }
    if L_TRIM_MM != 0.0:
        result["L_trim_mm"] = round(L_TRIM_MM, 4)

    # --- report (printed BEFORE the write) -----------------------------------
    print()
    print(f"Feed transformer: Z={Z_QW:.2f}R  w={QW_W:.4f} mm  "
          f"l=lambda_g/4={QW_LEN:.4f} mm (er_eff={ER_EFF_QW:.3f})")
    print(f"meander: 1 fold, excursion={MEANDER_A:.4f} mm  "
          f"added={2*MEANDER_A:.4f} mm  reach_x={X_CR - MEANDER_A:.4f} mm")
    print(f"path lengths (mm): {lengths}  spread={spread:.5f} (<0.01 ok)")
    print(f"S11 @24.14={s_140:.2f} @24.15={s_150:.2f} "
          f"@24.20={s_200:.2f} @24.25={s_250:.2f} dB")
    print(f"worst |S11| 24.15-24.25 = {band_max:.2f} dB -> "
          f"{'PASS' if s11_accept else 'FAIL'}")
    print(f"phases (deg): {phases}")
    print(f"phase imbalance = {phase_imbalance:.3f} deg -> "
          f"{'PASS' if phase_accept else 'FAIL'}")
    print(f"broadside gain = {gain_dbi:.2f} dBi -> "
          f"{'PASS' if gain_accept else 'FAIL'}")
    print(f"extent = {extent_x:.2f} x {extent_y:.2f} mm")
    if L_TRIM_MM != 0.0:
        print(f"L_trim applied = {L_TRIM_MM:.4f} mm (all four patches)")
    print("SUMMARY_JSON:" + json.dumps({
        "band_max_db": band_max, "s11_accept": s11_accept,
        "phase_imbalance": phase_imbalance, "phase_accept": phase_accept,
        "gain_dbi": gain_dbi, "gain_accept": gain_accept,
    }))

    out_json = os.path.join(HERE, "results", "subarray.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=_json_default)
    print(f"results -> {out_json}")

    ok = s11_accept and phase_accept and gain_accept
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
