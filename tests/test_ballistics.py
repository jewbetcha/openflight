"""Tests for the ballistics flight simulator and launch resolution."""

from datetime import datetime

import pytest

from openflight.ballistics import (
    CLUB_TYPICAL_SPIN_RPM,
    LaunchConditions,
    resolve_launch,
    simulate,
)
from openflight.launch_monitor import ClubType, Shot


def _shot(**kwargs) -> Shot:
    defaults = dict(
        ball_speed_mph=160.0,
        timestamp=datetime.now(),
        club=ClubType.DRIVER,
        launch_angle_vertical=12.0,
    )
    defaults.update(kwargs)
    return Shot(**defaults)


class TestResolveLaunch:
    def test_returns_none_without_vertical_launch_angle(self):
        shot = _shot(launch_angle_vertical=None)
        assert resolve_launch(shot) is None

    def test_uses_measured_spin_when_high_confidence(self):
        shot = _shot(spin_rpm=2500, spin_confidence=0.85)
        cond = resolve_launch(shot)
        assert cond is not None
        assert cond.spin_rpm == 2500
        assert cond.spin_source == "measured"

    def test_uses_club_typical_when_low_confidence(self):
        shot = _shot(spin_rpm=1500, spin_confidence=0.3, club=ClubType.DRIVER)
        cond = resolve_launch(shot)
        assert cond is not None
        assert cond.spin_rpm == CLUB_TYPICAL_SPIN_RPM[ClubType.DRIVER]
        assert cond.spin_source == "club_typical"

    def test_uses_club_typical_when_spin_missing(self):
        shot = _shot(spin_rpm=None, club=ClubType.IRON_7)
        cond = resolve_launch(shot)
        assert cond is not None
        assert cond.spin_rpm == CLUB_TYPICAL_SPIN_RPM[ClubType.IRON_7]
        assert cond.spin_source == "club_typical"

    def test_medium_confidence_still_falls_back(self):
        # Medium confidence (~0.5) is below the high threshold — use typical.
        shot = _shot(spin_rpm=3000, spin_confidence=0.5)
        cond = resolve_launch(shot)
        assert cond is not None
        assert cond.spin_source == "club_typical"

    def test_defaults_horizontal_angle_to_zero(self):
        shot = _shot(launch_angle_horizontal=None)
        cond = resolve_launch(shot)
        assert cond.launch_angle_h == 0.0

    def test_defaults_spin_axis_to_zero(self):
        shot = _shot(spin_axis_deg=None)
        cond = resolve_launch(shot)
        assert cond.spin_axis_deg == 0.0


def _driver(spin_rpm=2700, launch=11.0, ball_speed=165.0, axis=0.0, la_h=0.0):
    return LaunchConditions(
        ball_speed_mph=ball_speed,
        launch_angle_v=launch,
        launch_angle_h=la_h,
        spin_rpm=spin_rpm,
        spin_axis_deg=axis,
        spin_source="measured",
    )


class TestSimulate:
    def test_driver_carry_in_expected_range(self):
        # 165 mph ball speed / 11° / 2700 RPM is close to PGA Tour averages.
        # TrackMan data: ~270–285 yards carry.
        traj = simulate(_driver())
        assert 250 <= traj.carry_yards <= 300, (
            f"Driver carry {traj.carry_yards:.1f} yd outside plausible range"
        )

    def test_iron_carry_in_expected_range(self):
        # 7-iron: 120 mph ball speed, 17° launch, 6500 RPM → ~160-180 yd
        cond = LaunchConditions(
            ball_speed_mph=120.0,
            launch_angle_v=17.0,
            launch_angle_h=0.0,
            spin_rpm=6500,
            spin_axis_deg=0.0,
            spin_source="measured",
        )
        traj = simulate(cond)
        assert 140 <= traj.carry_yards <= 200, (
            f"7-iron carry {traj.carry_yards:.1f} yd outside plausible range"
        )

    def test_higher_launch_produces_higher_apex(self):
        low = simulate(_driver(launch=8.0))
        high = simulate(_driver(launch=15.0))
        assert high.apex_yards > low.apex_yards

    def test_more_spin_produces_higher_apex(self):
        low_spin = simulate(_driver(spin_rpm=1800))
        high_spin = simulate(_driver(spin_rpm=3500))
        assert high_spin.apex_yards > low_spin.apex_yards

    def test_fade_lands_right_of_target(self):
        traj = simulate(_driver(axis=10.0))  # +axis = fade
        assert traj.lateral_yards > 3.0

    def test_draw_lands_left_of_target(self):
        traj = simulate(_driver(axis=-10.0))  # -axis = draw
        assert traj.lateral_yards < -3.0

    def test_straight_shot_stays_near_center(self):
        traj = simulate(_driver(axis=0.0, la_h=0.0))
        assert abs(traj.lateral_yards) < 1.0

    def test_horizontal_launch_offsets_landing(self):
        # +la_h should push ball right
        traj = simulate(_driver(la_h=2.0))
        assert traj.lateral_yards > 1.0

    def test_trajectory_ends_at_ground(self):
        traj = simulate(_driver())
        assert traj.points[-1].z <= 0.01
        assert traj.points[-1].t == pytest.approx(traj.flight_time_s, rel=0.01)

    def test_spin_decays_over_flight(self):
        traj = simulate(_driver(spin_rpm=3000))
        final_spin = traj.points[-1].spin_rpm
        # 4%/s for ~6s flight → ~80% of initial
        assert 2300 < final_spin < 2900

    def test_flight_time_reasonable(self):
        traj = simulate(_driver())
        # Drivers typically spend 5-8 seconds in the air.
        assert 4.0 < traj.flight_time_s < 9.0

    def test_landing_angle_is_positive_descent(self):
        traj = simulate(_driver())
        # Ball descends on landing — angle below horizontal is positive.
        assert 20.0 < traj.landing_angle_deg < 60.0

    def test_zero_launch_angle_does_not_crash(self):
        # Extreme input should still produce a terminated trajectory.
        cond = LaunchConditions(
            ball_speed_mph=100.0,
            launch_angle_v=0.5,
            launch_angle_h=0.0,
            spin_rpm=3000,
            spin_axis_deg=0.0,
            spin_source="measured",
        )
        traj = simulate(cond)
        assert traj.carry_yards > 0
        assert traj.flight_time_s < 5.0

    def test_total_distance_includes_rollout(self):
        traj = simulate(_driver())
        assert traj.total_yards > traj.carry_yards


