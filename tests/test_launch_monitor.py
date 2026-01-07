"""Tests for launch_monitor module."""

import pytest
from datetime import datetime

from openlaunch.launch_monitor import (
    Shot,
    ClubType,
    estimate_carry_distance,
    LaunchMonitor,
)


class TestEstimateCarryDistance:
    """Tests for the carry distance estimation function."""

    def test_driver_150_mph(self):
        """150 mph driver should be around 265 yards."""
        carry = estimate_carry_distance(150, ClubType.DRIVER)
        assert 250 <= carry <= 280

    def test_driver_100_mph(self):
        """100 mph driver should be around 136 yards."""
        carry = estimate_carry_distance(100, ClubType.DRIVER)
        assert 130 <= carry <= 145

    def test_driver_180_mph(self):
        """180 mph driver (pro level) should be around 335 yards."""
        carry = estimate_carry_distance(180, ClubType.DRIVER)
        assert 320 <= carry <= 350

    def test_iron_7_lower_than_driver(self):
        """7 iron at same ball speed should carry less than driver."""
        driver_carry = estimate_carry_distance(120, ClubType.DRIVER)
        iron_carry = estimate_carry_distance(120, ClubType.IRON_7)
        assert iron_carry < driver_carry

    def test_club_factor_ordering(self):
        """Longer clubs should have higher distance factors."""
        ball_speed = 130
        driver = estimate_carry_distance(ball_speed, ClubType.DRIVER)
        wood_3 = estimate_carry_distance(ball_speed, ClubType.WOOD_3)
        iron_5 = estimate_carry_distance(ball_speed, ClubType.IRON_5)
        iron_9 = estimate_carry_distance(ball_speed, ClubType.IRON_9)
        pw = estimate_carry_distance(ball_speed, ClubType.PW)

        assert driver > wood_3 > iron_5 > iron_9 > pw

    def test_low_speed_extrapolation(self):
        """Very low speeds should still return positive distance."""
        carry = estimate_carry_distance(50, ClubType.DRIVER)
        assert carry > 0
        assert carry < 100

    def test_high_speed_extrapolation(self):
        """Very high speeds should extrapolate reasonably."""
        carry = estimate_carry_distance(220, ClubType.DRIVER)
        assert carry > 400
        assert carry < 500


class TestShot:
    """Tests for the Shot dataclass."""

    def test_basic_shot_creation(self):
        """Create a basic shot with ball speed only."""
        shot = Shot(ball_speed_mph=150.0, timestamp=datetime.now())
        assert shot.ball_speed_mph == 150.0
        assert shot.club == ClubType.DRIVER  # default

    def test_shot_with_club_speed(self):
        """Shot with both ball and club speed."""
        shot = Shot(
            ball_speed_mph=150.0,
            club_speed_mph=103.0,
            timestamp=datetime.now(),
        )
        assert shot.ball_speed_mph == 150.0
        assert shot.club_speed_mph == 103.0

    def test_smash_factor_calculation(self):
        """Smash factor should be ball_speed / club_speed."""
        shot = Shot(
            ball_speed_mph=150.0,
            club_speed_mph=100.0,
            timestamp=datetime.now(),
        )
        assert shot.smash_factor == 1.5

    def test_smash_factor_none_without_club_speed(self):
        """Smash factor should be None if no club speed."""
        shot = Shot(ball_speed_mph=150.0, timestamp=datetime.now())
        assert shot.smash_factor is None

    def test_speed_unit_conversion(self):
        """Test mph to m/s conversion."""
        shot = Shot(
            ball_speed_mph=100.0,
            club_speed_mph=70.0,
            timestamp=datetime.now(),
        )
        # 100 mph ~= 44.7 m/s
        assert 44.5 <= shot.ball_speed_ms <= 44.9
        assert 31.0 <= shot.club_speed_ms <= 31.5

    def test_estimated_carry_uses_club_type(self):
        """Estimated carry should vary by club type."""
        driver_shot = Shot(
            ball_speed_mph=140.0,
            timestamp=datetime.now(),
            club=ClubType.DRIVER,
        )
        iron_shot = Shot(
            ball_speed_mph=140.0,
            timestamp=datetime.now(),
            club=ClubType.IRON_7,
        )
        assert driver_shot.estimated_carry_yards > iron_shot.estimated_carry_yards

    def test_carry_range(self):
        """Carry range should be ±10% of estimate."""
        shot = Shot(ball_speed_mph=150.0, timestamp=datetime.now())
        low, high = shot.estimated_carry_range
        estimate = shot.estimated_carry_yards

        assert low == pytest.approx(estimate * 0.90, rel=0.01)
        assert high == pytest.approx(estimate * 1.10, rel=0.01)


