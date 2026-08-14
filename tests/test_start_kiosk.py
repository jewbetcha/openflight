"""Tests for the kiosk entry script flag wiring."""

import shutil
import subprocess
from pathlib import Path

import pytest

# The contract under test is the bash script's flag forwarding; without a
# POSIX shell there is nothing to exercise. With one present (e.g. Git Bash
# on Windows) --dry-run works everywhere.
pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="start-kiosk.sh contract tests need bash"
)


def _dry_run(*args: str, check: bool = True):
    # pathlib, not string-splitting on "/tests/": __file__ uses backslashes
    # on Windows, which made repo_root the test file itself (cwd=<file> ->
    # NotADirectoryError in CreateProcess).
    repo_root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        ["bash", "scripts/start-kiosk.sh", *args, "--dry-run"],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
    )


def test_ballistics_is_preferred_by_default():
    command_arguments = _dry_run().stdout.strip().split()

    assert "--ballistics" not in command_arguments
    assert "--no-ballistics" not in command_arguments


def test_no_ballistics_opt_out_is_forwarded():
    command_arguments = _dry_run("--no-ballistics").stdout.strip().split()

    assert "--no-ballistics" in command_arguments


def test_existing_ballistics_flag_remains_accepted():
    command_arguments = _dry_run("--ballistics").stdout.strip().split()

    assert "--no-ballistics" not in command_arguments


def test_kld7_requires_mount_tilt():
    """--kld7 without a mount tilt must fail loudly rather than assume a default."""
    result = _dry_run("--kld7", check=False)
    assert result.returncode != 0
    assert "mount tilt is unset" in (result.stdout + result.stderr)


def test_iwr6843_enables_ti_launch_pipeline_with_production_defaults():
    result = _dry_run("--iwr6843")
    command = result.stdout.strip()

    assert "--iwr6843" in command
    assert "--trigger sound" in command
    assert "--kld7" not in command


def test_hardware_trigger_is_opt_in_and_uses_six_pre_trigger_segments():
    """The existing sound startup remains the default; hardware flags are explicit."""
    default_command = _dry_run().stdout.strip()
    hardware_command = _dry_run("--trigger", "hardware").stdout.strip()

    assert "--trigger sound" in default_command
    assert "--trigger hardware" in hardware_command
    assert "--trigger-threshold 25" in hardware_command
    assert "--trigger-magnitude 40" in hardware_command
    assert "--pre-trigger-segments 6" in hardware_command
    assert "--sound-pre-trigger" not in hardware_command


def test_hardware_trigger_overrides_are_forwarded_without_changing_sound_alias():
    """Hardware-only names forward their values while sound keeps its legacy flag."""
    hardware = _dry_run(
        "--trigger",
        "hardware",
        "--trigger-threshold",
        "31",
        "--trigger-magnitude",
        "52",
        "--pre-trigger-segments",
        "20",
    ).stdout
    sound = _dry_run("--sound-pre-trigger", "18").stdout

    assert "--trigger-threshold 31" in hardware
    assert "--trigger-magnitude 52" in hardware
    assert "--pre-trigger-segments 20" in hardware
    assert "--sound-pre-trigger" not in hardware
    assert "--trigger sound" in sound
    assert "--sound-pre-trigger 18" in sound


def test_speed_trigger_keeps_its_existing_threshold_without_an_override():
    """The hardware default threshold must not alter the existing speed path."""
    command = _dry_run("--trigger", "speed").stdout

    assert "--trigger speed" in command
    assert "--trigger-threshold" not in command


def test_iwr6843_overrides_are_forwarded():
    result = _dry_run(
        "--iwr6843",
        "--iwr6843-port",
        "/dev/ttyUSB9",
        "--iwr6843-trigger-pin",
        "22",
        "--iwr6843-tee-m",
        "1.6",
        "--iwr6843-net-m",
        "4.8",
        "--iwr6843-tilt-deg",
        "10.4",
        "--iwr6843-radar-height-m",
        "0.1524",
        "--iwr6843-ball-height-m",
        "0.065",
        "--iwr6843-tx-order",
        "normal",
        "--iwr6843-capture-timeout",
        "15",
    )
    command = result.stdout.strip()

    assert "--iwr6843-port /dev/ttyUSB9" in command
    assert "--iwr6843-trigger-pin 22" in command
    assert "--iwr6843-tee-m 1.6" in command
    assert "--iwr6843-net-m 4.8" in command
    assert "--iwr6843-tilt-deg 10.4" in command
    assert "--iwr6843-radar-height-m 0.1524" in command
    assert "--iwr6843-ball-height-m 0.065" in command
    assert "--iwr6843-tx-order normal" in command
    assert "--iwr6843-capture-timeout 15" in command


def test_ops_radar_port_is_forwarded_separately_from_web_port():
    result = _dry_run("--radar-port", "/dev/serial0", "--port", "9090")
    command = result.stdout.strip()

    assert command.startswith("openflight-server --web-port 9090 --port /dev/serial0")


def test_ops_port_alias_is_forwarded_to_server_radar_port():
    result = _dry_run("--ops-port", "/dev/serial0")

    assert "--port /dev/serial0" in result.stdout


def test_plain_kld7_enables_two_ray_defaults():
    """--kld7 (with the required tilt) forwards the cleaned-up flag set."""
    result = _dry_run("--kld7", "--kld7-mount-tilt", "10")
    command = result.stdout.strip()

    assert "--kld7 --kld7-port /dev/kld7_vertical" in command
    # Boresight offset defaults to the calibrated 1.5, not the old 8.
    assert "--kld7-angle-offset 1.5" in command
    assert "--kld7-mount-tilt 10" in command
    # The estimator is a fixed cascade now — no selection flag.
    assert "--kld7-vertical-estimator" not in command
    # Gating is on by default; raw mode is opt-in.
    assert "--kld7-vertical-raw" not in command
    # Cosine correction rides on --kld7 server-side, not a kiosk flag.
    assert "--ball-speed-cosine-correction" not in command


def test_kld7_angle_offset_override_wins():
    """An explicit boresight offset overrides the 1.5 default."""
    result = _dry_run("--kld7", "--kld7-mount-tilt", "10", "--kld7-angle-offset", "3.5")
    command = result.stdout.strip()

    assert "--kld7-angle-offset 3.5" in command
    assert "--kld7-angle-offset 1.5" not in command


def test_swing_speed_flags_forwarded():
    """Swing speed training flags should reach the server command."""
    result = _dry_run(
        "--swing-speed",
        "--swing-speed-threshold",
        "35",
        "--swing-speed-max",
        "125",
        "--swing-speed-min-readings",
        "4",
        "--swing-speed-single-peak",
        "65",
        "--swing-speed-num-reports",
        "8",
        "--swing-speed-end-ms",
        "300",
        "--swing-speed-cooldown-ms",
        "900",
        "--swing-speed-rejected-cooldown-ms",
        "50",
    )
    command = result.stdout.strip()

    assert "--swing-speed" in command
    assert "--swing-speed-threshold 35" in command
    assert "--swing-speed-max 125" in command
    assert "--swing-speed-min-readings 4" in command
    assert "--swing-speed-single-peak 65" in command
    assert "--swing-speed-num-reports 8" in command
    assert "--swing-speed-end-ms 300" in command
    assert "--swing-speed-cooldown-ms 900" in command
    assert "--swing-speed-rejected-cooldown-ms 50" in command


def test_mock_swing_speed_flag_forwards_mock_mode():
    """Mock swing speed should use the server's no-hardware training mode."""
    result = _dry_run("--mock-swing-speed", "--swing-speed-threshold", "45")
    command = result.stdout.strip()

    assert "--mock-swing-speed" in command
    assert "--swing-speed-threshold 45" in command
    assert "--swing-speed " not in f"{command} "
    assert "--mock " not in f"{command} "


def test_mock_and_swing_speed_flags_collapse_to_mock_swing_speed():
    """The friendly --mock --swing-speed combo should avoid the server error path."""
    result = _dry_run("--mock", "--swing-speed")
    command = result.stdout.strip()

    assert "--mock-swing-speed" in command
    assert "--swing-speed " not in f"{command} "
    assert "--mock " not in f"{command} "


def test_kld7_vertical_raw_flag_forwarded():
    """--kld7-vertical-raw reaches the server as the renamed raw flag."""
    result = _dry_run("--kld7", "--kld7-mount-tilt", "10", "--kld7-vertical-raw")
    assert "--kld7-vertical-raw" in result.stdout


def test_trackman_test_dry_run_enables_raw_capture():
    """The field preset captures raw replay data and forwards the clean flags."""
    result = _dry_run("--trackman-test", "--kld7-mount-tilt", "10")
    command = result.stdout.strip()

    assert command.startswith("openflight-server --web-port 8080")
    assert "--session-location trackman" in command
    assert "--kld7-raw-logging" in command
    assert "--experimental-kld7-radc-tuning" not in command
    assert "--kld7 --kld7-port /dev/kld7_vertical --kld7-angle-offset 1.5" in command
    assert "--kld7-mount-tilt 10" in command
    assert "--kld7-horizontal" in command
    assert "--kld7-horizontal-port /dev/kld7_horizontal" in command
    assert "--no-camera" in command
    assert "--trigger sound" in command
    # No legacy estimator selection survives.
    assert "--kld7-vertical-estimator" not in command


