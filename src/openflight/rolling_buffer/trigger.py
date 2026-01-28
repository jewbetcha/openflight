"""
Trigger strategies for rolling buffer capture.

Defines different methods for determining when to capture the rolling buffer.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from .processor import RollingBufferProcessor
from .types import IQCapture

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
        min_readings: int = 1,
        min_speed_mph: float = 15,
    ):
        """
        Initialize polling trigger.

        Args:
            poll_interval: Seconds between poll attempts (default 0.3s for faster response)
            min_readings: Minimum outbound readings above min_speed (default 1)
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

                # Check for significant activity
                outbound = [r for r in timeline.readings
                            if r.is_outbound and r.speed_mph >= self.min_speed_mph]

                if len(outbound) >= self.min_readings:
                    peak = max(r.speed_mph for r in outbound)
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


class SpeedTriggeredCapture(TriggerStrategy):
    """
    Speed-triggered rolling buffer capture per OmniPreSense recommendation.

    This implements the manufacturer's recommended approach for golf:
    1. Run in fast speed detection mode (~150-200Hz report rate)
    2. When outbound speed >20mph detected, immediately switch to rolling buffer
    3. Capture ball impact and flight with S#0 (no pre-trigger history)

    Advantages over polling:
    - Much faster trigger response (~5-6ms vs 300ms+ polling)
    - Captures club speed in speed mode, ball in rolling buffer
    - Minimal data loss during mode switch

    Per manufacturer:
    "You'll lose a little data (~5-6ms) from the initial club speed detection
    time while the sensor determines there's probably a golf swing event to
    capture with the Rolling Buffer. But assuming the club speed detected to
    ball impact is around 20-40ms, that should be ok."
    """

    def __init__(
        self,
        min_trigger_speed_mph: float = 20.0,
        min_ball_speed_mph: float = 35.0,
        trigger_to_capture_delay_ms: float = 15.0,
    ):
        """
        Initialize speed-triggered capture.

        Args:
            min_trigger_speed_mph: Minimum speed to trigger capture (default 20mph)
            min_ball_speed_mph: Minimum ball speed to consider valid shot (default 35mph)
            trigger_to_capture_delay_ms: Delay after trigger before capture (default 15ms)
                This allows ball impact to happen before we dump the buffer.
        """
        self.min_trigger_speed_mph = min_trigger_speed_mph
        self.min_ball_speed_mph = min_ball_speed_mph
        self.trigger_to_capture_delay_ms = trigger_to_capture_delay_ms
        self._last_trigger_speed: float = 0
        self._needs_reconfigure = True

    def wait_for_trigger(
        self,
        radar: "OPS243Radar",
        processor: RollingBufferProcessor,
        timeout: float = 30.0,
    ) -> Optional[IQCapture]:
        """
        Wait for speed trigger, switch to rolling buffer, and capture.

        Flow:
        1. Configure radar for fast speed detection (if needed)
        2. Poll for speed readings at ~150-200Hz
        3. When speed >= threshold detected:
           a. Record club speed
           b. Switch to rolling buffer mode (GC + S#0)
           c. Wait for ball impact (~15-25ms)
           d. Trigger capture (S!)
        4. Return to speed detection mode for next shot
        """
        # Configure for speed trigger mode if needed
        if self._needs_reconfigure:
            radar.configure_for_speed_trigger()
            self._needs_reconfigure = False
            # Clear any buffered data from mode switch
            if radar.serial:
                radar.serial.reset_input_buffer()
            time.sleep(0.1)

        start_time = time.time()
        logger.info(f"Waiting for speed trigger >= {self.min_trigger_speed_mph} mph...")

        while (time.time() - start_time) < timeout:
            # Non-blocking speed read
            reading = radar.read_speed_nonblocking()

            if reading and reading.speed >= self.min_trigger_speed_mph:
                # Speed detected - this is likely the club
                self._last_trigger_speed = reading.speed
                trigger_time = time.time()

                logger.info(f"Trigger: {reading.speed:.1f} mph detected, "
                           f"switching to rolling buffer...")
                logger.info(f"{reading.speed:.1f} mph {reading.direction.value} - "
                            f"switching to rolling buffer")

                # Immediately switch to rolling buffer mode
                radar.switch_to_rolling_buffer()

                # Wait for ball impact
                # Club to ball is typically 20-40ms, we wait a portion of that
                delay_sec = self.trigger_to_capture_delay_ms / 1000.0
                time.sleep(delay_sec)

                # Capture the rolling buffer
                response = radar.trigger_capture(timeout=5.0)
                capture = processor.parse_capture(response)

                # Calculate timing
                capture_time = time.time()
                total_delay_ms = (capture_time - trigger_time) * 1000
                logger.info("Buffer captured %.1fms after trigger", total_delay_ms)

                if capture:
                    # Validate capture has ball speed
                    timeline = processor.process_standard(capture)
                    outbound = [r for r in timeline.readings
                               if r.is_outbound and r.speed_mph >= self.min_ball_speed_mph]

                    if outbound:
                        peak = max(r.speed_mph for r in outbound)
                        logger.info("Ball detected: %.1f mph in capture", peak)
                        logger.info(f"Ball detected: {peak:.1f} mph")

                        # Mark for reconfigure on next call
                        self._needs_reconfigure = True
                        return capture
                    else:
                        logger.info("No speed >= %.1f mph in capture", self.min_ball_speed_mph)
                        logger.warning("No ball speed found in capture")

                # Reconfigure for speed mode and continue
                self._needs_reconfigure = True
                radar.configure_for_speed_trigger()
                if radar.serial:
                    radar.serial.reset_input_buffer()

            # Brief sleep to avoid busy-waiting but stay responsive
            time.sleep(0.002)  # 2ms = 500Hz poll rate

        logger.info("Speed trigger timeout")
        return None

    def reset(self):
        """Reset trigger state and mark for reconfiguration."""
        self._last_trigger_speed = 0
        self._needs_reconfigure = True

    @property
    def last_trigger_speed(self) -> float:
        """Get the speed that triggered the last capture (likely club speed)."""
        return self._last_trigger_speed


def create_trigger(trigger_type: str = "speed", **kwargs) -> TriggerStrategy:
    """
    Factory function to create trigger strategy.

    Args:
        trigger_type: "speed" (recommended), "polling", "threshold", or "manual"
        **kwargs: Arguments passed to trigger constructor

    Returns:
        Configured TriggerStrategy instance

    Trigger types:
        - "speed": Fast speed detection triggers rolling buffer capture.
                   Recommended by OmniPreSense for golf. ~5-6ms response time.
        - "polling": Continuously capture and check for activity. Simple but slow.
        - "threshold": Speed threshold triggers capture. Less efficient than "speed".
        - "manual": External trigger for testing.
    """
    triggers = {
        "speed": SpeedTriggeredCapture,
        "polling": PollingTrigger,
        "threshold": ThresholdTrigger,
        "manual": ManualTrigger,
    }

    if trigger_type not in triggers:
        raise ValueError(f"Unknown trigger type: {trigger_type}. "
                        f"Available: {list(triggers.keys())}")

    return triggers[trigger_type](**kwargs)
