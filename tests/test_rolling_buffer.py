"""Tests for rolling_buffer module."""

import math
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from openflight.launch_monitor import ClubType, Shot
from openflight.rolling_buffer import (
    # Types
    IQCapture,
    SpeedReading,
    SpeedTimeline,
    SpinResult,
    ProcessedCapture,
    # Processor
    RollingBufferProcessor,
    # Triggers
    TriggerStrategy,
    PollingTrigger,
    ThresholdTrigger,
    ManualTrigger,
    create_trigger,
    # Monitor functions
    estimate_carry_with_spin,
    get_optimal_spin_for_ball_speed,
)


# =============================================================================
# Tests for Optimal Spin Calculation
# =============================================================================

class TestGetOptimalSpinForBallSpeed:
    """Tests for the optimal spin rate calculation based on ball speed."""

    def test_high_ball_speed_180_mph(self):
        """180 mph ball speed should have ~2050 rpm optimal spin."""
        optimal = get_optimal_spin_for_ball_speed(180, ClubType.DRIVER)
        assert 2000 <= optimal <= 2100

    def test_tour_average_167_mph(self):
        """167 mph (PGA Tour avg) should have ~2450 rpm optimal spin."""
        optimal = get_optimal_spin_for_ball_speed(167, ClubType.DRIVER)
        assert 2300 <= optimal <= 2600

    def test_moderate_speed_160_mph(self):
        """160 mph ball speed should have ~2550 rpm optimal spin."""
        optimal = get_optimal_spin_for_ball_speed(160, ClubType.DRIVER)
        assert 2500 <= optimal <= 2600

    def test_amateur_speed_140_mph(self):
        """140 mph ball speed should have ~2700 rpm optimal spin."""
        optimal = get_optimal_spin_for_ball_speed(140, ClubType.DRIVER)
        assert 2650 <= optimal <= 2750

    def test_slower_speed_120_mph(self):
        """120 mph ball speed should have ~2900 rpm optimal spin."""
        optimal = get_optimal_spin_for_ball_speed(120, ClubType.DRIVER)
        assert 2850 <= optimal <= 2950

    def test_very_slow_speed_100_mph(self):
        """100 mph ball speed should have ~3100 rpm optimal spin."""
        optimal = get_optimal_spin_for_ball_speed(100, ClubType.DRIVER)
        assert 3050 <= optimal <= 3150

    def test_optimal_spin_decreases_with_ball_speed(self):
        """Higher ball speeds should require less spin."""
        spin_120 = get_optimal_spin_for_ball_speed(120, ClubType.DRIVER)
        spin_140 = get_optimal_spin_for_ball_speed(140, ClubType.DRIVER)
        spin_160 = get_optimal_spin_for_ball_speed(160, ClubType.DRIVER)
        spin_180 = get_optimal_spin_for_ball_speed(180, ClubType.DRIVER)

        assert spin_120 > spin_140 > spin_160 > spin_180

    def test_irons_need_more_spin_than_driver(self):
        """Irons should have higher optimal spin than driver at same speed."""
        driver_spin = get_optimal_spin_for_ball_speed(140, ClubType.DRIVER)
        iron_7_spin = get_optimal_spin_for_ball_speed(140, ClubType.IRON_7)
        pw_spin = get_optimal_spin_for_ball_speed(140, ClubType.PW)

        assert iron_7_spin > driver_spin
        assert pw_spin > iron_7_spin

    def test_club_spin_ordering(self):
        """Shorter clubs should require more spin."""
        ball_speed = 130
        driver = get_optimal_spin_for_ball_speed(ball_speed, ClubType.DRIVER)
        wood_3 = get_optimal_spin_for_ball_speed(ball_speed, ClubType.WOOD_3)
        iron_5 = get_optimal_spin_for_ball_speed(ball_speed, ClubType.IRON_5)
        iron_9 = get_optimal_spin_for_ball_speed(ball_speed, ClubType.IRON_9)
        pw = get_optimal_spin_for_ball_speed(ball_speed, ClubType.PW)

        assert driver < wood_3 < iron_5 < iron_9 < pw


# =============================================================================
# Tests for Carry Distance with Spin
# =============================================================================

