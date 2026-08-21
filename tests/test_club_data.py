"""Tests for canonical club data consolidation and cross-module consistency."""

import pytest

from openflight.ballistics import CLUB_TYPICAL_SPIN_RPM as BALLISTICS_SPIN
from openflight.club_data import (
    CLUB_BALL_SPEEDS,
    CLUB_LAUNCH_DISTRIBUTIONS,
    CLUB_LAUNCH_MODELS,
    CLUB_PROFILES,
    CLUB_SPIN_DISTRIBUTIONS,
    CLUB_SPIN_MULTIPLIERS,
    CLUB_TYPICAL_SPIN_RPM,
    OPTIMAL_LAUNCH_ANGLES,
    OPTIMAL_SMASH_FACTORS,
    ClubProfile,
    ClubType,
    get_club_profile,
    get_optimal_launch_angle,
    get_optimal_smash,
    get_typical_spin_rpm,
)
from openflight.launch_monitor import _OPTIMAL_LAUNCH as LM_OPTIMAL_LAUNCH
from openflight.rolling_buffer.monitor import (
    CLUB_SPIN_MULTIPLIERS as RB_SPIN_MULTIPLIERS,
    OPTIMAL_SMASH_FACTORS as RB_SMASH_FACTORS,
)
from openflight.server import (
    _CLUB_LAUNCH_MODEL as SERVER_LAUNCH_MODEL,
    _OPTIMAL_SMASH as SERVER_OPTIMAL_SMASH,
    MockLaunchMonitor,
)
from openflight.sim.resolver import (
    _OPTIMAL_LAUNCH as SIM_OPTIMAL_LAUNCH,
    SPIN_MODEL_RPM as SIM_SPIN_MODEL,
)

WOODS = [ClubType.DRIVER, ClubType.WOOD_3, ClubType.WOOD_5, ClubType.WOOD_7]
HYBRIDS = [ClubType.HYBRID_3, ClubType.HYBRID_5, ClubType.HYBRID_7, ClubType.HYBRID_9]
IRONS_WEDGES = [
    ClubType.IRON_2,
    ClubType.IRON_3,
    ClubType.IRON_4,
    ClubType.IRON_5,
    ClubType.IRON_6,
    ClubType.IRON_7,
    ClubType.IRON_8,
    ClubType.IRON_9,
    ClubType.PW,
    ClubType.GW,
    ClubType.SW,
    ClubType.LW,
]


class TestClubDataCompleteness:
    def test_all_club_types_have_profiles(self):
        for club in ClubType:
            assert club in CLUB_PROFILES
            profile = CLUB_PROFILES[club]
            assert isinstance(profile, ClubProfile)
            assert profile.club == club

    def test_all_derived_dictionaries_contain_all_clubs(self):
        for club in ClubType:
            assert club in OPTIMAL_LAUNCH_ANGLES
            assert club in OPTIMAL_SMASH_FACTORS
            assert club in CLUB_TYPICAL_SPIN_RPM
            assert club in CLUB_LAUNCH_MODELS
            assert club in CLUB_SPIN_MULTIPLIERS
            assert club in CLUB_BALL_SPEEDS
            assert club in CLUB_SPIN_DISTRIBUTIONS
            assert club in CLUB_LAUNCH_DISTRIBUTIONS


