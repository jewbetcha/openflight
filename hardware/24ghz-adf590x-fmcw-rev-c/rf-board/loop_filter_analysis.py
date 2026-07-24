#!/usr/bin/env python3
"""Small-signal stability check for the Rev C ADF4159/ADF5901 PLL."""

from __future__ import annotations

import json
import math
from itertools import product
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "production-package" / "loop-filter-analysis.json"


def filter_transimpedance(
    frequencies_hz: np.ndarray,
    *,
    r_series_ohm: float = 510.0,
    r_damping_ohm: float = 620.0,
    c_cp_f: float = 220e-12,
    c_damping_f: float = 3.3e-9,
    c_vtune_f: float = 47e-12,
) -> np.ndarray:
    """Return VTUNE volts per ampere injected at the charge-pump node."""
    s = 2j * math.pi * np.asarray(frequencies_hz, dtype=float)
    g_series = 1.0 / r_series_ohm
    y_damping = 1.0 / (r_damping_ohm + 1.0 / (s * c_damping_f))
    y_cp = s * c_cp_f + y_damping + g_series
    y_vtune = s * c_vtune_f + g_series
    determinant = y_cp * y_vtune - g_series**2
    return g_series / determinant


def stability_metrics(frequencies_hz: np.ndarray, open_loop: np.ndarray) -> dict:
    """Interpolate the first descending 0 dB crossing and its phase margin."""
    frequencies_hz = np.asarray(frequencies_hz, dtype=float)
    open_loop = np.asarray(open_loop, dtype=complex)
    magnitude_db = 20.0 * np.log10(np.abs(open_loop))
    crossing_indices = np.flatnonzero(
        (magnitude_db[:-1] >= 0.0) & (magnitude_db[1:] < 0.0)
    )
    if not len(crossing_indices):
        raise ValueError("open-loop response has no descending unity-gain crossing")

    index = int(crossing_indices[0])
    fraction = magnitude_db[index] / (
        magnitude_db[index] - magnitude_db[index + 1]
    )
    log_frequency = np.log10(frequencies_hz)
    unity_gain_hz = 10.0 ** (
        log_frequency[index]
        + fraction * (log_frequency[index + 1] - log_frequency[index])
    )
    phase_deg = np.rad2deg(np.unwrap(np.angle(open_loop)))
    crossing_phase_deg = phase_deg[index] + fraction * (
        phase_deg[index + 1] - phase_deg[index]
    )
    phase_margin_deg = 180.0 + crossing_phase_deg
    return {
        "unity_gain_hz": float(unity_gain_hz),
        "phase_at_unity_deg": float(crossing_phase_deg),
        "phase_margin_deg": float(phase_margin_deg),
    }