class TestLaunchMonitorSessionStats:
    """Tests for LaunchMonitor session statistics."""

    def test_empty_session_stats(self):
        """Empty session should return zeros."""
        monitor = LaunchMonitor.__new__(LaunchMonitor)
        monitor._shots = []

        stats = monitor.get_session_stats()

        assert stats["shot_count"] == 0
        assert stats["avg_ball_speed"] == 0
        assert stats["max_ball_speed"] == 0
        assert stats["min_ball_speed"] == 0
        assert stats["avg_club_speed"] is None
        assert stats["avg_smash_factor"] is None
        assert stats["avg_carry_est"] == 0

    def test_single_shot_stats(self):
        """Stats with a single shot."""
        monitor = LaunchMonitor.__new__(LaunchMonitor)
        monitor._shots = [
            Shot(ball_speed_mph=150.0, club_speed_mph=100.0, timestamp=datetime.now())
        ]

        stats = monitor.get_session_stats()

        assert stats["shot_count"] == 1
        assert stats["avg_ball_speed"] == 150.0
        assert stats["max_ball_speed"] == 150.0
        assert stats["min_ball_speed"] == 150.0
        assert stats["avg_club_speed"] == 100.0
        assert stats["avg_smash_factor"] == 1.5

    def test_multiple_shots_stats(self):
        """Stats with multiple shots."""
        monitor = LaunchMonitor.__new__(LaunchMonitor)
        monitor._shots = [
            Shot(ball_speed_mph=140.0, club_speed_mph=95.0, timestamp=datetime.now()),
            Shot(ball_speed_mph=150.0, club_speed_mph=100.0, timestamp=datetime.now()),
            Shot(ball_speed_mph=160.0, club_speed_mph=108.0, timestamp=datetime.now()),
        ]

        stats = monitor.get_session_stats()

        assert stats["shot_count"] == 3
        assert stats["avg_ball_speed"] == 150.0
        assert stats["max_ball_speed"] == 160.0
        assert stats["min_ball_speed"] == 140.0

    def test_clear_session(self):
        """Clear session should reset shots."""
        monitor = LaunchMonitor.__new__(LaunchMonitor)
        monitor._shots = [
            Shot(ball_speed_mph=150.0, timestamp=datetime.now())
        ]

        monitor.clear_session()

        assert monitor._shots == []
        assert monitor.get_session_stats()["shot_count"] == 0

    def test_set_club(self):
        """Set club should update current club."""
        monitor = LaunchMonitor.__new__(LaunchMonitor)
        monitor._current_club = ClubType.DRIVER

        monitor.set_club(ClubType.IRON_7)

        assert monitor._current_club == ClubType.IRON_7


