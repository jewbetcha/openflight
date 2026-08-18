"""Power monitoring for supported OpenFlight installations."""

from .factory import (
    SUPPORTED_BATTERY_PROVIDERS,
    BatteryProvider,
    create_power_reader,
    normalize_battery_provider,
)
from .models import PowerSample, PowerState, PowerStatus
from .providers import GeekwormPowerReader, LinuxPowerReader
from .reader import PowerReader
from .service import PowerMonitor

__all__ = [
    "SUPPORTED_BATTERY_PROVIDERS",
    "BatteryProvider",
    "GeekwormPowerReader",
    "LinuxPowerReader",
    "PowerMonitor",
    "PowerReader",
    "PowerSample",
    "PowerState",
    "PowerStatus",
    "create_power_reader",
    "normalize_battery_provider",
]
