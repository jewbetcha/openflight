#!/usr/bin/env python3
"""Closed-form rectangular inset-fed patch synthesis for 24.2 GHz on RO4350B.

Runs on the host under `uv run python patch_design.py` (plain Python, no
openEMS). Produces the starting-point geometry that sim_patch.py refines in
FDTD. All the standard textbook formulas (Balanis, Antenna Theory) are used:

  - Width          W  = c/(2 f0) * sqrt(2/(er+1))
  - Effective eps  er_eff via Hammerstad (patch, wide-strip approximation)
  - Fringing dL    from the standard (er_eff, W/h) extension formula
  - Length         L  = c/(2 f0 sqrt(er_eff)) - 2 dL
  - Inset depth y0 for 50 ohm from the cos^2 edge-resistance model
  - Feed width     via Hammerstad-Jensen microstrip synthesis (target 50 ohm)

Substrate (interim, PCBWay-confirmation pending):
  h = 0.254 mm RO4350B, design Dk er = 3.66, tan_d = 0.0037.
"""

import numpy as np

# --- physical constants ----------------------------------------------------
C0 = 299_792_458.0  # speed of light, m/s

# --- design inputs ----------------------------------------------------------
F0 = 24.200e9       # target resonance, Hz
ER = 3.66           # substrate relative permittivity (design Dk)
H = 0.254e-3        # substrate thickness, m
Z0_FEED = 50.0      # feed characteristic impedance, ohm


def patch_width(f0: float, er: float) -> float:
    """Balanis eq. 14-6: efficient-radiator patch width, m."""
    return C0 / (2.0 * f0) * np.sqrt(2.0 / (er + 1.0))


def eff_permittivity(er: float, w: float, h: float) -> float:
    """Hammerstad effective permittivity for a wide microstrip (W/h > 1)."""
    return (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (1.0 + 12.0 * h / w) ** -0.5


def length_extension(er_eff: float, w: float, h: float) -> float:
    """Balanis eq. 14-2: fringing-field length extension dL, m."""
    num = (er_eff + 0.3) * (w / h + 0.264)
    den = (er_eff - 0.258) * (w / h + 0.8)
    return 0.412 * h * num / den


def patch_length(f0: float, er_eff: float, dl: float) -> float:
    """Physical patch length, m (resonant length minus 2*dL)."""
    return C0 / (2.0 * f0 * np.sqrt(er_eff)) - 2.0 * dl


def edge_resistance(er: float, er_eff: float, w: float, l: float,
                    f0: float, h: float) -> float:
    """Approximate radiation resistance at the radiating edge, ohm.

    Uses the Balanis single-slot conductance model (eq. 14-12) for the
    self-conductance G1, then Rin_edge = 1/(2 G1) (mutual coupling ignored).
    """
    lam0 = C0 / f0
    k0 = 2.0 * np.pi / lam0
    # numerically integrate the slot pattern integral I1 (Balanis 14-12a)
    theta = np.linspace(1e-6, np.pi, 2001)
    integrand = (np.sin(k0 * w / 2.0 * np.cos(theta)) / np.cos(theta)) ** 2 \
        * np.sin(theta) ** 3
    trapz = getattr(np, "trapezoid", None) or np.trapz
    i1 = trapz(integrand, theta)
    g1 = i1 / (120.0 * np.pi ** 2)
    return 1.0 / (2.0 * g1)


def inset_depth(r_edge: float, z0: float, l: float) -> float:
    """Inset depth y0 for a target input impedance z0, m.

    Rin(y0) = R_edge * cos^2(pi*y0/L)  ->  y0 = L/pi * arccos(sqrt(z0/R_edge)).
    """
    ratio = np.sqrt(z0 / r_edge)
    ratio = min(1.0, max(0.0, ratio))
    return l / np.pi * np.arccos(ratio)


def microstrip_width(z0: float, er: float, h: float) -> float:
    """Hammerstad-Jensen synthesis: microstrip width for target z0, m."""
    a = z0 / 60.0 * np.sqrt((er + 1.0) / 2.0) \
        + (er - 1.0) / (er + 1.0) * (0.23 + 0.11 / er)
    b = 377.0 * np.pi / (2.0 * z0 * np.sqrt(er))
    # W/h > 2 branch (correct for 50 ohm on this thin, high-er stackup)
    woh = 2.0 / np.pi * (b - 1.0 - np.log(2.0 * b - 1.0)
                         + (er - 1.0) / (2.0 * er)
                         * (np.log(b - 1.0) + 0.39 - 0.61 / er))
    if woh < 2.0:
        # narrow-strip branch as a fallback
        woh = 8.0 * np.exp(a) / (np.exp(2.0 * a) - 2.0)
    return woh * h


def main() -> None:
    w = patch_width(F0, ER)
    er_eff = eff_permittivity(ER, w, H)
    dl = length_extension(er_eff, w, H)
    l = patch_length(F0, er_eff, dl)
    r_edge = edge_resistance(ER, er_eff, w, l, F0, H)
    y0 = inset_depth(r_edge, Z0_FEED, l)
    feed_w = microstrip_width(Z0_FEED, ER, H)

    mm = 1e3
    print("Rectangular inset-fed patch, closed-form synthesis")
    print("=" * 52)
    print(f"  target f0        : {F0 / 1e9:8.3f} GHz")
    print(f"  substrate        : h={H * mm:.3f} mm, er={ER}, "
          f"tan_d=0.0037")
    print("-" * 52)
    print(f"  width  W         : {w * mm:8.4f} mm")
    print(f"  eps_eff          : {er_eff:8.4f}")
    print(f"  length ext. dL   : {dl * mm:8.4f} mm")
    print(f"  length L         : {l * mm:8.4f} mm")
    print(f"  edge resistance  : {r_edge:8.2f} ohm")
    print(f"  inset depth y0   : {y0 * mm:8.4f} mm (for {Z0_FEED:.0f} ohm)")
    print(f"  feed width       : {feed_w * mm:8.4f} mm (target {Z0_FEED:.0f} "
          f"ohm)")
    print("=" * 52)

    # sanity window from the brief
    w_mm, l_mm = w * mm, l * mm
    w_ok = 4.0 <= w_mm <= 4.6
    l_ok = 3.1 <= l_mm <= 3.4
    print(f"  W in [4.0, 4.6]  : {w_mm:.3f} -> {'ok' if w_ok else 'OUT'}")
    print(f"  L in [3.1, 3.4]  : {l_mm:.3f} -> {'ok' if l_ok else 'OUT'}")


if __name__ == "__main__":
    main()
