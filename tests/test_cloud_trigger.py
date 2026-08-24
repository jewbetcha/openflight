"""Tests for the non-blocking session-end push trigger."""

from openflight.cloud import trigger
from openflight.cloud.config import CloudConfig


class TestFirePushAsync:
    def test_fires_when_active(self, tmp_path):
        calls = []
        config = CloudConfig(device_token="t", device_id="i", enabled=True)
        ok = trigger.fire_push_async(
            config, log_dir=tmp_path, popen_fn=lambda cmd, **k: calls.append(cmd)
        )
        assert ok is True
        assert len(calls) == 1
        assert "push" in calls[0]

    def test_skips_when_inactive(self, tmp_path):
        calls = []
        config = CloudConfig(enabled=False)
        ok = trigger.fire_push_async(
            config, log_dir=tmp_path, popen_fn=lambda cmd, **k: calls.append(cmd)
        )
        assert ok is False
        assert calls == []

    def test_swallows_spawn_errors(self, tmp_path):
        def boom(cmd, **k):
            raise OSError("no exec")

        config = CloudConfig(device_token="t", device_id="i", enabled=True)
        # Must never raise into the caller (server shot path).
        assert trigger.fire_push_async(config, log_dir=tmp_path, popen_fn=boom) is False

    def test_passes_config_and_log_dir(self, tmp_path):
        calls = []
        config = CloudConfig(device_token="t", device_id="i", enabled=True)
        cfg_path = tmp_path / "cloud.json"
        trigger.fire_push_async(
            config,
            log_dir=tmp_path,
            config_path=cfg_path,
            popen_fn=lambda cmd, **k: calls.append(cmd),
        )
        cmd = calls[0]
        assert str(cfg_path) in cmd
        assert str(tmp_path) in cmd