class TestClubPhysicsProgression:
    @pytest.mark.parametrize("family", [WOODS, HYBRIDS, IRONS_WEDGES])
    def test_optimal_launch_angles_increase_within_family(self, family):
        angles = [CLUB_PROFILES[c].optimal_launch_deg for c in family]
        assert angles == sorted(angles)

    @pytest.mark.parametrize("family", [WOODS, HYBRIDS, IRONS_WEDGES])
    def test_optimal_smash_factors_decrease_within_family(self, family):
        smash = [CLUB_PROFILES[c].optimal_smash for c in family]
        assert smash == sorted(smash, reverse=True)

    @pytest.mark.parametrize("family", [WOODS, HYBRIDS, IRONS_WEDGES])
    def test_typical_spin_increases_within_family(self, family):
        spin = [CLUB_PROFILES[c].typical_spin_rpm for c in family]
        assert spin == sorted(spin)

    @pytest.mark.parametrize("family", [WOODS, HYBRIDS, IRONS_WEDGES])
    def test_average_ball_speed_decreases_within_family(self, family):
        speeds = [CLUB_PROFILES[c].avg_ball_speed_mph for c in family]
        assert speeds == sorted(speeds, reverse=True)

    @pytest.mark.parametrize("family", [WOODS, HYBRIDS, IRONS_WEDGES])
    def test_spin_multipliers_increase_within_family(self, family):
        mults = [CLUB_PROFILES[c].spin_multiplier for c in family]
        assert mults == sorted(mults)

    def test_overall_extrema(self):
        # Driver is lowest launch/spin, highest speed/smash
        driver = CLUB_PROFILES[ClubType.DRIVER]
        lw = CLUB_PROFILES[ClubType.LW]
        assert driver.optimal_launch_deg == min(
            p.optimal_launch_deg for p in CLUB_PROFILES.values()
        )
        assert driver.optimal_smash == max(p.optimal_smash for p in CLUB_PROFILES.values())
        assert driver.avg_ball_speed_mph == max(
            p.avg_ball_speed_mph for p in CLUB_PROFILES.values()
        )
        assert driver.typical_spin_rpm == min(p.typical_spin_rpm for p in CLUB_PROFILES.values())

        # Lob Wedge is highest launch/spin, lowest speed/smash
        assert lw.optimal_launch_deg == max(p.optimal_launch_deg for p in CLUB_PROFILES.values())
        assert lw.optimal_smash == min(p.optimal_smash for p in CLUB_PROFILES.values())
        assert lw.avg_ball_speed_mph == min(p.avg_ball_speed_mph for p in CLUB_PROFILES.values())
        assert lw.typical_spin_rpm == max(p.typical_spin_rpm for p in CLUB_PROFILES.values())


class TestCrossModuleConsistency:
    def test_launch_monitor_optimal_launch_matches(self):
        assert LM_OPTIMAL_LAUNCH == OPTIMAL_LAUNCH_ANGLES

    def test_ballistics_typical_spin_matches(self):
        assert BALLISTICS_SPIN == CLUB_TYPICAL_SPIN_RPM

    def test_sim_resolver_tables_match(self):
        assert SIM_SPIN_MODEL == CLUB_TYPICAL_SPIN_RPM
        assert SIM_OPTIMAL_LAUNCH == OPTIMAL_LAUNCH_ANGLES

    def test_server_tables_match(self):
        assert SERVER_LAUNCH_MODEL == CLUB_LAUNCH_MODELS
        assert SERVER_OPTIMAL_SMASH == OPTIMAL_SMASH_FACTORS
        assert MockLaunchMonitor._CLUB_BALL_SPEEDS == CLUB_BALL_SPEEDS
        assert MockLaunchMonitor._CLUB_SPIN == CLUB_SPIN_DISTRIBUTIONS
        assert MockLaunchMonitor._CLUB_LAUNCH == CLUB_LAUNCH_DISTRIBUTIONS

    def test_rolling_buffer_monitor_tables_match(self):
        assert RB_SPIN_MULTIPLIERS == CLUB_SPIN_MULTIPLIERS
        assert RB_SMASH_FACTORS == OPTIMAL_SMASH_FACTORS


class TestHelperFunctions:
    def test_get_club_profile_known(self):
        profile = get_club_profile(ClubType.IRON_7)
        assert profile.club == ClubType.IRON_7
        assert profile.optimal_launch_deg == 20.5
        assert profile.optimal_smash == 1.27
        assert profile.typical_spin_rpm == 6500.0

    def test_get_club_profile_unknown_and_none(self):
        assert get_club_profile(None) == CLUB_PROFILES[ClubType.UNKNOWN]
        assert get_club_profile(ClubType.UNKNOWN) == CLUB_PROFILES[ClubType.UNKNOWN]

    def test_get_optimal_launch_angle(self):
        assert get_optimal_launch_angle(ClubType.DRIVER) == 11.0
        assert get_optimal_launch_angle(None) == 18.0

    def test_get_optimal_smash(self):
        assert get_optimal_smash(ClubType.DRIVER) == 1.48
        assert get_optimal_smash(None) == 1.35

    def test_get_typical_spin_rpm(self):
        assert get_typical_spin_rpm(ClubType.DRIVER) == 2700.0
        assert get_typical_spin_rpm(None) == 5000.0