class TestEstimateCarryWithSpin:
    """Tests for the spin-adjusted carry distance calculation."""

    def test_optimal_spin_gives_best_carry(self):
        """Spin at optimal rate should give highest carry."""
        ball_speed = 160
        optimal_spin = get_optimal_spin_for_ball_speed(ball_speed, ClubType.DRIVER)

        carry_optimal = estimate_carry_with_spin(ball_speed, optimal_spin, ClubType.DRIVER)
        carry_low = estimate_carry_with_spin(ball_speed, optimal_spin - 1000, ClubType.DRIVER)
        carry_high = estimate_carry_with_spin(ball_speed, optimal_spin + 1000, ClubType.DRIVER)

        assert carry_optimal >= carry_low
        assert carry_optimal >= carry_high

    def test_low_spin_penalty_more_severe_than_high_spin(self):
        """Low spin should hurt carry more than high spin."""
        ball_speed = 160
        optimal_spin = get_optimal_spin_for_ball_speed(ball_speed, ClubType.DRIVER)

        carry_optimal = estimate_carry_with_spin(ball_speed, optimal_spin, ClubType.DRIVER)
        carry_1000_low = estimate_carry_with_spin(ball_speed, optimal_spin - 1000, ClubType.DRIVER)
        carry_1000_high = estimate_carry_with_spin(ball_speed, optimal_spin + 1000, ClubType.DRIVER)

        low_penalty = carry_optimal - carry_1000_low
        high_penalty = carry_optimal - carry_1000_high

        # Low spin penalty should be larger
        assert low_penalty > high_penalty

    def test_tour_average_produces_expected_carry(self):
        """167 mph with ~2686 rpm should produce ~275 yards (Tour avg)."""
        carry = estimate_carry_with_spin(167, 2686, ClubType.DRIVER)
        # Allow some tolerance since we don't have launch angle
        assert 260 <= carry <= 290

    def test_very_low_spin_significant_penalty(self):
        """Very low spin (1500 rpm at 160 mph) should lose significant distance."""
        carry_optimal = estimate_carry_with_spin(160, 2550, ClubType.DRIVER)
        carry_low_spin = estimate_carry_with_spin(160, 1500, ClubType.DRIVER)

        # Should lose at least 10% carry
        assert carry_low_spin < carry_optimal * 0.90

    def test_very_high_spin_moderate_penalty(self):
        """Very high spin (4500 rpm at 160 mph) should lose moderate distance."""
        carry_optimal = estimate_carry_with_spin(160, 2550, ClubType.DRIVER)
        carry_high_spin = estimate_carry_with_spin(160, 4500, ClubType.DRIVER)

        # Should lose some but not as much as low spin
        assert carry_high_spin < carry_optimal
        assert carry_high_spin > carry_optimal * 0.85

    def test_smash_factor_penalty_for_poor_contact(self):
        """Poor smash factor should reduce carry estimate."""
        ball_speed = 150
        spin = 2600

        # Good contact: 150 mph ball / 100 mph club = 1.50 smash
        carry_good = estimate_carry_with_spin(
            ball_speed, spin, ClubType.DRIVER, club_speed_mph=100
        )

        # Poor contact: 150 mph ball / 115 mph club = 1.30 smash
        carry_poor = estimate_carry_with_spin(
            ball_speed, spin, ClubType.DRIVER, club_speed_mph=115
        )

        assert carry_poor < carry_good

    def test_no_club_speed_no_smash_penalty(self):
        """Without club speed, no smash factor penalty applied."""
        ball_speed = 150
        spin = 2600

        carry_no_club = estimate_carry_with_spin(ball_speed, spin, ClubType.DRIVER)
        carry_with_club = estimate_carry_with_spin(
            ball_speed, spin, ClubType.DRIVER, club_speed_mph=101  # 1.48 smash - optimal
        )

        # Should be very close (club speed at optimal smash has minimal effect)
        assert abs(carry_no_club - carry_with_club) < 5

    def test_carry_increases_with_ball_speed(self):
        """Higher ball speed should always increase carry."""
        spin = 2600
        carry_120 = estimate_carry_with_spin(120, spin, ClubType.DRIVER)
        carry_140 = estimate_carry_with_spin(140, spin, ClubType.DRIVER)
        carry_160 = estimate_carry_with_spin(160, spin, ClubType.DRIVER)

        assert carry_120 < carry_140 < carry_160

    def test_realistic_carry_values(self):
        """Test that carry values are in realistic ranges."""
        # Amateur golfer: 140 mph ball speed, 2800 rpm
        amateur = estimate_carry_with_spin(140, 2800, ClubType.DRIVER)
        assert 220 <= amateur <= 250

        # Tour player: 170 mph ball speed, 2400 rpm
        tour = estimate_carry_with_spin(170, 2400, ClubType.DRIVER)
        assert 280 <= tour <= 320  # Widened range for slightly above optimal

        # Long drive: 190 mph ball speed, 2000 rpm
        long_drive = estimate_carry_with_spin(190, 2000, ClubType.DRIVER)
        assert 330 <= long_drive <= 380  # Widened for variation