class TestShotDetection:
    """Tests for shot detection logic."""

    def setup_method(self):
        """Set up test monitor instance."""
        self.monitor = LaunchMonitor.__new__(LaunchMonitor)
        self.monitor._shots = []
        self.monitor._current_readings = []
        self.monitor._shot_callback = None
        self.monitor._detect_club_speed = True
        self.monitor._current_club = ClubType.DRIVER

    def test_process_shot_extracts_ball_speed(self):
        """Ball speed should be the peak reading."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        self.monitor._current_readings = [
            SpeedReading(speed=95.0, direction=Direction.OUTBOUND, timestamp=time.time()),
            SpeedReading(speed=148.5, direction=Direction.OUTBOUND, timestamp=time.time()),
            SpeedReading(speed=147.2, direction=Direction.OUTBOUND, timestamp=time.time()),
        ]

        self.monitor._process_shot()

        assert len(self.monitor._shots) == 1
        assert self.monitor._shots[0].ball_speed_mph == 148.5

    def test_process_shot_extracts_club_speed(self):
        """Club speed should be detected from lower readings."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        base_time = time.time()
        # Simulate: club at ~100 mph, ball at ~145 mph (smash ~1.45)
        # Include magnitudes and proper timing (club before ball)
        self.monitor._current_readings = [
            SpeedReading(speed=98.0, direction=Direction.OUTBOUND, magnitude=300, timestamp=base_time),
            SpeedReading(speed=100.5, direction=Direction.OUTBOUND, magnitude=400, timestamp=base_time + 0.02),
            SpeedReading(speed=145.0, direction=Direction.OUTBOUND, magnitude=200, timestamp=base_time + 0.05),
            SpeedReading(speed=143.2, direction=Direction.OUTBOUND, magnitude=150, timestamp=base_time + 0.07),
        ]

        self.monitor._process_shot()

        assert len(self.monitor._shots) == 1
        shot = self.monitor._shots[0]
        assert shot.ball_speed_mph == 145.0
        assert shot.club_speed_mph is not None
        assert 95 <= shot.club_speed_mph <= 105

    def test_process_shot_minimum_readings(self):
        """Less than MIN_READINGS_FOR_SHOT should not create a shot."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        self.monitor._current_readings = [
            SpeedReading(speed=150.0, direction=Direction.OUTBOUND, timestamp=time.time()),
        ]

        self.monitor._process_shot()

        assert len(self.monitor._shots) == 0

    def test_process_shot_clears_readings(self):
        """Processing a shot should clear current readings."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        self.monitor._current_readings = [
            SpeedReading(speed=140.0, direction=Direction.OUTBOUND, timestamp=time.time()),
            SpeedReading(speed=145.0, direction=Direction.OUTBOUND, timestamp=time.time()),
        ]

        self.monitor._process_shot()

        assert len(self.monitor._current_readings) == 0

    def test_process_shot_callback_called(self):
        """Shot callback should be called with the shot."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        received_shots = []
        self.monitor._shot_callback = lambda s: received_shots.append(s)

        # Need 3 readings (MIN_READINGS_FOR_SHOT = 3)
        self.monitor._current_readings = [
            SpeedReading(speed=150.0, direction=Direction.OUTBOUND, timestamp=time.time()),
            SpeedReading(speed=152.0, direction=Direction.OUTBOUND, timestamp=time.time()),
            SpeedReading(speed=151.0, direction=Direction.OUTBOUND, timestamp=time.time()),
        ]

        self.monitor._process_shot()

        assert len(received_shots) == 1
        assert received_shots[0].ball_speed_mph == 152.0

    def test_process_shot_uses_current_club(self):
        """Shot should use the currently selected club."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        self.monitor._current_club = ClubType.IRON_7
        # Need 3 readings (MIN_READINGS_FOR_SHOT = 3)
        self.monitor._current_readings = [
            SpeedReading(speed=100.0, direction=Direction.OUTBOUND, timestamp=time.time()),
            SpeedReading(speed=102.0, direction=Direction.OUTBOUND, timestamp=time.time()),
            SpeedReading(speed=101.0, direction=Direction.OUTBOUND, timestamp=time.time()),
        ]

        self.monitor._process_shot()

        assert self.monitor._shots[0].club == ClubType.IRON_7

    def test_process_shot_records_magnitude(self):
        """Peak magnitude should be recorded."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        self.monitor._current_readings = [
            SpeedReading(speed=140.0, direction=Direction.OUTBOUND, magnitude=1200, timestamp=time.time()),
            SpeedReading(speed=150.0, direction=Direction.OUTBOUND, magnitude=1800, timestamp=time.time()),
            SpeedReading(speed=148.0, direction=Direction.OUTBOUND, magnitude=1500, timestamp=time.time()),
        ]

        self.monitor._process_shot()

        assert self.monitor._shots[0].peak_magnitude == 1800


class TestClubBallSeparation:
    """Tests for temporal + magnitude based club/ball separation."""

    def setup_method(self):
        """Set up test monitor instance."""
        self.monitor = LaunchMonitor.__new__(LaunchMonitor)
        self.monitor._shots = []
        self.monitor._current_readings = []
        self.monitor._shot_callback = None
        self.monitor._detect_club_speed = True
        self.monitor._current_club = ClubType.DRIVER

    def test_club_detected_before_ball_by_timing(self):
        """Club reading before ball (by timestamp) should be detected."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        base_time = time.time()
        # Simulate: club at t=0, ball at t=0.1s
        # Club: 95 mph, Ball: 140 mph (smash = 1.47)
        self.monitor._current_readings = [
            SpeedReading(speed=95.0, direction=Direction.OUTBOUND, magnitude=2000, timestamp=base_time),
            SpeedReading(speed=140.0, direction=Direction.OUTBOUND, magnitude=1200, timestamp=base_time + 0.1),
            SpeedReading(speed=138.0, direction=Direction.OUTBOUND, magnitude=1100, timestamp=base_time + 0.15),
        ]

        self.monitor._process_shot()

        assert len(self.monitor._shots) == 1
        shot = self.monitor._shots[0]
        assert shot.ball_speed_mph == 140.0
        assert shot.club_speed_mph == 95.0
        assert 1.4 <= shot.smash_factor <= 1.5

    def test_club_selected_by_highest_magnitude(self):
        """When multiple club candidates exist, prefer highest magnitude."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        base_time = time.time()
        # Two possible club readings, one with higher magnitude
        self.monitor._current_readings = [
            SpeedReading(speed=90.0, direction=Direction.OUTBOUND, magnitude=1500, timestamp=base_time),
            SpeedReading(speed=95.0, direction=Direction.OUTBOUND, magnitude=2500, timestamp=base_time + 0.05),
            SpeedReading(speed=142.0, direction=Direction.OUTBOUND, magnitude=1000, timestamp=base_time + 0.12),
            SpeedReading(speed=140.0, direction=Direction.OUTBOUND, magnitude=900, timestamp=base_time + 0.15),
        ]

        self.monitor._process_shot()

        shot = self.monitor._shots[0]
        assert shot.ball_speed_mph == 142.0
        # Should pick 95 mph (higher magnitude) over 90 mph
        assert shot.club_speed_mph == 95.0

    def test_club_rejected_if_smash_factor_invalid(self):
        """Club reading with invalid smash factor should be rejected."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        base_time = time.time()
        # Invalid: 50 mph club, 140 mph ball = smash 2.8 (too high)
        self.monitor._current_readings = [
            SpeedReading(speed=50.0, direction=Direction.OUTBOUND, magnitude=2000, timestamp=base_time),
            SpeedReading(speed=140.0, direction=Direction.OUTBOUND, magnitude=1000, timestamp=base_time + 0.1),
            SpeedReading(speed=138.0, direction=Direction.OUTBOUND, magnitude=900, timestamp=base_time + 0.15),
        ]

        self.monitor._process_shot()

        shot = self.monitor._shots[0]
        assert shot.ball_speed_mph == 140.0
        # Club should be rejected due to invalid smash factor
        assert shot.club_speed_mph is None

    def test_club_rejected_if_too_long_before_ball(self):
        """Readings spread over >300ms should be rejected as not a valid shot."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        base_time = time.time()
        # Club at t=0, ball at t=0.5s (550ms total duration - too spread out)
        # Real golf shots complete within 300ms, so this is likely walking/noise
        self.monitor._current_readings = [
            SpeedReading(speed=95.0, direction=Direction.OUTBOUND, magnitude=2000, timestamp=base_time),
            SpeedReading(speed=140.0, direction=Direction.OUTBOUND, magnitude=1000, timestamp=base_time + 0.5),
            SpeedReading(speed=138.0, direction=Direction.OUTBOUND, magnitude=900, timestamp=base_time + 0.55),
        ]

        self.monitor._process_shot()

        # Entire shot should be rejected due to excessive duration
        assert len(self.monitor._shots) == 0

    def test_no_club_when_only_ball_readings(self):
        """No club detected when all readings are at ball speed."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        base_time = time.time()
        # All readings are at ball speed (no club candidate)
        self.monitor._current_readings = [
            SpeedReading(speed=145.0, direction=Direction.OUTBOUND, magnitude=1200, timestamp=base_time),
            SpeedReading(speed=148.0, direction=Direction.OUTBOUND, magnitude=1500, timestamp=base_time + 0.05),
            SpeedReading(speed=146.0, direction=Direction.OUTBOUND, magnitude=1300, timestamp=base_time + 0.1),
        ]

        self.monitor._process_shot()

        shot = self.monitor._shots[0]
        assert shot.ball_speed_mph == 148.0
        assert shot.club_speed_mph is None

    def test_club_speed_range_validation(self):
        """Club speed must be within 50-85% of ball speed."""
        from openlaunch.ops243 import SpeedReading, Direction
        import time

        base_time = time.time()
        # 100 mph is ~71% of 140 mph - valid range
        self.monitor._current_readings = [
            SpeedReading(speed=100.0, direction=Direction.OUTBOUND, magnitude=2000, timestamp=base_time),
            SpeedReading(speed=140.0, direction=Direction.OUTBOUND, magnitude=1000, timestamp=base_time + 0.1),
            SpeedReading(speed=138.0, direction=Direction.OUTBOUND, magnitude=900, timestamp=base_time + 0.15),
        ]

        self.monitor._process_shot()

        shot = self.monitor._shots[0]
        assert shot.club_speed_mph == 100.0
        assert shot.smash_factor == 1.4


class TestMultiObjectReporting:
    """Tests for multi-object radar configuration."""

    def test_set_num_reports_single_digit(self):
        """set_num_reports should use On format for 1-9."""
        from openlaunch.ops243 import OPS243Radar

        radar = OPS243Radar.__new__(OPS243Radar)
        radar.serial = None

        # Verify the method exists and handles single digits
        # Can't test actual command without hardware, but method should not raise
        assert hasattr(radar, 'set_num_reports')

    def test_direction_constants(self):
        """Verify direction enum values."""
        from openlaunch.ops243 import Direction

        assert Direction.INBOUND.value == "inbound"
        assert Direction.OUTBOUND.value == "outbound"
        assert Direction.UNKNOWN.value == "unknown"
