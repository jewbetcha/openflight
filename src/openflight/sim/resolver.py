"""Translate a Shot into a protocol-neutral ResolvedShot with provenance.

This is the single place the measured-vs-estimated fallback table lives, so
every simulator connector inherits identical fallback behavior. Codecs only
serialize the ResolvedShot into their own wire format.
"""

import math
from typing import Dict, Tuple

from openflight.club_data import CLUB_TYPICAL_SPIN_RPM, OPTIMAL_LAUNCH_ANGLES
from openflight.launch_monitor import (
    SPIN_CONFIDENCE_HIGH,
    ClubType,
    Shot,
)
from openflight.sim.types import IncompleteShotError, PlayerState, ResolvedShot

# Per-club spin model (rpm) from canonical TrackMan averages (club_data.py)
SPIN_MODEL_RPM: Dict[ClubType, float] = dict(CLUB_TYPICAL_SPIN_RPM)
_OPTIMAL_LAUNCH: Dict[ClubType, float] = dict(OPTIMAL_LAUNCH_ANGLES)

_DEFAULT_SPIN_RPM = 5000.0
_DEFAULT_VLA_DEG = 18.0


def _resolve_total_spin(shot: Shot) -> Tuple[float, str]:
    """Measured spin if present and high-confidence, else the per-club model."""
    if (
        shot.spin_rpm is not None
        and shot.spin_rpm > 0
        and shot.spin_confidence is not None
        and shot.spin_confidence >= SPIN_CONFIDENCE_HIGH
    ):
        return float(shot.spin_rpm), "measured"
    return SPIN_MODEL_RPM.get(shot.club, _DEFAULT_SPIN_RPM), "estimated"


def resolve_shot(shot: Shot, player_state: PlayerState) -> ResolvedShot:
    """Fill every simulator field from a Shot, applying the fallback table.

    Raises IncompleteShotError when ball speed is missing — the one field that
    has no honest model. Allocates exactly one shot number per physical shot
    (so all connectors share a number for the same shot).
    """
    if shot.ball_speed_mph is None or shot.ball_speed_mph <= 0:
        raise IncompleteShotError("ball_speed_mph is required")

    provenance: Dict[str, str] = {"ball_speed": "measured"}

    if shot.launch_angle_vertical is not None:
        vla = float(shot.launch_angle_vertical)
        provenance["vla"] = "measured"
    else:
        vla = _OPTIMAL_LAUNCH.get(shot.club, _DEFAULT_VLA_DEG)
        provenance["vla"] = "estimated"

    if shot.launch_angle_horizontal is not None:
        hla = float(shot.launch_angle_horizontal)
        provenance["hla"] = "measured"
    else:
        hla = 0.0
        provenance["hla"] = "estimated"

    total_spin, spin_prov = _resolve_total_spin(shot)
    provenance["total_spin"] = spin_prov

    if shot.spin_axis_deg is not None:
        spin_axis = float(shot.spin_axis_deg)
        axis_prov = "measured"
    else:
        spin_axis = 0.0
        axis_prov = "estimated"
    provenance["spin_axis"] = axis_prov

    axis_rad = math.radians(spin_axis)
    back_spin = total_spin * math.cos(axis_rad)
    side_spin = total_spin * math.sin(axis_rad)
    derived_prov = (
        "measured" if (spin_prov == "measured" and axis_prov == "measured") else "estimated"
    )
    provenance["back_spin"] = derived_prov
    provenance["side_spin"] = derived_prov

    carry = float(shot.estimated_carry_yards)
    # Carry is always model-derived (never directly observed), so "measured" here
    # means launch-angle-informed: the carry model was driven by a measured launch
    # angle rather than falling back to club-type defaults. The UI badge reflects
    # that distinction, not a claim that carry itself was measured (PR #115 review #6).
    provenance["carry"] = "measured" if shot.has_launch_angle else "estimated"

    if shot.club_speed_mph is not None and shot.club_speed_mph > 0:
        club_speed = float(shot.club_speed_mph)
        provenance["club_speed"] = "measured"
    else:
        club_speed = None
        provenance["club_speed"] = "estimated"

    if shot.club_path_deg is not None:
        club_path = float(shot.club_path_deg)
        provenance["club_path"] = "measured"
    else:
        club_path = 0.0
        provenance["club_path"] = "estimated"

    return ResolvedShot(
        shot_number=player_state.next_shot_number(),
        ball_speed_mph=float(shot.ball_speed_mph),
        vla=vla,
        hla=hla,
        total_spin_rpm=total_spin,
        spin_axis_deg=spin_axis,
        back_spin_rpm=back_spin,
        side_spin_rpm=side_spin,
        carry_yards=carry,
        club_path_deg=club_path,
        club=shot.club,
        club_speed_mph=club_speed,
        provenance=provenance,
    )
