"""One collapsed channel must not drag the answer down.

Field data, 2026-07-25 session 140533 shot 1: two8 = -1.66, four4 = 19.25.
The plain mean reported 8.79; the operator confirmed the ball flew like a
normal 7-iron, which 8.79 is not. The 8.0 degree threshold sits in a real gap:
the one shot whose channels agreed had a 4.59 degree spread, the collapsed
ones spanned 15.9-20.2.

Three ways selection can go wrong once it exists, all covered below:
a channel that measured nothing being scored as if it had; a tie or an
absent score handing the answer to whichever channel happens to be first in
the dict; and a diagnostic-only component widening the spread far enough to
break a corroboration it can never win.
"""

import numpy as np
import pytest

from openflight.iwr6843 import lcmf


def test_agreeing_channels_are_averaged():
    angle, used, single = lcmf.combine_channels(
        {"channel_two8_deg": 26.62, "channel_four4_path_tdm_deg": 22.03},
        {"channel_two8_deg": 1.0, "channel_four4_path_tdm_deg": 1.0},
    )
    assert angle == pytest.approx(24.325, abs=0.01)
    assert single is False
    assert len(used) == 2


def test_collapsed_channel_is_dropped():
    """The field case: keep four4, discard two8."""
    angle, used, single = lcmf.combine_channels(
        {"channel_two8_deg": -1.66, "channel_four4_path_tdm_deg": 19.25},
        {"channel_two8_deg": 0.2, "channel_four4_path_tdm_deg": 0.9},
    )
    assert angle == pytest.approx(19.25, abs=0.01)
    assert used == ["channel_four4_path_tdm_deg"]
    assert single is True


def test_spread_threshold_boundary():
    just_inside = lcmf.combine_channels({"a": 10.0, "b": 17.9}, {"a": 1.0, "b": 1.0})
    just_outside = lcmf.combine_channels({"a": 10.0, "b": 18.1}, {"a": 0.1, "b": 1.0})
    assert just_inside[2] is False
    assert just_outside[2] is True


def test_single_channel_input_is_not_an_error():
    angle, used, single = lcmf.combine_channels({"a": 17.0}, {"a": 1.0})
    assert angle == pytest.approx(17.0)
    assert single is True


def test_curvature_measures_sharpness_of_the_minimum():
    """A sharp minimum scores higher than a flat one."""
    grid = np.linspace(-1.0, 1.0, 41)
    sharp = grid**2
    flat = 0.01 * grid**2
    assert lcmf.grid_curvature(sharp) > lcmf.grid_curvature(flat)


def test_edge_minimum_scores_none_not_zero():
    """ "Not measured" and "flat" are different verdicts and must not collide.

    An argmin on the grid edge means the true minimum lies OUTSIDE the
    searched range -- the grid runs to 45 deg and a lofted club can exceed
    that -- so the channel measured nothing at all. Scoring that 0.0, as it
    used to, let an edge-pinned healthy channel tie with a collapsed one and
    then lose the tie on dict-insertion order.

    A flat array is the same failure, not a separate "flat" case: every value
    ties, so argmin lands on index 0.
    """
    rising = np.arange(41, dtype=float)  # minimum at index 0
    falling = rising[::-1].copy()  # minimum at the last index
    assert lcmf.grid_curvature(rising) is None
    assert lcmf.grid_curvature(falling) is None
    assert lcmf.grid_curvature(np.zeros(41)) is None


def test_interior_curvature_is_always_strictly_positive():
    """0.0 is the contract's "degenerate" floor, not a value this can return.

    ``argmin`` reports the FIRST occurrence of the minimum, so an interior
    argmin ``i`` has ``y0 > y1`` strictly (otherwise the argmin would sit
    earlier) and ``y2 >= y1``. Their sum is therefore strictly positive, and
    the ``max(0.0, ...)`` clamp never fires. This is why the zero-evidence
    branches in ``combine_channels`` are reachable only from a caller that
    supplies its own scores -- worth knowing before treating them as live
    paths against real objectives.
    """
    rng = np.random.default_rng(7)
    scored = 0
    for _ in range(2000):
        objective = rng.normal(size=41) * float(10.0 ** rng.integers(-8, 9))
        curvature = lcmf.grid_curvature(objective)
        if curvature is not None:
            scored += 1
            assert curvature > 0.0, objective
    assert scored > 1500, f"fixture degenerate: only {scored} interior minima"


