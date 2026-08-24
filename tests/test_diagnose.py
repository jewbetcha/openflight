"""Tests for the hardware diagnostic script."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# diagnose.py is a script — import it as a module for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "hardware-test"))

import diagnose  # noqa: E402


class TestCheckResult:
    def test_default_status_fields(self):
        r = diagnose.CheckResult(name="Test", status="pass")
        assert r.name == "Test"
        assert r.status == "pass"
        assert r.detail == ""
        assert r.hint == ""
        assert r.elapsed_s == 0.0

    def test_with_all_fields(self):
        r = diagnose.CheckResult(
            name="Test",
            status="fail",
            detail="something broke",
            hint="try this",
            elapsed_s=1.5,
        )
        assert r.detail == "something broke"
        assert r.hint == "try this"
        assert r.elapsed_s == 1.5


class TestFormatSummary:
    def test_all_pass(self):
        results = [
            diagnose.CheckResult(name="A", status="pass", elapsed_s=1.0),
            diagnose.CheckResult(name="B", status="pass", elapsed_s=2.0),
        ]
        summary = diagnose.format_summary(results)
        assert "2 passed" in summary
        assert "0 failed" in summary
        assert "HEALTHY" in summary

    def test_with_failure(self):
        results = [
            diagnose.CheckResult(name="A", status="pass"),
            diagnose.CheckResult(name="B", status="fail"),
        ]
        summary = diagnose.format_summary(results)
        assert "1 passed" in summary
        assert "1 failed" in summary
        assert "HEALTHY" not in summary

    def test_with_skip(self):
        results = [
            diagnose.CheckResult(name="A", status="pass"),
            diagnose.CheckResult(name="B", status="skip"),
        ]
        summary = diagnose.format_summary(results)
        assert "1 skipped" in summary


class TestOverallStatus:
    def test_healthy_when_all_pass(self):
        results = [diagnose.CheckResult(name="A", status="pass")]
        assert diagnose.overall_status(results, require_all=False) == "HEALTHY"

    def test_healthy_with_skips_when_not_require_all(self):
        results = [
            diagnose.CheckResult(name="A", status="pass"),
            diagnose.CheckResult(name="B", status="skip"),
        ]
        assert diagnose.overall_status(results, require_all=False) == "HEALTHY"

    def test_unhealthy_with_skips_when_require_all(self):
        results = [
            diagnose.CheckResult(name="A", status="pass"),
            diagnose.CheckResult(name="B", status="skip"),
        ]
        assert diagnose.overall_status(results, require_all=True) == "UNHEALTHY"

    def test_unhealthy_on_any_fail(self):
        results = [diagnose.CheckResult(name="A", status="fail")]
        assert diagnose.overall_status(results, require_all=False) == "UNHEALTHY"


class TestDetectOps243Port:
    @patch("diagnose.serial.tools.list_ports.comports")
    def test_finds_acm_device(self, mock_comports):
        mock_port = MagicMock()
        mock_port.device = "/dev/ttyACM0"
        mock_comports.return_value = [mock_port]
        assert diagnose.detect_ops243_port() == "/dev/ttyACM0"

    @patch("diagnose.serial.tools.list_ports.comports")
    def test_finds_usbmodem_device(self, mock_comports):
        mock_port = MagicMock()
        mock_port.device = "/dev/cu.usbmodem14301"
        mock_comports.return_value = [mock_port]
        assert diagnose.detect_ops243_port() == "/dev/cu.usbmodem14301"

    @patch("diagnose.serial.tools.list_ports.comports")
    def test_returns_none_when_nothing_matches(self, mock_comports):
        mock_port = MagicMock()
        mock_port.device = "/dev/ttyS0"
        mock_comports.return_value = [mock_port]
        assert diagnose.detect_ops243_port() is None

    @patch("diagnose.serial.tools.list_ports.comports")
    def test_empty_port_list(self, mock_comports):
        mock_comports.return_value = []
        assert diagnose.detect_ops243_port() is None


class TestDetectKld7Ports:
    def _make_port(self, device, desc="", mfg=""):
        p = MagicMock()
        p.device = device
        p.description = desc
        p.manufacturer = mfg
        return p

    @patch("diagnose.serial.tools.list_ports.comports")
    def test_finds_ftdi_port(self, mock_comports):
        mock_comports.return_value = [
            self._make_port("/dev/ttyUSB0", desc="FTDI USB-Serial"),
        ]
        assert diagnose.detect_kld7_ports() == ["/dev/ttyUSB0"]

    @patch("diagnose.serial.tools.list_ports.comports")
    def test_finds_cp210x_port(self, mock_comports):
        mock_comports.return_value = [
            self._make_port("/dev/ttyUSB1", desc="CP210x UART Bridge"),
        ]
        assert diagnose.detect_kld7_ports() == ["/dev/ttyUSB1"]

    @patch("diagnose.serial.tools.list_ports.comports")
    def test_finds_two_ports(self, mock_comports):
        mock_comports.return_value = [
            self._make_port("/dev/ttyUSB0", desc="FTDI USB-Serial"),
            self._make_port("/dev/ttyUSB1", desc="CP210x UART"),
        ]
        assert diagnose.detect_kld7_ports() == ["/dev/ttyUSB0", "/dev/ttyUSB1"]

    @patch("diagnose.serial.tools.list_ports.comports")
    def test_ignores_acm_devices(self, mock_comports):
        """ACM devices are OPS243, not K-LD7."""
        mock_comports.return_value = [
            self._make_port("/dev/ttyACM0", desc="OPS243"),
        ]
        assert diagnose.detect_kld7_ports() == []

    @patch("diagnose.serial.tools.list_ports.comports")
    def test_empty_list(self, mock_comports):
        mock_comports.return_value = []
        assert diagnose.detect_kld7_ports() == []


class TestCheckOps243Connectivity:
    @patch("diagnose.detect_ops243_port")
    def test_returns_skip_when_no_port(self, mock_detect):
        mock_detect.return_value = None
        state = diagnose.DiagnosticState()
        result = diagnose.check_ops243_connectivity(state)
        assert result.status == "skip"
        assert "no OPS243" in result.detail
        assert state.ops243_port is None

    @patch("diagnose.detect_ops243_port")
    @patch("diagnose.OPS243Radar")
    def test_returns_pass_when_connects_and_returns_version(
        self,
        mock_radar_class,
        mock_detect,
    ):
        mock_detect.return_value = "/dev/ttyACM0"
        mock_radar = MagicMock()
        mock_radar.get_firmware_version.return_value = "1.2.3"
        mock_radar_class.return_value = mock_radar

        state = diagnose.DiagnosticState()
        result = diagnose.check_ops243_connectivity(state)

        assert result.status == "pass"
        assert "/dev/ttyACM0" in result.detail
        assert "1.2.3" in result.detail
        assert state.ops243_port == "/dev/ttyACM0"
        assert state.ops243_radar is mock_radar

    @patch("diagnose.detect_ops243_port")
    @patch("diagnose.OPS243Radar")
    def test_returns_fail_on_connect_exception(
        self,
        mock_radar_class,
        mock_detect,
    ):
        mock_detect.return_value = "/dev/ttyACM0"
        mock_radar = MagicMock()
        mock_radar.connect.side_effect = OSError("Permission denied")
        mock_radar_class.return_value = mock_radar

        state = diagnose.DiagnosticState()
        result = diagnose.check_ops243_connectivity(state)

        assert result.status == "fail"
        assert "Permission denied" in result.detail
        assert "dialout" in result.hint.lower()


class TestCheckOps243RollingBufferPersisted:
    def test_skipped_when_no_radar_in_state(self):
        state = diagnose.DiagnosticState()
        result = diagnose.check_ops243_rolling_buffer_persisted(state)
        assert result.status == "skip"

    def test_pass_when_no_data_streams(self):
        state = diagnose.DiagnosticState()
        mock_radar = MagicMock()
        mock_radar.serial.in_waiting = 0
        mock_radar.serial.read.return_value = b""
        state.ops243_radar = mock_radar

        result = diagnose.check_ops243_rolling_buffer_persisted(state)

        assert result.status == "pass"
        assert "rolling buffer" in result.detail.lower()

    def test_fail_when_data_streams(self):
        state = diagnose.DiagnosticState()
        mock_radar = MagicMock()
        mock_radar.serial.in_waiting = 42
        mock_radar.serial.read.return_value = b'{"speed": 12.5}\n'
        state.ops243_radar = mock_radar

        result = diagnose.check_ops243_rolling_buffer_persisted(state)

        assert result.status == "fail"
        assert "streaming" in result.detail.lower() or "cw mode" in result.detail.lower()
        assert "test_rolling_buffer_persist.py --setup" in result.hint


class TestCheckOps243SoftwareTrigger:
    def test_skipped_when_no_radar(self):
        state = diagnose.DiagnosticState()
        result = diagnose.check_ops243_software_trigger(state)
        assert result.status == "skip"

    @patch("diagnose.RollingBufferProcessor")
    def test_pass_with_valid_capture(self, mock_processor_class):
        state = diagnose.DiagnosticState()
        state.ops243_radar = MagicMock()
        state.ops243_radar.trigger_capture.return_value = '{"I":[...]}...'

        mock_capture = MagicMock()
        mock_capture.i_samples = [0] * 4096
        mock_capture.q_samples = [0] * 4096
        mock_processor = MagicMock()
        mock_processor.parse_capture.return_value = mock_capture
        mock_processor_class.return_value = mock_processor

        result = diagnose.check_ops243_software_trigger(state)

        assert result.status == "pass"
        assert "4096" in result.detail

    def test_fail_on_empty_response(self):
        state = diagnose.DiagnosticState()
        state.ops243_radar = MagicMock()
        state.ops243_radar.trigger_capture.return_value = ""

        result = diagnose.check_ops243_software_trigger(state)

        assert result.status == "fail"
        assert "no I/Q response" in result.detail or "no response" in result.detail.lower()

    @patch("diagnose.RollingBufferProcessor")
    def test_fail_on_unparseable_response(self, mock_processor_class):
        state = diagnose.DiagnosticState()
        state.ops243_radar = MagicMock()
        state.ops243_radar.trigger_capture.return_value = "garbage"

        mock_processor = MagicMock()
        mock_processor.parse_capture.return_value = None
        mock_processor_class.return_value = mock_processor

        result = diagnose.check_ops243_software_trigger(state)

        assert result.status == "fail"
        assert "parse" in result.detail.lower()


class TestCheckKld7Vertical:
    @patch("diagnose.detect_kld7_ports")
    def test_skip_when_no_kld7_detected(self, mock_detect):
        mock_detect.return_value = []
        state = diagnose.DiagnosticState()
        result = diagnose.check_kld7_vertical(state)
        assert result.status == "skip"
        assert "no K-LD7" in result.detail

    @patch("diagnose.detect_kld7_ports")
    @patch("diagnose.KLD7Tracker")
    @patch("diagnose.time.sleep")
    def test_pass_when_frames_stream(
        self,
        mock_sleep,
        mock_tracker_class,
        mock_detect,
    ):
        mock_detect.return_value = ["/dev/ttyUSB0"]
        mock_tracker = MagicMock()
        mock_tracker.connect.return_value = True
        mock_tracker._ring_buffer = [MagicMock() for _ in range(42)]
        mock_tracker_class.return_value = mock_tracker

        state = diagnose.DiagnosticState()
        result = diagnose.check_kld7_vertical(state)

        assert result.status == "pass"
        assert "42 frames" in result.detail
        assert state.kld7_vertical_port == "/dev/ttyUSB0"
        mock_tracker.stop.assert_called_once()

    @patch("diagnose.detect_kld7_ports")
    @patch("diagnose.KLD7Tracker")
    @patch("diagnose.time.sleep")
    def test_fail_when_no_frames(
        self,
        mock_sleep,
        mock_tracker_class,
        mock_detect,
    ):
        mock_detect.return_value = ["/dev/ttyUSB0"]
        mock_tracker = MagicMock()
        mock_tracker.connect.return_value = True
        mock_tracker._ring_buffer = []
        mock_tracker_class.return_value = mock_tracker

        state = diagnose.DiagnosticState()
        result = diagnose.check_kld7_vertical(state)

        assert result.status == "fail"
        assert "0 frames" in result.detail or "no frames" in result.detail.lower()

    @patch("diagnose.detect_kld7_ports")
    @patch("diagnose.KLD7Tracker")
    def test_fail_when_connect_returns_false(
        self,
        mock_tracker_class,
        mock_detect,
    ):
        mock_detect.return_value = ["/dev/ttyUSB0"]
        mock_tracker = MagicMock()
        mock_tracker.connect.return_value = False
        mock_tracker_class.return_value = mock_tracker

        state = diagnose.DiagnosticState()
        result = diagnose.check_kld7_vertical(state)

        assert result.status == "fail"
        assert "connect" in result.detail.lower()


class TestCheckKld7Horizontal:
    @patch("diagnose.detect_kld7_ports")
    def test_skip_when_no_kld7_detected(self, mock_detect):
        mock_detect.return_value = []
        state = diagnose.DiagnosticState()
        result = diagnose.check_kld7_horizontal(state)
        assert result.status == "skip"
        assert "no K-LD7" in result.detail

    @patch("diagnose.detect_kld7_ports")
    def test_skip_when_only_one_kld7_detected(self, mock_detect):
        mock_detect.return_value = ["/dev/ttyUSB0"]
        state = diagnose.DiagnosticState()
        state.kld7_vertical_port = "/dev/ttyUSB0"
        result = diagnose.check_kld7_horizontal(state)
        assert result.status == "skip"
        assert "only one K-LD7" in result.detail.lower() or "optional" in result.detail.lower()

    @patch("diagnose.detect_kld7_ports")
    @patch("diagnose.KLD7Tracker")
    @patch("diagnose.time.sleep")
    def test_pass_with_second_port(
        self,
        mock_sleep,
        mock_tracker_class,
        mock_detect,
    ):
        mock_detect.return_value = ["/dev/ttyUSB0", "/dev/ttyUSB1"]
        mock_tracker = MagicMock()
        mock_tracker.connect.return_value = True
        mock_tracker._ring_buffer = [MagicMock() for _ in range(40)]
        mock_tracker_class.return_value = mock_tracker

        state = diagnose.DiagnosticState()
        state.kld7_vertical_port = "/dev/ttyUSB0"

        result = diagnose.check_kld7_horizontal(state)

        assert result.status == "pass"
        assert "/dev/ttyUSB1" in result.detail
        assert state.kld7_horizontal_port == "/dev/ttyUSB1"


class TestCheckSoundTrigger:
    def test_skip_when_no_radar(self):
        state = diagnose.DiagnosticState()
        result = diagnose.check_sound_trigger_end_to_end(state, interactive=True)
        assert result.status == "skip"

    def test_skip_when_not_interactive(self):
        state = diagnose.DiagnosticState()
        state.ops243_radar = MagicMock()
        result = diagnose.check_sound_trigger_end_to_end(state, interactive=False)
        assert result.status == "skip"
        assert "interactive" in result.detail.lower()

    @patch("diagnose.RollingBufferProcessor")
    def test_pass_with_trigger_and_valid_capture(self, mock_processor_class):
        state = diagnose.DiagnosticState()
        radar = MagicMock()
        radar.wait_for_hardware_trigger.return_value = '{"I":[...]}'
        state.ops243_radar = radar

        mock_capture = MagicMock()
        mock_capture.i_samples = [0] * 4096
        mock_processor = MagicMock()
        mock_processor.parse_capture.return_value = mock_capture
        mock_processor_class.return_value = mock_processor

        result = diagnose.check_sound_trigger_end_to_end(state, interactive=True)

        assert result.status == "pass"
        assert "4096" in result.detail
        radar.rearm_rolling_buffer.assert_called_once()

    def test_fail_on_timeout(self):
        state = diagnose.DiagnosticState()
        radar = MagicMock()
        radar.wait_for_hardware_trigger.return_value = ""
        state.ops243_radar = radar

        result = diagnose.check_sound_trigger_end_to_end(state, interactive=True)

        assert result.status == "fail"
        assert "trigger" in result.detail.lower()
        assert "SEN-14262" in result.hint or "R17" in result.hint


class TestParseArgs:
    def test_default_flags(self):
        args = diagnose.parse_args([])
        assert args.require_all is False
        assert args.no_interactive is False
        assert args.ops_port is None
        assert args.ops_baud is None

    def test_require_all_flag(self):
        args = diagnose.parse_args(["--require-all"])
        assert args.require_all is True

    def test_no_interactive_flag(self):
        args = diagnose.parse_args(["--no-interactive"])
        assert args.no_interactive is True

    def test_ops_port_and_baud(self):
        args = diagnose.parse_args(["--ops-port", "/dev/ttyAMA0", "--ops-baud", "115200"])
        assert args.ops_port == "/dev/ttyAMA0"
        assert args.ops_baud == 115200


class TestUartPreflight:
    """The three UART-only failures that all look like "radar not responding"."""

    def test_skipped_on_usb(self):
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyACM0")
        result = diagnose.check_uart_preflight(state)
        assert result.status == "skip"
        assert "USB" in result.detail

    def test_skipped_when_no_port_given(self):
        result = diagnose.check_uart_preflight(diagnose.DiagnosticState())
        assert result.status == "skip"

    def test_passes_when_environment_is_clean(self):
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyAMA0")
        with (
            patch.object(diagnose.os.path, "exists", return_value=True),
            patch.object(diagnose, "_serial_console_units", return_value=[]),
            patch.object(diagnose, "detect_ops243_port", return_value=None),
        ):
            result = diagnose.check_uart_preflight(state)
        assert result.status == "pass"

    def test_fails_when_device_node_missing(self):
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyAMA0")
        with (
            patch.object(diagnose.os.path, "exists", return_value=False),
            patch.object(diagnose, "_serial_console_units", return_value=[]),
            patch.object(diagnose, "detect_ops243_port", return_value=None),
        ):
            result = diagnose.check_uart_preflight(state)
        assert result.status == "fail"
        assert "does not exist" in result.detail
        assert "enable_uart=1" in result.hint

    def test_fails_when_serial_console_holds_the_port(self):
        """Console chatter is transmitted into the radar's RxD pin."""
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyAMA0")
        with (
            patch.object(diagnose.os.path, "exists", return_value=True),
            patch.object(
                diagnose,
                "_serial_console_units",
                return_value=["serial-getty@ttyAMA0.service"],
            ),
            patch.object(diagnose, "detect_ops243_port", return_value=None),
        ):
            result = diagnose.check_uart_preflight(state)
        assert result.status == "fail"
        assert "console" in result.detail
        assert "systemctl disable" in result.hint

    def test_fails_when_ops_usb_is_also_enumerated(self):
        """Enumerating USB silences the UART entirely (AN-010-AD)."""
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyAMA0")
        with (
            patch.object(diagnose.os.path, "exists", return_value=True),
            patch.object(diagnose, "_serial_console_units", return_value=[]),
            patch.object(diagnose, "detect_ops243_port", return_value="/dev/ttyACM0"),
        ):
            result = diagnose.check_uart_preflight(state)
        assert result.status == "fail"
        assert "USB" in result.detail
        assert "Unplug" in result.hint


