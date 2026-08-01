"""Tests for rolling_buffer trigger strategies."""

import time
from unittest.mock import MagicMock

import pytest

from openflight.rolling_buffer import (
    IQCapture,
    ManualTrigger,
    PollingTrigger,
    SpeedReading,
    SpeedTimeline,
    ThresholdTrigger,
)
from openflight.rolling_buffer.trigger import (
    SoundTrigger,
    SpeedTriggeredCapture,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_capture(**kwargs):
    defaults = dict(
        sample_time=100.0,
        trigger_time=100.068,
        i_samples=[2048] * 4096,
        q_samples=[2048] * 4096,
    )
    defaults.update(kwargs)
    return IQCapture(**defaults)


def _make_timeline(speed_mph=130.0, direction="outbound"):
    return SpeedTimeline(
        readings=[
            SpeedReading(
                speed_mph=speed_mph,
                magnitude=1000.0,
                timestamp_ms=68.0,
                direction=direction,
            )
        ],
        sample_rate_hz=937.5,
    )


def _make_radar_mock(response="data", capture=None, timeline=None):
    radar = MagicMock()
    radar.trigger_capture.return_value = response
    return radar


def _make_processor_mock(capture=None, timeline=None):
    processor = MagicMock()
    processor.parse_capture.return_value = capture or _make_capture()
    processor.process_standard.return_value = timeline or _make_timeline()
    return processor


# ---------------------------------------------------------------------------
# TriggerStrategy base (tested via ManualTrigger)
# ---------------------------------------------------------------------------


class TestDrainDiagnostics:
    def test_returns_empty_list_when_no_diagnostics(self):
        trigger = ManualTrigger()
        assert trigger.drain_diagnostics() == []

    def test_returns_and_clears_diagnostics(self):
        trigger = ManualTrigger()
        trigger._append_diagnostic(accepted=True, reason="accepted")
        diags = trigger.drain_diagnostics()
        assert len(diags) == 1
        assert diags[0]["accepted"] is True
        assert diags[0]["reason"] == "accepted"
        # Should be cleared now
        assert trigger.drain_diagnostics() == []

    def test_append_diagnostic_includes_all_fields(self):
        trigger = ManualTrigger()
        trigger._append_diagnostic(
            accepted=False,
            reason="no_response",
            response_bytes=0,
            total_readings=5,
            outbound_readings=2,
            inbound_readings=3,
            peak_outbound_mph=45.0,
            peak_inbound_mph=20.0,
            all_outbound_speeds=[45.0, 30.0],
            all_inbound_speeds=[20.0],
            peak_outbound_magnitude=0.8,
            peak_inbound_magnitude=0.3,
            trigger_latency_ms=12.5,
        )
        diag = trigger.drain_diagnostics()[0]
        assert diag["response_bytes"] == 0
        assert diag["total_readings"] == 5
        assert diag["peak_outbound_mph"] == 45.0
        assert diag["trigger_latency_ms"] == 12.5

    def test_append_diagnostic_omits_latency_when_none(self):
        trigger = ManualTrigger()
        trigger._append_diagnostic(accepted=True, reason="accepted", trigger_latency_ms=None)
        diag = trigger.drain_diagnostics()[0]
        assert "trigger_latency_ms" not in diag

    def test_all_outbound_speeds_defaults_to_empty_list(self):
        trigger = ManualTrigger()
        trigger._append_diagnostic(accepted=False, reason="test")
        diag = trigger.drain_diagnostics()[0]
        assert diag["all_outbound_speeds"] == []
        assert diag["all_inbound_speeds"] == []


# ---------------------------------------------------------------------------
# ManualTrigger
# ---------------------------------------------------------------------------


class TestManualTrigger:
    def test_request_trigger_sets_flag(self):
        trigger = ManualTrigger()
        assert not trigger._trigger_requested
        trigger.request_trigger()
        assert trigger._trigger_requested

    def test_reset_clears_flag(self):
        trigger = ManualTrigger()
        trigger.request_trigger()
        trigger.reset()
        assert not trigger._trigger_requested

    def test_wait_for_trigger_fires_immediately_when_pre_requested(self):
        trigger = ManualTrigger()
        capture = _make_capture()
        radar = _make_radar_mock()
        processor = _make_processor_mock(capture=capture)

        trigger.request_trigger()
        result = trigger.wait_for_trigger(radar, processor, timeout=5.0)

        assert result is capture
        radar.trigger_capture.assert_called_once()
        radar.rearm_rolling_buffer.assert_called_once_with(12)

    def test_wait_for_trigger_returns_none_on_timeout(self):
        trigger = ManualTrigger()
        radar = _make_radar_mock()
        processor = _make_processor_mock()

        result = trigger.wait_for_trigger(radar, processor, timeout=0.05)

        assert result is None

    def test_wait_for_trigger_clears_flag_after_fire(self):
        trigger = ManualTrigger()
        radar = _make_radar_mock()
        processor = _make_processor_mock()

        trigger.request_trigger()
        trigger.wait_for_trigger(radar, processor, timeout=1.0)

        assert not trigger._trigger_requested

    def test_custom_pre_trigger_segments(self):
        trigger = ManualTrigger(pre_trigger_segments=20)
        capture = _make_capture()
        radar = _make_radar_mock()
        processor = _make_processor_mock(capture=capture)

        trigger.request_trigger()
        trigger.wait_for_trigger(radar, processor, timeout=1.0)

        radar.rearm_rolling_buffer.assert_called_once_with(20)


# ---------------------------------------------------------------------------
# PollingTrigger
# ---------------------------------------------------------------------------


class TestPollingTrigger:
    def test_default_params(self):
        trigger = PollingTrigger()
        assert trigger.poll_interval == 0.3
        assert trigger.min_readings == 1
        assert trigger.min_speed_mph == 15

    def test_custom_params(self):
        trigger = PollingTrigger(poll_interval=0.1, min_readings=2, min_speed_mph=30)
        assert trigger.poll_interval == 0.1
        assert trigger.min_readings == 2
        assert trigger.min_speed_mph == 30

    def test_reset_is_noop(self):
        trigger = PollingTrigger()
        trigger.reset()  # should not raise

    def test_wait_for_trigger_returns_capture_with_activity(self):
        trigger = PollingTrigger(poll_interval=0.0)
        capture = _make_capture()
        radar = _make_radar_mock()
        processor = _make_processor_mock(
            capture=capture,
            timeline=_make_timeline(speed_mph=130.0, direction="outbound"),
        )

        result = trigger.wait_for_trigger(radar, processor, timeout=5.0)

        assert result is capture

    def test_wait_for_trigger_skips_slow_captures(self):
        trigger = PollingTrigger(poll_interval=0.0, min_speed_mph=50)
        capture = _make_capture()
        radar = _make_radar_mock()

        # First call returns slow speed, second returns fast
        slow_timeline = _make_timeline(speed_mph=20.0, direction="outbound")
        fast_timeline = _make_timeline(speed_mph=130.0, direction="outbound")
        processor = MagicMock()
        processor.parse_capture.return_value = capture
        processor.process_standard.side_effect = [slow_timeline, fast_timeline]

        result = trigger.wait_for_trigger(radar, processor, timeout=5.0)

        assert result is capture
        assert processor.process_standard.call_count == 2

    def test_wait_for_trigger_returns_none_on_timeout(self):
        trigger = PollingTrigger(poll_interval=0.0, min_speed_mph=200)
        radar = _make_radar_mock()
        processor = _make_processor_mock(
            timeline=_make_timeline(speed_mph=10.0, direction="outbound")
        )

        result = trigger.wait_for_trigger(radar, processor, timeout=0.05)

        assert result is None

    def test_wait_for_trigger_handles_none_capture(self):
        trigger = PollingTrigger(poll_interval=0.0)
        radar = _make_radar_mock()
        processor = MagicMock()
        processor.parse_capture.return_value = None

        result = trigger.wait_for_trigger(radar, processor, timeout=0.05)

        assert result is None

    def test_wait_for_trigger_handles_radar_exception(self):
        trigger = PollingTrigger(poll_interval=0.0)
        radar = MagicMock()
        radar.trigger_capture.side_effect = [Exception("serial error"), Exception("serial error")]
        processor = _make_processor_mock()

        result = trigger.wait_for_trigger(radar, processor, timeout=0.05)

        assert result is None


# ---------------------------------------------------------------------------
# ThresholdTrigger
# ---------------------------------------------------------------------------


class TestThresholdTrigger:
    def test_default_params(self):
        trigger = ThresholdTrigger()
        assert trigger.speed_threshold_mph == 50
        assert trigger.check_interval == 0.1
        assert trigger.settling_time == 0.05

    def test_reset_clears_triggered_state(self):
        trigger = ThresholdTrigger()
        trigger._triggered = True
        trigger.reset()
        assert not trigger._triggered

    def test_wait_for_trigger_returns_capture_above_threshold(self):
        trigger = ThresholdTrigger(speed_threshold_mph=50, settling_time=0.0)
        capture = _make_capture()
        radar = _make_radar_mock()
        processor = _make_processor_mock(
            capture=capture,
            timeline=_make_timeline(speed_mph=130.0, direction="outbound"),
        )

        result = trigger.wait_for_trigger(radar, processor, timeout=5.0)

        assert result is capture
        assert trigger._triggered

    def test_wait_for_trigger_ignores_inbound_readings(self):
        trigger = ThresholdTrigger(speed_threshold_mph=50, settling_time=0.0)
        capture = _make_capture()
        radar = _make_radar_mock()

        # First call inbound, second outbound
        inbound = _make_timeline(speed_mph=130.0, direction="inbound")
        outbound = _make_timeline(speed_mph=130.0, direction="outbound")
        processor = MagicMock()
        processor.parse_capture.return_value = capture
        processor.process_standard.side_effect = [inbound, outbound]

        result = trigger.wait_for_trigger(radar, processor, timeout=5.0)

        assert result is capture

    def test_wait_for_trigger_returns_none_on_timeout(self):
        trigger = ThresholdTrigger(speed_threshold_mph=200, check_interval=0.0)
        radar = _make_radar_mock()
        processor = _make_processor_mock(
            timeline=_make_timeline(speed_mph=50.0, direction="outbound")
        )

        result = trigger.wait_for_trigger(radar, processor, timeout=0.05)

        assert result is None

    def test_wait_for_trigger_handles_exception(self):
        trigger = ThresholdTrigger(check_interval=0.0)
        radar = MagicMock()
        radar.trigger_capture.side_effect = Exception("error")
        processor = _make_processor_mock()

        result = trigger.wait_for_trigger(radar, processor, timeout=0.05)

        assert result is None


# ---------------------------------------------------------------------------
# SpeedTriggeredCapture
# ---------------------------------------------------------------------------


class TestSpeedTriggeredCapture:
    def test_default_params(self):
        trigger = SpeedTriggeredCapture()
        assert trigger.min_trigger_speed_mph == 20.0
        assert trigger.min_ball_speed_mph == 35.0
        assert trigger.trigger_to_capture_delay_ms == 15.0
        assert trigger._needs_reconfigure is True
        assert trigger._last_trigger_speed == 0

    def test_custom_params(self):
        trigger = SpeedTriggeredCapture(
            min_trigger_speed_mph=25.0,
            min_ball_speed_mph=40.0,
            trigger_to_capture_delay_ms=20.0,
        )
        assert trigger.min_trigger_speed_mph == 25.0
        assert trigger.min_ball_speed_mph == 40.0
        assert trigger.trigger_to_capture_delay_ms == 20.0

    def test_reset_clears_state(self):
        trigger = SpeedTriggeredCapture()
        trigger._last_trigger_speed = 95.0
        trigger._needs_reconfigure = False
        trigger.reset()
        assert trigger._last_trigger_speed == 0
        assert trigger._needs_reconfigure is True

    def test_last_trigger_speed_property(self):
        trigger = SpeedTriggeredCapture()
        trigger._last_trigger_speed = 88.5
        assert trigger.last_trigger_speed == 88.5


# ---------------------------------------------------------------------------
# SoundTrigger clock sync helpers
# ---------------------------------------------------------------------------


class TestClockSyncLastReadHostTime:
    def test_returns_host_after_from_last_read(self):
        clock_sync = {"reads": [{"host_after": 12345.6, "host_mid": 12345.5}]}
        result = SoundTrigger._clock_sync_last_read_host_time(clock_sync)
        assert result == 12345.6

    def test_falls_back_to_host_mid(self):
        clock_sync = {"reads": [{"host_mid": 12345.5}]}
        result = SoundTrigger._clock_sync_last_read_host_time(clock_sync)
        assert result == 12345.5

    def test_returns_none_for_empty_reads(self):
        clock_sync = {"reads": []}
        assert SoundTrigger._clock_sync_last_read_host_time(clock_sync) is None

    def test_returns_none_when_no_reads_key(self):
        assert SoundTrigger._clock_sync_last_read_host_time({}) is None

    def test_returns_none_when_last_read_not_dict(self):
        clock_sync = {"reads": ["not_a_dict"]}
        assert SoundTrigger._clock_sync_last_read_host_time(clock_sync) is None


class TestClockSyncAgeS:
    def test_returns_age_in_seconds(self):
        now = time.time()
        clock_sync = {"reads": [{"host_after": now - 5.0}]}
        age = SoundTrigger._clock_sync_age_s(clock_sync)
        assert age == pytest.approx(5.0, abs=0.5)

    def test_returns_none_when_no_host_time(self):
        clock_sync = {"reads": []}
        assert SoundTrigger._clock_sync_age_s(clock_sync) is None


class TestClockSyncQuality:
    def _valid_integer_rollover_sync(self):
        return {
            "usable_for_trigger_timestamps": True,
            "best_offset_s": 12000.0,
            "clock_sync_method": "integer_rollover",
            "rollover_uncertainty_ms": 10.0,
            "reads": [],
        }

    def test_valid_integer_rollover(self):
        sync = self._valid_integer_rollover_sync()
        valid, reason = SoundTrigger._clock_sync_quality(sync)
        assert valid is True
        assert reason == "valid_integer_rollover"

    def test_valid_fractional_clock(self):
        sync = {
            "usable_for_trigger_timestamps": True,
            "best_offset_s": 12000.0,
            "clock_sync_method": "fractional_clock",
            "reads": [],
        }
        valid, reason = SoundTrigger._clock_sync_quality(sync)
        assert valid is True
        assert reason == "valid_fractional_clock"

    def test_invalid_not_dict(self):
        valid, reason = SoundTrigger._clock_sync_quality(None)
        assert valid is False
        assert reason == "missing"

    def test_invalid_not_usable(self):
        sync = {"usable_for_trigger_timestamps": False, "clock_sync_method": "integer_rollover"}
        valid, reason = SoundTrigger._clock_sync_quality(sync)
        assert valid is False
        assert "unusable_method" in reason

    def test_invalid_missing_best_offset(self):
        sync = {
            "usable_for_trigger_timestamps": True,
            "best_offset_s": None,
            "clock_sync_method": "integer_rollover",
            "reads": [],
        }
        valid, reason = SoundTrigger._clock_sync_quality(sync)
        assert valid is False
        assert reason == "missing_best_offset"

    def test_invalid_high_rollover_uncertainty(self):
        sync = self._valid_integer_rollover_sync()
        sync["rollover_uncertainty_ms"] = 100.0
        valid, reason = SoundTrigger._clock_sync_quality(sync)
        assert valid is False
        assert "rollover_uncertainty" in reason

    def test_invalid_missing_rollover_uncertainty(self):
        sync = self._valid_integer_rollover_sync()
        del sync["rollover_uncertainty_ms"]
        valid, reason = SoundTrigger._clock_sync_quality(sync)
        assert valid is False
        assert reason == "missing_rollover_uncertainty"

    def test_invalid_timeout_reads(self):
        sync = self._valid_integer_rollover_sync()
        sync["reads"] = [{"radar_clock_s": None, "read_latency_ms": 60.0}]
        valid, reason = SoundTrigger._clock_sync_quality(sync)
        assert valid is False
        assert "timeout_reads" in reason

    def test_unsupported_method(self):
        sync = {
            "usable_for_trigger_timestamps": True,
            "best_offset_s": 12000.0,
            "clock_sync_method": "unknown_method",
            "reads": [],
        }
        valid, reason = SoundTrigger._clock_sync_quality(sync)
        assert valid is False
        assert "unsupported_method" in reason


class TestClockSyncSummaryForLog:
    def test_returns_none_for_non_dict(self):
        assert SoundTrigger._clock_sync_summary_for_log(None) is None

    def test_returns_summary_dict(self):
        sync = {
            "usable_for_trigger_timestamps": True,
            "best_offset_s": 12000.0,
            "clock_sync_method": "fractional_clock",
            "source": "per_shot",
            "samples": 3,
            "valid_samples": 3,
            "best_read_latency_ms": 2.1,
            "offset_spread_ms": 0.5,
            "reads": [{"host_after": time.time()}],
        }
        summary = SoundTrigger._clock_sync_summary_for_log(sync)
        assert summary["valid"] is True
        assert summary["reason"] == "valid_fractional_clock"
        assert summary["source"] == "per_shot"
        assert summary["best_offset_s"] == 12000.0
        assert summary["age_s"] is not None


class TestSoundTriggerEdgePaths:
    def test_wait_for_trigger_returns_none_on_timeout(self):
        trigger = SoundTrigger()
        radar = MagicMock()
        radar.wait_for_hardware_trigger.return_value = None
        processor = _make_processor_mock()

        result = trigger.wait_for_trigger(radar, processor, timeout=1.0)

        assert result is None

    def test_wait_for_trigger_returns_none_when_parse_fails(self):
        trigger = SoundTrigger()
        radar = MagicMock()
        radar.wait_for_hardware_trigger.return_value = "bad_data"
        radar.last_hardware_trigger_first_byte_timestamp = None
        processor = MagicMock()
        processor.parse_capture.return_value = None

        result = trigger.wait_for_trigger(radar, processor, timeout=1.0)

        assert result is None
        diags = trigger.drain_diagnostics()
        assert len(diags) == 1
        assert diags[0]["accepted"] is False
        assert diags[0]["reason"] == "parse_failed"

    def test_wait_for_trigger_rejects_false_trigger(self):
        trigger = SoundTrigger()
        radar = MagicMock()
        radar.wait_for_hardware_trigger.return_value = "data"
        radar.last_hardware_trigger_first_byte_timestamp = None
        radar.last_clock_sync = None

        capture = _make_capture()
        processor = MagicMock()
        processor.parse_capture.return_value = capture
        # No valid outbound readings
        processor.process_standard.return_value = _make_timeline(
            speed_mph=5.0, direction="outbound"
        )

        result = trigger.wait_for_trigger(radar, processor, timeout=1.0)

        assert result is None
        diags = trigger.drain_diagnostics()
        assert len(diags) == 1
        assert diags[0]["accepted"] is False
        assert diags[0]["reason"] == "no_outbound_speed"

    def test_reset_is_noop(self):
        trigger = SoundTrigger()
        trigger.reset()  # should not raise
