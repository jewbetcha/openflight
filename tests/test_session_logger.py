"""Tests for session_logger module."""

import json

from openflight import session_logger as session_logger_module
from openflight.kld7.radc import RADC_PAYLOAD_BYTES
from openflight.ops243 import Direction, SpeedReading
from openflight.session_logger import SessionLogger, init_session_logger, log_session_error


class TestLogError:
    """Tests for session error logging."""

    def test_log_error_writes_entry_and_increments_stats(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_error("capture loop failed", context={"component": "monitor"})

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["type"] == "error"
        assert entry["error"] == "capture loop failed"
        assert entry["context"] == {"component": "monitor"}
        assert logger.stats["errors"] == 1

    def test_log_error_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_error("should not write")
        assert logger.stats["errors"] == 0
        assert logger.session_path is None


class TestLogSessionError:
    """Tests for the module-level session error helper."""

    def test_log_session_error_delegates_to_global_logger(self, tmp_path, monkeypatch):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="mock", trigger_type="manual")
        monkeypatch.setattr(session_logger_module, "_session_logger", logger)

        log_session_error(
            "K-LD7 processing failed",
            component="server",
            context={"stage": "kld7"},
            exc=RuntimeError("boom"),
        )

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["type"] == "error"
        assert entry["error"] == "K-LD7 processing failed"
        assert entry["context"]["component"] == "server"
        assert entry["context"]["stage"] == "kld7"
        assert entry["context"]["exception_type"] == "RuntimeError"
        assert entry["context"]["exception_message"] == "boom"

    def test_log_session_error_noop_without_global_logger(self, monkeypatch):
        monkeypatch.setattr(session_logger_module, "_session_logger", None)
        log_session_error("ignored")  # must not raise


