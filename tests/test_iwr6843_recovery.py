"""Tests for the offline-only IWR6843 alternative-track selector."""

from unittest.mock import patch

import numpy as np
import pytest

from openflight.iwr6843.calibration import Calibration
from openflight.iwr6843.recovery import (
    RecoveryCandidate,
    RecoveryPolicy,
    RecoveryPrior,
    _candidate_tracks_for_scope,
    _fit_line,
    select_recovery_candidate,
    track_impact_time_s,
)
from openflight.iwr6843.tracking import BallTrack, Geometry


def _candidate(
    *,
    ratio: float,
    impact_s: float,
    inliers: int = 30,
    rms: float = 0.25,
    span_s: float = 0.040,
) -> RecoveryCandidate:
    track = BallTrack(
        speed_ms=ratio * 100.0 / 2.237,
        slope_bins=1000.0,
        intercept_bins=10.0,
        rms_bins=rms,
        n_inliers=inliers,
        t_first=0.010,
        t_last=0.010 + span_s,
        low_confidence=False,
    )
    return RecoveryCandidate(track, "window", impact_s, ratio)


def test_prior_uses_median_and_mad_floors():
    prior = RecoveryPrior.fit(
        [0.95, 0.96, 0.97],
        [0.014, 0.015, 0.016],
        [0.039, 0.040, 0.041],
    )

    assert prior.speed_ratio == pytest.approx(0.96)
    assert prior.speed_ratio_scale == pytest.approx(0.014826)
    assert prior.impact_s == pytest.approx(0.015)
    assert prior.impact_scale_s == pytest.approx(0.002)
    assert prior.span_scale_s == pytest.approx(0.004)


def test_selector_prefers_session_consistency_over_raw_support():
    prior = RecoveryPrior(0.96, 0.01, 0.015, 0.002, 0.040, 0.004)
    consistent = _candidate(ratio=0.958, impact_s=0.016, inliers=24)
    wrong_object = _candidate(ratio=0.79, impact_s=0.016, inliers=60)

    selected = select_recovery_candidate([wrong_object, consistent], prior)

    assert selected is not None
    assert selected.track is consistent.track


def test_selector_slightly_prefers_window_mti_when_tracks_are_equivalent():
    prior = RecoveryPrior(0.96, 0.01, 0.015, 0.002, 0.040, 0.004)
    burst = _candidate(ratio=0.96, impact_s=0.015)
    window = RecoveryCandidate(burst.track, "window", burst.impact_s, burst.speed_ratio)

    selected = select_recovery_candidate([burst, window], prior)

    assert selected is not None
    assert selected.scope == "window"


@pytest.mark.parametrize(
    ("candidate", "policy"),
    [
        (_candidate(ratio=0.96, impact_s=0.015, inliers=11), RecoveryPolicy()),
        (_candidate(ratio=0.96, impact_s=0.015, rms=0.49), RecoveryPolicy()),
        (_candidate(ratio=0.96, impact_s=0.015, span_s=0.008), RecoveryPolicy()),
        (
            _candidate(ratio=1.10, impact_s=0.015),
            RecoveryPolicy(max_prior_z=5.0),
        ),
    ],
)
def test_selector_rejects_weak_or_outlying_tracks(candidate, policy):
    prior = RecoveryPrior(0.96, 0.01, 0.015, 0.002, 0.040, 0.004)

    assert select_recovery_candidate([candidate], prior, policy=policy) is None


def test_prior_rejects_mismatched_or_tiny_batches():
    with pytest.raises(ValueError, match="equal lengths"):
        RecoveryPrior.fit([0.96], [0.015, 0.016], [0.040])
    with pytest.raises(ValueError, match="at least three"):
        RecoveryPrior.fit([0.95, 0.96], [0.014, 0.015], [0.039, 0.040])


def test_track_impact_back_extrapolates_to_apparent_tee_range():
    candidate = _candidate(ratio=0.96, impact_s=0.015)
    geometry = Geometry(24, 36, 3, 4, 53, 0.003, 0, range_fft_size=128)
    calibration = Calibration.identity()
    calibration.tee_range_m = 1.5
    calibration.range_bias_m = 0.06
    candidate.track.slope_bins = 1000.0
    candidate.track.intercept_bins = 23.28

    assert track_impact_time_s(candidate.track, geometry, calibration) == pytest.approx(0.010)


def test_closed_form_line_fit_matches_numpy_least_squares():
    times = np.array([0.003, 0.006, 0.012, 0.015, 0.024, 0.030, 0.039])
    bins = np.array([22.1, 24.0, 27.8, 29.9, 35.7, 39.5, 45.4])
    design = np.column_stack((times, np.ones(times.size)))
    expected, *_ = np.linalg.lstsq(design, bins, rcond=None)

    fitted = _fit_line(times, bins)

    assert fitted is not None
    assert fitted[0] == pytest.approx(expected[0], abs=1e-10)
    assert fitted[1] == pytest.approx(expected[1], abs=1e-12)


def test_closed_form_line_fit_rejects_degenerate_times():
    assert _fit_line(np.ones(4), np.arange(4.0)) is None


def test_candidate_generator_recovers_receding_range_walk():
    geometry = Geometry(24, 36, 3, 4, 53, 0.003, 0, range_fft_size=128)
    loop_indices = np.arange(20) * geometry.n_loops
    times = np.arange(20) * geometry.frame_period_s
    expected_speed_ms = 40.0
    bins = np.rint(32.0 + expected_speed_ms / geometry.range_res_m * times).astype(int)
    calibration = Calibration.identity()
    calibration.tee_range_m = 1.5

    with (
        patch("openflight.iwr6843.recovery.tracking.loop_power", return_value=np.zeros(1)),
        patch(
            "openflight.iwr6843.recovery.tracking._detections",
            return_value=(loop_indices, bins),
        ),
    ):
        candidates = _candidate_tracks_for_scope(
            np.zeros((1, 1)),
            geometry,
            calibration,
            scope="window",
            ball_speed_mph=90.0,
            max_range_m=None,
            mti=np.zeros((1, 1)),
        )

    assert candidates
    best = min(candidates, key=lambda candidate: abs(candidate.track.speed_ms - expected_speed_ms))
    assert best.track.speed_ms == pytest.approx(expected_speed_ms, abs=0.5)
    assert best.track.n_inliers >= 19
    assert best.track.rms_bins < 0.35
    assert best.track.t_first == pytest.approx(times[0])
    assert best.track.t_last == pytest.approx(times[-1])
