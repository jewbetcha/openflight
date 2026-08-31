"""The mesh fitter's depth search must contain the real camera-to-ball range.

`fit.py` inherited a 1425 mm camera-to-ball range from a 13.97 px ball
measurement. Across the 21 correctly exposed shots of session 20260825_181734
the teed ball measures 12.77 px, giving 1560 mm, and the tape gives 1581 mm
(camera lens 203.2 mm, ball centre 40 mm, radar slant tee range 1575 mm). The
13.97 px figure traces to the capture that was 99.8 % clipped, where the ball
bloomed.

That is not an inaccuracy, it is a fail-closed violation: both shipped
`range_grid_mm` grids spanned 1300-1550 and 1325-1525, so the true range sat
at or outside the edge and the search could not reach it.
"""

from __future__ import annotations

import inspect
import math

from openflight.camera.clubpose import fit

# Tape chain, all measured: kiosk log mount_height_m, cal json radar_height_m,
# server.py --iwr6843-tee-m / --iwr6843-ball-height-m defaults.
CAMERA_HEIGHT_M = 0.2032
CAMERA_LATERAL_M = -0.060325
RADAR_HEIGHT_M = 0.1524
TEE_RANGE_M = 1.575
BALL_HEIGHT_M = 0.040


def tape_camera_ball_range_mm() -> float:
    forward = math.sqrt(TEE_RANGE_M**2 - (BALL_HEIGHT_M - RADAR_HEIGHT_M) ** 2)
    return 1000.0 * math.hypot(
        math.hypot(forward, CAMERA_LATERAL_M), CAMERA_HEIGHT_M - BALL_HEIGHT_M
    )


def test_tape_chain_gives_about_1580_mm():
    """Guard the reference value itself, so the grids below have an anchor."""
    assert tape_camera_ball_range_mm() == __import__("pytest").approx(1580.0, abs=8.0)


def test_measured_camera_preset_uses_the_tape_range():
    camera = fit.measured_camera()
    implied = fit.FOCAL_PX / camera.plate_scale_px_per_mm
    assert implied == __import__("pytest").approx(tape_camera_ball_range_mm(), abs=25.0)


def test_range_grids_bracket_the_true_range():
    """Every default depth grid must contain the measured range, with margin."""
    truth = tape_camera_ball_range_mm()
    for func in (fit.fit_frame, fit.fit_frame_6dof, fit.fit_sequence):
        grid = inspect.signature(func).parameters["range_grid_mm"].default
        assert min(grid) < truth < max(grid), (
            f"{func.__name__} range_grid_mm={grid} does not contain {truth:.0f} mm"
        )
