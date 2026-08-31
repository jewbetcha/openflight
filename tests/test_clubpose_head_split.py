"""Tests for separating the clubhead from the shaft.

The shipped tracker treats one moving connected component as the clubhead. That
held only because the reference capture was so overexposed that the shaft had no
contrast. On a properly exposed capture (session 20260825_181734) the shaft is a
strong moving object and merges with the head for the frames closest to impact,
so the merged component's centroid sits halfway up the shaft.

These use synthetic masks with the geometry measured from that session, so they
run without the capture archive.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from openflight.camera.clubpose.head_split import (
    HEAD_CORE_PX,
    SHAFT_MAX_PX,
    SHAFT_REACH_PX,
    split_head,
)


def _head(shape=(200, 320), centre=(150, 148), half=(22, 15)) -> np.ndarray:
    """A compact body, the size a real clubhead measures at this plate scale."""
    m = np.zeros(shape, np.uint8)
    cv2.ellipse(m, centre, half, 0, 0, 360, 1, -1)
    return m


def _shaft(shape=(200, 320), start=(160, 138), end=(250, 20), width=5) -> np.ndarray:
    """A thin line. Measured shaft width on real frames is 4-6 px."""
    m = np.zeros(shape, np.uint8)
    cv2.line(m, start, end, 1, width)
    return m


def test_isolated_head_is_returned_whole():
    """A component that is entirely clubhead must come back unchanged.

    An earlier version seeded the shaft marker by distance from the head core
    alone, which cut the thin toe and sole extremities off 54 of 119 real heads.
    """
    head = _head()
    out = split_head(head)
    assert out is not None
    got, shaft = out
    assert int(shaft.sum()) == 0
    assert int(got.sum()) == int(head.sum())


def test_pure_shaft_is_refused():
    """Fail closed: a thin line is not a clubhead, so there is nothing to return."""
    assert split_head(_shaft()) is None


def test_merged_component_splits_at_the_neck():
    head, shaft = _head(), _shaft()
    merged = np.clip(head + shaft, 0, 1).astype(np.uint8)
    n, _ = cv2.connectedComponents(merged, 8)
    assert n == 2, "fixture must actually be one connected component"

    out = split_head(merged)
    assert out is not None
    got_head, got_shaft = out

    assert not np.any(got_head & (merged == 0))
    assert not np.any(got_shaft & (merged == 0))
    assert int((got_head | got_shaft).sum()) == int(merged.sum())

    overlap = int((got_head & head).sum()) / int(head.sum())
    assert overlap > 0.9, f"recovered only {overlap:.1%} of the head"
    stolen = int((got_head & (shaft & ~head)).sum())
    assert stolen < 0.25 * int(shaft.sum()), "kept too much shaft"


def test_merged_centroid_is_wrong_which_is_why_this_exists():
    """The regression this guards: the merged centroid is not the clubhead."""
    head, shaft = _head(), _shaft()
    merged = np.clip(head + shaft, 0, 1).astype(np.uint8)

    def centroid(m):
        ys, xs = np.nonzero(m)
        return np.array([xs.mean(), ys.mean()])

    drift = float(np.linalg.norm(centroid(merged) - centroid(head)))
    assert drift > 20.0, "fixture should reproduce the centroid drift"

    got_head, _ = split_head(merged)
    fixed = float(np.linalg.norm(centroid(got_head) - centroid(head)))
    # A shaft stub stays attached in this fixture (no sharp constriction);
    # what matters is the centroid is the head's, not the merged blob's.
    assert fixed < drift / 3.0, f"split centroid {fixed:.1f} px off vs merged {drift:.1f}"


def test_thresholds_sit_in_the_measured_gaps():
    """The constants are read off measurements, not tuned. Keep them there."""
    assert 3.0 < HEAD_CORE_PX < 5.0, "must exceed every shaft, sit below every head"
    assert 3.0 < SHAFT_MAX_PX < 5.0
    assert 40.8 < SHAFT_REACH_PX < 145.4, "must sit in the measured reach gap"


@pytest.mark.parametrize("width", [4, 5, 6, 7])
def test_split_survives_the_measured_shaft_width_range(width):
    head = _head()
    merged = np.clip(head + _shaft(width=width), 0, 1).astype(np.uint8)
    out = split_head(merged)
    assert out is not None
    got_head, _ = out
    assert int((got_head & head).sum()) / int(head.sum()) > 0.85
