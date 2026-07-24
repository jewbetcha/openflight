from __future__ import annotations

import math
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import subarray_geometry  # noqa: E402


def required_helper(name: str):
    assert hasattr(subarray_geometry, name), f"{name} has not been implemented"
    return getattr(subarray_geometry, name)


def test_phase_center_converts_drawing_millimeters_to_meters() -> None:
    phase_center_m = required_helper("phase_center_m")
    assert phase_center_m(0.0, 0.0, 0.127) == (0.0, 0.0, 0.000127)


def test_nf2ff_grid_uses_degrees_and_covers_full_sphere() -> None:
    nf2ff_angles_deg = required_helper("nf2ff_angles_deg")

    theta_deg, phi_deg = nf2ff_angles_deg(step_deg=2.0)

    assert theta_deg[0] == 0.0
    assert theta_deg[-1] == 180.0
    assert phi_deg[0] == -180.0
    assert phi_deg[-1] == 180.0
    assert theta_deg[-1] > math.pi


def test_far_field_rejects_incomplete_angular_grid() -> None:
    assess_far_field = required_helper("assess_far_field")
    result = assess_far_field(
        radiated_power_w=0.8,
        accepted_power_w=1.0,
        directivity_linear=10.0,
        angular_grid_complete=False,
    )

    assert result["valid"] is False
    assert "full sphere" in result["reason"]


def test_far_field_accepts_plausible_full_sphere_result() -> None:
    assess_far_field = required_helper("assess_far_field")
    result = assess_far_field(
        radiated_power_w=0.8,
        accepted_power_w=1.0,
        directivity_linear=10.0,
        angular_grid_complete=True,
    )

    assert result["valid"] is True
    assert result["radiation_efficiency"] == 0.8


def test_gain_includes_radiation_efficiency() -> None:
    gain_dbi_from_directivity = required_helper("gain_dbi_from_directivity")
    assert math.isclose(
        gain_dbi_from_directivity(directivity_linear=10.0, radiation_efficiency=0.5),
        10.0 * math.log10(5.0),
    )


def test_nf2ff_domain_encloses_finite_structure_inside_air_box() -> None:
    build_nf2ff_domain = required_helper("build_nf2ff_domain")

    domain = build_nf2ff_domain(
        structure_start_mm=(-10.0, -5.0, 0.0),
        structure_stop_mm=(10.0, 5.0, 0.254),
        air_clearance_mm=3.0,
        nf2ff_clearance_mm=0.6,
    )

    for axis in range(3):
        assert domain["simulation_start_mm"][axis] < domain["nf2ff_start_mm"][axis]
        assert domain["nf2ff_start_mm"][axis] < domain["structure_start_mm"][axis]
        assert domain["structure_stop_mm"][axis] < domain["nf2ff_stop_mm"][axis]
        assert domain["nf2ff_stop_mm"][axis] < domain["simulation_stop_mm"][axis]

    assert domain["phase_center_m"] == (0.0, 0.0, 0.000127)


def test_pattern_metrics_find_peak_and_broadside_directivity() -> None:
    pattern_metrics = required_helper("pattern_metrics")
    theta_deg = (0.0, 10.0, 20.0)
    phi_deg = (-90.0, 0.0, 90.0)
    e_norm = (
        (0.5, 0.5, 0.5),
        (0.2, 0.3, 1.0),
        (0.1, 0.2, 0.4),
    )

    metrics = pattern_metrics(
        theta_deg=theta_deg,
        phi_deg=phi_deg,
        e_norm=e_norm,
        directivity_linear=8.0,
    )

    assert metrics["beam_offset_deg"] == 10.0
    assert metrics["signed_y_beam_deg"] == 10.0
    assert metrics["phi_peak_deg"] == 90.0
    assert metrics["peak_directivity_linear"] == 8.0
    assert metrics["broadside_directivity_linear"] == 2.0