# =============================================================================
# Tests for Rolling Buffer Types
# =============================================================================

class TestIQCapture:
    """Tests for IQCapture dataclass."""

    def test_create_iq_capture(self):
        """Basic IQCapture creation."""
        i_samples = [100] * 4096
        q_samples = [100] * 4096
        capture = IQCapture(
            sample_time=0.136,
            trigger_time=0.0,
            i_samples=i_samples,
            q_samples=q_samples,
            timestamp=1234567890.0,
        )
        assert capture.sample_time == 0.136
        assert len(capture.i_samples) == 4096
        assert len(capture.q_samples) == 4096


class TestSpeedReading:
    """Tests for rolling buffer SpeedReading dataclass."""

    def test_create_speed_reading(self):
        """Basic SpeedReading creation."""
        reading = SpeedReading(
            speed_mph=155.3,
            timestamp_ms=50.0,
            magnitude=500.0,
            direction="outbound",
        )
        assert reading.speed_mph == 155.3
        assert reading.is_outbound is True

    def test_inbound_direction(self):
        """Test inbound direction detection."""
        reading = SpeedReading(
            speed_mph=50.0,
            timestamp_ms=10.0,
            magnitude=100.0,
            direction="inbound",
        )
        assert reading.is_outbound is False


class TestSpeedTimeline:
    """Tests for SpeedTimeline dataclass."""

    def test_peak_speed(self):
        """Peak speed should return highest reading."""
        readings = [
            SpeedReading(speed_mph=100.0, timestamp_ms=10.0, magnitude=100, direction="outbound"),
            SpeedReading(speed_mph=155.0, timestamp_ms=20.0, magnitude=200, direction="outbound"),
            SpeedReading(speed_mph=120.0, timestamp_ms=30.0, magnitude=150, direction="outbound"),
        ]
        timeline = SpeedTimeline(readings=readings, sample_rate_hz=937.5)

        assert timeline.peak_speed is not None
        assert timeline.peak_speed.speed_mph == 155.0

    def test_speeds_property(self):
        """speeds property should return list of speed values."""
        readings = [
            SpeedReading(speed_mph=100.0, timestamp_ms=10.0, magnitude=100, direction="outbound"),
            SpeedReading(speed_mph=150.0, timestamp_ms=20.0, magnitude=200, direction="outbound"),
        ]
        timeline = SpeedTimeline(readings=readings, sample_rate_hz=937.5)

        assert timeline.speeds == [100.0, 150.0]

    def test_duration_ms(self):
        """Duration should be difference between first and last timestamp."""
        readings = [
            SpeedReading(speed_mph=100.0, timestamp_ms=10.0, magnitude=100, direction="outbound"),
            SpeedReading(speed_mph=150.0, timestamp_ms=60.0, magnitude=200, direction="outbound"),
        ]
        timeline = SpeedTimeline(readings=readings, sample_rate_hz=937.5)

        assert timeline.duration_ms == 50.0


class TestSpinResult:
    """Tests for SpinResult dataclass."""

    def test_quality_high(self):
        """High confidence should produce 'high' quality."""
        result = SpinResult(
            spin_rpm=2800,
            confidence=0.85,
            snr=5.0,
            quality="high",
        )
        assert result.quality == "high"

    def test_quality_low(self):
        """Low confidence should produce 'low' quality."""
        result = SpinResult(
            spin_rpm=2800,
            confidence=0.3,
            snr=2.0,
            quality="low",
        )
        assert result.quality == "low"


# =============================================================================
# Tests for Rolling Buffer Processor
# =============================================================================

