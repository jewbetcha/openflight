"""Tests for server module."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from openflight.launch_monitor import Shot, ClubType
from openflight.kld7.types import KLD7Angle
from openflight import server as server_module
from openflight.server import (
    MockLaunchMonitor,
    estimate_launch_angle,
    on_shot_detected,
    radar_launch_is_plausible,
    shot_to_dict,
)


class TestShotToDict:
    """Tests for shot_to_dict conversion."""

    def test_basic_conversion(self):
        """Convert a basic shot to dict."""
        shot = Shot(
            ball_speed_mph=150.5,
            club_speed_mph=103.2,
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            club=ClubType.DRIVER,
        )

        result = shot_to_dict(shot)

        assert result["ball_speed_mph"] == 150.5
        assert result["club_speed_mph"] == 103.2
        assert result["club"] == "driver"
        assert result["timestamp"] == "2024-01-15T10:30:00"
        assert "estimated_carry_yards" in result
        assert "carry_range" in result
        assert len(result["carry_range"]) == 2

    def test_null_club_speed(self):
        """Shot without club speed should have null in dict."""
        shot = Shot(
            ball_speed_mph=150.0,
            timestamp=datetime.now(),
        )

        result = shot_to_dict(shot)

        assert result["club_speed_mph"] is None
        assert result["smash_factor"] is None

    def test_rounding(self):
        """Values should be rounded appropriately."""
        shot = Shot(
            ball_speed_mph=150.456,
            club_speed_mph=103.789,
            timestamp=datetime.now(),
        )

        result = shot_to_dict(shot)

        assert result["ball_speed_mph"] == 150.5  # 1 decimal
        assert result["club_speed_mph"] == 103.8  # 1 decimal
        assert result["smash_factor"] == 1.45  # 2 decimals


    def test_angle_source_field(self):
        """shot_to_dict should include angle_source."""
        shot = Shot(
            ball_speed_mph=150.0,
            timestamp=datetime.now(),
            launch_angle_vertical=12.5,
            launch_angle_confidence=0.8,
            angle_source="radar",
        )
        result = shot_to_dict(shot)
        assert result["angle_source"] == "radar"

    def test_angle_source_none_by_default(self):
        """Shot without angle source should have None."""
        shot = Shot(
            ball_speed_mph=150.0,
            timestamp=datetime.now(),
        )
        result = shot_to_dict(shot)
        assert result["angle_source"] is None


class TestEstimateLaunchAngle:
    """Tests for launch angle estimation from club type and ball speed."""

    def test_driver_average_speed(self):
        """Driver at average speed should return baseline launch angle."""
        angle, confidence = estimate_launch_angle(ClubType.DRIVER, 143)
        assert angle == 11.0
        assert confidence == 0.2

    def test_driver_fast_lowers_launch(self):
        """Faster than average ball speed should produce lower launch."""
        angle, _ = estimate_launch_angle(ClubType.DRIVER, 160)
        assert angle < 11.0

    def test_driver_slow_raises_launch(self):
        """Slower than average ball speed should produce higher launch."""
        angle, _ = estimate_launch_angle(ClubType.DRIVER, 120)
        assert angle > 11.0

    def test_wedge_high_launch(self):
        """Wedges should have high baseline launch angle."""
        angle, _ = estimate_launch_angle(ClubType.LW, 70)
        assert angle >= 30.0

    def test_floor_at_5_degrees(self):
        """Launch angle should never go below 5 degrees."""
        angle, _ = estimate_launch_angle(ClubType.DRIVER, 300)
        assert angle >= 5.0

    def test_unknown_club(self):
        """Unknown club should still return a reasonable estimate."""
        angle, confidence = estimate_launch_angle(ClubType.UNKNOWN, 120)
        assert 5.0 <= angle <= 40.0
        assert confidence == 0.2

    def test_low_smash_lowers_launch(self):
        """Low smash factor (thin hit) should lower launch angle, clamped."""
        baseline, _ = estimate_launch_angle(ClubType.DRIVER, 143)
        angle, _ = estimate_launch_angle(ClubType.DRIVER, 143, club_speed_mph=110)
        # smash = 143/110 = 1.30, well below optimal 1.48
        # Adjustment clamped to -3.0 degrees, so angle ≈ 11.0 - 3.0 = 8.0
        assert angle < baseline
        assert 7.0 <= angle <= 9.0

    def test_optimal_smash_no_change(self):
        """Optimal smash factor should not shift launch angle."""
        angle, _ = estimate_launch_angle(ClubType.DRIVER, 143, club_speed_mph=96.6)
        # smash = 143/96.6 ≈ 1.48 (optimal for driver)
        assert angle == 11.0

    def test_smash_raises_confidence(self):
        """Providing club speed should raise confidence from 0.2 to 0.35."""
        _, conf = estimate_launch_angle(ClubType.DRIVER, 143, club_speed_mph=96.6)
        assert conf == 0.35

    def test_high_smash_raises_launch(self):
        """High smash factor should slightly raise launch angle."""
        baseline, _ = estimate_launch_angle(ClubType.DRIVER, 143)
        # smash = 143/90 ≈ 1.59, above optimal 1.48
        angle, _ = estimate_launch_angle(ClubType.DRIVER, 143, club_speed_mph=90)
        assert angle > baseline
        assert angle <= baseline + 2.0  # capped at +2.0 degrees

    def test_iron_smash_adjustment(self):
        """Iron smash factor adjustment should lower angle for thin hit."""
        baseline, _ = estimate_launch_angle(ClubType.IRON_7, 100)
        # Low smash for 7-iron: smash = 100/80 = 1.25, below optimal ~1.34
        angle, _ = estimate_launch_angle(ClubType.IRON_7, 100, club_speed_mph=80)
        assert angle < baseline
        assert angle >= baseline - 3.0  # clamped

    def test_no_club_speed_unchanged(self):
        """Without club speed, behavior should be identical to current."""
        angle, conf = estimate_launch_angle(ClubType.DRIVER, 143)
        assert angle == 11.0
        assert conf == 0.2

    def test_zero_club_speed_ignored(self):
        """Zero club speed should be treated as no club speed."""
        angle, conf = estimate_launch_angle(ClubType.DRIVER, 143, club_speed_mph=0)
        assert angle == 11.0
        assert conf == 0.2

    def test_high_spin_raises_launch(self):
        """High spin should nudge launch angle up."""
        baseline, _ = estimate_launch_angle(ClubType.DRIVER, 143)
        angle, _ = estimate_launch_angle(ClubType.DRIVER, 143, spin_rpm=4000)
        # 4000 rpm is above optimal ~2500 for driver at 143 mph
        assert angle > baseline

    def test_low_spin_lowers_launch(self):
        """Low spin should nudge launch angle down."""
        baseline, _ = estimate_launch_angle(ClubType.DRIVER, 143)
        angle, _ = estimate_launch_angle(ClubType.DRIVER, 143, spin_rpm=1000)
        assert angle < baseline

    def test_spin_with_smash_raises_confidence(self):
        """Providing both club speed and spin should raise confidence to 0.5."""
        _, conf = estimate_launch_angle(
            ClubType.DRIVER, 143, club_speed_mph=96.6, spin_rpm=2500
        )
        assert conf == 0.5

    def test_spin_alone_confidence(self):
        """Spin without club speed should raise confidence to 0.35."""
        _, conf = estimate_launch_angle(ClubType.DRIVER, 143, spin_rpm=2500)
        assert conf == 0.35


class TestMockLaunchMonitor:
    """Tests for MockLaunchMonitor."""

    def test_initial_state(self):
        """New mock monitor should have empty state."""
        monitor = MockLaunchMonitor()

        assert monitor._shots == []
        assert monitor._current_club == ClubType.DRIVER
        assert not monitor._running

    def test_connect_disconnect(self):
        """Connect and disconnect should work."""
        monitor = MockLaunchMonitor()

        assert monitor.connect() is True
        monitor.disconnect()
        assert not monitor._running

    def test_simulate_shot(self):
        """Simulating a shot should create a shot record."""
        monitor = MockLaunchMonitor()
        monitor.connect()
        monitor.start()

        shot = monitor.simulate_shot(ball_speed=150.0)

        assert len(monitor._shots) == 1
        assert 140.0 <= shot.ball_speed_mph <= 160.0  # ±10 variance
        assert shot.club == ClubType.DRIVER
        assert shot.mode == "mock"
        assert shot.spin_rpm is not None and shot.spin_rpm >= 1000
        assert shot.launch_angle_vertical is not None and shot.launch_angle_vertical >= 5.0
        assert shot.launch_angle_horizontal is not None
        assert shot.launch_angle_confidence is not None

    def test_simulate_shot_with_callback(self):
        """Callback should be called when shot is simulated."""
        monitor = MockLaunchMonitor()
        received_shots = []

        def callback(shot):
            received_shots.append(shot)

        monitor.connect()
        monitor.start(shot_callback=callback)
        monitor.simulate_shot()

        assert len(received_shots) == 1

    def test_set_club(self):
        """Set club should affect future shots."""
        monitor = MockLaunchMonitor()
        monitor.connect()
        monitor.start()

        monitor.set_club(ClubType.IRON_7)
        shot = monitor.simulate_shot()

        assert shot.club == ClubType.IRON_7

    def test_get_shots(self):
        """Get shots should return copy of shots list."""
        monitor = MockLaunchMonitor()
        monitor.connect()
        monitor.start()
        monitor.simulate_shot()
        monitor.simulate_shot()

        shots = monitor.get_shots()

        assert len(shots) == 2
        # Verify it's a copy
        shots.append(None)
        assert len(monitor._shots) == 2

    def test_session_stats_empty(self):
        """Empty session should return zero stats."""
        monitor = MockLaunchMonitor()

        stats = monitor.get_session_stats()

        assert stats["shot_count"] == 0
        assert stats["avg_ball_speed"] == 0

    def test_session_stats_with_shots(self):
        """Session stats should reflect shots taken."""
        monitor = MockLaunchMonitor()
        monitor.connect()
        monitor.start()
        monitor.simulate_shot(ball_speed=140.0)
        monitor.simulate_shot(ball_speed=150.0)
        monitor.simulate_shot(ball_speed=160.0)

        stats = monitor.get_session_stats()

        assert stats["shot_count"] == 3
        # Averages will vary due to ±10 variance, but should be in range
        assert 140 <= stats["avg_ball_speed"] <= 160
        assert stats["avg_club_speed"] is not None
        assert stats["avg_smash_factor"] is not None

    def test_clear_session(self):
        """Clear session should reset all shots."""
        monitor = MockLaunchMonitor()
        monitor.connect()
        monitor.start()
        monitor.simulate_shot()
        monitor.simulate_shot()

        monitor.clear_session()

        assert monitor._shots == []
        assert monitor.get_session_stats()["shot_count"] == 0


class TestRadarLaunchGuard:
    """Tests for club-and-speed sanity checks on radar launch angles."""

    SESSION_LOG_PATH = (
        Path(__file__).parent.parent / "session_logs" / "session_20260402_121507_range.jsonl"
    )

    def test_rejects_implausible_7iron_launch(self):
        """An obviously impossible 7-iron launch angle should be rejected."""
        plausible, details = radar_launch_is_plausible(
            radar_angle_deg=79.4,
            club=ClubType.IRON_7,
            ball_speed_mph=100.0,
        )

        assert plausible is False
        assert details["expected_launch_deg"] == pytest.approx(20.5)
        assert details["delta_deg"] > details["allowed_delta_deg"]

    def test_accepts_plausible_driver_launch(self):
        """A realistic driver launch angle should pass the sanity guard."""
        plausible, details = radar_launch_is_plausible(
            radar_angle_deg=17.8,
            club=ClubType.DRIVER,
            ball_speed_mph=97.9,
            club_speed_mph=66.0,
        )

        assert plausible is True
        assert details["delta_deg"] < details["allowed_delta_deg"]

    def test_flags_known_outliers_in_real_session_log(self):
        """Historic backyard session log should surface the same three driver outliers."""
        if not self.SESSION_LOG_PATH.exists():
            pytest.skip(f"Session log not found: {self.SESSION_LOG_PATH}")

        implausible_shots = []
        total_shots = 0

        with self.SESSION_LOG_PATH.open() as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("type") != "shot_detected":
                    continue

                total_shots += 1
                plausible, _ = radar_launch_is_plausible(
                    radar_angle_deg=entry["launch_angle_vertical"],
                    club=ClubType(entry["club"]),
                    ball_speed_mph=entry["ball_speed_mph"],
                    club_speed_mph=entry.get("club_speed_mph"),
                    spin_rpm=entry.get("spin_rpm"),
                )
                if not plausible:
                    implausible_shots.append(entry["shot_number"])

        assert total_shots == 11
        assert implausible_shots == [3, 9, 11]


class TestOnShotDetected:
    """Tests for live shot processing in the server."""

    def test_kld7_uses_shot_impact_timestamp(self, monkeypatch):
        """K-LD7 selection should be anchored to the OPS243 impact timestamp."""
        calls = []

        class StubTracker:
            orientation = "vertical"

            def snapshot_buffer(self):
                return []

            def get_angle_for_shot(self, shot_timestamp=None, ball_speed_mph=None):
                calls.append(("ball", shot_timestamp))
                return KLD7Angle(vertical_deg=12.0, confidence=0.8, num_frames=2)

            def reset(self):
                calls.append(("reset", None))

        emitted = []
        monkeypatch.setattr(server_module, "kld7_vertical", StubTracker())
        monkeypatch.setattr(server_module, "camera_tracker", None)
        monkeypatch.setattr(server_module, "camera_enabled", False)
        monkeypatch.setattr(server_module, "monitor", None)
        monkeypatch.setattr(server_module, "debug_mode", False)
        monkeypatch.setattr(server_module, "get_session_logger", lambda: None)
        monkeypatch.setattr(server_module.socketio, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))

        shot = Shot(
            ball_speed_mph=150.0,
            timestamp=datetime.now(),
            impact_timestamp=1234.5,
            club=ClubType.DRIVER,
        )

        on_shot_detected(shot)

        assert ("ball", 1234.5) in calls
        assert emitted

    def test_implausible_kld7_angle_falls_back_to_estimate(self, monkeypatch):
        """Radar angles that conflict with club+speed should not override the estimate."""
        class StubTracker:
            orientation = "vertical"

            def snapshot_buffer(self):
                return []

            def get_angle_for_shot(self, shot_timestamp=None, ball_speed_mph=None):
                return KLD7Angle(vertical_deg=79.4, confidence=0.58, num_frames=1)

            def reset(self):
                return None

        monkeypatch.setattr(server_module, "kld7_vertical", StubTracker())
        monkeypatch.setattr(server_module, "camera_tracker", None)
        monkeypatch.setattr(server_module, "camera_enabled", False)
        monkeypatch.setattr(server_module, "monitor", None)
        monkeypatch.setattr(server_module, "debug_mode", False)
        monkeypatch.setattr(server_module, "get_session_logger", lambda: None)
        monkeypatch.setattr(server_module.socketio, "emit", lambda *args, **kwargs: None)

        shot = Shot(
            ball_speed_mph=100.0,
            timestamp=datetime.now(),
            club=ClubType.IRON_7,
        )

        on_shot_detected(shot)

        assert shot.angle_source == "estimated"
        assert shot.launch_angle_vertical == pytest.approx(20.5)

    def test_implausible_club_aoa_is_rejected(self, monkeypatch):
        """A +31° club AoA is physically impossible and should be discarded."""
        class StubTracker:
            orientation = "vertical"

            def snapshot_buffer(self):
                return []

            def get_angle_for_shot(self, shot_timestamp=None, ball_speed_mph=None):
                return KLD7Angle(vertical_deg=15.0, confidence=0.7, num_frames=2)

            def get_club_angle(self, club_speed_mph=None):
                # Radar reports -31° vertical → server negates to +31° AoA
                return KLD7Angle(vertical_deg=-31.0, confidence=0.7, num_frames=2)

            def reset(self):
                return None

        monkeypatch.setattr(server_module, "kld7_vertical", StubTracker())
        monkeypatch.setattr(server_module, "camera_tracker", None)
        monkeypatch.setattr(server_module, "camera_enabled", False)
        monkeypatch.setattr(server_module, "monitor", None)
        monkeypatch.setattr(server_module, "debug_mode", False)
        monkeypatch.setattr(server_module, "get_session_logger", lambda: None)
        monkeypatch.setattr(server_module.socketio, "emit", lambda *args, **kwargs: None)

        shot = Shot(
            ball_speed_mph=115.0,
            club_speed_mph=80.0,
            timestamp=datetime.now(),
            club=ClubType.IRON_7,
        )

        on_shot_detected(shot)

        assert shot.club_angle_deg is None, (
            f"AoA of +31° should be rejected, got {shot.club_angle_deg}"
        )

    def test_plausible_kld7_angle_remains_radar_source(self, monkeypatch):
        """Plausible radar angles should continue to override the estimate."""
        class StubTracker:
            orientation = "vertical"

            def snapshot_buffer(self):
                return []

            def get_angle_for_shot(self, shot_timestamp=None, ball_speed_mph=None):
                return KLD7Angle(vertical_deg=18.7, confidence=0.8, num_frames=2)

            def reset(self):
                return None

        monkeypatch.setattr(server_module, "kld7_vertical", StubTracker())
        monkeypatch.setattr(server_module, "camera_tracker", None)
        monkeypatch.setattr(server_module, "camera_enabled", False)
        monkeypatch.setattr(server_module, "monitor", None)
        monkeypatch.setattr(server_module, "debug_mode", False)
        monkeypatch.setattr(server_module, "get_session_logger", lambda: None)
        monkeypatch.setattr(server_module.socketio, "emit", lambda *args, **kwargs: None)

        shot = Shot(
            ball_speed_mph=82.5,
            club_speed_mph=57.0,
            timestamp=datetime.now(),
            club=ClubType.DRIVER,
        )

        on_shot_detected(shot)

        assert shot.angle_source == "radar"
        assert shot.launch_angle_vertical == pytest.approx(18.7)
