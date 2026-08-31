"""Physical constraints for sequence-level clubhead rotation."""

from __future__ import annotations

import math

import numpy as np
import pytest

from openflight.camera.clubpose.motion import axis_from_angles, constrained_omega_deg_s


@pytest.mark.parametrize(
    ("azimuth_deg", "elevation_deg", "expected"),
    (
        (0.0, 0.0, (1.0, 0.0, 0.0)),
        (90.0, 0.0, (0.0, 1.0, 0.0)),
        (0.0, 90.0, (0.0, 0.0, 1.0)),
    ),
)
def test_axis_angles_form_a_unit_world_axis(azimuth_deg, elevation_deg, expected):
    axis = axis_from_angles(azimuth_deg, elevation_deg)
    np.testing.assert_allclose(axis, expected, atol=1e-12)
    assert np.linalg.norm(axis) == pytest.approx(1.0)


def test_constrained_omega_has_v_over_r_magnitude():
    omega = constrained_omega_deg_s(
        speed_mps=36.6,
        swing_radius_m=1.6,
        axis_azimuth_deg=30.0,
        axis_elevation_deg=-20.0,
    )

    assert np.linalg.norm(omega) == pytest.approx(math.degrees(36.6 / 1.6))
    np.testing.assert_allclose(
        omega / np.linalg.norm(omega),
        axis_from_angles(30.0, -20.0),
        atol=1e-12,
    )


@pytest.mark.parametrize("speed_mps,swing_radius_m", ((0.0, 1.6), (36.6, 0.0), (-1.0, 1.6)))
def test_constrained_omega_rejects_non_physical_inputs(speed_mps, swing_radius_m):
    with pytest.raises(ValueError):
        constrained_omega_deg_s(speed_mps, swing_radius_m, 0.0, 0.0)