class TestRollingBufferProcessor:
    """Tests for the FFT-based rolling buffer processor."""

    @pytest.fixture
    def processor(self):
        """Create a processor instance for testing."""
        return RollingBufferProcessor()

    def test_processor_creation(self):
        """Processor should initialize with correct constants."""
        processor = RollingBufferProcessor()
        assert processor.WINDOW_SIZE == 128
        assert processor.FFT_SIZE == 4096
        assert processor.SAMPLE_RATE == 30000

    def test_parse_capture_valid_json(self, processor):
        """Parser should handle valid JSON response."""
        # Create a mock JSON response like the radar would return
        # The radar sends each field as a separate JSON line
        i_samples = [2048 + int(100 * math.sin(2 * math.pi * i / 128)) for i in range(4096)]
        q_samples = [2048 + int(100 * math.cos(2 * math.pi * i / 128)) for i in range(4096)]

        import json
        response = (
            '{"sample_time": 0.136}\n'
            '{"trigger_time": 0.0}\n'
            f'{{"I": {json.dumps(i_samples)}}}\n'
            f'{{"Q": {json.dumps(q_samples)}}}'
        )

        capture = processor.parse_capture(response)

        assert capture is not None
        assert len(capture.i_samples) == 4096
        assert len(capture.q_samples) == 4096
        assert capture.sample_time == 0.136
        assert capture.trigger_time == 0.0

    def test_parse_capture_invalid_json(self, processor):
        """Parser should handle invalid JSON gracefully."""
        capture = processor.parse_capture("not valid json")
        assert capture is None

    def test_parse_capture_missing_fields(self, processor):
        """Parser should handle missing fields."""
        capture = processor.parse_capture('{"sample_time":0.136}')
        assert capture is None

    def test_process_standard_returns_timeline(self, processor):
        """Standard processing should return a SpeedTimeline."""
        # Create synthetic I/Q data with a Doppler frequency that corresponds
        # to a realistic golf ball speed. At 30 kHz sample rate:
        # bin = speed * (FFT_SIZE / SAMPLE_RATE) / 0.0063
        # For 150 mph: bin ≈ 150 * (4096/30000) / 0.0063 ≈ 3252
        # Frequency = bin * SAMPLE_RATE / FFT_SIZE ≈ 23.8 kHz (unrealistic)
        # Actually: speed = bin * 0.0063 * (30000 / 4096), so for 150 mph:
        # bin = 150 / (0.0063 * 7.324) ≈ 3252
        # Let's use a lower test frequency that maps to a detectable speed
        doppler_freq = 500  # Hz - corresponds to ~10 mph
        i_samples = [2048 + int(500 * math.sin(2 * math.pi * doppler_freq * i / 30000)) for i in range(4096)]
        q_samples = [2048 + int(500 * math.cos(2 * math.pi * doppler_freq * i / 30000)) for i in range(4096)]

        capture = IQCapture(
            sample_time=0.136,
            trigger_time=0.0,
            i_samples=i_samples,
            q_samples=q_samples,
            timestamp=1234567890.0,
        )

        timeline = processor.process_standard(capture)

        assert timeline is not None
        assert isinstance(timeline, SpeedTimeline)
        # With 4096 samples and 128 block size, we get 4096/128 = 32 readings
        assert len(timeline.readings) == 32

    def test_process_overlapping_higher_resolution(self, processor):
        """Overlapping processing should give more readings than standard."""
        doppler_freq = 500  # Hz
        i_samples = [2048 + int(500 * math.sin(2 * math.pi * doppler_freq * i / 30000)) for i in range(4096)]
        q_samples = [2048 + int(500 * math.cos(2 * math.pi * doppler_freq * i / 30000)) for i in range(4096)]

        capture = IQCapture(
            sample_time=0.136,
            trigger_time=0.0,
            i_samples=i_samples,
            q_samples=q_samples,
            timestamp=1234567890.0,
        )

        standard = processor.process_standard(capture)
        overlapping = processor.process_overlapping(capture)

        # Standard: 4096/128 = 32 readings
        # Overlapping: (4096-128)/32 + 1 = 125 readings (4x more)
        assert len(overlapping.readings) > len(standard.readings)
        assert len(standard.readings) == 32
        assert len(overlapping.readings) >= 120  # Allow some tolerance


# =============================================================================
# Tests for Trigger Strategies
# =============================================================================

