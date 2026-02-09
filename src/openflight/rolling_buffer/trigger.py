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
        pre_trigger_segments: int = 12,
        debounce_ms: int = 200,
    ):
        """
        Initialize GPIO-assisted sound trigger.

        Args:
            gpio_pin: GPIO pin (BCM numbering) for GATE input (default: 17)
            pre_trigger_segments: Number of pre-trigger segments for S# command.
                Each segment = 128 samples = ~4.27ms at 30ksps.
                Default 12 gives ~51ms pre-trigger, ~85ms post-trigger.
                NOTE: This is passed to enter_rolling_buffer_mode() by the caller.
                The trigger does NOT configure rolling buffer mode itself.
            debounce_ms: Debounce time in ms to ignore rapid triggers (default: 200)
        """
        self.gpio_pin = gpio_pin
        self.pre_trigger_segments = pre_trigger_segments
        self.debounce_ms = debounce_ms
        self._button = None
        self._trigger_event = {"triggered": False}
        self._gpio_initialized = False

    def _init_gpio(self):
        """Initialize GPIO - called lazily on first wait_for_trigger."""
        if self._gpio_initialized:
            return True

        try:
            from gpiozero import Button  # pylint: disable=import-outside-toplevel
        except ImportError:
            logger.error("gpiozero not available. Install with: uv pip install gpiozero lgpio")
            return False

        def on_trigger():
            self._trigger_event["triggered"] = True

        self._button = Button(
            self.gpio_pin,
            pull_up=False,
            bounce_time=self.debounce_ms / 1000.0
        )
        self._button.when_pressed = on_trigger
        self._gpio_initialized = True

        print(f"[GPIO] Pin {self.gpio_pin} configured for sound trigger (debounce={self.debounce_ms}ms)")
        logger.info(
            "GPIO%d configured for sound trigger (debounce=%dms)",
            self.gpio_pin, self.debounce_ms
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
            logger.error("GPIO initialization failed")
            return None

        print(f"[GPIO] Waiting for sound trigger on GPIO{self.gpio_pin}...")
        logger.info(
            "Waiting for GPIO sound trigger on GPIO%d (timeout=%ss, S#%s)...",
            self.gpio_pin, timeout, self.pre_trigger_segments
        )

        start_time = time.time()
        self._trigger_event["triggered"] = False

        while (time.time() - start_time) < timeout:
            if self._trigger_event["triggered"]:
                self._trigger_event["triggered"] = False
                print("[GPIO] Edge detected! Sending S! trigger...")
                logger.info("GPIO edge detected! Triggering radar capture...")

                # Send S! to trigger the radar capture
                response = radar.trigger_capture(timeout=5.0)

                if not response:
                    print("[GPIO] No response from radar!")
                    logger.warning("No response from radar after S! trigger")
                    radar.rearm_rolling_buffer()
                    time.sleep(0.3)  # Extra time for buffer to fill
                    continue

                print(f"[GPIO] Capture received: {len(response)} bytes")
                logger.info("Capture received, %d bytes", len(response))
                # Debug: log first 500 chars of response to see what we got
                if len(response) < 5000:
                    logger.info("Response content: %s", repr(response))
                else:
                    logger.info("Response preview: %s...", repr(response[:500]))

                # Re-arm for next capture
                radar.rearm_rolling_buffer()
                time.sleep(0.3)  # Extra time for buffer to fill before next trigger

                capture = processor.parse_capture(response)

                if not capture:
                    # Failed to parse - log and continue waiting for next trigger
                    logger.warning("Failed to parse capture, continuing to wait for next trigger...")
                    continue

                # Quick validation: does the capture contain any real swing data?
                timeline = processor.process_standard(capture)
                all_readings = timeline.readings
                outbound = [
                    r for r in all_readings
                    if r.is_outbound and r.speed_mph >= 15.0
                ]

                if not outbound:
                    # Log details about what WAS detected for debugging
                    all_outbound = [r for r in all_readings if r.is_outbound]
                    all_inbound = [r for r in all_readings if not r.is_outbound]
                    peak_outbound = max((r.speed_mph for r in all_outbound), default=0)
                    peak_inbound = max((r.speed_mph for r in all_inbound), default=0)
                    logger.info(
                        "GPIO trigger REJECTED: no swing >= 15 mph. "
                        "Total readings: %d, outbound: %d (peak %.1f mph), inbound: %d (peak %.1f mph). "
                        "Likely false trigger from nearby sound. Re-arming...",
                        len(all_readings), len(all_outbound), peak_outbound,
                        len(all_inbound), peak_inbound
                    )
                    # Continue waiting for next trigger instead of exiting
                    continue

                peak = max(r.speed_mph for r in outbound)
                logger.info(
                    "GPIO trigger ACCEPTED: %d outbound readings >= 15 mph, peak %.1f mph",
                    len(outbound), peak
                )

                return capture

            time.sleep(0.01)  # 10ms poll interval

        logger.info("GPIO sound trigger timeout - no trigger received")
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


class GPIOPassthroughTrigger(TriggerStrategy):
    """
    Ultra-low-latency GPIO passthrough trigger using Pi as voltage booster.

    IMPORTANT: Rolling buffer mode must be configured BEFORE using this trigger.
    Call radar.configure_for_rolling_buffer() or radar.enter_rolling_buffer_mode()
    before calling wait_for_trigger().

    Wiring:
        SEN-14262 GATE → Pi GPIO17 (input, default)
        Pi GPIO27 (output, default) → OPS243-A HOST_INT (J3 Pin 3)

    How it works:
        1. GATE goes HIGH (~2.5V) on sound detection
        2. Pi GPIO input detects edge (threshold ~1.8V, faster than HOST_INT)
        3. lgpio callback immediately sets GPIO output HIGH (3.3V)
        4. Radar HOST_INT receives clean 3.3V signal, triggers buffer dump
        5. Python waits for I/Q data on serial (existing wait_for_hardware_trigger)

    Trigger latency: ~10μs (hardware + C callback), vs 1-18ms for software S!

    Physical pin mapping:
        GPIO17 = Physical pin 11
        GPIO27 = Physical pin 13
        3.3V   = Physical pin 1
        GND    = Physical pin 6, 9, 14, 20, 25, 30, 34, 39

    Requires: lgpio library (uv pip install lgpio)
    """

    def __init__(
        self,
        input_pin: int = 17,
        output_pin: int = 27,
        pre_trigger_segments: int = 12,
        pulse_width_us: int = 100,
    ):
        """
        Initialize GPIO passthrough trigger.

        Args:
            input_pin: GPIO pin (BCM) for GATE input (default: 17, physical pin 11)
            output_pin: GPIO pin (BCM) for HOST_INT output (default: 27, physical pin 13)
            pre_trigger_segments: Number of pre-trigger segments for S# command.
                Each segment = 128 samples = ~4.27ms at 30ksps.
                Default 12 gives ~51ms pre-trigger, ~85ms post-trigger.
                NOTE: This is passed to enter_rolling_buffer_mode() by the caller.
                The trigger does NOT configure rolling buffer mode itself.
            pulse_width_us: Pulse width in microseconds (default: 100)
        """
        self.input_pin = input_pin
        self.output_pin = output_pin
        self.pre_trigger_segments = pre_trigger_segments
        self.pulse_width_us = pulse_width_us
        self._handle = None
        self._gpio_initialized = False

    def _init_gpio(self):
        """Initialize GPIO with lgpio for lowest latency."""
        if self._gpio_initialized:
            return True

        try:
            import lgpio  # pylint: disable=import-outside-toplevel
        except ImportError:
            logger.error("lgpio not available. Install with: uv pip install lgpio")
            return False

        try:
            self._handle = lgpio.gpiochip_open(0)

            # Configure input with pull-down and alert for edge detection
            lgpio.gpio_claim_alert(self._handle, self.input_pin, lgpio.RISING_EDGE, lgpio.SET_PULL_DOWN)

            # Configure output, initially LOW
            lgpio.gpio_claim_output(self._handle, self.output_pin, 0)

            # Store lgpio module reference for callback
            self._lgpio = lgpio

            # Set up edge callback - runs in lgpio's C thread for minimal latency
            def on_gate_rising(chip, gpio, level, tick):  # pylint: disable=unused-argument
                if level == 1:  # Rising edge
                    # Immediately pulse output HIGH - this is C-speed!
                    lgpio.gpio_write(self._handle, self.output_pin, 1)
                    time.sleep(self.pulse_width_us / 1_000_000)  # Brief pulse
                    lgpio.gpio_write(self._handle, self.output_pin, 0)

            self._callback_id = lgpio.callback(
                self._handle,
                self.input_pin,
                lgpio.RISING_EDGE,
                on_gate_rising
            )

            self._gpio_initialized = True
            logger.info(
                "GPIO passthrough configured: GPIO%d (in) → GPIO%d (out), pulse=%dμs",
                self.input_pin, self.output_pin, self.pulse_width_us
            )
            return True

        except Exception as e:
            logger.error("Failed to initialize GPIO passthrough: %s", e)
            if self._handle is not None:
                try:
                    lgpio.gpiochip_close(self._handle)
                except Exception:
                    pass
                self._handle = None
            return False

    def wait_for_trigger(
        self,
        radar: "OPS243Radar",
        processor: RollingBufferProcessor,
        timeout: float = 30.0,
    ) -> Optional[IQCapture]:
        """
        Wait for hardware trigger (fired by GPIO passthrough).

        PREREQUISITE: Rolling buffer mode must already be configured via
        radar.configure_for_rolling_buffer() or radar.enter_rolling_buffer_mode().

        The GPIO passthrough fires HOST_INT directly via hardware callback.
        We just wait for the radar to dump its buffer via serial.
        """
        if not self._init_gpio():
            logger.error("GPIO passthrough initialization failed")
            return None

        logger.info(
            "Waiting for GPIO passthrough trigger: GPIO%d→GPIO%d (timeout=%ss)...",
            self.input_pin, self.output_pin, timeout
        )

        # Use existing wait_for_hardware_trigger - radar triggered via HOST_INT
        response = radar.wait_for_hardware_trigger(timeout=timeout)

        if not response:
            logger.info("GPIO passthrough trigger timeout - no hardware trigger received")
            return None

        logger.info("Hardware trigger fired (via GPIO passthrough), received %d bytes", len(response))

        # Re-arm for next capture
        radar.rearm_rolling_buffer()

        capture = processor.parse_capture(response)

        if not capture:
            return None

        # Quick validation: does the capture contain any real swing data?
        timeline = processor.process_standard(capture)
        outbound = [
            r for r in timeline.readings
            if r.is_outbound and r.speed_mph >= 15.0
        ]

        if not outbound:
            logger.info("GPIO passthrough trigger: no swing detected in capture, re-arming")
            return None

        peak = max(r.speed_mph for r in outbound)
        logger.info("GPIO passthrough capture: %d readings, peak %.1f mph",
                   len(outbound), peak)

        return capture

    def reset(self):
        """Reset trigger state."""
        pass  # No state to reset

    def cleanup(self):
        """Clean up GPIO resources."""
        if self._handle is not None:
            try:
                import lgpio  # pylint: disable=import-outside-toplevel
                if hasattr(self, '_callback_id'):
                    lgpio.callback_cancel(self._callback_id)
                lgpio.gpiochip_close(self._handle)
            except Exception as e:
                logger.warning("Error cleaning up GPIO: %s", e)
            self._handle = None
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
        self.pre_trigger_segments = pre_trigger_segments

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
        print(f"[SOUND] Waiting for hardware trigger (timeout={timeout}s)...")
        logger.info(
            "Waiting for hardware sound trigger (timeout=%ss)...",
            timeout
        )

        response = radar.wait_for_hardware_trigger(timeout=timeout)

        if not response:
            print("[SOUND] Timeout - no hardware trigger received")
            logger.info("Sound trigger timeout - no hardware trigger received")
            return None

        print(f"[SOUND] Hardware trigger fired! Received {len(response)} bytes")
        logger.info("Hardware trigger fired, received %d bytes", len(response))

        # Re-arm for next capture
        radar.rearm_rolling_buffer()

        capture = processor.parse_capture(response)

        if not capture:
            return None

        # Quick validation: does the capture contain any real swing data?
        # At a driving range, a nearby player's impact sound can trip the
        # trigger even though nothing was moving in front of our radar.
        # Discard these false triggers immediately so we re-arm fast.
        timeline = processor.process_standard(capture)
        outbound = [
            r for r in timeline.readings
            if r.is_outbound and r.speed_mph >= 15.0
        ]

        if not outbound:
            logger.info("Sound trigger: no swing detected in capture, re-arming")
            return None

        peak = max(r.speed_mph for r in outbound)
        logger.info("Sound trigger capture: %d readings, peak %.1f mph",
                   len(outbound), peak)

        return capture

    def reset(self):
        """Reset trigger state."""
        pass  # No state to reset


def create_trigger(trigger_type: str = "speed", **kwargs) -> TriggerStrategy:
    """
    Factory function to create trigger strategy.

    Args:
        trigger_type: "speed" (recommended), "polling", "threshold", "manual",
                      "sound", "sound-gpio", or "sound-passthrough"
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
        - "sound-passthrough": Ultra-low-latency GPIO passthrough trigger.
                               Uses Pi as voltage booster: GATE → Pi GPIO (in) → Pi GPIO (out) → HOST_INT.
                               ~10μs trigger latency vs 1-18ms for software S! trigger.
                               Requires lgpio library.
    """
    triggers = {
        "speed": SpeedTriggeredCapture,
        "polling": PollingTrigger,
        "threshold": ThresholdTrigger,
        "manual": ManualTrigger,
        "sound": SoundTrigger,
        "sound-gpio": GPIOSoundTrigger,
        "sound-passthrough": GPIOPassthroughTrigger,
    }

    if trigger_type not in triggers:
        raise ValueError(f"Unknown trigger type: {trigger_type}. "
                        f"Available: {list(triggers.keys())}")

    return triggers[trigger_type](**kwargs)
