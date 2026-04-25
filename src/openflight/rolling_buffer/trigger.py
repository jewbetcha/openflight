"""
Trigger strategies for rolling buffer capture.

Defines different methods for determining when to capture the rolling buffer.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from .processor import RollingBufferProcessor
from .types import IQCapture

if TYPE_CHECKING:
    from ..ops243 import OPS243Radar

# Incremented per capture for log sequencing (not shot number)

logger = logging.getLogger("openflight.rolling_buffer.trigger")


class TriggerStrategy(ABC):
    """
    Base class for trigger strategies.

    A trigger strategy determines when to capture the rolling buffer.
    Different strategies trade off between simplicity, reliability, and efficiency.
    """

    def __init__(self, pre_trigger_segments: int = 12):
        self._diagnostics: List[dict] = []
        self.pre_trigger_segments = pre_trigger_segments

    def drain_diagnostics(self) -> List[dict]:
        """Return and clear accumulated diagnostic entries.

        Diagnostics are accumulated during wait_for_trigger() calls.
        The monitor drains these after each call to log and emit them.
        """
        diagnostics = self._diagnostics
        self._diagnostics = []
        return diagnostics

    def _append_diagnostic(
        self,
        accepted: bool,
        reason: str,
        response_bytes: int = 0,
        total_readings: int = 0,
        outbound_readings: int = 0,
        inbound_readings: int = 0,
        peak_outbound_mph: float = 0.0,
        peak_inbound_mph: float = 0.0,
        all_outbound_speeds: Optional[List[float]] = None,
        all_inbound_speeds: Optional[List[float]] = None,
        peak_outbound_magnitude: float = 0.0,
        peak_inbound_magnitude: float = 0.0,
        trigger_latency_ms: Optional[float] = None,
    ):
        """Append a diagnostic entry for the current trigger event."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "accepted": accepted,
            "reason": reason,
            "response_bytes": response_bytes,
            "total_readings": total_readings,
            "outbound_readings": outbound_readings,
            "inbound_readings": inbound_readings,
            "peak_outbound_mph": peak_outbound_mph,
            "peak_inbound_mph": peak_inbound_mph,
            "all_outbound_speeds": all_outbound_speeds or [],
            "all_inbound_speeds": all_inbound_speeds or [],
            "peak_outbound_magnitude": peak_outbound_magnitude,
            "peak_inbound_magnitude": peak_inbound_magnitude,
        }
        if trigger_latency_ms is not None:
            entry["trigger_latency_ms"] = trigger_latency_ms
        self._diagnostics.append(entry)

    def _log_capture(self, capture: IQCapture, accepted: bool):
        """No-op: capture logging moved to monitor (with processed speed data).

        Kept as no-op to avoid breaking subclass call sites.
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
        pre_trigger_segments: int = 12,
    ):
        """
        Initialize polling trigger.

        Args:
            poll_interval: Seconds between poll attempts (default 0.3s for faster response)
            min_readings: Minimum outbound readings above min_speed (default 1)
            min_speed_mph: Minimum speed to consider activity (default 15 mph)
            pre_trigger_segments: Number of pre-trigger segments for re-arm (0-32)
        """
        super().__init__(pre_trigger_segments=pre_trigger_segments)
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
                capture_timestamp = time.time()
                response = radar.trigger_capture(timeout=10.0)

                # Re-arm for next capture (sensor goes to idle after output)
                radar.rearm_rolling_buffer(self.pre_trigger_segments)

                # Parse response
                capture = processor.parse_capture(response, capture_timestamp=capture_timestamp)

                if capture is None:
                    time.sleep(self.poll_interval)
                    continue

                # Quick check for activity using standard processing
                timeline = processor.process_standard(capture)

                # Check for significant activity
                outbound = [
                    r
                    for r in timeline.readings
                    if r.is_outbound and r.speed_mph >= self.min_speed_mph
                ]

                if len(outbound) >= self.min_readings:
                    peak = max(r.speed_mph for r in outbound)
                    logger.info(
                        "[TRIGGER] Activity detected: %d readings, peak %.1f mph",
                        len(outbound),
                        peak,
                    )
                    return capture

                time.sleep(self.poll_interval)

            except Exception as e:
                logger.warning("[TRIGGER] Poll error: %s", e, exc_info=True)
                time.sleep(self.poll_interval)

        logger.info("[TRIGGER] Polling trigger timeout")
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
        pre_trigger_segments: int = 12,
    ):
        """
        Initialize threshold trigger.

        Args:
            speed_threshold_mph: Speed that triggers capture
            check_interval: Seconds between threshold checks
            settling_time: Time to wait after threshold before capture
            pre_trigger_segments: Number of pre-trigger segments for re-arm (0-32)
        """
        super().__init__(pre_trigger_segments=pre_trigger_segments)
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
                capture_timestamp = time.time()
                response = radar.trigger_capture(timeout=10.0)

                # Re-arm for next capture
                radar.rearm_rolling_buffer(self.pre_trigger_segments)

                capture = processor.parse_capture(response, capture_timestamp=capture_timestamp)

                if capture is None:
                    time.sleep(self.check_interval)
                    continue

                # Check for threshold speed
                timeline = processor.process_standard(capture)

                peak = timeline.peak_speed
                if peak and peak.is_outbound and peak.speed_mph >= self.speed_threshold_mph:
                    logger.info(
                        "[TRIGGER] Threshold triggered: %.1f mph >= %.1f mph",
                        peak.speed_mph,
                        self.speed_threshold_mph,
                    )
                    self._triggered = True

                    # Brief settling time for ball to clear
                    time.sleep(self.settling_time)

                    # Capture again for complete swing data
                    final_capture_timestamp = time.time()
                    response = radar.trigger_capture(timeout=10.0)
                    radar.rearm_rolling_buffer(self.pre_trigger_segments)
                    final_capture = processor.parse_capture(
                        response,
                        capture_timestamp=final_capture_timestamp,
                    )

                    return final_capture or capture

                time.sleep(self.check_interval)

            except Exception as e:
                logger.warning("[TRIGGER] Threshold check error: %s", e, exc_info=True)
                time.sleep(self.check_interval)

        logger.info("[TRIGGER] Threshold trigger timeout")
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

    def __init__(self, pre_trigger_segments: int = 12):
        super().__init__(pre_trigger_segments=pre_trigger_segments)
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
                logger.info("[TRIGGER] Manual trigger activated")

                capture_timestamp = time.time()
                response = radar.trigger_capture(timeout=10.0)
                radar.rearm_rolling_buffer(self.pre_trigger_segments)
                return processor.parse_capture(response, capture_timestamp=capture_timestamp)

            time.sleep(0.1)

        logger.info("[TRIGGER] Manual trigger timeout")
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
        pre_trigger_segments: int = 0,  # Speed trigger defaults to 0 (no pre-trigger)
    ):
        """
        Initialize speed-triggered capture.

        Args:
            min_trigger_speed_mph: Minimum speed to trigger capture (default 20mph)
            min_ball_speed_mph: Minimum ball speed to consider valid shot (default 35mph)
            trigger_to_capture_delay_ms: Delay after trigger before capture (default 15ms)
                This allows ball impact to happen before we dump the buffer.
            pre_trigger_segments: Pre-trigger segments (default 0 for speed trigger)
        """
        super().__init__(pre_trigger_segments=pre_trigger_segments)
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
        logger.info(
            "[TRIGGER] Waiting for speed trigger >= %.1f mph...", self.min_trigger_speed_mph
        )

        while (time.time() - start_time) < timeout:
            # Non-blocking speed read
            reading = radar.read_speed_nonblocking()

            if reading and reading.speed >= self.min_trigger_speed_mph:
                # Speed detected - this is likely the club
                self._last_trigger_speed = reading.speed
                trigger_time = time.time()

                logger.info(
                    "[TRIGGER] Speed trigger: %.1f mph %s detected, switching to rolling buffer...",
                    reading.speed,
                    reading.direction.value,
                )

                # Immediately switch to rolling buffer mode
                radar.switch_to_rolling_buffer()

                # Wait for ball impact
                # Club to ball is typically 20-40ms, we wait a portion of that
                delay_sec = self.trigger_to_capture_delay_ms / 1000.0
                time.sleep(delay_sec)

                # Capture the rolling buffer
                capture_trigger_time = time.time()
                response = radar.trigger_capture(timeout=5.0)
                capture = processor.parse_capture(
                    response,
                    capture_timestamp=capture_trigger_time,
                )

                # Calculate timing
                capture_time = time.time()
                total_delay_ms = (capture_time - trigger_time) * 1000
                logger.info("[TRIGGER] Buffer captured %.1fms after trigger", total_delay_ms)

                if capture:
                    # Validate capture has ball speed
                    timeline = processor.process_standard(capture)
                    outbound = [
                        r
                        for r in timeline.readings
                        if r.is_outbound and r.speed_mph >= self.min_ball_speed_mph
                    ]

                    if outbound:
                        peak = max(r.speed_mph for r in outbound)
                        logger.info("[TRIGGER] Ball detected: %.1f mph in capture", peak)

                        # Mark for reconfigure on next call
                        self._needs_reconfigure = True
                        return capture
                    else:
                        logger.info(
                            "[TRIGGER] No speed >= %.1f mph in capture", self.min_ball_speed_mph
                        )

                # Reconfigure for speed mode and continue
                self._needs_reconfigure = True
                radar.configure_for_speed_trigger()
                if radar.serial:
                    radar.serial.reset_input_buffer()

            # Brief sleep to avoid busy-waiting but stay responsive
            time.sleep(0.002)  # 2ms = 500Hz poll rate

        logger.info("[TRIGGER] Speed trigger timeout")
        return None

    def reset(self):
        """Reset trigger state and mark for reconfiguration."""
        self._last_trigger_speed = 0
        self._needs_reconfigure = True

    @property
    def last_trigger_speed(self) -> float:
        """Get the speed that triggered the last capture (likely club speed)."""
        return self._last_trigger_speed


class GPIOSoundTrigger(TriggerStrategy):
    """
    GPIO-assisted sound trigger using SparkFun SEN-14262.

    Wiring: SEN-14262 GATE → Pi GPIO pin (default: GPIO17, physical pin 11)

    IMPORTANT: Rolling buffer mode must be configured BEFORE using this trigger.
    Call radar.configure_for_rolling_buffer() or radar.enter_rolling_buffer_mode()
    before calling wait_for_trigger().

    This is a workaround for voltage level issues where the SEN-14262 GATE
    doesn't reach the 3.3V threshold required by HOST_INT. The Pi GPIO has
    a lower voltage threshold (~1.8V vs ~2.0V), making it more reliable.

    How it works:
        1. Pi GPIO detects rising edge on GATE (lower voltage threshold)
        2. Python sends S! command to radar to trigger buffer dump
        3. Script reads and processes I/Q data

    Requires: gpiozero library (uv pip install gpiozero lgpio)
    """

    def __init__(
        self,
        gpio_pin: int = 17,
        pre_trigger_segments: int = 32,
        debounce_ms: int = 20,
    ):
        """
        Initialize GPIO-assisted sound trigger.

        Args:
            gpio_pin: GPIO pin (BCM numbering) for GATE input (default: 17)
            pre_trigger_segments: Number of pre-trigger segments for S# command.
                Each segment = 128 samples = ~4.27ms at 30ksps.
                Default 20 gives ~85ms pre-trigger, ~51ms post-trigger.
                NOTE: This is passed to enter_rolling_buffer_mode() by the caller.
                The trigger does NOT configure rolling buffer mode itself.
            debounce_ms: Debounce time in ms to ignore rapid triggers (default: 200)
        """
        super().__init__(pre_trigger_segments=pre_trigger_segments)
        self.gpio_pin = gpio_pin
        self.debounce_ms = debounce_ms
        self._button = None
        self._trigger_event = {"triggered": False, "edge_time": 0.0}
        self._gpio_initialized = False

    def _init_gpio(self):
        """Initialize GPIO - called lazily on first wait_for_trigger."""
        if self._gpio_initialized:
            return True

        try:
            from gpiozero import Button  # pylint: disable=import-outside-toplevel
        except ImportError:
            logger.error(
                "[TRIGGER] gpiozero not available. Install with: uv pip install gpiozero lgpio"
            )
            return False

        def on_trigger():
            self._trigger_event["edge_time"] = time.time()
            self._trigger_event["triggered"] = True

        self._button = Button(self.gpio_pin, pull_up=False, bounce_time=self.debounce_ms / 1000.0)
        self._button.when_pressed = on_trigger
        self._gpio_initialized = True

        logger.info(
            "[TRIGGER] GPIO%d configured for sound trigger (debounce=%dms)",
            self.gpio_pin,
            self.debounce_ms,
        )
        return True

    def wait_for_trigger(
        self,
        radar: "OPS243Radar",
        processor: RollingBufferProcessor,
        timeout: float = 30.0,
    ) -> Optional[IQCapture]:
        """
        Wait for GPIO sound trigger and capture buffer.

        PREREQUISITE: Rolling buffer mode must already be configured via
        radar.configure_for_rolling_buffer() or radar.enter_rolling_buffer_mode().

        Unlike direct SoundTrigger (HOST_INT), this uses Pi GPIO to detect
        the SEN-14262 GATE signal, then sends S! to trigger the capture.
        """
        if not self._init_gpio():
            logger.error("[TRIGGER] GPIO initialization failed")
            return None

        logger.info(
            "[TRIGGER] Waiting for GPIO sound trigger on GPIO%d (timeout=%.0fs, S#%s)...",
            self.gpio_pin,
            timeout,
            self.pre_trigger_segments,
        )

        start_time = time.time()
        self._trigger_event["triggered"] = False

        while (time.time() - start_time) < timeout:
            if self._trigger_event["triggered"]:
                edge_time = self._trigger_event["edge_time"]
                self._trigger_event["triggered"] = False

                # Measure edge-to-S! latency (from GPIO callback to now)
                capture_timestamp = time.time()
                trigger_latency = (capture_timestamp - edge_time) * 1000
                logger.info(
                    "[TRIGGER] GPIO edge detected on GPIO%d (%.1fms ago), sending S! trigger...",
                    self.gpio_pin,
                    trigger_latency,
                )
                response = radar.trigger_capture(timeout=5.0)

                if not response:
                    logger.warning(
                        "[TRIGGER] No response from radar after S! (%.1fms after edge)",
                        trigger_latency,
                    )
                    self._append_diagnostic(
                        accepted=False,
                        reason="no_response",
                        response_bytes=0,
                        trigger_latency_ms=trigger_latency,
                    )
                    radar.rearm_rolling_buffer(self.pre_trigger_segments)
                    logger.debug("[TRIGGER] Discarding GPIO edges during re-arm")
                    self._trigger_event["triggered"] = False  # discard edges during rearm
                    continue

                response_len = len(response)
                logger.info(
                    "[TRIGGER] Capture received, %d bytes (S! sent %.1fms after edge)",
                    response_len,
                    trigger_latency,
                )
                if response_len < 5000:
                    logger.debug("[TRIGGER] Response content: %s", repr(response))
                else:
                    logger.debug("[TRIGGER] Response preview: %s...", repr(response[:500]))

                # Re-arm for next capture
                radar.rearm_rolling_buffer(self.pre_trigger_segments)
                logger.debug("[TRIGGER] Discarding GPIO edges during re-arm")
                self._trigger_event["triggered"] = False  # discard edges during rearm

                capture = processor.parse_capture(response, capture_timestamp=capture_timestamp)

                if not capture:
                    logger.warning("[TRIGGER] Failed to parse capture (%d bytes)", response_len)
                    self._append_diagnostic(
                        accepted=False,
                        reason="parse_failed",
                        response_bytes=response_len,
                        trigger_latency_ms=trigger_latency,
                    )
                    continue

                # Log raw I/Q for ALL triggers (accepted or rejected) for offline analysis
                self._log_capture(capture, accepted=False)  # updated to True below if accepted

                # Quick validation: does the capture contain any real swing data?
                timeline = processor.process_standard(capture)
                all_readings = timeline.readings
                all_outbound = [r for r in all_readings if r.is_outbound]
                all_inbound = [r for r in all_readings if not r.is_outbound]
                outbound_speeds = [r.speed_mph for r in all_outbound]
                inbound_speeds = [r.speed_mph for r in all_inbound]
                peak_outbound = max(outbound_speeds, default=0)
                peak_inbound = max(inbound_speeds, default=0)
                peak_out_mag = max((r.magnitude for r in all_outbound), default=0)
                peak_in_mag = max((r.magnitude for r in all_inbound), default=0)

                outbound_valid = [r for r in all_outbound if r.speed_mph >= 15.0]

                if not outbound_valid:
                    logger.info(
                        "[TRIGGER] GPIO trigger rejected — no outbound speed >= 15 mph "
                        "(peak=%.1f mph, %d readings)",
                        peak_outbound,
                        len(all_readings),
                    )
                    self._append_diagnostic(
                        accepted=False,
                        reason="no_outbound_speed",
                        response_bytes=response_len,
                        total_readings=len(all_readings),
                        outbound_readings=len(all_outbound),
                        inbound_readings=len(all_inbound),
                        peak_outbound_mph=peak_outbound,
                        peak_inbound_mph=peak_inbound,
                        all_outbound_speeds=outbound_speeds,
                        all_inbound_speeds=inbound_speeds,
                        peak_outbound_magnitude=peak_out_mag,
                        peak_inbound_magnitude=peak_in_mag,
                        trigger_latency_ms=trigger_latency,
                    )
                    continue

                peak = max(r.speed_mph for r in outbound_valid)
                logger.info(
                    "[TRIGGER] GPIO trigger accepted — peak %.1f mph, %d outbound readings",
                    peak,
                    len(outbound_valid),
                )
                self._append_diagnostic(
                    accepted=True,
                    reason="accepted",
                    response_bytes=response_len,
                    total_readings=len(all_readings),
                    outbound_readings=len(all_outbound),
                    inbound_readings=len(all_inbound),
                    peak_outbound_mph=peak_outbound,
                    peak_inbound_mph=peak_inbound,
                    all_outbound_speeds=outbound_speeds,
                    all_inbound_speeds=inbound_speeds,
                    peak_outbound_magnitude=peak_out_mag,
                    peak_inbound_magnitude=peak_in_mag,
                    trigger_latency_ms=trigger_latency,
                )

                return capture

            time.sleep(0.001)  # 1ms poll interval — latency-critical path

        logger.info("[TRIGGER] GPIO sound trigger timeout — no trigger received")
        return None

    def reset(self):
        """Reset trigger state."""
        self._trigger_event["triggered"] = False

    def cleanup(self):
        """Clean up GPIO resources."""
        if self._button:
            self._button.close()
            self._button = None
            self._gpio_initialized = False


class SoundTrigger(TriggerStrategy):
    """
    Hardware sound trigger using SparkFun SEN-14262.

    IMPORTANT: Rolling buffer mode must be configured BEFORE using this trigger.
    Call radar.configure_for_rolling_buffer() or radar.enter_rolling_buffer_mode()
    before calling wait_for_trigger().

    Wiring: SEN-14262 GATE → OPS243-A J3 Pin 3 (HOST_INT)
    The GATE output goes HIGH on loud sound (club impact).
    OPS243-A uses rising edge detection on HOST_INT as trigger.

    No software trigger (S!) needed — the radar triggers itself
    via hardware. We just need to wait for data to appear on serial.

    Note: If GATE voltage doesn't reach 3.3V threshold, use GPIOSoundTrigger
    instead, which uses Pi GPIO (lower threshold) + software S! trigger.
    """

    def __init__(
        self,
        pre_trigger_segments: int = 12,
    ):
        """
        Initialize sound trigger.

        Args:
            pre_trigger_segments: Number of pre-trigger segments for S# command.
                Each segment = 128 samples = ~4.27ms at 30ksps.
                Default 12 gives ~51ms pre-trigger, ~85ms post-trigger.
                NOTE: This is passed to enter_rolling_buffer_mode() by the caller.
                The trigger does NOT configure rolling buffer mode itself.
        """
        super().__init__(pre_trigger_segments=pre_trigger_segments)

    def wait_for_trigger(
        self,
        radar: "OPS243Radar",
        processor: RollingBufferProcessor,
        timeout: float = 30.0,
    ) -> Optional[IQCapture]:
        """
        Wait for hardware sound trigger and capture buffer.

        PREREQUISITE: Rolling buffer mode must already be configured via
        radar.configure_for_rolling_buffer() or radar.enter_rolling_buffer_mode().

        Unlike other triggers, no S! command is sent. The radar's
        HOST_INT pin receives the trigger from the SEN-14262 GATE
        output, causing the radar to dump its rolling buffer automatically.
        We just block on serial read waiting for the I/Q data to arrive.
        """
        logger.info("[TRIGGER] Waiting for sound trigger (timeout=%.0fs)...", timeout)

        response = radar.wait_for_hardware_trigger(timeout=timeout)

        if not response:
            logger.info("[TRIGGER] Sound trigger timeout — no hardware trigger received")
            return None

        response_len = len(response)
        logger.info("[TRIGGER] Sound trigger fired, %d bytes received", response_len)

        # Re-arm for next capture
        radar.rearm_rolling_buffer(self.pre_trigger_segments)

        capture = processor.parse_capture(
            response,
            capture_timestamp=radar.last_hardware_trigger_time,
        )

        if not capture:
            logger.warning("[TRIGGER] Sound trigger parse failed (%d bytes received)", response_len)
            self._append_diagnostic(
                accepted=False,
                reason="parse_failed",
                response_bytes=response_len,
            )
            return None

        # Log raw I/Q for ALL triggers for offline analysis
        self._log_capture(capture, accepted=False)

        # Quick validation: does the capture contain any real swing data?
        # At a driving range, a nearby player's impact sound can trip the
        # trigger even though nothing was moving in front of our radar.
        # Discard these false triggers immediately so we re-arm fast.
        timeline = processor.process_standard(capture)
        all_readings = timeline.readings
        all_outbound = [r for r in all_readings if r.is_outbound]
        all_inbound = [r for r in all_readings if not r.is_outbound]
        outbound_speeds = [r.speed_mph for r in all_outbound]
        inbound_speeds = [r.speed_mph for r in all_inbound]
        peak_outbound = max(outbound_speeds, default=0)
        peak_inbound = max(inbound_speeds, default=0)
        peak_out_mag = max((r.magnitude for r in all_outbound), default=0)
        peak_in_mag = max((r.magnitude for r in all_inbound), default=0)

        outbound_valid = [r for r in all_outbound if r.speed_mph >= 15.0]

        if not outbound_valid:
            logger.info(
                "[TRIGGER] Sound trigger rejected — no outbound speed >= 15 mph (peak=%.1f mph, %d readings)",
                peak_outbound,
                len(all_readings),
            )
            self._append_diagnostic(
                accepted=False,
                reason="no_outbound_speed",
                response_bytes=response_len,
                total_readings=len(all_readings),
                outbound_readings=len(all_outbound),
                inbound_readings=len(all_inbound),
                peak_outbound_mph=peak_outbound,
                peak_inbound_mph=peak_inbound,
                all_outbound_speeds=outbound_speeds,
                all_inbound_speeds=inbound_speeds,
                peak_outbound_magnitude=peak_out_mag,
                peak_inbound_magnitude=peak_in_mag,
            )
            return None

        peak = max(r.speed_mph for r in outbound_valid)
        logger.info(
            "[TRIGGER] Sound trigger accepted — peak %.1f mph, %d outbound readings",
            peak,
            len(outbound_valid),
        )
        self._append_diagnostic(
            accepted=True,
            reason="accepted",
            response_bytes=response_len,
            total_readings=len(all_readings),
            outbound_readings=len(all_outbound),
            inbound_readings=len(all_inbound),
            peak_outbound_mph=peak_outbound,
            peak_inbound_mph=peak_inbound,
            all_outbound_speeds=outbound_speeds,
            all_inbound_speeds=inbound_speeds,
            peak_outbound_magnitude=peak_out_mag,
            peak_inbound_magnitude=peak_in_mag,
        )

        return capture

    def reset(self):
        """Reset trigger state."""
        pass  # No state to reset


def create_trigger(trigger_type: str = "speed", **kwargs) -> TriggerStrategy:
    """
    Factory function to create trigger strategy.

    Args:
        trigger_type: "speed" (recommended), "polling", "threshold", "manual",
                      "sound", or "sound-gpio"
        **kwargs: Arguments passed to trigger constructor

    Returns:
        Configured TriggerStrategy instance

    Trigger types:
        - "speed": Fast speed detection triggers rolling buffer capture.
                   Recommended by OmniPreSense for golf. ~5-6ms response time.
        - "polling": Continuously capture and check for activity. Simple but slow.
        - "threshold": Speed threshold triggers capture. Less efficient than "speed".
        - "manual": External trigger for testing.
        - "sound": Hardware sound trigger via SparkFun SEN-14262 GATE → HOST_INT.
                   Requires GATE voltage to reach 3.3V threshold.
        - "sound-gpio": GPIO-assisted sound trigger via Pi GPIO + S! command.
                        Use when GATE voltage doesn't reach HOST_INT threshold.
                        Requires gpiozero library.
    """
    triggers = {
        "speed": SpeedTriggeredCapture,
        "polling": PollingTrigger,
        "threshold": ThresholdTrigger,
        "manual": ManualTrigger,
        "sound": SoundTrigger,
        "sound-gpio": GPIOSoundTrigger,
    }

    if trigger_type not in triggers:
        raise ValueError(
            f"Unknown trigger type: {trigger_type}. Available: {list(triggers.keys())}"
        )

    return triggers[trigger_type](**kwargs)
