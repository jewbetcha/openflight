"""Is the orientation measuring stick itself correct?

Everything that judges a pose physically possible depends on this conversion,
so it is checked against facts known independently of the fitter: the mesh's
own catalogue geometry, and the fact that a square club must be expressible.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from openflight.camera.clubpose.angles import (
    ENVELOPE,
    STATIC_LIE_DEG,
    STATIC_LOFT_DEG,
    angles_from_pose,
    basis_from_angles,
    delivered_angles,
    in_envelope,
    square_pose,
)


class TestSquarePose:
    def test_a_square_club_is_expressible(self):
        """If no pose delivers the club's own static geometry, the conversion
        or the parameterisation is wrong and every verdict built on it is void."""
        got = angles_from_pose(*square_pose())
        assert got["dynamic_loft_deg"] == pytest.approx(STATIC_LOFT_DEG, abs=0.05)
        assert got["face_angle_deg"] == pytest.approx(0.0, abs=0.05)
        assert got["lie_deg"] == pytest.approx(STATIC_LIE_DEG, abs=0.05)

    def test_the_square_pose_is_nowhere_near_the_origin(self):
        """This is the whole reason the module exists: a fit seeded on a grid
        around zero never reaches the square club."""
        yaw, pitch, roll = square_pose()
        assert abs(math.remainder(pitch, 360.0)) > 90.0, (
            f"pitch {pitch} is near zero, so the seeding hazard has gone away "
            "and the warning in the docstring should be revisited"
        )

    def test_the_origin_is_a_backwards_club(self):
        origin = angles_from_pose(0.0, 0.0, 0.0)
        assert abs(origin["face_angle_deg"]) > 150.0
        assert not in_envelope(origin)

    def test_solves_for_a_requested_non_square_delivery(self):
        got = angles_from_pose(*square_pose(dynamic_loft_deg=28.0, face_angle_deg=-4.0))
        assert got["dynamic_loft_deg"] == pytest.approx(28.0, abs=0.05)
        assert got["face_angle_deg"] == pytest.approx(-4.0, abs=0.05)


class TestDeliveredAngles:
    def test_basis_is_orthonormal(self):
        basis = basis_from_angles(11.0, -37.0, 64.0)
        assert np.allclose(basis.T @ basis, np.eye(3), atol=1e-9)

    def test_face_angle_sign_is_open_to_the_right(self):
        """A right-handed player's open face points right, which is +y."""
        yaw, pitch, roll = square_pose(face_angle_deg=6.0)
        assert angles_from_pose(yaw, pitch, roll)["face_angle_deg"] > 0

    def test_angles_are_continuous_under_small_perturbation(self):
        base = square_pose()
        before = angles_from_pose(*base)
        after = angles_from_pose(base[0] + 1.0, base[1], base[2])
        for key in ("dynamic_loft_deg", "lie_deg"):
            assert abs(after[key] - before[key]) < 5.0
        assert abs(math.remainder(after["face_angle_deg"] - before["face_angle_deg"], 360.0)) < 5.0

    def test_rejects_a_degenerate_basis(self):
        with pytest.raises(ValueError):
            delivered_angles([[0, 0, 0], [0, 0, 0], [0, 0, 0]])


class TestEnvelope:
    def test_a_square_club_is_inside(self):
        assert in_envelope(angles_from_pose(*square_pose()))

    def test_negative_loft_is_rejected(self):
        """A lofted iron cannot present a downward-facing face at contact.
        An earlier fit produced exactly this and had to be caught."""
        assert not in_envelope({"dynamic_loft_deg": -7.1, "face_angle_deg": 16.7, "lie_deg": 28.2})

    def test_a_backwards_face_is_rejected(self):
        assert not in_envelope({"dynamic_loft_deg": 27.3, "face_angle_deg": -163.0, "lie_deg": 5.2})

    def test_a_realistic_delivery_is_accepted(self):
        assert in_envelope({"dynamic_loft_deg": 27.5, "face_angle_deg": -1.8, "lie_deg": 62.4})

    def test_envelope_covers_the_static_geometry_with_margin(self):
        low, high = ENVELOPE["dynamic_loft_deg"]
        assert low < STATIC_LOFT_DEG < high
        low, high = ENVELOPE["lie_deg"]
        assert low < STATIC_LIE_DEG < high
