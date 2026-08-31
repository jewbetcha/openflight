"""Properties of the polarity-agnostic ball detector, pinned by test.

Each test here corresponds to a defect found by pointing the existing detector at
the first real OpenFlight capture (`frames.npz`, 2026-08-24). They are written so a
regression re-breaks the specific thing that was broken.
"""

from __future__ import annotations

import numpy as np
import pytest

from openflight.camera.clubpose.teed_ball import (
    BallNotFound,
    _fit_circle,
    candidates,
    fit_teed_ball_sequence,
)


def _disc(shape, center, radius, fg, bg, *, cap=None):
    """Render a disc. `cap` clips everything above that row to the background,
    reproducing a ball whose lit upper surface has blended into a saturated mat."""
    image = np.full(shape, bg, dtype=np.uint8)
    ys, xs = np.mgrid[0 : shape[0], 0 : shape[1]]
    inside = (xs - center[0]) ** 2 + (ys - center[1]) ** 2 <= radius**2
    if cap is not None:
        inside &= ys >= cap
    image[inside] = fg
    return image


@pytest.mark.parametrize("arc_deg", [360, 300, 240, 180, 120, 90])
def test_circle_fit_is_exact_on_partial_arcs(arc_deg):
    """The previous algebraic fit was biased -44% at 120 degrees of arc.

    Partial arcs are the normal case, not the exception: at address the ball's lit
    side blends into the background and only part of its outline survives.
    """
    angles = np.radians(np.linspace(0.0, arc_deg, max(12, arc_deg // 6), endpoint=False))
    center, radius = np.array([127.0, 154.0]), 7.3
    points = np.column_stack(
        [center[0] + radius * np.cos(angles), center[1] + radius * np.sin(angles)]
    )
    fitted_center, fitted_radius = _fit_circle(points)
    assert fitted_radius == pytest.approx(radius, abs=1e-6)
    assert fitted_center == pytest.approx(center, abs=1e-6)


def test_finds_ball_darker_than_its_background():
    """The real teed ball is 62 DN DARKER than the clipped mat it sits on.

    The rule it replaces asked for `>= background + 210 DN`, which cannot express a
    negative contrast at any threshold value.
    """
    frame = _disc((200, 320), (127, 154), 7, fg=192, bg=255)
    found = candidates(frame)
    assert found, "a dark ball on a light background must be detectable"
    best = min(found, key=lambda c: np.linalg.norm(c.center - np.array([127.0, 154.0])))
    assert best.polarity == "dark_on_light"
    assert best.contrast_dn < 0
    assert best.center == pytest.approx(np.array([127.0, 154.0]), abs=1.5)


def test_finds_ball_brighter_than_its_background_below_the_old_threshold():
    """The real airborne ball is +122 DN, which the old `+210 DN` bar also failed."""
    frame = _disc((200, 320), (128, 84), 7, fg=224, bg=102)
    found = candidates(frame)
    best = min(found, key=lambda c: np.linalg.norm(c.center - np.array([128.0, 84.0])))
    assert best.polarity == "light_on_dark"
    assert 0 < best.contrast_dn < 210
    assert best.center == pytest.approx(np.array([128.0, 84.0]), abs=1.5)


def test_detector_is_not_fooled_by_a_static_round_distractor():
    """A bay contains signage and shoes that fit a circle better than a blended ball.

    Shape alone picked the golfer's leg in 10 real frames out of 10. Departure is
    what separates them: the ball leaves, the clutter does not.
    """
    frames = []
    for index in range(40):
        frame = _disc((200, 320), (40, 30), 9, fg=230, bg=100)  # static distractor
        if index < 30:  # ball, gone after 30
            ys, xs = np.mgrid[0:200, 0:320]
            frame[(xs - 127) ** 2 + (ys - 154) ** 2 <= 49] = 60
        frames.append(frame)
    result = fit_teed_ball_sequence(
        np.array(frames), 30, (80, 120, 200, 190), lead=30, look_after=4
    )
    assert result.center == pytest.approx(np.array([127.0, 154.0]), abs=3.0)


def test_rejection_is_named_not_silent():
    frames = np.full((20, 200, 320), 128, dtype=np.uint8)
    with pytest.raises(BallNotFound) as excinfo:
        fit_teed_ball_sequence(frames, 12, (80, 120, 200, 190), lead=10, look_after=3)
    assert str(excinfo.value) in {
        "no_candidate_in_tee_region",
        "no_departing_candidate_in_tee_region",
        "no_comparable_post_impact_frame",
    }


def _mat_scene(n_frames, balls, occluder=None):
    """A blown-out mat carrying several balls. `balls` is (x, y, departs_at|None)."""
    frames = []
    for index in range(n_frames):
        frame = np.full((200, 320), 255, dtype=np.uint8)
        ys, xs = np.mgrid[0:200, 0:320]
        for bx, by, departs in balls:
            if departs is not None and index >= departs:
                continue
            frame[(xs - bx) ** 2 + (ys - by) ** 2 <= 49] = 192
        if occluder is not None:
            ox, oy, active = occluder
            if index in active:
                frame[max(0, oy - 14) : oy + 14, max(0, ox - 16) : ox + 16] = 120
        frames.append(frame)
    return np.array(frames)


TEE = (80, 120, 220, 190)


def test_picks_the_struck_ball_when_several_are_on_the_mat():
    """A real bay holds spares. Only the struck ball leaves."""
    scene = _mat_scene(40, [(127, 154, 30), (160, 168, None), (100, 140, None)])
    result = fit_teed_ball_sequence(scene, 30, TEE, lead=30, look_after=4)
    assert result.center == pytest.approx(np.array([127.0, 154.0]), abs=4.0)


def test_a_spare_ball_swept_over_by_the_club_is_not_mistaken_for_the_struck_one():
    """Brief occlusion looks like a partial departure; full departure must outrank it."""
    scene = _mat_scene(40, [(127, 154, 30), (175, 170, None)], occluder=(175, 170, {32, 33, 34}))
    result = fit_teed_ball_sequence(scene, 30, TEE, lead=30, look_after=4)
    assert result.center == pytest.approx(np.array([127.0, 154.0]), abs=4.0)


def test_selection_is_by_departure_not_by_position_in_the_tee_region():
    """The struck ball need not be the one nearest the middle of the region."""
    scene = _mat_scene(40, [(200, 180, None), (95, 130, 30)])
    result = fit_teed_ball_sequence(scene, 30, TEE, lead=30, look_after=4)
    assert result.center == pytest.approx(np.array([95.0, 130.0]), abs=4.0)
