"""
Trigger strategies for rolling buffer capture.

Defines different methods for determining when to capture the rolling buffer.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from .types import IQCapture
from .processor import RollingBufferProcessor

if TYPE_CHECKING:
    from ..ops243 import OPS243Radar

logger = logging.getLogger("openflight.rolling_buffer.trigger")


class TriggerStrategy(ABC):
    """
    Base class for trigger strategies.

    A trigger strategy determines when to capture the rolling buffer.
    Different strategies trade off between simplicity, reliability, and efficiency.
    """

    @abstractmethod
    def wait_for_trigger(
        self,
        radar: "OPS243Radar",
        processor: RollingBufferProcessor,
        timeout: float = 30.0,
    ) -> Optional[IQCapture]:
        """
        Wait for trigger condition and capture buffer.

        Args:
            radar: Connected OPS243Radar instance in rolling buffer mode
            processor: Processor for parsing capture response
            timeout: Maximum time to wait for trigger

        Returns:
            IQCapture if triggered and captured, None if timeout or error
        """
        pass

    @abstractmethod
    def reset(self):
        """Reset trigger state for next capture."""
        pass


class PollingTrigger(TriggerStrategy):
    """
    Simple polling-based trigger.

    Continuously captures and checks for activity. Simple but
    less efficient than threshold-based triggers.

    Best for testing and development.
    """

    def __init__(
        self,
        poll_interval: float = 0.3,
        min_readings: int = 2,
        min_speed_mph: float = 15,
    ):
        """
        Initialize polling trigger.

        Args:
            poll_interval: Seconds between poll attempts (default 0.3s for faster response)
            min_readings: Minimum outbound readings above min_speed (default 2)
            min_speed_mph: Minimum speed to consider activity (default 15 mph)
        """
        self.poll_interval = poll_interval
        self.min_readings = min_readings
        self.min_speed_mph = min_speed_mph

    def wait_for_trigger(
        self,
        radar: "OPS243Radar",
        processor: RollingBufferProcessor,
        timeout: float = 30.0,
    ) -> Optional[IQCapture]:
        """Poll for activity and return capture when detected."""
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                # Trigger capture (10s timeout for large I/Q data transfer)
                response = radar.trigger_capture(timeout=10.0)

                # Re-arm for next capture (sensor goes to idle after output)
                radar.rearm_rolling_buffer()

                # Parse response
                capture = processor.parse_capture(response)

                if capture is None:
                    time.sleep(self.poll_interval)
                    continue

                # Quick check for activity using standard processing
                timeline = processor.process_standard(capture)

                # Debug: show timeline stats
                if timeline.readings:
                    speeds = [r.speed_mph for r in timeline.readings]
                    outbound_speeds = [r.speed_mph for r in timeline.readings if r.is_outbound]
                    peak_outbound = max(outbound_speeds) if outbound_speeds else 0
                    print(f"[DEBUG] Timeline: {len(timeline.readings)} readings, "
                          f"speeds {min(speeds):.1f}-{max(speeds):.1f} mph, "
                          f"peak outbound: {peak_outbound:.1f} mph (need >={self.min_speed_mph})")
                else:
                    print("[DEBUG] Timeline: 0 readings (no signal detected)")

                # Check for significant activity
                outbound = [r for r in timeline.readings
                            if r.is_outbound and r.speed_mph >= self.min_speed_mph]

                if len(outbound) >= self.min_readings:
                    peak = max(r.speed_mph for r in outbound)
                    print(f"[SHOT DETECTED] {len(outbound)} readings >= {self.min_speed_mph} mph, "
                          f"peak {peak:.1f} mph")
                    logger.info(f"Activity detected: {len(outbound)} readings, peak {peak:.1f} mph")
                    return capture

                time.sleep(self.poll_interval)

            except Exception as e:
                logger.warning(f"Poll error: {e}")
                time.sleep(self.poll_interval)

        logger.info("Polling trigger timeout")
        return None

    def reset(self):
        """No state to reset for polling trigger."""
        pass


class ThresholdTrigger(TriggerStrategy):
    """
    Speed threshold-based trigger.

    Uses a brief streaming check to detect when speed exceeds threshold,
    then immediately captures the rolling buffer.

    More efficient than polling but requires threshold tuning.
    """

    def __init__(
        self,
        speed_threshold_mph: float = 50,
        check_interval: float = 0.1,
        settling_time: float = 0.05,
    ):
        """
        Initialize threshold trigger.

        Args:
            speed_threshold_mph: Speed that triggers capture
            check_interval: Seconds between threshold checks
            settling_time: Time to wait after threshold before capture
        """
        self.speed_threshold_mph = speed_threshold_mph
        self.check_interval = check_interval
        self.settling_time = settling_time
        self._triggered = False

    def wait_for_trigger(
        self,
        radar: "OPS243Radar",
        processor: RollingBufferProcessor,
        timeout: float = 30.0,
    ) -> Optional[IQCapture]:
        """
        Wait for speed to exceed threshold, then capture.

        Note: This implementation uses polling-style capture since the
        radar's internal threshold trigger may not be available in G1 mode.
        For production use, consider external GPIO trigger.
        """
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                # Capture and check for threshold (10s timeout for large I/Q data)
                response = radar.trigger_capture(timeout=10.0)

                # Re-arm for next capture
                radar.rearm_rolling_buffer()

                capture = processor.parse_capture(response)

                if capture is None:
                    time.sleep(self.check_interval)
                    continue

                # Check for threshold speed
                timeline = processor.process_standard(capture)

                peak = timeline.peak_speed
                if peak and peak.is_outbound and peak.speed_mph >= self.speed_threshold_mph:
                    logger.info(f"Threshold triggered: {peak.speed_mph:.1f} mph "
                               f">= {self.speed_threshold_mph} mph")
                    self._triggered = True

                    # Brief settling time for ball to clear
                    time.sleep(self.settling_time)

                    # Capture again for complete swing data
                    response = radar.trigger_capture(timeout=10.0)
                    radar.rearm_rolling_buffer()
                    final_capture = processor.parse_capture(response)

                    return final_capture or capture

                time.sleep(self.check_interval)

            except Exception as e:
                logger.warning(f"Threshold check error: {e}")
                time.sleep(self.check_interval)

        logger.info("Threshold trigger timeout")
        return None

    def reset(self):
        """Reset triggered state."""
        self._triggered = False


class ManualTrigger(TriggerStrategy):
    """
    Manual trigger for testing.

    Waits for external signal (e.g., keyboard input, GPIO) before capturing.
    Useful for controlled testing scenarios.
    """

    def __init__(self):
        self._trigger_requested = False

    def request_trigger(self):
        """Request a capture (called externally)."""
        self._trigger_requested = True

    def wait_for_trigger(
        self,
        radar: "OPS243Radar",
        processor: RollingBufferProcessor,
        timeout: float = 30.0,
    ) -> Optional[IQCapture]:
        """Wait for manual trigger request."""
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            if self._trigger_requested:
                self._trigger_requested = False
                logger.info("Manual trigger activated")

                response = radar.trigger_capture(timeout=10.0)
                radar.rearm_rolling_buffer()
                return processor.parse_capture(response)

            time.sleep(0.1)

        logger.info("Manual trigger timeout")
        return None

    def reset(self):
        """Reset trigger request."""
        self._trigger_requested = False


def create_trigger(trigger_type: str = "polling", **kwargs) -> TriggerStrategy:
    """
    Factory function to create trigger strategy.

    Args:
        trigger_type: "polling", "threshold", or "manual"
        **kwargs: Arguments passed to trigger constructor

    Returns:
        Configured TriggerStrategy instance
    """
    triggers = {
        "polling": PollingTrigger,
        "threshold": ThresholdTrigger,
        "manual": ManualTrigger,
    }

    if trigger_type not in triggers:
        raise ValueError(f"Unknown trigger type: {trigger_type}. "
                        f"Available: {list(triggers.keys())}")

    return triggers[trigger_type](**kwargs)
