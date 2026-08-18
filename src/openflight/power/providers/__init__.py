"""Hardware-specific battery telemetry providers."""

from .geekworm import GeekwormPowerReader
from .linux import LinuxPowerReader

__all__ = ["GeekwormPowerReader", "LinuxPowerReader"]
