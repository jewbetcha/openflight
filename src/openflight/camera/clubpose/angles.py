"""Clubface orientation in the terms a golfer uses, and the poses that are possible.

The fitter parameterises orientation as yaw, pitch and roll applied to the
mesh's own frame. Those numbers are not checkable by eye, are not what the
product reports, and are measured from a misleading origin: the mesh's local
+x axis points out the BACK of the club, so ``triad(0, 0, 0)`` is a clubface
aimed at the camera -- **face angle +178.7 deg, loft -19.7 deg**.

That origin caused a real error. A fit seeded on a grid around zero searches
the neighbourhood of a backwards club and never reaches the square one, which
sits near ``pitch = -194 deg``. Seeds must come from :func:`square_pose`.

The three angles here have known physical envelopes, so they validate a fit
without a reference instrument: a 7-iron delivered with negative loft, or a
shaft twenty degrees off its lie, is wrong whatever it scores.

Club axes are measured off the mesh (see
the fork's feat/silhouette-poc branch), not assumed, and give
loft 33.10 deg / lie 61.19 deg -- consistent with a 690CB catalogue 34/62.
"""

from __future__ import annotations

import math

import numpy as np

from .fit import triad

FACE_NORMAL_LOCAL = np.array([-0.941, 0.021, -0.337])
FACE_NORMAL_LOCAL = FACE_NORMAL_LOCAL / np.linalg.norm(FACE_NORMAL_LOCAL)
SHAFT_LOCAL = np.array([-0.245, 0.295, -0.924])
SHAFT_LOCAL = SHAFT_LOCAL / np.linalg.norm(SHAFT_LOCAL)

STATIC_LOFT_DEG = 33.10
STATIC_LIE_DEG = 61.19

# Wider than any real delivery: outside these a pose is wrong, not unusual.
ENVELOPE = {
    "dynamic_loft_deg": (15.0, 50.0),
    "face_angle_deg": (-25.0, 25.0),
    "lie_deg": (45.0, 78.0),
}


def basis_from_angles(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    """Local-to-world matrix for a pose, columns being the mesh's own axes."""
    normal, width, height = triad(yaw_deg, pitch_deg, roll_deg)
    return np.column_stack((normal, width, height))


def delivered_angles(basis_world: np.ndarray) -> dict[str, float]:
    """Dynamic loft, face angle and lie in degrees, from a local-to-world basis.

    World axes are x downrange, y right, z up. Face angle is the azimuth of the
    face normal about vertical, so zero is square and positive is open for a
    right-handed player.
    """
    basis = np.asarray(basis_world, dtype=float)
    face = basis @ FACE_NORMAL_LOCAL
    shaft = basis @ SHAFT_LOCAL
    face_norm, shaft_norm = np.linalg.norm(face), np.linalg.norm(shaft)
    # Fail closed: NaN angles would read as "implausible pose", not "broken input".
    if (
        not (np.isfinite(face_norm) and np.isfinite(shaft_norm))
        or min(face_norm, shaft_norm) < 1e-9
    ):
        raise ValueError("degenerate basis: club axes collapse to zero length")
    face = face / face_norm
    shaft = shaft / shaft_norm
    return {
        "dynamic_loft_deg": math.degrees(math.asin(float(np.clip(face[2], -1.0, 1.0)))),
        "face_angle_deg": math.degrees(math.atan2(float(face[1]), float(face[0]))),
        "lie_deg": math.degrees(math.asin(float(np.clip(abs(shaft[2]), -1.0, 1.0)))),
    }


def angles_from_pose(yaw_deg: float, pitch_deg: float, roll_deg: float) -> dict[str, float]:
    """Convenience wrapper: pose angles straight to delivered angles."""
    return delivered_angles(basis_from_angles(yaw_deg, pitch_deg, roll_deg))


def in_envelope(angles: dict[str, float]) -> bool:
    """Could a real club have been delivered in this orientation?"""
    return all(low <= angles[key] <= high for key, (low, high) in ENVELOPE.items())


def square_pose(
    dynamic_loft_deg: float = STATIC_LOFT_DEG,
    face_angle_deg: float = 0.0,
    lie_deg: float = STATIC_LIE_DEG,
) -> tuple[float, float, float]:
    """The (yaw, pitch, roll) that delivers the requested angles.

    Solved rather than hard-coded, so it stays correct if the mesh, its
    measured axes, or ``triad``'s convention change. Used to seed fits: a grid
    around the origin searches the neighbourhood of a backwards club.
    """
    from scipy.optimize import minimize  # noqa: PLC0415

    target = {
        "dynamic_loft_deg": float(dynamic_loft_deg),
        "face_angle_deg": float(face_angle_deg),
        "lie_deg": float(lie_deg),
    }

    def cost(params: np.ndarray) -> float:
        angles = angles_from_pose(*params)
        # Circular difference: near +-180 is not 360 degrees from its target.
        total = 0.0
        for key, want in target.items():
            delta = angles[key] - want
            if key == "face_angle_deg":
                delta = math.remainder(delta, 360.0)
            total += delta * delta
        return total

    best = None
    for yaw in (-90.0, 0.0, 90.0, 180.0):
        for pitch in (-180.0, -90.0, 0.0, 90.0):
            for roll in (-90.0, 0.0, 90.0, 180.0):
                result = minimize(
                    cost,
                    np.array([yaw, pitch, roll], dtype=float),
                    method="Nelder-Mead",
                    options={"maxiter": 2000, "xatol": 1e-5, "fatol": 1e-10},
                )
                if best is None or result.fun < best.fun:
                    best = result
    if best is None or best.fun > 1e-3:
        raise RuntimeError(
            f"no pose delivers {target}; residual {None if best is None else best.fun}"
        )
    return tuple(float(v) for v in best.x)