class TestLogTriggerDiagnostic:
    """Tests for the trigger diagnostic logging method."""

    def test_accepted_diagnostic_writes_correct_entry(self, tmp_path):
        """Accepted trigger diagnostic should write all fields."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound-gpio")

        logger.log_trigger_diagnostic(
            trigger_type="sound-gpio",
            accepted=True,
            reason="accepted",
            response_bytes=32768,
            total_readings=32,
            outbound_readings=8,
            inbound_readings=24,
            peak_outbound_mph=155.3,
            peak_inbound_mph=45.0,
            all_outbound_speeds=[155.3, 140.2, 102.1],
            all_inbound_speeds=[45.0, 30.5],
            ball_speed_mph=155.3,
            club_speed_mph=103.2,
            spin_rpm=2800,
            carry_yards=265,
            latency_ms=12.5,
        )

        # Read back the JSONL file
        lines = logger.session_path.read_text().strip().split("\n")
        # Last line should be the trigger_diagnostic
        entry = json.loads(lines[-1])

        assert entry["type"] == "trigger_diagnostic"
        assert entry["trigger_type"] == "sound-gpio"
        assert entry["accepted"] is True
        assert entry["reason"] == "accepted"
        assert entry["response_bytes"] == 32768
        assert entry["total_readings"] == 32
        assert entry["outbound_readings"] == 8
        assert entry["inbound_readings"] == 24
        assert entry["peak_outbound_mph"] == 155.3
        assert entry["peak_inbound_mph"] == 45.0
        assert entry["ball_speed_mph"] == 155.3
        assert entry["club_speed_mph"] == 103.2
        assert entry["spin_rpm"] == 2800
        assert entry["carry_yards"] == 265
        assert entry["latency_ms"] == 12.5
        assert len(entry["all_outbound_speeds"]) == 3
        assert len(entry["all_inbound_speeds"]) == 2

    def test_rejected_diagnostic_writes_reason(self, tmp_path):
        """Rejected trigger diagnostic should include reason."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound-gpio")

        logger.log_trigger_diagnostic(
            trigger_type="sound-gpio",
            accepted=False,
            reason="no_outbound_speed",
            response_bytes=32768,
            total_readings=12,
            outbound_readings=0,
            inbound_readings=12,
            peak_outbound_mph=0.0,
            peak_inbound_mph=42.1,
        )

        lines = logger.session_path.read_text().strip().split("\n")
        entry = json.loads(lines[-1])

        assert entry["type"] == "trigger_diagnostic"
        assert entry["accepted"] is False
        assert entry["reason"] == "no_outbound_speed"
        assert entry["outbound_readings"] == 0
        assert entry["peak_inbound_mph"] == 42.1
        # Shot fields should be None/null
        assert entry["ball_speed_mph"] is None
        assert entry["club_speed_mph"] is None

    def test_no_response_diagnostic(self, tmp_path):
        """No-response trigger should log with minimal fields."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound-gpio")

        logger.log_trigger_diagnostic(
            trigger_type="sound-gpio",
            accepted=False,
            reason="no_response",
            response_bytes=0,
        )

        lines = logger.session_path.read_text().strip().split("\n")
        entry = json.loads(lines[-1])

        assert entry["type"] == "trigger_diagnostic"
        assert entry["accepted"] is False
        assert entry["reason"] == "no_response"
        assert entry["response_bytes"] == 0
        assert entry["total_readings"] == 0

    def test_stats_tracking(self, tmp_path):
        """Stats should track accepted/rejected counts."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound-gpio")

        logger.log_trigger_diagnostic(trigger_type="sound-gpio", accepted=True, reason="accepted")
        logger.log_trigger_diagnostic(
            trigger_type="sound-gpio", accepted=False, reason="no_response"
        )
        logger.log_trigger_diagnostic(
            trigger_type="sound-gpio", accepted=False, reason="no_outbound_speed"
        )

        assert logger.stats["triggers_total"] == 3
        assert logger.stats["triggers_accepted"] == 1
        assert logger.stats["triggers_rejected"] == 2

    def test_disabled_logger_skips_write(self, tmp_path):
        """Disabled logger should not write anything."""
        logger = SessionLogger(log_dir=tmp_path, enabled=False)

        logger.log_trigger_diagnostic(trigger_type="sound-gpio", accepted=True, reason="accepted")

        # No session file created when disabled
        assert logger.session_path is None

    def test_empty_speed_lists_default(self, tmp_path):
        """Speed lists should default to empty arrays."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound-gpio")

        logger.log_trigger_diagnostic(
            trigger_type="sound-gpio",
            accepted=False,
            reason="parse_failed",
        )

        lines = logger.session_path.read_text().strip().split("\n")
        entry = json.loads(lines[-1])

        assert entry["all_outbound_speeds"] == []
        assert entry["all_inbound_speeds"] == []


class TestLogShot:
    """Tests for shot logging."""

    def test_shot_logs_spin_diagnostics(self, tmp_path):
        """Shot entries should preserve rejected-spin diagnostics."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_shot(
            ball_speed_mph=120.0,
            club_speed_mph=85.0,
            smash_factor=1.41,
            estimated_carry_yards=165.0,
            club="7-iron",
            peak_magnitude=None,
            readings_count=0,
            spin_snr=2.96,
            spin_peak_freq_hz=95.21484375,
            spin_seam_cycles=4.8,
            spin_candidates=[
                {
                    "rank": 1,
                    "rpm": 5713,
                    "snr": 2.96,
                    "relative_magnitude": 1.0,
                    "selected": True,
                }
            ],
            spin_phase_method="phase_residual",
            spin_phase_rpm=5713,
            spin_phase_snr=3.2,
            spin_phase_agreement_pct=2.1,
            spin_phase_confirmed=True,
            spin_rejection_reason="SNR too low (2.96, need 3.0)",
            launch_angle_vertical=12.3,
            launch_angle_horizontal=-1.2,
            launch_angle_confidence=0.8,
            launch_angle_vertical_confidence=0.8,
            launch_angle_horizontal_confidence=0.6,
            launch_angle_vertical_source="radar",
            launch_angle_horizontal_source="estimated",
            impact_timestamp=1234567890.25,
        )

        lines = logger.session_path.read_text().strip().split("\n")
        entry = json.loads(lines[-1])

        assert entry["type"] == "shot_detected"
        assert entry["spin_rpm"] is None
        assert entry["spin_snr"] == 2.96
        assert entry["spin_candidate_rpm"] == 5713
        assert entry["spin_candidates"][0]["rpm"] == 5713
        assert entry["spin_candidates"][0]["selected"] is True
        assert entry["spin_phase_method"] == "phase_residual"
        assert entry["spin_phase_rpm"] == 5713
        assert entry["spin_phase_snr"] == 3.2
        assert entry["spin_phase_agreement_pct"] == 2.1
        assert entry["spin_phase_confirmed"] is True
        assert entry["spin_rejection_reason"] == "SNR too low (2.96, need 3.0)"
        assert entry["launch_angle_vertical_confidence"] == 0.8
        assert entry["launch_angle_horizontal_confidence"] == 0.6
        assert entry["launch_angle_vertical_source"] == "radar"
        assert entry["launch_angle_horizontal_source"] == "estimated"
        assert entry["impact_timestamp"] == 1234567890.25

    def test_rolling_buffer_capture_logs_trigger_timing(self, tmp_path):
        """Rolling-buffer captures should preserve host trigger timing fields."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_rolling_buffer_capture(
            shot_number=1,
            sample_time=100.0,
            trigger_time=100.068,
            i_samples=[2048] * 4,
            q_samples=[2048] * 4,
            first_byte_timestamp=1234567890.25,
            trigger_timestamp=1234567890.182,
            trigger_timestamp_source="ops_clock_sync",
            clock_sync_offset_s=1234567790.114,
            post_trigger_duration_ms=68.0,
        )

        lines = logger.session_path.read_text().strip().split("\n")
        entry = json.loads(lines[-1])

        assert entry["type"] == "rolling_buffer_capture"
        assert entry["first_byte_timestamp"] == 1234567890.25
        assert entry["trigger_timestamp"] == 1234567890.182
        assert entry["trigger_timestamp_source"] == "ops_clock_sync"
        assert entry["trigger_timestamp_from_first_byte"] == 1234567890.182
        assert entry["trigger_timestamp_delta_from_first_byte_ms"] == 0.0
        assert entry["clock_sync_offset_s"] == 1234567790.114
        assert entry["post_trigger_duration_ms"] == 68.0


class TestLogKld7Buffer:
    """Tests for the K-LD7 ring buffer logging method."""

    def test_kld7_buffer_logs_ball_and_club_angles(self, tmp_path):
        """Both ball_angle and club_angle should round-trip through the JSONL log.

        Regression: server.py used to compute club_angle AFTER calling
        log_kld7_buffer, so club_angle in every horizontal kld7_buffer log
        entry was always None even when shot.club_path_deg was populated
        downstream. This test guards the logger's end of the contract.
        """
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        ball = {
            "horizontal_deg": -3.5,
            "confidence": 0.82,
            "detection_class": "ball",
            "magnitude": 12.4,
            "num_frames": 3,
        }
        club = {
            "horizontal_deg": -2.1,
            "confidence": 0.65,
            "detection_class": "club",
            "magnitude": 8.7,
            "num_frames": 2,
        }
        logger.log_kld7_buffer(
            shot_number=1,
            shot_timestamp=1234567890.0,
            orientation="horizontal",
            buffer_frames=[
                {"timestamp": 1234567889.0, "has_radc": True},
                {"timestamp": 1234567889.05, "has_radc": True},
            ],
            ball_angle=ball,
            club_angle=club,
        )

        lines = logger.session_path.read_text().strip().split("\n")
        entry = json.loads(lines[-1])

        assert entry["type"] == "kld7_buffer"
        assert entry["orientation"] == "horizontal"
        assert entry["frame_count"] == 2
        assert entry["radc_frame_count"] == 2
        assert entry["radc_payload_count"] == 0
        assert entry["radc_payload_valid_count"] == 0
        assert entry["radc_payload_invalid_count"] == 0
        assert entry["radc_payload_expected"] is None
        assert entry["radc_payload_complete"] is False
        assert entry["ball_angle"] == ball
        assert entry["club_angle"] == club, (
            "club_angle must be preserved in the kld7_buffer log entry "
            "so offline analysis can correlate it with the ball angle."
        )

    def test_kld7_buffer_logs_raw_radc_payload_counts(self, tmp_path):
        """Top-level counts make TrackMan replay readiness obvious per shot."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_kld7_buffer(
            shot_number=1,
            shot_timestamp=1234567890.0,
            orientation="vertical",
            buffer_frames=[
                {"timestamp": 1.0, "has_radc": True, "radc_b64": "AQID"},
                {"timestamp": 2.0, "has_radc": True},
                {"timestamp": 3.0},
            ],
            raw_payload_expected=True,
        )

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["frame_count"] == 3
        assert entry["radc_frame_count"] == 2
        assert entry["radc_payload_count"] == 1
        assert entry["radc_payload_valid_count"] == 0
        assert entry["radc_payload_invalid_count"] == 0
        assert entry["radc_payload_expected"] is True
        assert entry["radc_payload_complete"] is False

    def test_kld7_buffer_marks_complete_raw_radc_payloads(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_kld7_buffer(
            shot_number=1,
            shot_timestamp=1234567890.0,
            orientation="vertical",
            buffer_frames=[
                {
                    "timestamp": 1.0,
                    "has_radc": True,
                    "radc_b64": "AQID",
                    "radc_payload_bytes": RADC_PAYLOAD_BYTES,
                },
                {
                    "timestamp": 2.0,
                    "has_radc": True,
                    "radc_b64": "BAUG",
                    "radc_payload_bytes": RADC_PAYLOAD_BYTES,
                },
            ],
            raw_payload_expected=True,
        )

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["radc_payload_count"] == 2
        assert entry["radc_payload_valid_count"] == 2
        assert entry["radc_payload_invalid_count"] == 0
        assert entry["radc_payload_expected"] is True
        assert entry["radc_payload_complete"] is True

    def test_kld7_buffer_marks_wrong_size_payloads_incomplete(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_kld7_buffer(
            shot_number=1,
            shot_timestamp=1234567890.0,
            orientation="vertical",
            buffer_frames=[
                {
                    "timestamp": 1.0,
                    "has_radc": True,
                    "radc_b64": "AQID",
                    "radc_payload_bytes": 3,
                },
            ],
            raw_payload_expected=True,
        )

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["radc_payload_count"] == 1
        assert entry["radc_payload_valid_count"] == 0
        assert entry["radc_payload_invalid_count"] == 1
        assert entry["radc_payload_complete"] is False

    def test_kld7_buffer_club_angle_optional(self, tmp_path):
        """Missing club_angle is allowed (e.g. shot before club_speed available)."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_kld7_buffer(
            shot_number=1,
            shot_timestamp=1.0,
            orientation="vertical",
            buffer_frames=[],
            ball_angle={
                "vertical_deg": 12.5,
                "confidence": 0.9,
                "detection_class": "ball",
                "magnitude": 15.0,
                "num_frames": 2,
            },
        )

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["ball_angle"]["vertical_deg"] == 12.5
        assert entry["club_angle"] is None


class TestLogIWR6843Capture:
    """TI logs retain raw-file linkage and all frozen estimator evidence."""

    def test_iwr6843_capture_round_trips_lcmf_measurement(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")
        measurement = {
            "estimator": "lcmf_v1",
            "launch_angle_deg": 17.4,
            "components_deg": {"channel_two8_deg": 14.1},
        }

        logger.log_iwr6843_capture(
            shot_number=2,
            shot_timestamp=100.0,
            trigger_timestamp=100.012,
            capture_path="/tmp/iwr6843_002.l3dump",
            capture_bytes=786452,
            dump_duration_s=7.56,
            capture_error=None,
            ball_speed_mph=101.2,
            measurement=measurement,
        )

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["type"] == "iwr6843_capture"
        assert entry["shot_number"] == 2
        assert entry["trigger_delta_ms"] == 12.0
        assert entry["capture_bytes"] == 786452
        assert entry["ball_speed_source"] == "ops243"
        assert entry["measurement"] == measurement

    def test_iwr6843_capture_logs_club_path(self, tmp_path):
        """Club path evidence must be replayable from the session log alone."""
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_iwr6843_capture(
            shot_number=1,
            shot_timestamp=100.0,
            trigger_timestamp=100.002,
            capture_path="/tmp/x.l3dump",
            capture_bytes=549542,
            dump_duration_s=5.33,
            capture_error=None,
            ball_speed_mph=94.5,
            measurement={"status": "accepted", "track_span_s": 0.0334},
            club_path={"status": "accepted", "path_deg": 2.4, "confidence": 0.8},
        )

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["type"] == "iwr6843_capture"
        assert entry["club_path"]["path_deg"] == 2.4
        assert entry["measurement"]["track_span_s"] == 0.0334

    def test_iwr6843_capture_club_path_defaults_to_none(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_iwr6843_capture(
            shot_number=1,
            shot_timestamp=100.0,
            trigger_timestamp=None,
            capture_path=None,
            capture_bytes=0,
            dump_duration_s=None,
            capture_error="no capture",
            ball_speed_mph=94.5,
        )

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["club_path"] is None


class TestLogClockSync:
    """Tests for OPS clock-sync logging (H1 timing instrumentation)."""

    def _summary(self):
        return {
            "samples": 3,
            "valid_samples": 3,
            "best_offset_s": 1780000000.5,
            "best_read_latency_ms": 2.1,
            "offset_spread_ms": 0.8,
            "reads": [
                {
                    "radar_clock_s": 137.4,
                    "offset_s": 1780000000.5,
                    "read_latency_ms": 2.1,
                    "raw": '{"Clock":"137.4"}',
                },
            ],
        }

    def test_clock_sync_writes_entry(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")

        logger.log_clock_sync(device="ops243", port="/dev/ttyACM0", summary=self._summary())

        entry = json.loads(logger.session_path.read_text().strip().split("\n")[-1])
        assert entry["type"] == "ops_clock_sync"
        assert entry["device"] == "ops243"
        assert entry["port"] == "/dev/ttyACM0"
        assert entry["best_offset_s"] == 1780000000.5
        assert entry["valid_samples"] == 3
        assert entry["reads"][0]["raw"] == '{"Clock":"137.4"}'

    def test_clock_sync_disabled_skips_write(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_clock_sync(device="ops243", port="x", summary=self._summary())
        assert logger.session_path is None


class TestSessionIdentity:
    """session_start must carry a globally unique ID and format version so
    cloud sync can dedupe sessions by content, not filename."""

    def _start_entry(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        logger.start_session(mode="rolling-buffer", trigger_type="sound")
        logger.end_session()
        session_file = next(tmp_path.glob("session_*.jsonl"))
        with session_file.open() as handle:
            first = json.loads(handle.readline())
        return first

    def test_session_start_has_uuid_and_format_version(self, tmp_path):
        import uuid

        import openflight

        entry = self._start_entry(tmp_path)
        assert entry["type"] == "session_start"
        # Valid UUID4, distinct from the timestamp-based session_id
        parsed = uuid.UUID(entry["session_uuid"])
        assert parsed.version == 4
        assert entry["session_uuid"] != entry["session_id"]
        assert entry["format_version"] == 1
        assert entry["app_version"] == openflight.__version__

    def test_session_uuid_is_unique_per_session(self, tmp_path):
        first = self._start_entry(tmp_path / "a")
        second = self._start_entry(tmp_path / "b")
        assert first["session_uuid"] != second["session_uuid"]


def _start(tmp_path, **kwargs):
    logger = SessionLogger(log_dir=tmp_path, enabled=True)
    logger.start_session(mode="rolling-buffer", trigger_type="sound", **kwargs)
    return logger


def _last_entry(logger):
    lines = logger.session_path.read_text().strip().split("\n")
    return json.loads(lines[-1])


class TestLogConnection:
    def test_writes_device_port_baud(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_connection(device="ops243", port="/dev/ttyACM0", baud=115200)
        entry = _last_entry(logger)
        assert entry["type"] == "connection"
        assert entry["device"] == "ops243"
        assert entry["port"] == "/dev/ttyACM0"
        assert entry["baud"] == 115200

    def test_includes_firmware_when_provided(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_connection(device="ops243", port="/dev/ttyACM0", firmware="OPS243-A v2.1.0")
        entry = _last_entry(logger)
        assert entry["firmware"] == "OPS243-A v2.1.0"

    def test_omits_firmware_when_not_provided(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_connection(device="ops243", port="/dev/ttyACM0")
        entry = _last_entry(logger)
        assert "firmware" not in entry

    def test_includes_radc_available_when_provided(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_connection(device="ops243", port="/dev/ttyACM0", radc_available=True)
        entry = _last_entry(logger)
        assert entry["radc_available"] is True

    def test_omits_radc_available_when_none(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_connection(device="ops243", port="/dev/ttyACM0", radc_available=None)
        entry = _last_entry(logger)
        assert "radc_available" not in entry

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_connection(device="ops243", port="/dev/ttyACM0")
        assert logger.session_path is None


class TestLogAcceptedReading:
    def _reading(self, speed=105.0, direction=Direction.OUTBOUND, magnitude=0.85):
        return SpeedReading(speed=speed, direction=direction, magnitude=magnitude)

    def test_writes_reading_entry(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_accepted_reading(self._reading())
        entry = _last_entry(logger)
        assert entry["type"] == "reading_accepted"
        assert entry["speed"] == 105.0
        assert entry["magnitude"] == 0.85

    def test_increments_readings_accepted_stat(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_accepted_reading(self._reading())
        logger.log_accepted_reading(self._reading(speed=50.0))
        assert logger.stats["readings_accepted"] == 2

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_accepted_reading(self._reading())
        assert logger.stats["readings_accepted"] == 0


class TestLogShotOptionalFields:
    def _minimal_shot(self, logger):
        logger.log_shot(
            ball_speed_mph=130.0,
            club_speed_mph=90.0,
            smash_factor=1.44,
            estimated_carry_yards=220.0,
            club="driver",
            peak_magnitude=0.9,
            readings_count=5,
        )

    def test_angle_source_included_when_provided(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_shot(
            ball_speed_mph=130.0,
            club_speed_mph=90.0,
            smash_factor=1.44,
            estimated_carry_yards=220.0,
            club="driver",
            peak_magnitude=0.9,
            readings_count=5,
            angle_source="kld7",
        )
        entry = _last_entry(logger)
        assert entry["angle_source"] == "kld7"

    def test_angle_source_omitted_when_none(self, tmp_path):
        logger = _start(tmp_path)
        self._minimal_shot(logger)
        entry = _last_entry(logger)
        assert "angle_source" not in entry

    def test_club_angle_deg_included_when_provided(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_shot(
            ball_speed_mph=130.0,
            club_speed_mph=90.0,
            smash_factor=1.44,
            estimated_carry_yards=220.0,
            club="driver",
            peak_magnitude=0.9,
            readings_count=5,
            club_angle_deg=-2.5,
        )
        entry = _last_entry(logger)
        assert entry["club_angle_deg"] == -2.5

    def test_club_path_deg_included_when_provided(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_shot(
            ball_speed_mph=130.0,
            club_speed_mph=90.0,
            smash_factor=1.44,
            estimated_carry_yards=220.0,
            club="driver",
            peak_magnitude=0.9,
            readings_count=5,
            club_path_deg=3.1,
        )
        entry = _last_entry(logger)
        assert entry["club_path_deg"] == 3.1

    def test_spin_axis_deg_included_when_provided(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_shot(
            ball_speed_mph=130.0,
            club_speed_mph=90.0,
            smash_factor=1.44,
            estimated_carry_yards=220.0,
            club="driver",
            peak_magnitude=0.9,
            readings_count=5,
            spin_axis_deg=-5.0,
        )
        entry = _last_entry(logger)
        assert entry["spin_axis_deg"] == -5.0

    def test_pipeline_ms_included_when_provided(self, tmp_path):
        logger = _start(tmp_path)
        timing = {"spin": 12.4, "carry": 0.3}
        logger.log_shot(
            ball_speed_mph=130.0,
            club_speed_mph=90.0,
            smash_factor=1.44,
            estimated_carry_yards=220.0,
            club="driver",
            peak_magnitude=0.9,
            readings_count=5,
            pipeline_ms=timing,
        )
        entry = _last_entry(logger)
        assert entry["pipeline_ms"] == timing

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        self._minimal_shot(logger)
        assert logger.stats["shots_detected"] == 0


class TestLogCameraData:
    def test_writes_camera_entry(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_camera_data(
            shot_number=1,
            launch_angle_vertical=12.5,
            launch_angle_horizontal=-1.0,
            confidence=0.9,
            positions_tracked=4,
            launch_detected=True,
        )
        entry = _last_entry(logger)
        assert entry["type"] == "shot_camera"
        assert entry["shot_number"] == 1
        assert entry["launch_angle_vertical"] == 12.5
        assert entry["launch_angle_horizontal"] == -1.0
        assert entry["confidence"] == 0.9
        assert entry["positions_tracked"] == 4
        assert entry["launch_detected"] is True

    def test_accepts_none_angles(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_camera_data(
            shot_number=1,
            launch_angle_vertical=None,
            launch_angle_horizontal=None,
            confidence=None,
            positions_tracked=0,
            launch_detected=False,
        )
        entry = _last_entry(logger)
        assert entry["launch_angle_vertical"] is None
        assert entry["launch_detected"] is False

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_camera_data(
            shot_number=1,
            launch_angle_vertical=12.5,
            launch_angle_horizontal=None,
            confidence=None,
            positions_tracked=0,
            launch_detected=False,
        )
        assert logger.session_path is None


class TestLogConfigChange:
    def test_writes_config_entry_with_default_source(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_config_change({"min_speed": 35, "dc_mask": 15})
        entry = _last_entry(logger)
        assert entry["type"] == "config_change"
        assert entry["config"]["min_speed"] == 35
        assert entry["source"] == "user"

    def test_writes_custom_source(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_config_change({"mode": "rolling-buffer"}, source="setup_script")
        entry = _last_entry(logger)
        assert entry["source"] == "setup_script"

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_config_change({"min_speed": 35})
        assert logger.session_path is None


class TestLogSimSend:
    def test_writes_sim_send_entry(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_sim_send(
            target="gspro",
            shot_number=3,
            provenance={"ball_speed": "measured", "spin": "estimated"},
            values={"ball_speed": 130.0, "carry": 220.0},
        )
        entry = _last_entry(logger)
        assert entry["type"] == "sim_send"
        assert entry["target"] == "gspro"
        assert entry["shot_number"] == 3
        assert entry["provenance"]["spin"] == "estimated"
        assert entry["values"]["carry"] == 220.0

    def test_values_defaults_to_empty_dict_when_none(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_sim_send(
            target="gspro",
            shot_number=1,
            provenance={},
            values=None,
        )
        entry = _last_entry(logger)
        assert entry["values"] == {}

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_sim_send(target="gspro", shot_number=1, provenance={})
        assert logger.session_path is None


class TestLogSimStatus:
    def test_writes_sim_status_entry(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_sim_status(
            target="gspro",
            state="connected",
            host="192.168.1.60",
            port=921,
            message="ready",
            attempt=1,
            next_retry_in_s=0.0,
        )
        entry = _last_entry(logger)
        assert entry["type"] == "sim_status"
        assert entry["target"] == "gspro"
        assert entry["state"] == "connected"
        assert entry["host"] == "192.168.1.60"
        assert entry["port"] == 921
        assert entry["message"] == "ready"
        assert entry["attempt"] == 1
        assert entry["next_retry_in_s"] == 0.0

    def test_writes_retry_state(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_sim_status(
            target="gspro",
            state="retrying",
            attempt=3,
            next_retry_in_s=5.0,
        )
        entry = _last_entry(logger)
        assert entry["state"] == "retrying"
        assert entry["attempt"] == 3
        assert entry["next_retry_in_s"] == 5.0

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_sim_status(target="gspro", state="connected")
        assert logger.session_path is None


class TestLogSimPlayer:
    def test_writes_sim_player_entry(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_sim_player(target="gspro", handed="right", club="7-iron")
        entry = _last_entry(logger)
        assert entry["type"] == "sim_player"
        assert entry["target"] == "gspro"
        assert entry["handed"] == "right"
        assert entry["club"] == "7-iron"

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_sim_player(target="gspro", handed="right", club="driver")
        assert logger.session_path is None


class TestLogIQReading:
    def test_writes_iq_reading_entry(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_iq_reading(
            speed_mph=105.0,
            direction="outbound",
            magnitude=0.85,
            snr=12.3,
            peak_bin=42,
            cfar_validated=True,
            block_count=8,
        )
        entry = _last_entry(logger)
        assert entry["type"] == "iq_reading"
        assert entry["speed_mph"] == 105.0
        assert entry["direction"] == "outbound"
        assert entry["magnitude"] == 0.85
        assert entry["snr"] == 12.3
        assert entry["peak_bin"] == 42
        assert entry["cfar_validated"] is True
        assert entry["block_count"] == 8

    def test_cfar_not_validated(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_iq_reading(
            speed_mph=30.0,
            direction="inbound",
            magnitude=0.2,
            snr=2.1,
            peak_bin=10,
            cfar_validated=False,
            block_count=4,
        )
        entry = _last_entry(logger)
        assert entry["cfar_validated"] is False

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_iq_reading(
            speed_mph=100.0,
            direction="outbound",
            magnitude=0.8,
            snr=10.0,
            peak_bin=40,
            cfar_validated=True,
            block_count=6,
        )
        assert logger.session_path is None


class TestLogIQBlocks:
    def test_writes_iq_blocks_entry(self, tmp_path):
        logger = _start(tmp_path)
        blocks = [
            {"i_samples": [1, 2, 3], "q_samples": [4, 5, 6], "timestamp": 1.0},
            {"i_samples": [7, 8, 9], "q_samples": [10, 11, 12], "timestamp": 2.0},
        ]
        logger.log_iq_blocks(shot_number=1, blocks=blocks)
        entry = _last_entry(logger)
        assert entry["type"] == "iq_blocks"
        assert entry["shot_number"] == 1
        assert entry["block_count"] == 2
        assert len(entry["blocks"]) == 2

    def test_empty_blocks(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_iq_blocks(shot_number=2, blocks=[])
        entry = _last_entry(logger)
        assert entry["block_count"] == 0
        assert entry["blocks"] == []

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_iq_blocks(shot_number=1, blocks=[])
        assert logger.session_path is None


class TestLogTriggerEvent:
    def test_writes_accepted_trigger_event(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_trigger_event(
            trigger_type="sound-gpio",
            accepted=True,
            reason=None,
            peak_speed_mph=145.0,
            readings_count=12,
            latency_ms=8.5,
        )
        entry = _last_entry(logger)
        assert entry["type"] == "trigger_event"
        assert entry["trigger_type"] == "sound-gpio"
        assert entry["accepted"] is True
        assert entry["peak_speed_mph"] == 145.0
        assert entry["readings_count"] == 12
        assert entry["latency_ms"] == 8.5

    def test_writes_rejected_trigger_event(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_trigger_event(
            trigger_type="sound-gpio",
            accepted=False,
            reason="no_outbound_speed",
        )
        entry = _last_entry(logger)
        assert entry["accepted"] is False
        assert entry["reason"] == "no_outbound_speed"

    def test_increments_stats(self, tmp_path):
        logger = _start(tmp_path)
        logger.log_trigger_event(trigger_type="sound-gpio", accepted=True)
        logger.log_trigger_event(trigger_type="sound-gpio", accepted=False)
        logger.log_trigger_event(trigger_type="sound-gpio", accepted=False)
        assert logger.stats["triggers_total"] == 3
        assert logger.stats["triggers_accepted"] == 1
        assert logger.stats["triggers_rejected"] == 2

    def test_skipped_when_disabled(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=False)
        logger.log_trigger_event(trigger_type="sound-gpio", accepted=True)
        assert logger.session_path is None


class TestProperties:
    def test_session_id_returns_timestamp_string(self, tmp_path):
        logger = _start(tmp_path)
        sid = logger.session_id
        assert sid is not None
        assert len(sid) == 15  # YYYYMMDD_HHMMSS

    def test_session_id_none_before_start(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        assert logger.session_id is None

    def test_raw_path_points_to_log_file(self, tmp_path):
        logger = _start(tmp_path)
        assert logger.raw_path is not None
        assert logger.raw_path.suffix == ".log"
        assert "radar_raw" in logger.raw_path.name

    def test_raw_path_none_before_start(self, tmp_path):
        logger = SessionLogger(log_dir=tmp_path, enabled=True)
        assert logger.raw_path is None


class TestInitSessionLogger:
    def test_returns_session_logger_instance(self, tmp_path):
        logger = init_session_logger(log_dir=tmp_path, location="test", enabled=True)
        assert isinstance(logger, SessionLogger)

    def test_sets_global_logger(self, tmp_path):
        from openflight.session_logger import get_session_logger

        logger = init_session_logger(log_dir=tmp_path, enabled=True)
        assert get_session_logger() is logger

    def test_disabled_logger_creates_instance(self, tmp_path):
        logger = init_session_logger(log_dir=tmp_path, enabled=False)
        assert isinstance(logger, SessionLogger)
        assert not logger.enabled
