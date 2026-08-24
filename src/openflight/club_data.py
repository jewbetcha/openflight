"""Golf club physics profiles and canonical reference data.

Consolidates TrackMan-derived and empirical club physics data (launch angles,
smash factors, spin models, and speed profiles) into a single source of truth
to prevent numerical divergence across modules.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class ClubType(Enum):
    """Golf club types for distance estimation and physics simulation."""

    DRIVER = "driver"
    WOOD_3 = "3-wood"
    WOOD_5 = "5-wood"
    WOOD_7 = "7-wood"
    HYBRID_3 = "3-hybrid"
    HYBRID_5 = "5-hybrid"
    HYBRID_7 = "7-hybrid"
    HYBRID_9 = "9-hybrid"
    IRON_2 = "2-iron"
    IRON_3 = "3-iron"
    IRON_4 = "4-iron"
    IRON_5 = "5-iron"
    IRON_6 = "6-iron"
    IRON_7 = "7-iron"
    IRON_8 = "8-iron"
    IRON_9 = "9-iron"
    PW = "pw"
    GW = "gw"
    SW = "sw"
    LW = "lw"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClubProfile:
    """Physics characteristics and reference averages for a single club type."""

    club: ClubType
    optimal_launch_deg: float
    avg_launch_deg: float
    avg_ball_speed_mph: float
    launch_deg_per_mph: float
    optimal_smash: float
    typical_spin_rpm: float
    spin_multiplier: float
    # Amateur simulation distributions (used by mock monitors)
    ball_speed_std_dev: float = 10.0
    mock_smash: float = 1.35
    spin_std_dev: float = 500.0
    launch_std_dev: float = 2.0


# Canonical per-club data table based on TrackMan averages and empirical calibrations.
CLUB_PROFILES: Dict[ClubType, ClubProfile] = {
    ClubType.DRIVER: ClubProfile(
        club=ClubType.DRIVER,
        optimal_launch_deg=11.0,
        avg_launch_deg=11.0,
        avg_ball_speed_mph=143.0,
        launch_deg_per_mph=0.15,
        optimal_smash=1.48,
        typical_spin_rpm=2700.0,
        spin_multiplier=1.0,
        ball_speed_std_dev=12.0,
        mock_smash=1.45,
        spin_std_dev=400.0,
        launch_std_dev=2.0,
    ),
    ClubType.WOOD_3: ClubProfile(
        club=ClubType.WOOD_3,
        optimal_launch_deg=12.5,
        avg_launch_deg=12.5,
        avg_ball_speed_mph=135.0,
        launch_deg_per_mph=0.18,
        optimal_smash=1.44,
        typical_spin_rpm=3500.0,
        spin_multiplier=1.15,
        ball_speed_std_dev=10.0,
        mock_smash=1.42,
        spin_std_dev=400.0,
        launch_std_dev=2.0,
    ),
    ClubType.WOOD_5: ClubProfile(
        club=ClubType.WOOD_5,
        optimal_launch_deg=14.0,
        avg_launch_deg=14.0,
        avg_ball_speed_mph=128.0,
        launch_deg_per_mph=0.20,
        optimal_smash=1.42,
        typical_spin_rpm=4200.0,
        spin_multiplier=1.25,
        ball_speed_std_dev=10.0,
        mock_smash=1.40,
        spin_std_dev=400.0,
        launch_std_dev=2.0,
    ),
    ClubType.WOOD_7: ClubProfile(
        club=ClubType.WOOD_7,
        optimal_launch_deg=15.5,
        avg_launch_deg=15.5,
        avg_ball_speed_mph=122.0,
        launch_deg_per_mph=0.20,
        optimal_smash=1.41,
        typical_spin_rpm=4800.0,
        spin_multiplier=1.32,
        ball_speed_std_dev=9.0,
        mock_smash=1.40,
        spin_std_dev=500.0,
        launch_std_dev=2.0,
    ),
    ClubType.HYBRID_3: ClubProfile(
        club=ClubType.HYBRID_3,
        optimal_launch_deg=13.5,
        avg_launch_deg=13.5,
        avg_ball_speed_mph=123.0,
        launch_deg_per_mph=0.22,
        optimal_smash=1.39,
        typical_spin_rpm=4400.0,
        spin_multiplier=1.45,
        ball_speed_std_dev=9.0,
        mock_smash=1.39,
        spin_std_dev=400.0,
        launch_std_dev=2.0,
    ),
    ClubType.HYBRID_5: ClubProfile(
        club=ClubType.HYBRID_5,
        optimal_launch_deg=15.0,
        avg_launch_deg=15.0,
        avg_ball_speed_mph=118.0,
        launch_deg_per_mph=0.22,
        optimal_smash=1.37,
        typical_spin_rpm=4900.0,
        spin_multiplier=1.55,
        ball_speed_std_dev=9.0,
        mock_smash=1.37,
        spin_std_dev=500.0,
        launch_std_dev=2.0,
    ),
    ClubType.HYBRID_7: ClubProfile(
        club=ClubType.HYBRID_7,
        optimal_launch_deg=16.5,
        avg_launch_deg=16.5,
        avg_ball_speed_mph=112.0,
        launch_deg_per_mph=0.25,
        optimal_smash=1.35,
        typical_spin_rpm=5300.0,
        spin_multiplier=1.65,
        ball_speed_std_dev=8.0,
        mock_smash=1.35,
        spin_std_dev=500.0,
        launch_std_dev=2.0,
    ),
    ClubType.HYBRID_9: ClubProfile(
        club=ClubType.HYBRID_9,
        optimal_launch_deg=18.0,
        avg_launch_deg=18.0,
        avg_ball_speed_mph=106.0,
        launch_deg_per_mph=0.25,
        optimal_smash=1.33,
        typical_spin_rpm=5800.0,
        spin_multiplier=1.75,
        ball_speed_std_dev=8.0,
        mock_smash=1.33,
        spin_std_dev=500.0,
        launch_std_dev=2.5,
    ),
    ClubType.IRON_2: ClubProfile(
        club=ClubType.IRON_2,
        optimal_launch_deg=13.0,
        avg_launch_deg=13.0,
        avg_ball_speed_mph=120.0,
        launch_deg_per_mph=0.25,
        optimal_smash=1.36,
        typical_spin_rpm=4000.0,
        spin_multiplier=1.50,
        ball_speed_std_dev=9.0,
        mock_smash=1.35,
        spin_std_dev=400.0,
        launch_std_dev=2.0,
    ),
    ClubType.IRON_3: ClubProfile(
        club=ClubType.IRON_3,
        optimal_launch_deg=14.5,
        avg_launch_deg=14.5,
        avg_ball_speed_mph=118.0,
        launch_deg_per_mph=0.25,
        optimal_smash=1.35,
        typical_spin_rpm=4500.0,
        spin_multiplier=1.60,
        ball_speed_std_dev=9.0,
        mock_smash=1.35,
        spin_std_dev=400.0,
        launch_std_dev=2.0,
    ),
    ClubType.IRON_4: ClubProfile(
        club=ClubType.IRON_4,
        optimal_launch_deg=16.0,
        avg_launch_deg=16.0,
        avg_ball_speed_mph=114.0,
        launch_deg_per_mph=0.28,
        optimal_smash=1.33,
        typical_spin_rpm=5000.0,
        spin_multiplier=1.80,
        ball_speed_std_dev=8.0,
        mock_smash=1.33,
        spin_std_dev=500.0,
        launch_std_dev=2.0,
    ),
    ClubType.IRON_5: ClubProfile(
        club=ClubType.IRON_5,
        optimal_launch_deg=17.5,
        avg_launch_deg=17.5,
        avg_ball_speed_mph=110.0,
        launch_deg_per_mph=0.28,
        optimal_smash=1.31,
        typical_spin_rpm=5400.0,
        spin_multiplier=2.00,
        ball_speed_std_dev=8.0,
        mock_smash=1.31,
        spin_std_dev=500.0,
        launch_std_dev=2.0,
    ),
    ClubType.IRON_6: ClubProfile(
        club=ClubType.IRON_6,
        optimal_launch_deg=19.0,
        avg_launch_deg=19.0,
        avg_ball_speed_mph=105.0,
        launch_deg_per_mph=0.30,
        optimal_smash=1.29,
        typical_spin_rpm=6000.0,
        spin_multiplier=2.20,
        ball_speed_std_dev=7.0,
        mock_smash=1.29,
        spin_std_dev=600.0,
        launch_std_dev=2.5,
    ),
    ClubType.IRON_7: ClubProfile(
        club=ClubType.IRON_7,
        optimal_launch_deg=20.5,
        avg_launch_deg=20.5,
        avg_ball_speed_mph=100.0,
        launch_deg_per_mph=0.30,
        optimal_smash=1.27,
        typical_spin_rpm=6500.0,
        spin_multiplier=2.50,
        ball_speed_std_dev=7.0,
        mock_smash=1.27,
        spin_std_dev=600.0,
        launch_std_dev=2.5,
    ),
    ClubType.IRON_8: ClubProfile(
        club=ClubType.IRON_8,
        optimal_launch_deg=23.0,
        avg_launch_deg=23.0,
        avg_ball_speed_mph=94.0,
        launch_deg_per_mph=0.30,
        optimal_smash=1.25,
        typical_spin_rpm=7500.0,
        spin_multiplier=2.80,
        ball_speed_std_dev=6.0,
        mock_smash=1.25,
        spin_std_dev=700.0,
        launch_std_dev=3.0,
    ),
    ClubType.IRON_9: ClubProfile(
        club=ClubType.IRON_9,
        optimal_launch_deg=25.5,
        avg_launch_deg=25.5,
        avg_ball_speed_mph=88.0,
        launch_deg_per_mph=0.30,
        optimal_smash=1.23,
        typical_spin_rpm=8500.0,
        spin_multiplier=3.20,
        ball_speed_std_dev=6.0,
        mock_smash=1.23,
        spin_std_dev=800.0,
        launch_std_dev=3.0,
    ),
    ClubType.PW: ClubProfile(
        club=ClubType.PW,
        optimal_launch_deg=28.0,
        avg_launch_deg=28.0,
        avg_ball_speed_mph=82.0,
        launch_deg_per_mph=0.30,
        optimal_smash=1.21,
        typical_spin_rpm=9000.0,
        spin_multiplier=3.60,
        ball_speed_std_dev=5.0,
        mock_smash=1.21,
        spin_std_dev=800.0,
        launch_std_dev=3.0,
    ),
    ClubType.GW: ClubProfile(
        club=ClubType.GW,
        optimal_launch_deg=30.0,
        avg_launch_deg=30.0,
        avg_ball_speed_mph=76.0,
        launch_deg_per_mph=0.30,
        optimal_smash=1.19,
        typical_spin_rpm=9500.0,
        spin_multiplier=4.10,
        ball_speed_std_dev=5.0,
        mock_smash=1.20,
        spin_std_dev=900.0,
        launch_std_dev=3.5,
    ),
    ClubType.SW: ClubProfile(
        club=ClubType.SW,
        optimal_launch_deg=32.0,
        avg_launch_deg=32.0,
        avg_ball_speed_mph=73.0,
        launch_deg_per_mph=0.30,
        optimal_smash=1.18,
        typical_spin_rpm=10000.0,
        spin_multiplier=4.30,
        ball_speed_std_dev=5.0,
        mock_smash=1.19,
        spin_std_dev=1000.0,
        launch_std_dev=4.0,
    ),
    ClubType.LW: ClubProfile(
        club=ClubType.LW,
        optimal_launch_deg=35.0,
        avg_launch_deg=35.0,
        avg_ball_speed_mph=70.0,
        launch_deg_per_mph=0.30,
        optimal_smash=1.17,
        typical_spin_rpm=10500.0,
        spin_multiplier=4.60,
        ball_speed_std_dev=5.0,
        mock_smash=1.18,
        spin_std_dev=1000.0,
        launch_std_dev=4.0,
    ),
    ClubType.UNKNOWN: ClubProfile(
        club=ClubType.UNKNOWN,
        optimal_launch_deg=18.0,
        avg_launch_deg=18.0,
        avg_ball_speed_mph=120.0,
        launch_deg_per_mph=0.25,
        optimal_smash=1.35,
        typical_spin_rpm=5000.0,
        spin_multiplier=1.0,
        ball_speed_std_dev=15.0,
        mock_smash=1.35,
        spin_std_dev=800.0,
        launch_std_dev=3.0,
    ),
}

# Derived mapping dictionaries for high-performance direct lookups
OPTIMAL_LAUNCH_ANGLES: Dict[ClubType, float] = {
    c: p.optimal_launch_deg for c, p in CLUB_PROFILES.items()
}

OPTIMAL_SMASH_FACTORS: Dict[ClubType, float] = {
    c: p.optimal_smash for c, p in CLUB_PROFILES.items()
}

CLUB_TYPICAL_SPIN_RPM: Dict[ClubType, float] = {
    c: p.typical_spin_rpm for c, p in CLUB_PROFILES.items()
}

CLUB_LAUNCH_MODELS: Dict[ClubType, Tuple[float, float, float]] = {
    c: (p.avg_launch_deg, p.avg_ball_speed_mph, p.launch_deg_per_mph)
    for c, p in CLUB_PROFILES.items()
}

CLUB_SPIN_MULTIPLIERS: Dict[ClubType, float] = {
    c: p.spin_multiplier for c, p in CLUB_PROFILES.items()
}

CLUB_BALL_SPEEDS: Dict[ClubType, Tuple[float, float, float]] = {
    c: (p.avg_ball_speed_mph, p.ball_speed_std_dev, p.mock_smash) for c, p in CLUB_PROFILES.items()
}

CLUB_SPIN_DISTRIBUTIONS: Dict[ClubType, Tuple[float, float]] = {
    c: (p.typical_spin_rpm, p.spin_std_dev) for c, p in CLUB_PROFILES.items()
}

CLUB_LAUNCH_DISTRIBUTIONS: Dict[ClubType, Tuple[float, float]] = {
    c: (p.avg_launch_deg, p.launch_std_dev) for c, p in CLUB_PROFILES.items()
}


def get_club_profile(club: Optional[ClubType]) -> ClubProfile:
    """Return the profile for the given club, defaulting to UNKNOWN if None or unrecognized."""
    if club is None:
        return CLUB_PROFILES[ClubType.UNKNOWN]
    return CLUB_PROFILES.get(club, CLUB_PROFILES[ClubType.UNKNOWN])


def get_optimal_launch_angle(club: Optional[ClubType]) -> float:
    """Return optimal vertical launch angle in degrees for the given club."""
    return get_club_profile(club).optimal_launch_deg


def get_optimal_smash(club: Optional[ClubType]) -> float:
    """Return optimal smash factor for the given club."""
    return get_club_profile(club).optimal_smash


def get_typical_spin_rpm(club: Optional[ClubType]) -> float:
    """Return typical spin in RPM for the given club."""
    return get_club_profile(club).typical_spin_rpm
