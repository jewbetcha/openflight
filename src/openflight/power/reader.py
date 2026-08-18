"""Common reader contract for battery and external-power providers."""

from typing import Protocol

from .models import PowerSample


class PowerReader(Protocol):  # pylint: disable=unnecessary-ellipsis
    """Hardware-independent telemetry reader used by the power monitor."""

    def read(self) -> PowerSample:
        """Read one battery and external-power sample."""
        ...  # pylint: disable=unnecessary-ellipsis

    def close(self) -> None:
        """Release resources held by the reader."""
        ...  # pylint: disable=unnecessary-ellipsis
