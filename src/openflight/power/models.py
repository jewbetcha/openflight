"""Shared battery and external-power telemetry models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class PowerState(str, Enum):
    """User-facing power states emitted to the OpenFlight UI."""

    PLUGGED_IN = "plugged_in"
    ON_BATTERY = "on_battery"
    LOW = "low"
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class PowerSample:
    """Minimum telemetry shared by every supported battery provider."""

    battery_percent: float
    battery_voltage_v: float
    external_power: bool


@dataclass(frozen=True)
class PowerStatus:
    """Power state sent to clients and session logs."""

    available: bool
    provider: str
    state: PowerState
    battery_percent: float | None
    battery_voltage_v: float | None
    external_power: bool | None
    updated_at: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible status payload."""
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload
