"""Tests for X1202/X1206 battery and adapter telemetry."""

import sys
from types import ModuleType

from openflight import gpio_factory
from openflight.power import (
    BatteryProvider,
    GeekwormPowerReader,
    LinuxPowerReader,
    PowerMonitor,
    PowerSample,
    PowerState,
    create_power_reader,
)


class FakeBus:
    def __init__(self, registers):
        self.registers = registers
        self.closed = False

    def read_i2c_block_data(self, address, register, length):
        assert address == 0x36
        assert length == 2
        return self.registers[register]

    def close(self):
        self.closed = True


class FakeInput:
    def __init__(self, value):
        self.value = value
        self.closed = False

    def close(self):
        self.closed = True


class SequenceReader:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.closed = False

    def read(self):
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self):
        self.closed = True


def test_reader_decodes_max17043_voltage_soc_and_adapter_state():
    bus = FakeBus({0x02: [0xC3, 0x00], 0x04: [65, 128]})
    ac_input = FakeInput(1)
    reader = GeekwormPowerReader(bus=bus, ac_input=ac_input)

    sample = reader.read()

    assert sample.battery_voltage_v == 3.9
    assert sample.battery_percent == 65.5
    assert sample.external_power is True


def test_reader_releases_i2c_and_gpio_resources_once():
    bus = FakeBus({0x02: [0, 0], 0x04: [0, 0]})
    ac_input = FakeInput(0)
    reader = GeekwormPowerReader(bus=bus, ac_input=ac_input)

    reader.close()
    reader.close()

    assert bus.closed is True
    assert ac_input.closed is True


def test_reader_treats_gpio6_as_active_high_with_a_fail_safe_pull_down(monkeypatch):
    created = {}

    class SpyInput(FakeInput):
        def __init__(self, pin, **kwargs):
            if kwargs.get("pull_up") is not None and kwargs.get("active_state") is not None:
                raise ValueError('Pin GPIO6 is not floating, but "active_state" is not None')
            super().__init__(value=1)
            created.update(pin=pin, **kwargs)

    fake_gpiozero = ModuleType("gpiozero")
    fake_gpiozero.DigitalInputDevice = SpyInput
    monkeypatch.setitem(sys.modules, "gpiozero", fake_gpiozero)
    monkeypatch.setattr(gpio_factory, "ensure_lgpio_pin_factory", lambda: None)

    reader = GeekwormPowerReader(
        bus=FakeBus({0x02: [0xC3, 0x00], 0x04: [50, 0]}),
    )

    assert created == {"pin": 6, "pull_up": False}
    assert reader.read().external_power is True


def test_native_reader_discovers_linux_battery_and_mains_devices(tmp_path):
    battery = tmp_path / "battery"
    battery.mkdir()
    (battery / "type").write_text("Battery\n", encoding="ascii")
    (battery / "capacity").write_text("47\n", encoding="ascii")
    (battery / "voltage_now").write_text("3787500\n", encoding="ascii")

    mains = tmp_path / "charger@0"
    mains.mkdir()
    (mains / "type").write_text("Mains\n", encoding="ascii")
    (mains / "online").write_text("1\n", encoding="ascii")

    reader = LinuxPowerReader(power_supply_path=tmp_path)

    assert reader.read() == PowerSample(
        battery_percent=47.0,
        battery_voltage_v=3.7875,
        external_power=True,
    )


def test_native_reader_clamps_small_capacity_overshoot_to_full(tmp_path):
    battery = tmp_path / "battery"
    battery.mkdir()
    (battery / "type").write_text("Battery\n", encoding="ascii")
    (battery / "capacity").write_text("101\n", encoding="ascii")
    (battery / "voltage_now").write_text("4200000\n", encoding="ascii")

    mains = tmp_path / "charger"
    mains.mkdir()
    (mains / "type").write_text("Mains\n", encoding="ascii")
    (mains / "online").write_text("1\n", encoding="ascii")

    reader = LinuxPowerReader(power_supply_path=tmp_path)

    assert reader.read() == PowerSample(
        battery_percent=100.0,
        battery_voltage_v=4.2,
        external_power=True,
    )