class TestConnectivityReportsBaud:
    """Over UART, a low negotiated baud is a failure, not a footnote."""

    def _radar(self, baud):
        radar = MagicMock()
        radar.baud = baud
        radar.DUMP_BYTES = 45000
        radar.bytes_per_second = baud / 10.0
        radar.get_firmware_version.return_value = "1.5.2"
        return radar

    def test_pass_at_target_baud_reports_it(self):
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyAMA0")
        with patch.object(diagnose, "OPS243Radar", return_value=self._radar(230400)):
            result = diagnose.check_ops243_connectivity(state)
        assert result.status == "pass"
        assert "230400 baud" in result.detail

    def test_fail_when_negotiation_settled_low(self):
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyAMA0")
        with patch.object(diagnose, "OPS243Radar", return_value=self._radar(19200)):
            result = diagnose.check_ops243_connectivity(state)
        assert result.status == "fail"
        assert "19200" in result.detail
        assert "pin 6" in result.hint, "hint should point at the Pi TX -> OPS RX wire"

    def test_usb_detail_omits_baud(self):
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyACM0")
        with patch.object(diagnose, "OPS243Radar", return_value=self._radar(57600)):
            result = diagnose.check_ops243_connectivity(state)
        assert result.status == "pass"
        assert "baud" not in result.detail

    def test_explicit_port_overrides_autodetect(self):
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyAMA0")
        with (
            patch.object(diagnose, "OPS243Radar", return_value=self._radar(230400)) as radar_cls,
            patch.object(diagnose, "detect_ops243_port", return_value="/dev/ttyACM0"),
        ):
            diagnose.check_ops243_connectivity(state)
        assert radar_cls.call_args.kwargs["port"] == "/dev/ttyAMA0"

    def test_baud_override_is_passed_to_the_driver(self):
        state = diagnose.DiagnosticState(ops243_port="/dev/ttyAMA0", ops243_baud=115200)
        with patch.object(diagnose, "OPS243Radar", return_value=self._radar(115200)) as radar_cls:
            diagnose.check_ops243_connectivity(state)
        assert radar_cls.call_args.kwargs["uart_baud"] == 115200

    def test_skip_hint_points_at_the_uart_flag(self):
        with patch.object(diagnose, "detect_ops243_port", return_value=None):
            result = diagnose.check_ops243_connectivity(diagnose.DiagnosticState())
        assert result.status == "skip"
        assert "--ops-port" in result.hint
