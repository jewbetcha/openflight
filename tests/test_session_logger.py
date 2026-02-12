"""Tests for session_logger module."""

import json
import pytest
from pathlib import Path

from openflight.session_logger import SessionLogger


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
        lines = logger.session_path.read_text().strip().split('\n')
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

        lines = logger.session_path.read_text().strip().split('\n')
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

        lines = logger.session_path.read_text().strip().split('\n')
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

        logger.log_trigger_diagnostic(
            trigger_type="sound-gpio", accepted=True, reason="accepted"
        )
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

        logger.log_trigger_diagnostic(
            trigger_type="sound-gpio", accepted=True, reason="accepted"
        )

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

        lines = logger.session_path.read_text().strip().split('\n')
        entry = json.loads(lines[-1])

        assert entry["all_outbound_speeds"] == []
        assert entry["all_inbound_speeds"] == []