def test_native_reader_requires_battery_and_mains_devices(tmp_path):
    battery = tmp_path / "battery"
    battery.mkdir()
    (battery / "type").write_text("Battery\n", encoding="ascii")
    (battery / "capacity").write_text("47\n", encoding="ascii")
    (battery / "voltage_now").write_text("3787500\n", encoding="ascii")

    try:
        LinuxPowerReader(power_supply_path=tmp_path)
    except OSError as error:
        assert "Mains" in str(error)
    else:
        raise AssertionError("missing native mains device should fail")


def test_reader_factory_prefers_native_power_supply(tmp_path):
    battery = tmp_path / "battery"
    battery.mkdir()
    (battery / "type").write_text("Battery\n", encoding="ascii")
    (battery / "capacity").write_text("47\n", encoding="ascii")
    (battery / "voltage_now").write_text("3787500\n", encoding="ascii")
    mains = tmp_path / "charger@0"
    mains.mkdir()
    (mains / "type").write_text("Mains\n", encoding="ascii")
    (mains / "online").write_text("1\n", encoding="ascii")

    selected = create_power_reader(
        BatteryProvider.GEEKWORM,
        power_supply_path=tmp_path,
        provider_factory=lambda: (_ for _ in ()).throw(AssertionError("direct reader used")),
    )

    assert isinstance(selected, LinuxPowerReader)


def test_reader_factory_falls_back_when_native_power_supply_is_missing(tmp_path):
    direct_reader = SequenceReader([PowerSample(12.0, 3.5, False)])

    selected = create_power_reader(
        BatteryProvider.GEEKWORM,
        power_supply_path=tmp_path,
        provider_factory=lambda: direct_reader,
    )

    assert selected is direct_reader


def test_reader_factory_rejects_unknown_provider():
    try:
        create_power_reader("unknown")
    except ValueError as error:
        assert "Unsupported battery provider" in str(error)
    else:
        raise AssertionError("unknown battery provider should fail")


def test_monitor_classifies_plugged_low_and_critical_states():
    samples = [
        PowerSample(50.0, 3.8, True),
        PowerSample(20.0, 3.5, False),
        PowerSample(10.0, 3.3, False),
    ]

    assert [PowerMonitor._state_for(sample) for sample in samples] == [
        PowerState.PLUGGED_IN,
        PowerState.LOW,
        PowerState.CRITICAL,
    ]


def test_monitor_recovers_after_a_read_failure_and_logs_transitions():
    readers = [
        SequenceReader([OSError("I2C device 0x36 missing")]),
        SequenceReader([PowerSample(42.25, 3.72, False)]),
    ]
    emitted = []
    logged = []
    now = iter([0.0, 1.0])
    monitor = PowerMonitor(
        provider=BatteryProvider.GEEKWORM,
        on_status=emitted.append,
        on_log=logged.append,
        reader_factory=lambda: readers.pop(0),
        clock=lambda: next(now),
    )

    unavailable = monitor.poll_once()
    recovered = monitor.poll_once()

    assert unavailable.state is PowerState.UNAVAILABLE
    assert unavailable.provider == "geekworm"
    assert "0x36 missing" in unavailable.error
    assert recovered.state is PowerState.ON_BATTERY
    assert recovered.battery_percent == 42.2
    assert emitted == [unavailable, recovered]
    assert logged == [unavailable, recovered]


def test_monitor_throttles_unchanged_session_log_samples():
    reader = SequenceReader(
        [
            PowerSample(80.0, 4.0, False),
            PowerSample(79.0, 3.99, False),
            PowerSample(78.0, 3.98, False),
        ]
    )
    logged = []
    now = iter([0.0, 5.0, 65.0])
    monitor = PowerMonitor(
        provider=BatteryProvider.GEEKWORM,
        on_status=lambda _status: None,
        on_log=logged.append,
        reader_factory=lambda: reader,
        log_interval_s=60.0,
        clock=lambda: next(now),
    )

    monitor.poll_once()
    monitor.poll_once()
    monitor.poll_once()

    assert [status.battery_percent for status in logged] == [80.0, 78.0]
