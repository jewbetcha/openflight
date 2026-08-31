"""Sequence-level rigid-rotation primitives for clubhead pose experiments."""

from __future__ import annotations

import math

import numpy as np


def axis_from_angles(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    """Return a unit world axis from azimuth and elevation in degrees."""
    azimuth = math.radians(float(azimuth_deg))
    elevation = math.radians(float(elevation_deg))
    horizontal = math.cos(elevation)
    return np.asarray(
        (
            horizontal * math.cos(azimuth),
            horizontal * math.sin(azimuth),
            math.sin(elevation),
        ),
        dtype=float,
    )


def constrained_omega_deg_s(
    speed_mps: float,
    swing_radius_m: float,
    axis_azimuth_deg: float,
    axis_elevation_deg: float,
) -> np.ndarray:
    """Return angular velocity whose magnitude is fixed by ``omega = v / r``."""
    speed = float(speed_mps)
    radius = float(swing_radius_m)
    if not math.isfinite(speed) or speed <= 0.0:
        raise ValueError("club speed must be finite and positive")
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError("swing radius must be finite and positive")
    magnitude_deg_s = math.degrees(speed / radius)
    return magnitude_deg_s * axis_from_angles(axis_azimuth_deg, axis_elevation_deg)