def analyze_rev_c_loop_filter(
    *,
    charge_pump_currents_a: tuple[float, ...] = (2.5e-3, 4.8e-3),
    feedback_vco_gains_hz_per_v: tuple[float, ...] = (75e6, 125e6),
) -> dict:
    """Sweep the documented nominal/max CP current and ADF5901 gain range."""
    pfd_hz = 100e6
    n_divider = 121.0
    ramp_time_s = 150e-6
    frequencies_hz = np.logspace(1, 8, 20_001)
    corners = []

    tolerances = {
        "r_series": (0.99, 1.01),
        "r_damping": (0.99, 1.01),
        "c_cp": (0.95, 1.05),
        "c_damping": (0.90, 1.10),
        "c_vtune": (0.95, 1.05),
    }
    for (
        charge_pump_current_a,
        feedback_vco_gain_hz_per_v,
        r_series_factor,
        r_damping_factor,
        c_cp_factor,
        c_damping_factor,
        c_vtune_factor,
    ) in product(
        charge_pump_currents_a,
        feedback_vco_gains_hz_per_v,
        tolerances["r_series"],
        tolerances["r_damping"],
        tolerances["c_cp"],
        tolerances["c_damping"],
        tolerances["c_vtune"],
    ):
        transimpedance = filter_transimpedance(
            frequencies_hz,
            r_series_ohm=510.0 * r_series_factor,
            r_damping_ohm=620.0 * r_damping_factor,
            c_cp_f=220e-12 * c_cp_factor,
            c_damping_f=3.3e-9 * c_damping_factor,
            c_vtune_f=47e-12 * c_vtune_factor,
        )
        phase_detector_gain_a_per_rad = charge_pump_current_a / (2.0 * math.pi)
        vco_gain_rad_per_s_per_v = 2.0 * math.pi * feedback_vco_gain_hz_per_v
        open_loop = (
            phase_detector_gain_a_per_rad
            * transimpedance
            * vco_gain_rad_per_s_per_v
            / (2j * math.pi * frequencies_hz * n_divider)
        )
        metrics = stability_metrics(frequencies_hz, open_loop)
        corners.append(
            {
                "charge_pump_current_ma": charge_pump_current_a * 1e3,
                "feedback_vco_gain_mhz_per_v": feedback_vco_gain_hz_per_v / 1e6,
                "component_tolerance_factors": {
                    "R21": r_series_factor,
                    "R22": r_damping_factor,
                    "C33": c_cp_factor,
                    "C34": c_damping_factor,
                    "C35": c_vtune_factor,
                },
                **metrics,
                "unity_gain_cycles_per_ramp": metrics["unity_gain_hz"]
                * ramp_time_s,
            }
        )

    worst_phase = min(corners, key=lambda corner: corner["phase_margin_deg"])
    slowest = min(corners, key=lambda corner: corner["unity_gain_hz"])
    fastest = max(corners, key=lambda corner: corner["unity_gain_hz"])
    phase_margin_pass = worst_phase["phase_margin_deg"] >= 50.0
    chirp_response_pass = slowest["unity_gain_cycles_per_ramp"] >= 10.0
    pfd_separation_pass = fastest["unity_gain_hz"] <= pfd_hz / 10.0

    return {
        "analysis": "linear_small_signal_charge_pump_pll",
        "source_topology": "ADI UG-866 Figure 12",
        "component_values": {
            "R21_series_ohm": 510.0,
            "C33_cp_shunt_f": 220e-12,
            "C34_damping_f": 3.3e-9,
            "R22_damping_ohm": 620.0,
            "C35_vtune_shunt_f": 47e-12,
            "R23_output_ohm": 0.0,
        },
        "assumptions": {
            "pfd_hz": pfd_hz,
            "feedback_divider": 2,
            "n_divider": n_divider,
            "ramp_time_s": ramp_time_s,
            "feedback_vco_gain_basis": "ADF5901 Figure 11 estimate over the Rev C band after AUX divide-by-2",
            "charge_pump_current_basis": "ADF4159 2.5 mA typical example and 4.8 mA RSET maximum",
            "component_tolerances": {
                "R21_R22": "+/-1%",
                "C33_C35": "+/-5%",
                "C34": "+/-10%",
            },
        },
        "corners": corners,
        "worst_case": dict(worst_phase),
        "slowest_corner": dict(slowest),
        "fastest_corner": dict(fastest),
        "acceptance": {
            "phase_margin_at_least_50_deg": phase_margin_pass,
            "at_least_10_unity_gain_cycles_per_ramp": chirp_response_pass,
            "unity_gain_below_pfd_over_10": pfd_separation_pass,
            "overall": phase_margin_pass and chirp_response_pass and pfd_separation_pass,
        },
        "limitations": [
            "This is a linear small-signal model, not ADIsimPLL nonlinear ramp simulation.",
            "ADF5901 tuning gain is estimated from the datasheet plot; bench chirp linearity remains a bring-up measurement.",
        ],
    }


def main() -> int:
    result = analyze_rev_c_loop_filter()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["acceptance"], indent=2))
    print(f"wrote {OUTPUT}")
    return 0 if result["acceptance"]["overall"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