def test_trackman_test_allows_explicit_session_location():
    """A bay/location override should survive the TrackMan preset defaults."""
    result = _dry_run("--trackman-test", "--kld7-mount-tilt", "10", "--session-location", "bay-2")

    assert "--session-location bay-2" in result.stdout
    assert "--session-location trackman " not in result.stdout


def test_startup_applies_kld7_latency_setup_before_server_start():
    """Kiosk startup should attempt the FTDI latency setup for K-LD7 sessions."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    script = (repo_root / "scripts/start-kiosk.sh").read_text(encoding="utf-8")

    setup_idx = script.index("\nconfigure_kld7_latency\n")
    server_start_idx = script.index("$SERVER_CMD &")

    assert "scripts/setup/setup_kld7_latency.sh" in script
    assert 'sudo -n "$setup_script" --latency 1' in script
    assert setup_idx < server_start_idx


def test_shutdown_requests_server_cleanup_before_forcing_process_exit():
    """The wrapper must let the server drain IWR data and stop firmware first."""
    repo_root = Path(__file__).resolve().parents[1]
    script = (repo_root / "scripts/start-kiosk.sh").read_text(encoding="utf-8")
    cleanup = script[script.index("shutdown_server() {") : script.index("configure_kld7_latency()")]

    api_idx = cleanup.index("/api/shutdown")
    wait_idx = cleanup.index('kill -0 "$SERVER_PID"', api_idx)
    term_idx = cleanup.index('kill -TERM "$SERVER_PID"')

    assert api_idx < wait_idx < term_idx


def test_radc_tuning_values_are_ignored_without_experimental_gate():
    """Loose tuning flags should not alter production extraction by accident."""
    result = _dry_run(
        "--experimental-kld7-speed-tolerance", "6", "--experimental-kld7-spectrum-source", "sum12"
    )

    assert "--experimental-kld7-speed-tolerance 6" not in result.stdout
    assert "--experimental-kld7-spectrum-source sum12" not in result.stdout
    assert "Ignoring experimental K-LD7 RADC tuning values" in result.stdout


def test_radc_tuning_values_are_forwarded_with_experimental_gate():
    """When explicitly enabled, replay-discovered RADC knobs reach the server."""
    result = _dry_run(
        "--kld7-raw-logging",
        "--experimental-kld7-radc-tuning",
        "--experimental-kld7-speed-tolerance",
        "6",
        "--experimental-kld7-spectrum-source",
        "sum12",
        "--experimental-kld7-horizontal-angle-limit",
        "30",
    )
    command = result.stdout.strip()

    assert "--kld7-raw-logging" in command
    assert "--experimental-kld7-radc-tuning" in command
    assert "--experimental-kld7-speed-tolerance 6" in command
    assert "--experimental-kld7-spectrum-source sum12" in command
    assert "--experimental-kld7-horizontal-angle-limit 30" in command


def test_ops_uart_port_and_baud_are_forwarded():
    """The GPIO-UART wiring needs both the device and the target rate."""
    result = _dry_run("--radar-port", "/dev/ttyAMA0", "--ops-baud", "230400")
    command = result.stdout.strip()

    assert "--port /dev/ttyAMA0" in command
    assert "--ops-baud 230400" in command


def test_ops_baud_is_omitted_by_default():
    """No flag means the driver picks its own target; don't pin it here."""
    command = _dry_run().stdout.strip()
    assert "--ops-baud" not in command


def test_ops_port_alias_matches_radar_port():
    """--ops-port and --radar-port must behave identically (docs use both)."""
    via_ops = _dry_run("--ops-port", "/dev/ttyAMA0").stdout.strip()
    via_radar = _dry_run("--radar-port", "/dev/ttyAMA0").stdout.strip()
    assert via_ops == via_radar
    assert "--port /dev/ttyAMA0" in via_ops


def test_iwr6843_azimuth_offset_is_forwarded():
    """Club path is relative to the target line, so the aim offset must reach the server."""
    command = _dry_run("--iwr6843", "--iwr6843-azimuth-offset-deg", "1.5").stdout.strip()
    assert "--iwr6843-azimuth-offset-deg 1.5" in command


def test_iwr6843_azimuth_offset_omitted_by_default():
    command = _dry_run("--iwr6843").stdout.strip()
    assert "--iwr6843-azimuth-offset-deg" not in command