class TestAirDensityAtAltitude:
    """Tests for the ISA air density function."""

    def test_sea_level_matches_standard(self):
        """At 0 m altitude should return standard sea-level density."""
        from openflight.ballistics import AIR_DENSITY_STD, air_density_at_altitude

        assert air_density_at_altitude(0) == pytest.approx(AIR_DENSITY_STD, rel=1e-3)

    def test_density_decreases_with_altitude(self):
        """Higher altitude should produce lower air density."""
        from openflight.ballistics import air_density_at_altitude

        assert air_density_at_altitude(1000) < air_density_at_altitude(0)
        assert air_density_at_altitude(2000) < air_density_at_altitude(1000)

    def test_denver_altitude(self):
        """Denver (~1609 m / 5280 ft) should be ~83% of sea-level density."""
        from openflight.ballistics import AIR_DENSITY_STD, air_density_at_altitude

        denver = air_density_at_altitude(1609)
        ratio = denver / AIR_DENSITY_STD
        assert 0.84 <= ratio <= 0.87

    def test_high_altitude_course(self):
        """Leadville, CO (~3094 m / 10,152 ft) should be ~70% of sea level."""
        from openflight.ballistics import AIR_DENSITY_STD, air_density_at_altitude

        leadville = air_density_at_altitude(3094)
        ratio = leadville / AIR_DENSITY_STD
        assert 0.72 <= ratio <= 0.75

    def test_negative_altitude_clamped_to_sea_level(self):
        """Below sea level (e.g. Dead Sea) should return sea-level density."""
        from openflight.ballistics import air_density_at_altitude

        assert air_density_at_altitude(-100) == pytest.approx(air_density_at_altitude(0), rel=1e-6)

    def test_returns_float(self):
        from openflight.ballistics import air_density_at_altitude

        assert isinstance(air_density_at_altitude(1000), float)


class TestSimulateAltitude:
    """Tests for altitude_m parameter on simulate()."""

    def _conditions(self):
        from openflight.ballistics import LaunchConditions

        return LaunchConditions(
            ball_speed_mph=150.0,
            launch_angle_v=12.0,
            launch_angle_h=0.0,
            spin_rpm=2700,
            spin_axis_deg=0.0,
            spin_source="club_typical",
        )

    def test_altitude_increases_carry(self):
        """Higher altitude should produce longer carry due to thinner air."""
        from openflight.ballistics import simulate

        sea_level = simulate(self._conditions(), altitude_m=0)
        denver = simulate(self._conditions(), altitude_m=1609)
        assert denver.carry_yards > sea_level.carry_yards

    def test_high_altitude_carry_significantly_longer(self):
        """At 2000m carry should be meaningfully longer than sea level."""
        from openflight.ballistics import simulate

        sea_level = simulate(self._conditions(), altitude_m=0)
        high = simulate(self._conditions(), altitude_m=2000)
        # Expect at least 5% more carry at 2000m
        assert high.carry_yards > sea_level.carry_yards * 1.03

    def test_altitude_overrides_air_density(self):
        """altitude_m should override explicit air_density argument."""
        from openflight.ballistics import AIR_DENSITY_STD, air_density_at_altitude, simulate

        result_via_altitude = simulate(
            self._conditions(), air_density=AIR_DENSITY_STD, altitude_m=1609
        )
        result_via_density = simulate(self._conditions(), air_density=air_density_at_altitude(1609))
        assert result_via_altitude.carry_yards == pytest.approx(
            result_via_density.carry_yards, rel=1e-6
        )

    def test_zero_altitude_matches_default(self):
        """altitude_m=0 should match the default sea-level simulation."""
        from openflight.ballistics import simulate

        default = simulate(self._conditions())
        explicit = simulate(self._conditions(), altitude_m=0)
        assert explicit.carry_yards == pytest.approx(default.carry_yards, rel=1e-3)

    def test_none_altitude_uses_air_density_param(self):
        """altitude_m=None should leave air_density param untouched."""
        from openflight.ballistics import AIR_DENSITY_STD, simulate

        default = simulate(self._conditions())
        explicit = simulate(self._conditions(), altitude_m=None, air_density=AIR_DENSITY_STD)
        assert explicit.carry_yards == pytest.approx(default.carry_yards, rel=1e-6)
