from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def load_analysis_module():
    try:
        return importlib.import_module("loop_filter_analysis")
    except ModuleNotFoundError:
        pytest.fail("loop_filter_analysis has not been implemented")


def test_transimpedance_matches_direct_nodal_solution() -> None:
    analysis = load_analysis_module()
    frequency_hz = 100_000.0
    s = 2j * math.pi * frequency_hz
    r_series = 1_000.0
    r_damping = 510.0
    c_cp = 220e-12
    c_damping = 3.3e-9
    c_vtune = 100e-12

    g_series = 1.0 / r_series
    y_damping = 1.0 / (r_damping + 1.0 / (s * c_damping))
    nodal = np.array(
        [
            [s * c_cp + y_damping + g_series, -g_series],
            [-g_series, s * c_vtune + g_series],
        ],
        dtype=complex,
    )
    expected = np.linalg.solve(nodal, np.array([1.0, 0.0]))[1]

    actual = analysis.filter_transimpedance(
        np.array([frequency_hz]),
        r_series_ohm=r_series,
        r_damping_ohm=r_damping,
        c_cp_f=c_cp,
        c_damping_f=c_damping,
        c_vtune_f=c_vtune,
    )[0]

    assert actual == pytest.approx(expected)


def test_stability_metrics_interpolate_known_integrator_crossing() -> None:
    analysis = load_analysis_module()
    frequencies_hz = np.logspace(3, 7, 1001)
    open_loop = 100_000.0 / (2j * math.pi * frequencies_hz)
    open_loop *= 2.0 * math.pi

    metrics = analysis.stability_metrics(frequencies_hz, open_loop)

    assert metrics["unity_gain_hz"] == pytest.approx(100_000.0, rel=0.01)
    assert metrics["phase_margin_deg"] == pytest.approx(90.0, abs=0.1)


def test_rev_c_corner_sweep_reports_every_planned_corner() -> None:
    analysis = load_analysis_module()
    result = analysis.analyze_rev_c_loop_filter(
        charge_pump_currents_a=(2.5e-3, 4.8e-3),
        feedback_vco_gains_hz_per_v=(75e6, 125e6),
    )

    assert len(result["corners"]) == 128
    assert result["assumptions"]["feedback_divider"] == 2
    assert result["assumptions"]["n_divider"] == pytest.approx(121.0)
    assert result["component_values"]["R21_series_ohm"] == 510.0
    assert result["component_values"]["R22_damping_ohm"] == 620.0
    assert result["component_values"]["C35_vtune_shunt_f"] == 47e-12
    assert result["worst_case"]["phase_margin_deg"] == min(
        corner["phase_margin_deg"] for corner in result["corners"]
    )
    assert result["worst_case"]["phase_margin_deg"] >= 50.0
    assert result["acceptance"]["overall"] is True