def test_edge_pinned_channel_does_not_participate():
    """A channel that measured nothing cannot win, tie, or widen the spread.

    Two channels 23 deg apart, one of them off the grid: the surviving
    channel is the whole answer, and the disagreement with a non-measurement
    is not a disagreement.
    """
    angle, used, single = lcmf.combine_channels(
        {"channel_two8_deg": -1.66, "channel_four4_path_tdm_deg": 21.7},
        {"channel_two8_deg": None, "channel_four4_path_tdm_deg": 2.0e-3},
    )
    assert angle == pytest.approx(21.7)
    assert used == ["channel_four4_path_tdm_deg"]
    assert single is True


def test_tied_curvature_rejects_rather_than_picking_the_first_channel():
    """Two flat channels 23 deg apart is a rejection, not a coin flip.

    ``max()`` returns the FIRST key on a tie, and ``channel_two8_deg`` is
    first in insertion order -- the very channel that collapses. Silently
    returning -1.66 deg here would report a 7-iron as flat.
    """
    angle, used, single = lcmf.combine_channels(
        {"channel_two8_deg": -1.66, "channel_four4_path_tdm_deg": 21.7},
        {"channel_two8_deg": 0.0, "channel_four4_path_tdm_deg": 0.0},
    )
    assert angle is None
    assert used == []
    assert single is False


def test_missing_evidence_rejects_rather_than_picking_the_first_channel():
    """Absent evidence is not zero evidence, and neither one selects.

    ``evidence.get(name, 0.0)`` used to swallow the difference, so a caller
    that forgot to record curvature got the insertion-order-first channel
    back and no indication anything was wrong.
    """
    angle, used, single = lcmf.combine_channels(
        {"channel_two8_deg": -1.66, "channel_four4_path_tdm_deg": 21.7},
        {},
    )
    assert angle is None
    assert used == []
    assert single is False


def test_disagreeing_channels_select_only_on_positive_curvature():
    """A flat channel loses to a sharp one even when it is listed first."""
    angle, used, _single = lcmf.combine_channels(
        {"channel_two8_deg": -1.66, "channel_four4_path_tdm_deg": 21.7},
        {"channel_two8_deg": 0.0, "channel_four4_path_tdm_deg": 1.0e-3},
    )
    assert angle == pytest.approx(21.7)
    assert used == ["channel_four4_path_tdm_deg"]


def test_fast_components_are_logged_but_never_vote():
    """Diagnostic components must not be able to veto a real corroboration.

    Two channels agreeing to 0.4 deg is the corroborated case. Merging the
    ``fast_*`` estimates into the same comparison put an 11 deg outlier in
    the spread, pushed it past CHANNEL_SPREAD_MAX_DEG, and forced selection
    -- and because those estimates carried zero evidence they could never be
    chosen, so the result was one channel flagged ``single_channel`` and
    derated. Here the estimator is called through ``combine_channels``
    directly with only the selectable channels, which is the fix.
    """
    channels = {"channel_two8_deg": 17.9, "channel_four4_path_tdm_deg": 18.3}
    evidence = {"channel_two8_deg": 1.0e-3, "channel_four4_path_tdm_deg": 2.0e-3}

    angle, used, single = lcmf.combine_channels(channels, evidence)
    assert single is False, "two channels 0.4 deg apart are corroborated"
    assert len(used) == 2
    assert angle == pytest.approx(18.1)

    polluted = dict(channels) | {"fast_direct1_deg": 7.0}
    assert lcmf.combine_channels(polluted, evidence)[2] is False, (
        "an unscored diagnostic component must not reach the spread gate"
    )


def test_measured_field_curvatures_pick_four4():
    """Real curvatures from session 140533 must select the healthy channel.

    two8 is flatter on every shot by 3.7-10.7x. Using distance from the
    component median instead would tie and pick two8, defeating the fix.
    """
    for two8_curv, four4_curv in [
        (3.21e-04, 2.03e-03),
        (4.33e-04, 4.63e-03),
        (4.43e-04, 3.71e-03),
    ]:
        angle, used, single = lcmf.combine_channels(
            {"channel_two8_deg": -1.0, "channel_four4_path_tdm_deg": 19.0},
            {"channel_two8_deg": two8_curv, "channel_four4_path_tdm_deg": four4_curv},
        )
        assert used == ["channel_four4_path_tdm_deg"], used
        assert angle == pytest.approx(19.0)
        assert single is True
