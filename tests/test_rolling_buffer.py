"""Tests for rolling_buffer module."""

import math
import pytest
import numpy as np
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
        # Use a Doppler frequency above DC_MASK_BINS (150 bins ≈ 15 mph).
        # 1500 Hz → bin ~205 → ~20.9 mph, safely above the mask.
        # I=sin, Q=cos produces a negative-frequency (inbound) tone.
        doppler_freq = 1500  # Hz - corresponds to ~20.9 mph
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
        doppler_freq = 1500  # Hz - ~20.9 mph, above DC mask
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

    def test_two_outbound_peaks_extracted(self, processor):
        """Two outbound signals (club+ball) should both be extracted."""
        import numpy as np

        n = processor.WINDOW_SIZE
        t = np.arange(n) / processor.SAMPLE_RATE

        # Club at ~40 mph, Ball at ~120 mph — both outbound (positive freq)
        club_freq = (40 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M
        ball_freq = (120 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M

        i_signal = (
            400 * np.cos(2 * np.pi * club_freq * t)
            + 300 * np.cos(2 * np.pi * ball_freq * t)
        )
        q_signal = (
            400 * np.sin(2 * np.pi * club_freq * t)
            + 300 * np.sin(2 * np.pi * ball_freq * t)
        )

        i_block = (i_signal + 2048).astype(np.float64)
        q_block = (q_signal + 2048).astype(np.float64)

        results = processor._process_block(i_block, q_block)

        outbound = [(s, m, d) for s, m, d in results if d == "outbound"]
        assert len(outbound) >= 2, f"Expected 2+ outbound peaks, got {len(outbound)}: {results}"

        speeds = sorted([s for s, m, d in outbound])
        assert any(abs(s - 40) < 5 for s in speeds), f"No peak near 40 mph: {speeds}"
        assert any(abs(s - 120) < 5 for s in speeds), f"No peak near 120 mph: {speeds}"

    def test_single_outbound_peak_no_regression(self, processor):
        """Single outbound signal should still work correctly."""
        import numpy as np

        n = processor.WINDOW_SIZE
        t = np.arange(n) / processor.SAMPLE_RATE

        outbound_freq = (80 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M
        i_signal = 500 * np.cos(2 * np.pi * outbound_freq * t)
        q_signal = 500 * np.sin(2 * np.pi * outbound_freq * t)

        i_block = (i_signal + 2048).astype(np.float64)
        q_block = (q_signal + 2048).astype(np.float64)

        results = processor._process_block(i_block, q_block)

        outbound = [(s, m, d) for s, m, d in results if d == "outbound"]
        assert len(outbound) >= 1
        assert abs(outbound[0][0] - 80) < 5

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


# =============================================================================
# Tests for _find_peaks
# =============================================================================

class TestFindPeaks:
    """Tests for the _find_peaks local maxima finder."""

    @pytest.fixture
    def processor(self):
        return RollingBufferProcessor()

    def test_single_peak(self, processor):
        """Single peak above threshold should be found."""
        import numpy as np

        magnitude = np.zeros(2048)
        magnitude[500] = 100.0  # Clear peak
        magnitude[499] = 20.0   # Neighbors lower
        magnitude[501] = 20.0

        peaks = processor._find_peaks(magnitude, start=1, end=2048)
        assert len(peaks) >= 1
        assert peaks[0][0] == 500
        assert peaks[0][1] == 100.0

    def test_two_separated_peaks(self, processor):
        """Two well-separated peaks should both be found."""
        import numpy as np

        magnitude = np.zeros(2048)
        # Peak 1
        magnitude[300] = 80.0
        magnitude[299] = 10.0
        magnitude[301] = 10.0
        # Peak 2 — well separated (>50 bins apart)
        magnitude[600] = 120.0
        magnitude[599] = 10.0
        magnitude[601] = 10.0

        peaks = processor._find_peaks(magnitude, start=1, end=2048)
        assert len(peaks) >= 2
        bins = [p[0] for p in peaks]
        assert 300 in bins
        assert 600 in bins

    def test_close_peaks_merged(self, processor):
        """Two peaks within MIN_PEAK_SEPARATION_BINS should keep only the stronger."""
        import numpy as np

        magnitude = np.zeros(2048)
        # Peak 1 — weaker
        magnitude[300] = 50.0
        magnitude[299] = 10.0
        magnitude[301] = 10.0
        # Peak 2 — stronger, only 20 bins away (< 50)
        magnitude[320] = 80.0
        magnitude[319] = 10.0
        magnitude[321] = 10.0

        peaks = processor._find_peaks(magnitude, start=1, end=2048)
        # Should only keep the stronger peak at 320
        assert len(peaks) == 1
        assert peaks[0][0] == 320

    def test_below_threshold_rejected(self, processor):
        """Peaks below MAGNITUDE_THRESHOLD should be rejected."""
        import numpy as np

        magnitude = np.zeros(2048)
        magnitude[500] = 1.0  # Below threshold (3)
        magnitude[499] = 0.5
        magnitude[501] = 0.5

        peaks = processor._find_peaks(magnitude, start=1, end=2048)
        assert len(peaks) == 0

    def test_max_peaks_cap(self, processor):
        """Should return at most MAX_PEAKS_PER_DIRECTION peaks."""
        import numpy as np

        magnitude = np.zeros(2048)
        # Create 5 well-separated peaks
        for i, pos in enumerate([200, 400, 600, 800, 1000]):
            magnitude[pos] = 100.0 + i * 10
            magnitude[pos - 1] = 5.0
            magnitude[pos + 1] = 5.0

        peaks = processor._find_peaks(magnitude, start=1, end=2048)
        assert len(peaks) <= processor.MAX_PEAKS_PER_DIRECTION

    def test_flat_region_no_peaks(self, processor):
        """Flat constant signal should produce no peaks."""
        import numpy as np

        magnitude = np.ones(2048) * 50.0  # Flat — no local maxima

        peaks = processor._find_peaks(magnitude, start=1, end=2048)
        assert len(peaks) == 0

    def test_sorted_by_magnitude_descending(self, processor):
        """Returned peaks should be sorted by magnitude descending."""
        import numpy as np

        magnitude = np.zeros(2048)
        magnitude[200] = 50.0
        magnitude[199] = 5.0
        magnitude[201] = 5.0
        magnitude[400] = 100.0
        magnitude[399] = 5.0
        magnitude[401] = 5.0
        magnitude[600] = 75.0
        magnitude[599] = 5.0
        magnitude[601] = 5.0

        peaks = processor._find_peaks(magnitude, start=1, end=2048)
        mags = [p[1] for p in peaks]
        assert mags == sorted(mags, reverse=True)


# =============================================================================
# Tests for find_club_speed with concurrent readings
# =============================================================================

class TestFindClubSpeedOverlap:
    """Tests for find_club_speed searching concurrent timestamps."""

    @pytest.fixture
    def processor(self):
        return RollingBufferProcessor()

    def test_club_at_same_timestamp_as_ball(self, processor):
        """Club reading at the same timestamp as ball should be found."""
        readings = [
            SpeedReading(speed_mph=60.0, magnitude=200.0, timestamp_ms=10.0, direction="outbound"),
            SpeedReading(speed_mph=80.0, magnitude=300.0, timestamp_ms=10.0, direction="outbound"),
        ]
        timeline = SpeedTimeline(readings=readings, sample_rate_hz=937.5)

        club_speed, club_ts = processor.find_club_speed(
            timeline, ball_speed_mph=80.0, ball_timestamp_ms=10.0
        )

        assert club_speed == 60.0
        assert club_ts == 10.0

    def test_club_before_ball_still_works(self, processor):
        """Club at earlier timestamp should still be found."""
        readings = [
            SpeedReading(speed_mph=58.0, magnitude=200.0, timestamp_ms=5.0, direction="outbound"),
            SpeedReading(speed_mph=80.0, magnitude=300.0, timestamp_ms=10.0, direction="outbound"),
        ]
        timeline = SpeedTimeline(readings=readings, sample_rate_hz=937.5)

        club_speed, club_ts = processor.find_club_speed(
            timeline, ball_speed_mph=80.0, ball_timestamp_ms=10.0
        )

        assert club_speed == 58.0
        assert club_ts == 5.0

    def test_ball_not_returned_as_club(self, processor):
        """Ball reading itself should not be returned as club speed."""
        readings = [
            SpeedReading(speed_mph=80.0, magnitude=300.0, timestamp_ms=10.0, direction="outbound"),
        ]
        timeline = SpeedTimeline(readings=readings, sample_rate_hz=937.5)

        club_speed, club_ts = processor.find_club_speed(
            timeline, ball_speed_mph=80.0, ball_timestamp_ms=10.0
        )

        assert club_speed is None
        assert club_ts is None

    def test_speed_range_filtering(self, processor):
        """Only speeds within 67-85% of ball speed should be candidates."""
        readings = [
            # Too slow (< 67% of 100)
            SpeedReading(speed_mph=60.0, magnitude=200.0, timestamp_ms=10.0, direction="outbound"),
            # Too fast (> 85% of 100)
            SpeedReading(speed_mph=90.0, magnitude=200.0, timestamp_ms=10.0, direction="outbound"),
            # Just right (75% of 100)
            SpeedReading(speed_mph=75.0, magnitude=200.0, timestamp_ms=10.0, direction="outbound"),
            # Ball
            SpeedReading(speed_mph=100.0, magnitude=400.0, timestamp_ms=10.0, direction="outbound"),
        ]
        timeline = SpeedTimeline(readings=readings, sample_rate_hz=937.5)

        club_speed, _ = processor.find_club_speed(
            timeline, ball_speed_mph=100.0, ball_timestamp_ms=10.0
        )

        assert club_speed == 75.0

    def test_highest_magnitude_selected(self, processor):
        """Among valid candidates, highest magnitude should win."""
        readings = [
            SpeedReading(speed_mph=70.0, magnitude=100.0, timestamp_ms=10.0, direction="outbound"),
            SpeedReading(speed_mph=75.0, magnitude=250.0, timestamp_ms=10.0, direction="outbound"),
            SpeedReading(speed_mph=100.0, magnitude=400.0, timestamp_ms=10.0, direction="outbound"),
        ]
        timeline = SpeedTimeline(readings=readings, sample_rate_hz=937.5)

        club_speed, _ = processor.find_club_speed(
            timeline, ball_speed_mph=100.0, ball_timestamp_ms=10.0
        )

        assert club_speed == 75.0  # Higher magnitude


# =============================================================================
# Tests for Multi-Peak Integration (end-to-end)
# =============================================================================

class TestMultiPeakIntegration:
    """End-to-end test: process_capture with synthetic club+ball I/Q."""

    @pytest.fixture
    def processor(self):
        return RollingBufferProcessor()

    def test_process_capture_finds_club_and_ball(self, processor):
        """process_capture should find both club and ball from dual-tone I/Q."""
        import numpy as np

        n_samples = 4096
        t = np.arange(n_samples) / processor.SAMPLE_RATE

        # Club at ~60 mph (outbound), Ball at ~80 mph (outbound)
        club_freq = (60 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M
        ball_freq = (80 / processor.MPS_TO_MPH) * 2 / processor.WAVELENGTH_M

        i_signal = (
            400 * np.cos(2 * np.pi * club_freq * t)
            + 300 * np.cos(2 * np.pi * ball_freq * t)
        )
        q_signal = (
            400 * np.sin(2 * np.pi * club_freq * t)
            + 300 * np.sin(2 * np.pi * ball_freq * t)
        )

        i_samples = (i_signal + 2048).astype(int).tolist()
        q_samples = (q_signal + 2048).astype(int).tolist()

        capture = IQCapture(
            sample_time=0.0,
            trigger_time=0.0,
            i_samples=i_samples,
            q_samples=q_samples,
            timestamp=1234567890.0,
        )

        result = processor.process_capture(capture)

        assert result is not None
        assert abs(result.ball_speed_mph - 80) < 5, (
            f"Ball speed {result.ball_speed_mph} not near 80 mph"
        )
        assert result.club_speed_mph is not None, "Club speed not detected"
        assert abs(result.club_speed_mph - 60) < 5, (
            f"Club speed {result.club_speed_mph} not near 60 mph"
        )


# =============================================================================
# Tests for extract_ball_speeds (spin detection fix)
# =============================================================================

class TestExtractBallSpeeds:
    """Tests for the updated extract_ball_speeds using ball position instead of trigger offset."""

    def _make_timeline(self, readings):
        """Helper to create a SpeedTimeline from a list of reading tuples."""
        speed_readings = [
            SpeedReading(
                speed_mph=speed,
                magnitude=mag,
                timestamp_ms=ts,
                direction=direction,
            )
            for speed, mag, ts, direction in readings
        ]
        return SpeedTimeline(readings=speed_readings, sample_rate_hz=937.5)

    def test_finds_ball_readings_at_ball_timestamp(self):
        """Ball readings at ball_timestamp_ms are included."""
        timeline = self._make_timeline([
            # Ball signal at t=10-60ms
            (75.0, 10.0, 10.0, "outbound"),
            (74.5, 9.0, 20.0, "outbound"),
            (75.2, 8.0, 30.0, "outbound"),
            (74.8, 7.0, 40.0, "outbound"),
            (75.1, 6.0, 50.0, "outbound"),
            # Club signal earlier
            (55.0, 15.0, 0.0, "outbound"),
            # Inbound noise
            (30.0, 5.0, 25.0, "inbound"),
        ])
        processor = RollingBufferProcessor()
        speeds = processor.extract_ball_speeds(
            timeline, ball_timestamp_ms=10.0, ball_speed_mph=75.0
        )
        assert len(speeds) == 5
        assert all(70 <= s <= 80 for s in speeds)

    def test_filters_by_speed_band(self):
        """Only readings within speed tolerance of ball_speed_mph are included."""
        timeline = self._make_timeline([
            (75.0, 10.0, 10.0, "outbound"),  # In band
            (74.0, 9.0, 20.0, "outbound"),   # In band
            (55.0, 15.0, 15.0, "outbound"),  # Out of band (club speed)
            (90.0, 5.0, 25.0, "outbound"),   # Out of band (too fast)
        ])
        processor = RollingBufferProcessor()
        speeds = processor.extract_ball_speeds(
            timeline, ball_timestamp_ms=10.0, ball_speed_mph=75.0,
            speed_tolerance_mph=5.0,
        )
        assert len(speeds) == 2
        assert 55.0 not in speeds
        assert 90.0 not in speeds

    def test_respects_window(self):
        """Only readings within window_ms after ball_timestamp_ms are included."""
        timeline = self._make_timeline([
            (75.0, 10.0, 10.0, "outbound"),
            (74.5, 9.0, 30.0, "outbound"),
            (75.2, 8.0, 50.0, "outbound"),
            (74.8, 7.0, 80.0, "outbound"),  # Outside 50ms window
            (75.1, 6.0, 100.0, "outbound"),  # Outside 50ms window
        ])
        processor = RollingBufferProcessor()
        speeds = processor.extract_ball_speeds(
            timeline, ball_timestamp_ms=10.0, ball_speed_mph=75.0,
            window_ms=50,
        )
        assert len(speeds) == 3

    def test_excludes_inbound_readings(self):
        """Inbound readings are always excluded."""
        timeline = self._make_timeline([
            (75.0, 10.0, 10.0, "outbound"),
            (74.0, 9.0, 20.0, "inbound"),   # Same speed band but inbound
        ])
        processor = RollingBufferProcessor()
        speeds = processor.extract_ball_speeds(
            timeline, ball_timestamp_ms=10.0, ball_speed_mph=75.0,
        )
        assert len(speeds) == 1

    def test_excludes_readings_before_ball_timestamp(self):
        """Readings before ball_timestamp_ms are excluded."""
        timeline = self._make_timeline([
            (75.0, 10.0, 0.0, "outbound"),   # Before ball_timestamp
            (74.5, 9.0, 5.0, "outbound"),    # Before ball_timestamp
            (75.2, 8.0, 10.0, "outbound"),   # At ball_timestamp (included)
            (74.8, 7.0, 20.0, "outbound"),   # After (included)
        ])
        processor = RollingBufferProcessor()
        speeds = processor.extract_ball_speeds(
            timeline, ball_timestamp_ms=10.0, ball_speed_mph=75.0,
        )
        assert len(speeds) == 2

    def test_empty_timeline_returns_empty(self):
        """Empty timeline returns empty list."""
        timeline = self._make_timeline([])
        processor = RollingBufferProcessor()
        speeds = processor.extract_ball_speeds(
            timeline, ball_timestamp_ms=10.0, ball_speed_mph=75.0,
        )
        assert speeds == []

    def test_custom_speed_tolerance(self):
        """Custom speed_tolerance_mph is respected."""
        timeline = self._make_timeline([
            (75.0, 10.0, 10.0, "outbound"),
            (72.0, 9.0, 20.0, "outbound"),  # Within ±5 but not ±2
            (74.0, 8.0, 30.0, "outbound"),  # Within ±2
        ])
        processor = RollingBufferProcessor()
        speeds = processor.extract_ball_speeds(
            timeline, ball_timestamp_ms=10.0, ball_speed_mph=75.0,
            speed_tolerance_mph=2.0,
        )
        assert len(speeds) == 2  # 75.0 and 74.0 only
        assert 72.0 not in speeds


class TestSpinDetectionIntegration:
    """End-to-end spin detection tests using synthetic I/Q with speed oscillations."""

    def _make_iq_with_seam_modulation(
        self,
        base_speed_mph: float,
        spin_rpm: float,
        modulation_depth: float = 0.03,
        sample_rate: int = 30000,
        num_samples: int = 4096,
    ):
        """Generate synthetic I/Q with amplitude modulation at 1x spin rate.

        The golf ball seam is a single great circle that crosses the radar beam
        once per revolution, creating amplitude modulation at the spin frequency.
        """
        wavelength = 0.01243
        speed_mps = base_speed_mph / 2.23694
        doppler_hz = 2 * speed_mps / wavelength
        seam_hz = spin_rpm / 60.0

        t = np.arange(num_samples) / sample_rate
        phase = 2 * np.pi * doppler_hz * t

        amplitude = 200 * (1.0 + modulation_depth * np.sin(2 * np.pi * seam_hz * t))

        i_samples = (amplitude * np.cos(phase) + 2048).astype(int).clip(0, 4095).tolist()
        q_samples = (amplitude * np.sin(phase) + 2048).astype(int).clip(0, 4095).tolist()

        return i_samples, q_samples

    def test_spin_detected_7iron(self):
        """7-iron at 7000 RPM should be reliably detected."""
        i_samples, q_samples = self._make_iq_with_seam_modulation(
            base_speed_mph=120, spin_rpm=7000, modulation_depth=0.03,
        )
        capture = IQCapture(
            sample_time=0.0, trigger_time=0.068,
            i_samples=i_samples, q_samples=q_samples,
        )
        processor = RollingBufferProcessor()
        result = processor.process_capture(capture)
        assert result is not None
        assert result.spin is not None
        assert result.spin.spin_rpm > 0, f"Should detect spin, got quality={result.spin.quality}"
        assert abs(result.spin.spin_rpm - 7000) < 500, f"Expected ~7000, got {result.spin.spin_rpm}"

    def test_spin_detected_driver(self):
        """Driver at 3000 RPM should still be detectable.

        At 160 mph the ball's Doppler is near the top of the FFT window, so
        process_capture finds the ball late in the synthetic capture. We call
        detect_spin directly with an explicit ball timestamp to exercise
        the spin algorithm independent of the speed timeline.
        """
        i_samples, q_samples = self._make_iq_with_seam_modulation(
            base_speed_mph=160, spin_rpm=3000, modulation_depth=0.03,
        )
        capture = IQCapture(
            sample_time=0.0, trigger_time=0.068,
            i_samples=i_samples, q_samples=q_samples,
        )
        processor = RollingBufferProcessor()
        result = processor.detect_spin(capture, ball_speed_mph=160, ball_timestamp_ms=5.0)
        assert result.spin_rpm > 0, f"Should detect spin, got quality={result.quality}"
        assert abs(result.spin_rpm - 3000) < 500, f"Expected ~3000, got {result.spin_rpm}"

    def test_spin_detected_wedge(self):
        """Wedge at 10000 RPM."""
        i_samples, q_samples = self._make_iq_with_seam_modulation(
            base_speed_mph=90, spin_rpm=10000, modulation_depth=0.05,
        )
        capture = IQCapture(
            sample_time=0.0, trigger_time=0.068,
            i_samples=i_samples, q_samples=q_samples,
        )
        processor = RollingBufferProcessor()
        result = processor.process_capture(capture)
        assert result is not None
        assert result.spin is not None
        assert result.spin.spin_rpm > 0
        assert abs(result.spin.spin_rpm - 10000) < 500

    def test_no_spin_with_constant_amplitude(self):
        """Constant amplitude should yield no spin."""
        sample_rate = 30000
        num_samples = 4096
        speed_mph = 150
        wavelength = 0.01243
        speed_mps = speed_mph / 2.23694
        freq = 2 * speed_mps / wavelength

        t = np.arange(num_samples) / sample_rate
        phase = 2 * np.pi * freq * t

        i_samples = (200 * np.cos(phase) + 2048).astype(int).clip(0, 4095).tolist()
        q_samples = (200 * np.sin(phase) + 2048).astype(int).clip(0, 4095).tolist()

        capture = IQCapture(
            sample_time=0.0, trigger_time=0.068,
            i_samples=i_samples, q_samples=q_samples,
        )
        processor = RollingBufferProcessor()
        result = processor.process_capture(capture)
        assert result is not None
        assert result.spin is not None
        assert result.spin.spin_rpm == 0 or result.spin.quality not in ("high", "medium"), \
            f"Unexpected spin: {result.spin.spin_rpm} RPM, quality={result.spin.quality}"

    def test_spin_result_is_populated(self):
        """process_capture should always populate the spin field."""
        i_samples, q_samples = self._make_iq_with_seam_modulation(
            base_speed_mph=130, spin_rpm=5000,
        )
        capture = IQCapture(
            sample_time=0.0, trigger_time=0.068,
            i_samples=i_samples, q_samples=q_samples,
        )
        processor = RollingBufferProcessor()
        result = processor.process_capture(capture)
        assert result is not None
        assert result.spin is not None