class TestTriggerFactory:
    """Tests for the trigger factory function."""

    def test_create_polling_trigger(self):
        """Factory should create PollingTrigger."""
        trigger = create_trigger("polling")
        assert isinstance(trigger, PollingTrigger)

    def test_create_threshold_trigger(self):
        """Factory should create ThresholdTrigger."""
        trigger = create_trigger("threshold", speed_threshold_mph=60)
        assert isinstance(trigger, ThresholdTrigger)

    def test_create_manual_trigger(self):
        """Factory should create ManualTrigger."""
        trigger = create_trigger("manual")
        assert isinstance(trigger, ManualTrigger)

    def test_invalid_trigger_type(self):
        """Factory should raise error for unknown trigger type."""
        with pytest.raises(ValueError):
            create_trigger("invalid_type")


class TestPollingTrigger:
    """Tests for the polling-based trigger."""

    def test_default_parameters(self):
        """Polling trigger should have sensible defaults."""
        trigger = PollingTrigger()
        assert trigger.poll_interval == 0.3
        assert trigger.min_readings == 1
        assert trigger.min_speed_mph == 15

    def test_custom_parameters(self):
        """Polling trigger should accept custom parameters."""
        trigger = PollingTrigger(
            poll_interval=0.2,
            min_readings=5,
            min_speed_mph=50,
        )
        assert trigger.poll_interval == 0.2
        assert trigger.min_readings == 5
        assert trigger.min_speed_mph == 50

    def test_reset_no_state(self):
        """Polling trigger reset should be no-op."""
        trigger = PollingTrigger()
        trigger.reset()  # Should not raise


class TestThresholdTrigger:
    """Tests for the threshold-based trigger."""

    def test_default_threshold(self):
        """Threshold trigger should have default 50 mph threshold."""
        trigger = ThresholdTrigger()
        assert trigger.speed_threshold_mph == 50

    def test_custom_threshold(self):
        """Threshold trigger should accept custom threshold."""
        trigger = ThresholdTrigger(speed_threshold_mph=70)
        assert trigger.speed_threshold_mph == 70

    def test_reset_clears_triggered(self):
        """Reset should clear triggered state."""
        trigger = ThresholdTrigger()
        trigger._triggered = True
        trigger.reset()
        assert trigger._triggered is False


class TestManualTrigger:
    """Tests for the manual trigger."""

    def test_initial_state(self):
        """Manual trigger should start with no request."""
        trigger = ManualTrigger()
        assert trigger._trigger_requested is False

    def test_request_trigger(self):
        """Request should set trigger flag."""
        trigger = ManualTrigger()
        trigger.request_trigger()
        assert trigger._trigger_requested is True

    def test_reset_clears_request(self):
        """Reset should clear trigger request."""
        trigger = ManualTrigger()
        trigger.request_trigger()
        trigger.reset()
        assert trigger._trigger_requested is False


# =============================================================================
# Tests for Shot with Spin Fields
# =============================================================================

class TestShotWithSpin:
    """Tests for Shot dataclass spin-related fields."""

    def test_shot_with_spin_data(self):
        """Shot should accept spin fields."""
        shot = Shot(
            ball_speed_mph=160.0,
            timestamp=datetime.now(),
            club_speed_mph=108.0,
            spin_rpm=2550.0,
            spin_confidence=0.85,
            carry_spin_adjusted=275.0,
        )
        assert shot.spin_rpm == 2550.0
        assert shot.spin_confidence == 0.85
        assert shot.carry_spin_adjusted == 275.0

    def test_shot_without_spin_data(self):
        """Shot should work without spin fields."""
        shot = Shot(
            ball_speed_mph=160.0,
            timestamp=datetime.now(),
        )
        assert shot.spin_rpm is None
        assert shot.spin_confidence is None
        assert shot.carry_spin_adjusted is None

    def test_has_spin_property(self):
        """has_spin should return True when spin_rpm is set."""
        shot_with_spin = Shot(
            ball_speed_mph=160.0,
            timestamp=datetime.now(),
            spin_rpm=2550.0,
        )
        shot_without_spin = Shot(
            ball_speed_mph=160.0,
            timestamp=datetime.now(),
        )

        assert shot_with_spin.has_spin is True
        assert shot_without_spin.has_spin is False

    def test_spin_quality_high(self):
        """High confidence should return 'high' quality."""
        shot = Shot(
            ball_speed_mph=160.0,
            timestamp=datetime.now(),
            spin_rpm=2550.0,
            spin_confidence=0.8,
        )
        assert shot.spin_quality == "high"

    def test_spin_quality_medium(self):
        """Medium confidence should return 'medium' quality."""
        shot = Shot(
            ball_speed_mph=160.0,
            timestamp=datetime.now(),
            spin_rpm=2550.0,
            spin_confidence=0.5,
        )
        assert shot.spin_quality == "medium"

    def test_spin_quality_low(self):
        """Low confidence should return 'low' quality."""
        shot = Shot(
            ball_speed_mph=160.0,
            timestamp=datetime.now(),
            spin_rpm=2550.0,
            spin_confidence=0.3,
        )
        assert shot.spin_quality == "low"

    def test_spin_quality_none_without_confidence(self):
        """No confidence should return None quality."""
        shot = Shot(
            ball_speed_mph=160.0,
            timestamp=datetime.now(),
        )
        assert shot.spin_quality is None


