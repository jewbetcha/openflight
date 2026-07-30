"""Additional tests for session_logger uncovered paths."""

import json

from openflight.ops243 import Direction, SpeedReading
from openflight.session_logger import SessionLogger


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
        from openflight.session_logger import init_session_logger

        logger = init_session_logger(log_dir=tmp_path, location="test", enabled=True)
        assert isinstance(logger, SessionLogger)

    def test_sets_global_logger(self, tmp_path):
        from openflight.session_logger import get_session_logger, init_session_logger

        logger = init_session_logger(log_dir=tmp_path, enabled=True)
        assert get_session_logger() is logger

    def test_disabled_logger_creates_instance(self, tmp_path):
        from openflight.session_logger import init_session_logger

        logger = init_session_logger(log_dir=tmp_path, enabled=False)
        assert isinstance(logger, SessionLogger)
        assert not logger.enabled
