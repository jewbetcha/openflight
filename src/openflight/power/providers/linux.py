"""Reader for battery telemetry managed by Linux power_supply drivers."""

from __future__ import annotations

import math
from pathlib import Path

from ..models import PowerSample


class LinuxPowerReader:
    """Read battery and adapter state exposed by Linux power_supply drivers."""

    DEFAULT_POWER_SUPPLY_PATH = Path("/sys/class/power_supply")

    def __init__(self, *, power_supply_path: Path = DEFAULT_POWER_SUPPLY_PATH):
        self.power_supply_path = power_supply_path
        self.battery_path = self._find_supply(
            "Battery",
            required_files=("capacity", "voltage_now"),
        )
        self.mains_path = self._find_supply("Mains", required_files=("online",))

    def _find_supply(self, supply_type: str, *, required_files: tuple[str, ...]) -> Path:
        if not self.power_supply_path.is_dir():
            raise OSError(f"Linux power supply path is unavailable: {self.power_supply_path}")

        for candidate in sorted(self.power_supply_path.iterdir()):
            try:
                candidate_type = (candidate / "type").read_text(encoding="ascii").strip()
            except (OSError, UnicodeError):
                continue
            if candidate_type == supply_type and all(
                (candidate / filename).is_file() for filename in required_files
            ):
                return candidate

        raise OSError(f"Linux {supply_type} power supply is unavailable")

    @staticmethod
    def _read_number(path: Path) -> float:
        try:
            return float(path.read_text(encoding="ascii").strip())
        except (OSError, UnicodeError, ValueError) as error:
            raise OSError(f"Could not read Linux power telemetry from {path}: {error}") from error

    def read(self) -> PowerSample:
        """Read and validate one sample from Linux sysfs."""
        battery_percent = self._read_number(self.battery_path / "capacity")
        battery_voltage_v = self._read_number(self.battery_path / "voltage_now") / 1_000_000
        external_power_raw = self._read_number(self.mains_path / "online")

        if not math.isfinite(battery_percent) or battery_percent < 0.0:
            raise OSError(f"Linux battery percentage is invalid: {battery_percent:.2f}%")
        battery_percent = min(battery_percent, 100.0)
        if not 0.0 <= battery_voltage_v <= 5.0:
            raise OSError(f"Linux battery voltage is invalid: {battery_voltage_v:.3f}V")
        if external_power_raw not in (0.0, 1.0):
            raise OSError(f"Linux external power state is invalid: {external_power_raw}")

        return PowerSample(
            battery_percent=battery_percent,
            battery_voltage_v=battery_voltage_v,
            external_power=bool(external_power_raw),
        )

    def close(self) -> None:
        """Native sysfs reads do not hold resources between samples."""
