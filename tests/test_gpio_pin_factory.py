"""Pin-factory selection must not rely on gpiozero's Pi 5 auto-detection.

Field failure on a Pi 5 (2026-07-25): every gpiozero backend fell back and
startup died with ``BadPinFactory: Unable to load any default pin factory!``,
taking the IWR6843 down with it. The cause is upstream — gpiozero
2.0.1.post2 (the latest release) has this in ``pins/lgpio.py`` with no
``import os`` anywhere in the module:

    if chip is None:
        chip = 4 if (self._get_revision() & 0xff0) >> 4 == 0x17 \
            and os.path.exists('/dev/gpiochip4') else 0

Revision type ``0x17`` is the Pi 5, and ``and`` short-circuits, so a Pi 4
never evaluates ``os`` and works. A Pi 5 raises ``NameError``, which
gpiozero swallows into a ``PinFactoryFallback`` warning; the remaining
backends then fail for their own reasons (no RPi.GPIO, no pigpio, and no
``/dev/gpiomem`` on a Pi 5).

The ``if chip is None`` guard is the escape: passing a chip explicitly skips
the broken line. These tests pin that down, since the failure is invisible
on any machine without a Pi 5.
"""

import os
from unittest.mock import patch

import pytest

from openflight.gpio_factory import (
    GPIO_CHIP_ENV,
    detect_gpio_chip,
    ensure_lgpio_pin_factory,
)


class FakeLGPIOFactory:
    """Records how gpiozero's factory was constructed."""

    instances = []

    def __init__(self, chip=None):
        self.chip = chip
        self.closed = False
        FakeLGPIOFactory.instances.append(self)

    def close(self):
        self.closed = True


class FakeDevice:
    """Stand-in for gpiozero.Device's class-level pin_factory slot."""

    pin_factory = None


@pytest.fixture(autouse=True)
def _reset():
    FakeLGPIOFactory.instances = []
    FakeDevice.pin_factory = None
    yield


def _install(**kwargs):
    with patch(
        "openflight.gpio_factory._load_gpiozero", return_value=(FakeDevice, FakeLGPIOFactory)
    ):
        return ensure_lgpio_pin_factory(**kwargs)


class TestChipDetection:
    def test_pi5_header_chip_used_when_present(self):
        with patch.object(os.path, "exists", lambda p: p == "/dev/gpiochip4"):
            assert detect_gpio_chip() == 4

    def test_falls_back_to_chip_zero(self):
        with patch.object(os.path, "exists", return_value=False):
            assert detect_gpio_chip() == 0

    def test_env_override_wins(self):
        with (
            patch.dict(os.environ, {GPIO_CHIP_ENV: "0"}),
            patch.object(os.path, "exists", lambda p: p == "/dev/gpiochip4"),
        ):
            assert detect_gpio_chip() == 0

    def test_bad_env_override_is_rejected_loudly(self):
        """A typo must not silently fall back to the wrong gpiochip."""
        with patch.dict(os.environ, {GPIO_CHIP_ENV: "not-a-number"}):
            with pytest.raises(ValueError) as exc:
                detect_gpio_chip()
        assert GPIO_CHIP_ENV in str(exc.value)


class TestEnsureLgpioPinFactory:
    def test_chip_is_always_explicit(self):
        """The whole point: never let gpiozero compute the chip itself."""
        _install()
        assert len(FakeLGPIOFactory.instances) == 1
        chip = FakeLGPIOFactory.instances[0].chip
        assert chip is not None, (
            "constructed LGPIOFactory() without a chip — this is the call that "
            "raises NameError inside gpiozero on a Pi 5"
        )
        assert isinstance(chip, int)

    def test_installs_factory_on_device(self):
        factory = _install()
        assert FakeDevice.pin_factory is factory

    def test_explicit_chip_is_honoured(self):
        _install(chip=4)
        assert FakeLGPIOFactory.instances[0].chip == 4

    def test_idempotent_and_does_not_replace_existing_factory(self):
        """Called from two trigger paths; the second must be a no-op."""
        first = _install()
        second = _install()
        assert first is second
        assert len(FakeLGPIOFactory.instances) == 1

    def test_missing_lgpio_raises_actionable_error(self):
        def boom():
            raise ImportError("No module named 'lgpio'")

        with patch("openflight.gpio_factory._load_gpiozero", side_effect=boom):
            with pytest.raises(RuntimeError) as exc:
                ensure_lgpio_pin_factory()
        assert "uv sync" in str(exc.value)


class TestMonitorInstallsFactory:
    """The IWR6843 monitor is what actually died in the field."""

    def _monitor(self, tmp_path, **kwargs):
        from openflight.iwr6843.monitor import IWR6843CaptureMonitor

        config = tmp_path / "radar.cfg"
        config.write_text("sensorStart\n", encoding="utf-8")

        class FakeRadar:
            port = "/dev/fake"

            def send_config(self, path):
                pass

            def close(self):
                pass

        return IWR6843CaptureMonitor(
            config_path=config,
            output_dir=tmp_path / "dumps",
            radar=FakeRadar(),
            **kwargs,
        )

    def test_real_button_path_installs_pin_factory_first(self, tmp_path):
        calls = []

        class SpyButton:
            def __init__(self, pin, pull_up, bounce_time):
                calls.append("button")

            def close(self):
                pass

        monitor = self._monitor(tmp_path)
        with (
            patch(
                "openflight.iwr6843.monitor.ensure_lgpio_pin_factory",
                side_effect=lambda: calls.append("factory"),
            ),
            patch.dict("sys.modules"),
        ):
            import sys
            import types

            fake_gpiozero = types.ModuleType("gpiozero")
            fake_gpiozero.Button = SpyButton
            sys.modules["gpiozero"] = fake_gpiozero
            monitor.start(armed=False)

        try:
            assert calls == ["factory", "button"], (
                "pin factory must be installed before the first gpiozero "
                f"Device is constructed, got {calls}"
            )
        finally:
            monitor.stop()

    def test_injected_button_factory_skips_pin_factory(self, tmp_path):
        """Tests and replay paths inject a double and need no real GPIO."""

        class FakeButton:
            def __init__(self, pin, pull_up, bounce_time):
                pass

            def close(self):
                pass

        monitor = self._monitor(tmp_path, button_factory=FakeButton)
        with patch("openflight.iwr6843.monitor.ensure_lgpio_pin_factory") as ensure:
            monitor.start(armed=False)
        try:
            ensure.assert_not_called()
        finally:
            monitor.stop()
