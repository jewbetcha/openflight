"""Span floor at 15 ms, and span recorded so the gate is visible.

Session 140533 went 6/7 to 7/7 accepted at 15 ms, recovering shot 1 at
19.25 deg. Session 130951 went 1/7 to 2/7. Span was the gate that rejected
7 of 8 shots in the first session and was invisible in the log.
"""

from openflight.iwr6843 import shot as shotmod
from openflight.iwr6843.lcmf import LCMFResult


def test_span_floor_is_15ms():
    assert shotmod.REJECT_MIN_SPAN_S == 0.015


def test_track_broken_boundary():
    class FakeTrack:
        rms_bins = 0.20
        n_inliers = 40

        def __init__(self, span_s):
            self.t_first = 0.0
            self.t_last = span_s

    assert shotmod.track_broken(FakeTrack(0.0149)) is True
    assert shotmod.track_broken(FakeTrack(0.0151)) is False


def test_track_broken_still_enforces_rms_and_inliers():
    """Relaxing span must not weaken the other two gates."""

    class FakeTrack:
        def __init__(self, rms, inliers):
            self.rms_bins = rms
            self.n_inliers = inliers
            self.t_first = 0.0
            self.t_last = 0.033

    assert shotmod.track_broken(FakeTrack(0.60, 40)) is True  # rms >= 0.50
    assert shotmod.track_broken(FakeTrack(0.20, 27)) is True  # inliers < 28
    assert shotmod.track_broken(FakeTrack(0.20, 40)) is False


def test_result_exposes_track_span():
    payload = LCMFResult(status="accepted", track_span_s=0.0331).to_dict()
    assert payload["track_span_s"] == 0.0331
