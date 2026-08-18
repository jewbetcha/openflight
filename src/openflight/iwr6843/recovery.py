"""Experimental second-pass range-track selection for offline LCMF replay.

This module never changes the production ball tracker. It ranks alternative
range walks using only radar/OPS observables and a prior learned from accepted
captures in the same batch. TrackMan launch angle is deliberately absent from
the API so it cannot leak into selection.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from openflight.iwr6843 import tracking
from openflight.iwr6843.calibration import Calibration
from openflight.iwr6843.dump import is_range_snapshot, parse_dump, project_tx_pair
from openflight.iwr6843.shot import TX2_LOOP_PERIOD_S, PreparedShotDump, geometry_from_header
from openflight.iwr6843.tracking import BallTrack, Geometry


@dataclass(frozen=True)
class RecoveryPrior:
    """Robust center and scale of accepted-track observables."""

    speed_ratio: float
    speed_ratio_scale: float
    impact_s: float
    impact_scale_s: float
    span_s: float
    span_scale_s: float

    @classmethod
    def fit(
        cls,
        speed_ratios: list[float],
        impact_times_s: list[float],
        spans_s: list[float],
    ) -> "RecoveryPrior":
        """Fit median/MAD priors without launch-angle truth."""
        if len(speed_ratios) != len(impact_times_s) or len(speed_ratios) != len(spans_s):
            raise ValueError("recovery prior observations must have equal lengths")
        if len(speed_ratios) < 3:
            raise ValueError("recovery prior requires at least three accepted tracks")

        def robust(values: list[float], floor: float) -> tuple[float, float]:
            array = np.asarray(values, dtype=float)
            if not np.all(np.isfinite(array)):
                raise ValueError("recovery prior observations must be finite")
            median = float(np.median(array))
            sigma = float(1.4826 * np.median(np.abs(array - median)))
            return median, max(sigma, floor)

        ratio, ratio_scale = robust(speed_ratios, 0.01)
        impact, impact_scale = robust(impact_times_s, 0.002)
        span, span_scale = robust(spans_s, 0.004)
        return cls(ratio, ratio_scale, impact, impact_scale, span, span_scale)


@dataclass(frozen=True)
class RecoveryCandidate:
    """One alternative physical range walk plus truth-free rank evidence."""

    track: BallTrack
    scope: str
    impact_s: float
    speed_ratio: float
    score: float = float("inf")


@dataclass(frozen=True)
class RecoveryPolicy:
    """Conservative gates frozen from the 2026-08-11 offline experiment."""

    min_inliers: int = 12
    min_span_s: float = 0.009
    max_rms_bins: float = 0.48
    max_prior_z: float = 5.0
    burst_scope_penalty: float = 0.5


def _fit_line(times: np.ndarray, bins: np.ndarray) -> tuple[float, float] | None:
    """Fit ``bins = slope * times + intercept`` without allocating a design matrix."""
    count = times.size
    sum_time = float(times.sum())
    sum_bin = float(bins.sum())
    sum_time_sq = float(np.dot(times, times))
    denominator = count * sum_time_sq - sum_time * sum_time
    if denominator <= 0.0:
        return None
    slope = (count * float(np.dot(times, bins)) - sum_time * sum_bin) / denominator
    intercept = (sum_bin - slope * sum_time) / count
    return slope, intercept


def track_impact_time_s(
    track: BallTrack,
    geometry: Geometry,
    calibration: Calibration,
) -> float | None:
    """Back-extrapolate a receding track to the configured tee range."""
    if calibration.tee_range_m is None or track.slope_bins <= 0.0:
        return None
    apparent_tee_m = calibration.tee_range_m + calibration.range_bias_m
    impact_s = (apparent_tee_m / geometry.range_res_m - track.intercept_bins) / track.slope_bins
    if not 0.0 <= impact_s <= geometry.capture_duration_s:
        return None
    return float(impact_s)


def _candidate_tracks_for_scope(  # pylint: disable=too-many-arguments
    cube: np.ndarray,
    geometry: Geometry,
    calibration: Calibration,
    *,
    scope: str,
    ball_speed_mph: float,
    max_range_m: float | None,
    mti: np.ndarray | None = None,
) -> list[RecoveryCandidate]:
    if mti is None:
        mti = tracking.mti_filter(
            cube,
            scope=scope,
            range_domain=True,
            geometry=geometry,
        )
    power = tracking.loop_power(mti)
    loop_indices, bins = tracking._detections(  # pylint: disable=protected-access
        power,
        geometry,
        max_range_m=max_range_m,
    )
    if loop_indices.size < 8:
        return []

    times = np.asarray(
        [
            geometry.loop_time(index // geometry.n_loops, index % geometry.n_loops)
            for index in loop_indices
        ]
    )
    resolution_m = geometry.range_res_m
    candidates: dict[tuple[int, int], RecoveryCandidate] = {}
    if calibration.tee_range_m is None:
        raise ValueError("recovery requires measured tee range")
    apparent_tee_m = calibration.tee_range_m + calibration.range_bias_m
    min_slope = 20.0 / resolution_m
    max_slope = 90.0 / resolution_m
    for first in range(times.size - 1):
        later_times = times[first + 1 :]
        delta_times = times[first] - later_times
        valid_time = np.abs(delta_times) >= 0.003
        slopes = np.divide(
            bins[first] - bins[first + 1 :],
            delta_times,
            out=np.zeros_like(delta_times),
            where=valid_time,
        )
        valid_seconds = np.flatnonzero(valid_time & (slopes >= min_slope) & (slopes <= max_slope))
        for second_offset in valid_seconds:
            slope = float(slopes[second_offset])
            intercept = bins[first] - slope * times[first]
            inliers = np.abs(bins - (slope * times + intercept)) < 0.8
            count = int(inliers.sum())
            if count < 10:
                continue
            inlier_times = times[inliers]
            inlier_bins = bins[inliers]
            fit = _fit_line(inlier_times, inlier_bins)
            if fit is None:
                continue
            fitted_slope, fitted_intercept = fit
            speed_ms = float(fitted_slope * resolution_m)
            if not 20.0 <= speed_ms <= 90.0:
                continue
            residuals = inlier_bins - (fitted_slope * inlier_times + fitted_intercept)
            rms = float(np.sqrt(np.mean(residuals**2)))
            first_time = float(inlier_times.min())
            last_time = float(inlier_times.max())
            track = BallTrack(
                speed_ms=speed_ms,
                slope_bins=float(fitted_slope),
                intercept_bins=float(fitted_intercept),
                rms_bins=rms,
                n_inliers=count,
                t_first=first_time,
                t_last=last_time,
                low_confidence=rms >= 0.45 or last_time - first_time < 0.012,
            )
            impact_s = (apparent_tee_m / resolution_m - fitted_intercept) / fitted_slope
            if not 0.0 <= impact_s <= geometry.capture_duration_s:
                continue
            candidate = RecoveryCandidate(
                track=track,
                scope=scope,
                impact_s=float(impact_s),
                speed_ratio=track.speed_mph / ball_speed_mph,
            )
            key = (round(speed_ms / 0.6), round(impact_s / 0.0008))
            incumbent = candidates.get(key)
            quality = (count, -rms, last_time - first_time)
            if incumbent is None:
                candidates[key] = candidate
                continue
            old = incumbent.track
            old_quality = (old.n_inliers, -old.rms_bins, old.t_last - old.t_first)
            if quality > old_quality:
                candidates[key] = candidate
    return list(candidates.values())


def find_recovery_candidates(
    raw: bytes,
    calibration: Calibration,
    *,
    ball_speed_mph: float,
    net_range_m: float | None,
    prepared: PreparedShotDump | None = None,
) -> list[RecoveryCandidate]:
    """Generate alternative tracks from burst- and window-scope MTI."""
    if ball_speed_mph <= 0:
        raise ValueError("ball_speed_mph must be positive")
    if calibration.tee_range_m is None:
        raise ValueError("recovery requires measured tee range")
    if prepared is None:
        metadata, _ = parse_dump(raw)
        vertical_raw = project_tx_pair(raw, (0, 2)) if metadata["n_tx"] == 3 else raw
        vertical_meta, cube = parse_dump(vertical_raw)
        loop_period_s = TX2_LOOP_PERIOD_S if metadata["n_tx"] == 3 else tracking.LOOP_PRI_S
        geometry = geometry_from_header(vertical_meta, loop_period_s=loop_period_s)
    else:
        vertical_meta = prepared.metadata
        cube = prepared.cube
        geometry = prepared.geometry
    if not is_range_snapshot(vertical_meta):
        raise ValueError("recovery currently requires a range-snapshot dump")
    max_range_m = net_range_m - 0.25 if net_range_m is not None else None
    candidates: list[RecoveryCandidate] = []
    for scope in ("burst", "window"):
        if prepared is None:
            candidates.extend(
                _candidate_tracks_for_scope(
                    cube,
                    geometry,
                    calibration,
                    scope=scope,
                    ball_speed_mph=ball_speed_mph,
                    max_range_m=max_range_m,
                )
            )
            continue
        candidates.extend(
            _candidate_tracks_for_scope(
                cube,
                geometry,
                calibration,
                scope=scope,
                ball_speed_mph=ball_speed_mph,
                max_range_m=max_range_m,
                mti=prepared.mti(scope),
            )
        )
    return candidates


def select_recovery_candidate(
    candidates: list[RecoveryCandidate],
    prior: RecoveryPrior,
    *,
    policy: RecoveryPolicy = RecoveryPolicy(),
) -> RecoveryCandidate | None:
    """Select the closest credible track to accepted session behavior."""
    if not candidates:
        return None
    max_inliers = max(candidate.track.n_inliers for candidate in candidates)
    ranked: list[RecoveryCandidate] = []
    for candidate in candidates:
        track = candidate.track
        span_s = track.t_last - track.t_first
        ratio_z = (candidate.speed_ratio - prior.speed_ratio) / prior.speed_ratio_scale
        impact_z = (candidate.impact_s - prior.impact_s) / prior.impact_scale_s
        span_z = (span_s - prior.span_s) / prior.span_scale_s
        if (
            abs(ratio_z) > policy.max_prior_z
            or abs(impact_z) > policy.max_prior_z
            or track.n_inliers < policy.min_inliers
            or span_s < policy.min_span_s
            or track.rms_bins > policy.max_rms_bins
        ):
            continue
        support = track.n_inliers / max_inliers
        score = (
            ratio_z**2
            + impact_z**2
            + 0.20 * span_z**2
            + 1.50 * (1.0 - support) ** 2
            + 0.20 * (track.rms_bins / 0.4) ** 2
            + (policy.burst_scope_penalty if candidate.scope == "burst" else 0.0)
        )
        ranked.append(
            RecoveryCandidate(
                track=track,
                scope=candidate.scope,
                impact_s=candidate.impact_s,
                speed_ratio=candidate.speed_ratio,
                score=float(score),
            )
        )
    return min(ranked, key=lambda candidate: candidate.score) if ranked else None


__all__ = [
    "RecoveryCandidate",
    "RecoveryPolicy",
    "RecoveryPrior",
    "find_recovery_candidates",
    "select_recovery_candidate",
    "track_impact_time_s",
]