# =============================================================================
# Integration Tests
# =============================================================================

class TestCarryCalculationIntegration:
    """Integration tests for the complete carry calculation pipeline."""

    def test_full_shot_carry_calculation(self):
        """Test complete flow from ball speed + spin to carry distance."""
        # Simulate a Tour-quality shot
        ball_speed = 167  # Tour average
        club_speed = 113  # Tour average
        spin = 2686  # Tour average

        # Calculate optimal spin for validation
        optimal_spin = get_optimal_spin_for_ball_speed(ball_speed, ClubType.DRIVER)

        # Calculate carry
        carry = estimate_carry_with_spin(
            ball_speed, spin, ClubType.DRIVER, club_speed_mph=club_speed
        )

        # Should be close to Tour average (~275 yards)
        assert 265 <= carry <= 285

        # Smash factor check
        smash = ball_speed / club_speed
        assert 1.45 <= smash <= 1.52  # Tour range

    def test_amateur_shot_comparison(self):
        """Compare amateur vs Tour carry distances."""
        # Amateur: 140 mph ball, 95 mph club, 3000 rpm spin (slightly high)
        amateur_carry = estimate_carry_with_spin(
            140, 3000, ClubType.DRIVER, club_speed_mph=95
        )

        # Tour: 167 mph ball, 113 mph club, 2686 rpm spin (optimal)
        tour_carry = estimate_carry_with_spin(
            167, 2686, ClubType.DRIVER, club_speed_mph=113
        )

        # Tour should be significantly longer (at least 30 yards more)
        assert tour_carry > amateur_carry + 30

    def test_same_ball_speed_different_spin(self):
        """Same ball speed with different spins should produce different carries."""
        ball_speed = 155
        club_speed = 105

        carry_low_spin = estimate_carry_with_spin(
            ball_speed, 1800, ClubType.DRIVER, club_speed_mph=club_speed
        )
        carry_optimal_spin = estimate_carry_with_spin(
            ball_speed, 2650, ClubType.DRIVER, club_speed_mph=club_speed
        )
        carry_high_spin = estimate_carry_with_spin(
            ball_speed, 3500, ClubType.DRIVER, club_speed_mph=club_speed
        )

        # Optimal should be best
        assert carry_optimal_spin > carry_low_spin
        assert carry_optimal_spin > carry_high_spin

        # All should be positive and reasonable (widen ranges)
        assert 200 <= carry_low_spin <= 270
        assert 230 <= carry_optimal_spin <= 280
        assert 210 <= carry_high_spin <= 270


# =============================================================================
# Tests for Trigger Diagnostics
# =============================================================================

