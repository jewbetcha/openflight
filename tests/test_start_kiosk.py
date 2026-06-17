"""Tests for the kiosk entry script experiment flag wiring."""
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _dry_run(*args: str):
    import subprocess

    return subprocess.run(
        ["bash", "scripts/start-kiosk.sh", *args, "--dry-run"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_trackman_test_dry_run_enables_raw_capture_without_calibration():
    """The field preset should capture raw replay data without changing live angles."""
    result = _dry_run("--trackman-test")
    command = result.stdout.strip()

    assert command.startswith("openflight-server --web-port 8080")
    assert "--session-location trackman" in command
    assert "--experimental-kld7-raw-radc-logging" in command
    assert "--experimental-kld7-trackman-calibration" not in command
    assert "--experimental-kld7-radc-tuning" not in command
    assert "--kld7 --kld7-port /dev/kld7_vertical --kld7-angle-offset 2.5" in command
    assert "--kld7-vertical-estimator geometry" in command
    assert "--kld7-mount-tilt 10" in command
    assert "--kld7-ball-distance 5" in command
    assert "--kld7-horizontal" in command
    assert "--kld7-horizontal-port /dev/kld7_horizontal" in command
    assert "--no-camera" in command
    assert "--trigger sound" in command


def test_kld7_geometry_preset_enables_field_geometry_defaults():
    """The geometry preset should opt into validated launch-angle defaults."""
    result = _dry_run("--kld7-geometry")
    command = result.stdout.strip()

    assert "--kld7 --kld7-port /dev/kld7_vertical" in command
    assert "--kld7-angle-offset 2.5" in command
    assert "--kld7-vertical-estimator geometry" in command
    assert "--kld7-mount-tilt 10" in command
    assert "--kld7-ball-distance 5" in command
    assert "--kld7-horizontal" in command
    assert "--kld7-horizontal-port /dev/kld7_horizontal" in command
    assert "--kld7-horizontal-offset 0" in command


def test_plain_kld7_keeps_legacy_angle_path():
    """The existing --kld7 flag should not opt into geometry by accident."""
    result = _dry_run("--kld7")
    command = result.stdout.strip()

    assert "--kld7 --kld7-port /dev/kld7_vertical --kld7-angle-offset 8" in command
    assert "--kld7-vertical-estimator" not in command
    assert "--kld7-mount-tilt" not in command
    assert "--kld7-ball-distance" not in command
    assert "setup_kld7_latency" not in command


def test_startup_applies_kld7_latency_setup_before_server_start():
    """Kiosk startup should attempt the FTDI latency setup for K-LD7 sessions."""
    script = (_REPO_ROOT / "scripts/start-kiosk.sh").read_text(encoding="utf-8")

    setup_idx = script.index("\nconfigure_kld7_latency\n")
    server_start_idx = script.index("$SERVER_CMD &")

    assert "scripts/setup/setup_kld7_latency.sh" in script
    assert "sudo -n \"$setup_script\" --latency 1" in script
    assert setup_idx < server_start_idx


def test_kld7_geometry_preset_preserves_explicit_overrides():
    """Specific K-LD7 settings should still win over geometry preset defaults."""
    result = _dry_run(
        "--kld7-geometry",
        "--kld7-angle-offset",
        "1.25",
        "--kld7-vertical-estimator",
        "naive",
        "--kld7-mount-tilt",
        "12",
        "--kld7-ball-distance",
        "4.75",
    )
    command = result.stdout.strip()

    assert "--kld7-angle-offset 1.25" in command
    assert "--kld7-vertical-estimator naive" in command
    assert "--kld7-mount-tilt 12" in command
    assert "--kld7-ball-distance 4.75" in command
    assert "--kld7-angle-offset 2.5" not in command
    assert "--kld7-mount-tilt 10" not in command
    assert "--kld7-ball-distance 5" not in command


def test_trackman_test_allows_explicit_session_location():
    """A bay/location override should survive the TrackMan preset defaults."""
    result = _dry_run("--trackman-test", "--session-location", "trackman-bay-2")

    assert "--session-location trackman-bay-2" in result.stdout
    assert "--session-location trackman " not in result.stdout


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
        "--experimental-kld7-raw-radc-logging",
        "--experimental-kld7-radc-tuning",
        "--experimental-kld7-speed-tolerance",
        "6",
        "--experimental-kld7-spectrum-source",
        "sum12",
        "--experimental-kld7-horizontal-angle-limit",
        "30",
    )
    command = result.stdout.strip()

    assert "--experimental-kld7-raw-radc-logging" in command
    assert "--experimental-kld7-radc-tuning" in command
    assert "--experimental-kld7-speed-tolerance 6" in command
    assert "--experimental-kld7-spectrum-source sum12" in command
    assert "--experimental-kld7-horizontal-angle-limit 30" in command
