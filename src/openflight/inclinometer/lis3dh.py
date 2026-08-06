"""Minimal LIS3DH I2C driver for enclosure orientation readings."""

from __future__ import annotations

import time
from typing import Protocol

from .models import AccelerationSample


class SMBusLike(Protocol):  # pylint: disable=unnecessary-ellipsis
    """Subset of smbus2 used by the driver, allowing deterministic tests."""

    def read_byte_data(self, address: int, register: int) -> int:
        """Read one register byte."""
        ...  # pylint: disable=unnecessary-ellipsis

    def write_byte_data(self, address: int, register: int, value: int) -> None:
        """Write one register byte."""
        ...  # pylint: disable=unnecessary-ellipsis

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        """Read a contiguous register block."""
        ...  # pylint: disable=unnecessary-ellipsis

    def close(self) -> None:
        """Close the bus."""
        ...  # pylint: disable=unnecessary-ellipsis


class LIS3DHIdentityError(RuntimeError):
    """Raised when the expected LIS3DH identity register is not present."""


class LIS3DH:
    """Read a LIS3DH configured for +/-2g high-resolution measurements."""

    DEFAULT_ADDRESS = 0x18
    WHO_AM_I = 0x0F
    WHO_AM_I_VALUE = 0x33
    CTRL_REG1 = 0x20
    CTRL_REG4 = 0x23
    OUT_X_L = 0x28
    AUTO_INCREMENT = 0x80

    def __init__(
        self,
        *,
        bus_number: int = 1,
        address: int = DEFAULT_ADDRESS,
        bus: SMBusLike | None = None,
    ):
        if bus is None:
            from smbus2 import SMBus  # pylint: disable=import-outside-toplevel,import-error

            bus = SMBus(bus_number)
        self.bus = bus
        self.bus_number = bus_number
        self.address = address
        self._closed = False

    def initialize(self) -> None:
        """Verify identity and enable 100 Hz, high-resolution XYZ sampling."""
        identity = self.bus.read_byte_data(self.address, self.WHO_AM_I)
        if identity != self.WHO_AM_I_VALUE:
            raise LIS3DHIdentityError(
                f"LIS3DH WHO_AM_I expected 0x{self.WHO_AM_I_VALUE:02x}, got 0x{identity:02x}"
            )
        self.bus.write_byte_data(self.address, self.CTRL_REG1, 0x57)
        self.bus.write_byte_data(self.address, self.CTRL_REG4, 0x88)

    @staticmethod
    def _axis_g(low: int, high: int) -> float:
        """Decode one left-aligned 12-bit high-resolution +/-2g axis."""
        raw = (high << 8) | low
        if raw & 0x8000:
            raw -= 1 << 16
        return (raw >> 4) * 0.001

    def read(self, *, timestamp: float | None = None) -> AccelerationSample:
        """Read one XYZ sample in units of gravity."""
        data = self.bus.read_i2c_block_data(
            self.address,
            self.OUT_X_L | self.AUTO_INCREMENT,
            6,
        )
        if len(data) != 6:
            raise OSError(f"LIS3DH returned {len(data)} data bytes; expected 6")
        return AccelerationSample(
            timestamp=time.time() if timestamp is None else timestamp,
            x_g=self._axis_g(data[0], data[1]),
            y_g=self._axis_g(data[2], data[3]),
            z_g=self._axis_g(data[4], data[5]),
        )

    def close(self) -> None:
        """Close the owned I2C bus."""
        if not self._closed:
            self.bus.close()
            self._closed = True