class TestTriggerStrategyDiagnostics:
    """Tests for the diagnostic accumulation in TriggerStrategy."""

    def test_drain_diagnostics_returns_empty_list(self):
        """drain_diagnostics should return empty list when no diagnostics."""
        trigger = PollingTrigger()
        result = trigger.drain_diagnostics()
        assert result == []

    def test_drain_diagnostics_clears_list(self):
        """drain_diagnostics should clear the internal list."""
        trigger = PollingTrigger()
        trigger._append_diagnostic(
            accepted=False,
            reason="test",
        )
        assert len(trigger.drain_diagnostics()) == 1
        assert len(trigger.drain_diagnostics()) == 0

    def test_append_diagnostic_accepted(self):
        """Appending accepted diagnostic should include all fields."""
        trigger = PollingTrigger()
        trigger._append_diagnostic(
            accepted=True,
            reason="accepted",
            response_bytes=32768,
            total_readings=32,
            outbound_readings=8,
            inbound_readings=24,
            peak_outbound_mph=155.3,
            peak_inbound_mph=45.0,
            all_outbound_speeds=[155.3, 140.2],
            all_inbound_speeds=[45.0],
        )

        diagnostics = trigger.drain_diagnostics()
        assert len(diagnostics) == 1

        diag = diagnostics[0]
        assert diag["accepted"] is True
        assert diag["reason"] == "accepted"
        assert diag["response_bytes"] == 32768
        assert diag["total_readings"] == 32
        assert diag["outbound_readings"] == 8
        assert diag["peak_outbound_mph"] == 155.3
        assert len(diag["all_outbound_speeds"]) == 2
        assert "timestamp" in diag

    def test_append_diagnostic_rejected(self):
        """Appending rejected diagnostic should include reason."""
        trigger = ThresholdTrigger()
        trigger._append_diagnostic(
            accepted=False,
            reason="no_outbound_speed",
            total_readings=12,
            outbound_readings=0,
            inbound_readings=12,
            peak_inbound_mph=42.1,
        )

        diagnostics = trigger.drain_diagnostics()
        assert len(diagnostics) == 1
        assert diagnostics[0]["accepted"] is False
        assert diagnostics[0]["reason"] == "no_outbound_speed"
        assert diagnostics[0]["peak_inbound_mph"] == 42.1

    def test_multiple_diagnostics_accumulate(self):
        """Multiple diagnostic entries should accumulate."""
        trigger = PollingTrigger()
        trigger._append_diagnostic(accepted=False, reason="no_response")
        trigger._append_diagnostic(accepted=False, reason="parse_failed")
        trigger._append_diagnostic(accepted=True, reason="accepted")

        diagnostics = trigger.drain_diagnostics()
        assert len(diagnostics) == 3
        assert diagnostics[0]["reason"] == "no_response"
        assert diagnostics[1]["reason"] == "parse_failed"
        assert diagnostics[2]["reason"] == "accepted"

    def test_default_empty_speed_lists(self):
        """Speed lists should default to empty when not provided."""
        trigger = ManualTrigger()
        trigger._append_diagnostic(accepted=False, reason="timeout")

        diagnostics = trigger.drain_diagnostics()
        assert diagnostics[0]["all_outbound_speeds"] == []
        assert diagnostics[0]["all_inbound_speeds"] == []

    def test_all_trigger_types_have_diagnostics(self):
        """All trigger types should support diagnostics via base class."""
        triggers = [
            PollingTrigger(),
            ThresholdTrigger(),
            ManualTrigger(),
        ]
        for trigger in triggers:
            trigger._append_diagnostic(accepted=False, reason="test")
            assert len(trigger.drain_diagnostics()) == 1

    def test_diagnostic_includes_magnitude_fields(self):
        """Diagnostics should include peak magnitude fields."""
        trigger = PollingTrigger()
        trigger._append_diagnostic(
            accepted=True,
            reason="accepted",
            peak_outbound_magnitude=245.5,
            peak_inbound_magnitude=180.3,
        )
        diagnostics = trigger.drain_diagnostics()
        assert diagnostics[0]["peak_outbound_magnitude"] == 245.5
        assert diagnostics[0]["peak_inbound_magnitude"] == 180.3

    def test_diagnostic_magnitude_defaults_to_zero(self):
        """Magnitude fields should default to 0 when not provided."""
        trigger = PollingTrigger()
        trigger._append_diagnostic(accepted=False, reason="test")
        diagnostics = trigger.drain_diagnostics()
        assert diagnostics[0]["peak_outbound_magnitude"] == 0.0
        assert diagnostics[0]["peak_inbound_magnitude"] == 0.0


# =============================================================================
# Tests for FFT Dual-Peak Extraction and DC Mask
# =============================================================================

