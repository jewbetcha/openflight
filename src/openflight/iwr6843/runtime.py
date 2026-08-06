"""Runtime boundary joining TI capture to the frozen LCMF estimator."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from openflight.iwr6843.calibration import Calibration
from openflight.iwr6843.club import ClubPathResult, estimate_club_path
from openflight.iwr6843.lcmf import LCMFResult, estimate_lcmf_v1
from openflight.iwr6843.monitor import IWR6843Capture, IWR6843CaptureMonitor

# The ball estimate's measured tdm_sign_used takes priority; this only
# resolves the TDM sign for the club-path fallback when it is unavailable.
# "auto" has no fixed sign of its own, so it defaults to positive, same as
# this module's own tdm_sign_policy default.
_TDM_SIGN_BY_POLICY = {"positive": 1, "negative": -1, "auto": 1}


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
    tdm_sign_policy: str = "positive"

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
        measurement = estimate_lcmf_v1(
            capture.raw,
            shot_calibration,
            ball_speed_mph=ball_speed_mph,
            club=club,
            net_range_m=self.net_range_m,
            tx_order=self.tx_order,
            tdm_sign_policy=self.tdm_sign_policy,
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
