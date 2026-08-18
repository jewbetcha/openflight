"""Runtime boundary joining TI capture to the frozen LCMF estimator."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace

from openflight.iwr6843.calibration import Calibration
from openflight.iwr6843.club import ClubPathResult, estimate_club_path
from openflight.iwr6843.lcmf import (
    LCMFResult,
    PreparedLCMFCapture,
    estimate_lcmf_v1,
    prepare_lcmf_capture,
)
from openflight.iwr6843.monitor import IWR6843Capture, IWR6843CaptureMonitor
from openflight.iwr6843.recovery import RecoveryCandidate, find_recovery_candidates

logger = logging.getLogger(__name__)

# The ball estimate's measured tdm_sign_used takes priority; this only
# resolves the TDM sign for the club-path fallback when it is unavailable.
# "auto" has no fixed sign of its own, so it defaults to positive, same as
# this module's own tdm_sign_policy default.
_TDM_SIGN_BY_POLICY = {"positive": 1, "negative": -1, "auto": 1}

# TrackMan holdout tracks centered almost exactly on OPS speed. A larger
# disagreement is unusual enough to justify a bounded alternate-track pass,
# but not enough by itself to choose an angle.
OPS_TRACK_SPEED_TOLERANCE_FRAC = 0.15
OPS_GUIDED_MAX_CANDIDATES = 8
OPS_GUIDED_MIN_LAUNCH_DEG = 2.0


def _ops_candidate_rank(candidate: RecoveryCandidate) -> tuple[float, int, float]:
    """Rank truth-free range walks before the more expensive LCMF pass."""
    return (
        abs(candidate.speed_ratio - 1.0),
        -candidate.track.n_inliers,
        candidate.track.rms_bins,
    )


def _credible_ops_candidates(
    candidates: list[RecoveryCandidate],
) -> list[RecoveryCandidate]:
    """Return a small, deduplicated set of OPS-compatible range walks."""
    credible = [
        candidate
        for candidate in candidates
        if abs(candidate.speed_ratio - 1.0) <= OPS_TRACK_SPEED_TOLERANCE_FRAC
        and candidate.track.n_inliers >= 12
        and candidate.track.rms_bins <= 0.48
        and candidate.track.t_last - candidate.track.t_first >= 0.009
    ]
    credible.sort(key=_ops_candidate_rank)
    selected: list[RecoveryCandidate] = []
    seen: set[tuple[int, int]] = set()
    for candidate in credible:
        # RANSAC emits many nearly identical lines. Keep one representative
        # per approximately 1 mph / 1.5 ms speed-impact cell.
        key = (
            round(candidate.track.speed_mph),
            round(candidate.impact_s / 0.0015),
        )
        if key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
        if len(selected) >= OPS_GUIDED_MAX_CANDIDATES:
            break
    return selected


def _recovery_result_rank(
    candidate: RecoveryCandidate,
    result: LCMFResult,
) -> tuple[bool, float, float, int, float]:
    """Combine OPS agreement with independent spatial-estimator evidence."""
    # A single channel can still be useful (shot 6 on 2026-08-14), but must
    # beat a corroborated candidate by a meaningful OPS-speed margin.
    single_channel_penalty = 0.03 if result.single_channel else 0.0
    spread = float(result.component_std_deg or 0.0)
    return (
        result.single_channel,
        abs(candidate.speed_ratio - 1.0) + single_channel_penalty + 0.01 * min(spread, 8.0),
        candidate.track.rms_bins,
        -result.n_frames,
        -candidate.track.n_inliers,
    )


@dataclass(frozen=True)
class IWR6843ShotResult:
    """Capture transport result and optional angle measurement."""

    capture: IWR6843Capture | None
    measurement: LCMFResult | None
    club_path: ClubPathResult | None = None


@dataclass
class IWR6843Runtime:
    """Configured TI hardware and estimator state for the server."""

    capture_monitor: IWR6843CaptureMonitor
    calibration: Calibration
    net_range_m: float | None
    tx_order: str = "normal"
    capture_timeout_s: float = 12.0
    azimuth_offset_deg: float = 0.0
    horizontal_phase_reference_rad: float | None = None
    tdm_sign_policy: str = "positive"

    def _ops_guided_measurement(  # pylint: disable=too-many-return-statements
        self,
        raw: bytes,
        calibration: Calibration,
        *,
        ball_speed_mph: float,
        club: str | None,
        baseline: LCMFResult,
        prepared: PreparedLCMFCapture,
    ) -> LCMFResult:
        """Replace a suspicious TI range walk with an OPS-compatible one."""
        speed = baseline.track_speed_mph
        if baseline.accepted and speed is None:
            return replace(baseline, status="accepted_track_speed_warning")
        speed_error = (
            abs(speed / ball_speed_mph - 1.0)
            if speed is not None and ball_speed_mph > 0.0
            else float("inf")
        )
        if baseline.accepted and speed_error <= OPS_TRACK_SPEED_TOLERANCE_FRAC:
            return baseline

        try:
            candidates = _credible_ops_candidates(
                find_recovery_candidates(
                    raw,
                    calibration,
                    ball_speed_mph=ball_speed_mph,
                    net_range_m=self.net_range_m,
                    prepared=prepared.vertical,
                )
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            logger.warning("[IWR6843] OPS-guided track search failed: %s", error)
            if baseline.accepted:
                return replace(baseline, status="accepted_track_speed_warning")
            return baseline
        recoveries: list[tuple[RecoveryCandidate, LCMFResult]] = []
        for candidate in candidates:
            result = estimate_lcmf_v1(
                raw,
                calibration,
                ball_speed_mph=ball_speed_mph,
                club=club,
                net_range_m=self.net_range_m,
                tx_order=self.tx_order,
                tdm_sign_policy=self.tdm_sign_policy,
                horizontal_phase_reference_rad=self.horizontal_phase_reference_rad,
                track_override=candidate.track,
                track_override_scope=candidate.scope,
                prepared=prepared,
            )
            if (
                result.accepted
                and result.n_frames >= 4
                and result.angle_deg is not None
                and result.angle_deg >= OPS_GUIDED_MIN_LAUNCH_DEG
            ):
                recoveries.append((candidate, result))

        if recoveries:
            _candidate, selected = min(
                recoveries,
                key=lambda item: _recovery_result_rank(item[0], item[1]),
            )
            status = (
                "accepted_ops_guided_single_channel"
                if selected.single_channel
                else "accepted_ops_guided"
            )
            return replace(selected, status=status)
        if baseline.accepted:
            return replace(baseline, status="accepted_track_speed_warning")
        return baseline

    def process_shot(  # pylint: disable=too-many-arguments
        self,
        *,
        impact_timestamp: float | None,
        ball_speed_mph: float,
        club: str | None,
        club_speed_mph: float | None = None,
        tilt_deg: float | None = None,
    ) -> IWR6843ShotResult:
        """Match one OPS shot to TI data and run LCMF-v1."""
        capture = self.capture_monitor.capture_for_shot(
            impact_timestamp,
            timeout_s=self.capture_timeout_s,
        )
        if capture is None or not capture.valid or capture.raw is None:
            return IWR6843ShotResult(capture=capture, measurement=None)
        shot_calibration = self.calibration
        if tilt_deg is not None:
            shot_calibration = replace(self.calibration, tilt_rad=math.radians(tilt_deg))
        prepared = prepare_lcmf_capture(capture.raw)
        measurement = estimate_lcmf_v1(
            capture.raw,
            shot_calibration,
            ball_speed_mph=ball_speed_mph,
            club=club,
            net_range_m=self.net_range_m,
            tx_order=self.tx_order,
            tdm_sign_policy=self.tdm_sign_policy,
            horizontal_phase_reference_rad=self.horizontal_phase_reference_rad,
            prepared=prepared,
        )
        if isinstance(measurement, LCMFResult):
            measurement = self._ops_guided_measurement(
                capture.raw,
                shot_calibration,
                ball_speed_mph=ball_speed_mph,
                club=club,
                baseline=measurement,
                prepared=prepared,
            )
        horizontal_deg = getattr(measurement, "horizontal_deg", None)
        if horizontal_deg is not None:
            measurement = replace(
                measurement,
                horizontal_deg=horizontal_deg + self.azimuth_offset_deg,
                horizontal_raw_deg=horizontal_deg,
            )
        club_path = None
        # No OPS club speed means no identity gate to distinguish the club
        # track from hands, body, or the ball itself, so an estimate here
        # would be an unverifiable guess -- worse than no estimate at all.
        if club_speed_mph:
            ball_sign = getattr(measurement, "tdm_sign_used", None)
            fallback = ball_sign not in (-1, 1)
            policy_sign = _TDM_SIGN_BY_POLICY.get(self.tdm_sign_policy, 1)
            club_path = estimate_club_path(
                capture.raw,
                shot_calibration,
                ops_club_speed_mph=club_speed_mph,
                aim_offset_deg=self.azimuth_offset_deg,
                tdm_sign=policy_sign if fallback else ball_sign,
            )
            if fallback:
                # The ball measurement had no usable sign, so this is the
                # configured policy's guess, not a measured value. Recorded
                # in the status so a later replay can tell the two apart.
                club_path.status = f"{club_path.status}_tdm_sign_fallback"
        return IWR6843ShotResult(capture=capture, measurement=measurement, club_path=club_path)

    def stop(self) -> None:
        """Release TI hardware."""
        self.capture_monitor.stop()


__all__ = ["IWR6843Runtime", "IWR6843ShotResult"]
