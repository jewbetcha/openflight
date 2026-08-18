"""Background battery monitor with retry and log throttling."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from .factory import BatteryProvider, create_power_reader, normalize_battery_provider
from .models import PowerSample, PowerState, PowerStatus
from .reader import PowerReader

logger = logging.getLogger(__name__)


class PowerMonitor:
    """Poll one battery provider and publish application-level status."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        provider: BatteryProvider | str,
        on_status: Callable[[PowerStatus], None],
        on_log: Callable[[PowerStatus], None] | None = None,
        reader_factory: Callable[[], PowerReader] | None = None,
        poll_interval_s: float = 5.0,
        log_interval_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.provider = normalize_battery_provider(provider)
        self.on_status = on_status
        self.on_log = on_log
        self.reader_factory = reader_factory or (lambda: create_power_reader(self.provider))
        self.poll_interval_s = poll_interval_s
        self.log_interval_s = log_interval_s
        self.clock = clock
        self._reader: PowerReader | None = None
        self._status: PowerStatus | None = None
        self._last_log_key: tuple[PowerState, bool | None] | None = None
        self._last_log_at: float | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def status(self) -> PowerStatus | None:
        """Return the most recently published status."""
        with self._lock:
            return self._status

    @staticmethod
    def _state_for(sample: PowerSample) -> PowerState:
        if sample.external_power:
            return PowerState.PLUGGED_IN
        if sample.battery_percent <= 10.0:
            return PowerState.CRITICAL
        if sample.battery_percent <= 20.0:
            return PowerState.LOW
        return PowerState.ON_BATTERY

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _available_status(self, sample: PowerSample) -> PowerStatus:
        return PowerStatus(
            available=True,
            provider=self.provider.value,
            state=self._state_for(sample),
            battery_percent=round(sample.battery_percent, 1),
            battery_voltage_v=round(sample.battery_voltage_v, 3),
            external_power=sample.external_power,
            updated_at=self._timestamp(),
        )

    def _unavailable_status(self, error: Exception) -> PowerStatus:
        return PowerStatus(
            available=False,
            provider=self.provider.value,
            state=PowerState.UNAVAILABLE,
            battery_percent=None,
            battery_voltage_v=None,
            external_power=None,
            updated_at=self._timestamp(),
            error=str(error),
        )

    def _close_reader(self) -> None:
        if self._reader is None:
            return
        try:
            self._reader.close()
        except Exception:
            logger.warning("[POWER] Failed to close battery reader", exc_info=True)
        finally:
            self._reader = None

    def poll_once(self) -> PowerStatus:
        """Read and publish one status, recovering from hardware failures."""
        try:
            if self._reader is None:
                self._reader = self.reader_factory()
            status = self._available_status(self._reader.read())
        except Exception as error:  # Hardware access must never stop OpenFlight.
            logger.warning("[POWER] %s telemetry unavailable: %s", self.provider.value, error)
            self._close_reader()
            status = self._unavailable_status(error)

        with self._lock:
            self._status = status

        try:
            self.on_status(status)
        except Exception:
            logger.warning("[POWER] Status callback failed", exc_info=True)

        now = self.clock()
        log_key = (status.state, status.external_power)
        log_due = self._last_log_at is None or now - self._last_log_at >= self.log_interval_s
        if self.on_log and (log_key != self._last_log_key or log_due):
            try:
                self.on_log(status)
                self._last_log_key = log_key
                self._last_log_at = now
            except Exception:
                logger.warning("[POWER] Session log callback failed", exc_info=True)

        return status

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.poll_interval_s)
        self._close_reader()

    def start(self) -> None:
        """Start polling in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="battery-power", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop polling and release hardware resources."""
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=max(1.0, self.poll_interval_s + 1.0))
        self._close_reader()