class TestDualPeakExtraction:
    """Tests for dual-peak FFT processing and DC mask."""

    @pytest.fixture
    def processor(self):
        """Create a processor instance for testing."""
        return RollingBufferProcessor()

    def test_dc_mask_bins_constant(self, processor):
        """DC_MASK_BINS should be 150 (~15 mph exclusion zone)."""
        assert processor.DC_MASK_BINS == 150

    def test_both_peaks_extracted_from_block(self, processor):
        """A signal with outbound + inbound tones should produce two peaks."""
        import numpy as np

        n = processor.WINDOW_SIZE
        t = np.arange(n) / processor.SAMPLE_RATE

        # Outbound tone at ~120 mph
        # speed = freq * wavelength / 2 => freq = speed / (wavelength/2)
        # freq = 120 / 2.23694 (m/s) * 2 / 0.01243 = ~8630 Hz
        outbound_freq = (120 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M
        # Inbound tone at ~50 mph
        inbound_freq = (50 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M

        # Outbound = positive frequency, Inbound = negative frequency
        # I + jQ: positive freq => I=cos, Q=sin; negative freq => I=cos, Q=-sin
        i_signal = (
            500 * np.cos(2 * np.pi * outbound_freq * t)
            + 400 * np.cos(2 * np.pi * inbound_freq * t)
        )
        q_signal = (
            500 * np.sin(2 * np.pi * outbound_freq * t)
            - 400 * np.sin(2 * np.pi * inbound_freq * t)
        )

        # Offset to simulate ADC midpoint
        i_block = (i_signal + 2048).astype(np.float64)
        q_block = (q_signal + 2048).astype(np.float64)

        results = processor._process_block(i_block, q_block)

        # Should find both peaks
        directions = [r[2] for r in results]
        assert "outbound" in directions, f"Expected outbound peak, got: {results}"
        assert "inbound" in directions, f"Expected inbound peak, got: {results}"

        # Check speeds are approximately correct
        for speed, mag, direction in results:
            if direction == "outbound":
                assert abs(speed - 120) < 5, f"Outbound speed {speed} not near 120 mph"
            elif direction == "inbound":
                assert abs(speed - 50) < 5, f"Inbound speed {speed} not near 50 mph"

    def test_dc_leakage_does_not_mask_real_signal(self, processor):
        """Strong DC offset should not prevent detection of real Doppler signal."""
        import numpy as np

        n = processor.WINDOW_SIZE
        t = np.arange(n) / processor.SAMPLE_RATE

        # Real outbound Doppler at ~80 mph
        real_freq = (80 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M

        # Strong DC component (large offset that won't be fully removed by mean subtraction
        # due to windowing artifacts) plus real signal
        i_signal = 2048 + 300 * np.cos(2 * np.pi * real_freq * t)
        q_signal = 2048 + 300 * np.sin(2 * np.pi * real_freq * t)

        i_block = i_signal.astype(np.float64)
        q_block = q_signal.astype(np.float64)

        results = processor._process_block(i_block, q_block)

        # Should find the real signal, not a DC artifact
        outbound_results = [(s, m, d) for s, m, d in results if d == "outbound"]
        assert len(outbound_results) > 0, f"No outbound peak found, results: {results}"

        # The detected speed should be near 80 mph, not near 0
        speed = outbound_results[0][0]
        assert speed > 10, f"Detected speed {speed} mph is too low (DC artifact?)"
        assert abs(speed - 80) < 5, f"Outbound speed {speed} not near 80 mph"

    def test_ball_found_when_backswing_stronger(self, processor):
        """Outbound ball should be found even when inbound backswing is stronger."""
        import numpy as np

        # Create full 4096-sample capture with strong inbound + weaker outbound
        n_samples = 4096
        t = np.arange(n_samples) / processor.SAMPLE_RATE

        # Strong inbound (backswing) at 50 mph, amplitude 800
        inbound_freq = (50 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M
        # Weaker outbound (ball) at 120 mph, amplitude 300
        outbound_freq = (120 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M

        i_signal = (
            300 * np.cos(2 * np.pi * outbound_freq * t)
            + 800 * np.cos(2 * np.pi * inbound_freq * t)
        )
        q_signal = (
            300 * np.sin(2 * np.pi * outbound_freq * t)
            - 800 * np.sin(2 * np.pi * inbound_freq * t)
        )

        i_samples = (i_signal + 2048).astype(int).tolist()
        q_samples = (q_signal + 2048).astype(int).tolist()

        capture = IQCapture(
            sample_time=0.136,
            trigger_time=0.0,
            i_samples=i_samples,
            q_samples=q_samples,
            timestamp=1234567890.0,
        )

        timeline = processor.process_standard(capture)

        # Should have outbound readings despite stronger inbound
        outbound = [r for r in timeline.readings if r.is_outbound]
        assert len(outbound) > 0, (
            f"No outbound readings found. Total readings: {len(timeline.readings)}, "
            f"directions: {[r.direction for r in timeline.readings]}"
        )

        # Peak outbound should be near 120 mph
        peak_outbound = max(r.speed_mph for r in outbound)
        assert peak_outbound > 100, f"Peak outbound {peak_outbound} mph too low"
