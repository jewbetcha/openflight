#!/usr/bin/env python3
"""
GPIO passthrough sound trigger tester for SEN-14262 + OPS243-A.

Uses Pi as a voltage booster: GATE → GPIO input → GPIO output → HOST_INT.
This bypasses Python for the trigger path - the lgpio callback fires at C-speed.

Wiring:
    SEN-14262 VCC  → 3.3V (Pi or radar)
    SEN-14262 GND  → GND (shared)
    SEN-14262 GATE → Pi GPIO17 (input, physical pin 11)
    Pi GPIO27      → OPS243-A HOST_INT (J3 Pin 3, physical pin 13)

How it works:
    1. GATE goes HIGH (~2.5V) on sound detection
    2. Pi GPIO input detects edge (threshold ~1.8V)
    3. lgpio C callback immediately pulses GPIO output HIGH (3.3V)
    4. Radar HOST_INT receives clean 3.3V signal, triggers buffer dump
    5. Python reads I/Q data from serial

Latency measurement:
    - sound_time: When lgpio callback fires (GATE edge detected)
    - data_time: When I/Q data arrives on serial
    - Difference shows total trigger-to-data latency

Usage:
    uv run python scripts/test_sound_trigger_passthrough.py
    uv run python scripts/test_sound_trigger_passthrough.py --gpio-input 17 --gpio-output 27
    uv run python scripts/test_sound_trigger_passthrough.py --swings-only
"""

import argparse
import sys
import threading
import time

# Add src to path so we can import openflight
sys.path.insert(0, "src")

# Try to import lgpio
LGPIO_AVAILABLE = False
try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    pass

if not LGPIO_AVAILABLE:
    print("ERROR: lgpio library required for GPIO passthrough.")
    print("Install with: pip install lgpio")
    print("On Raspberry Pi OS: sudo apt install python3-lgpio")
    sys.exit(1)

from openflight.ops243 import OPS243Radar  # noqa: E402
from openflight.rolling_buffer.processor import RollingBufferProcessor  # noqa: E402

# Radar constants (AN-027)
SAMPLES_PER_SEGMENT = 128
TOTAL_SEGMENTS = 32
SEGMENT_DURATION_MS = SAMPLES_PER_SEGMENT / 30000 * 1000  # ~4.27ms at 30ksps

# Default GPIO pins (BCM numbering)
DEFAULT_INPUT_PIN = 17   # Physical pin 11 - GATE input
DEFAULT_OUTPUT_PIN = 27  # Physical pin 13 - HOST_INT output


def gpio_to_physical(bcm_pin: int) -> int:
    """Convert BCM GPIO number to physical pin number."""
    bcm_to_physical = {
        2: 3, 3: 5, 4: 7, 17: 11, 27: 13, 22: 15,
        10: 19, 9: 21, 11: 23, 5: 29, 6: 31, 13: 33,
        19: 35, 26: 37, 14: 8, 15: 10, 18: 12, 23: 16,
        24: 18, 25: 22, 8: 24, 7: 26, 12: 32, 16: 36,
        20: 38, 21: 40,
    }
    return bcm_to_physical.get(bcm_pin, 0)


class PassthroughTriggerTester:
    """Tests the GPIO passthrough trigger with latency measurement."""

    def __init__(self, input_pin: int, output_pin: int, pulse_width_us: int = 100):
        self.input_pin = input_pin
        self.output_pin = output_pin
        self.pulse_width_us = pulse_width_us

        self._handle = None
        self._callback_id = None

        # Latency tracking
        self._sound_time = 0.0  # When GATE edge detected
        self._trigger_count = 0
        self._lock = threading.Lock()

    def setup(self):
        """Initialize GPIO passthrough."""
        print(f"Setting up GPIO passthrough: GPIO{self.input_pin} → GPIO{self.output_pin}")

        self._handle = lgpio.gpiochip_open(0)

        # Configure input with pull-down
        lgpio.gpio_claim_input(self._handle, self.input_pin, lgpio.SET_PULL_DOWN)

        # Configure output, initially LOW
        lgpio.gpio_claim_output(self._handle, self.output_pin, 0)

        # Set up edge callback - this fires in lgpio's C thread!
        def on_gate_rising(chip, gpio, level, tick):
            if level == 1:  # Rising edge
                with self._lock:
                    self._sound_time = time.perf_counter()
                    self._trigger_count += 1

                # Immediately pulse output HIGH - this is C-speed!
                lgpio.gpio_write(self._handle, self.output_pin, 1)
                time.sleep(self.pulse_width_us / 1_000_000)
                lgpio.gpio_write(self._handle, self.output_pin, 0)

        self._callback_id = lgpio.callback(
            self._handle,
            self.input_pin,
            lgpio.RISING_EDGE,
            on_gate_rising
        )

        print(f"  Input:  GPIO{self.input_pin} (physical pin {gpio_to_physical(self.input_pin)})")
        print(f"  Output: GPIO{self.output_pin} (physical pin {gpio_to_physical(self.output_pin)})")
        print(f"  Pulse:  {self.pulse_width_us}μs")

    def get_last_sound_time(self) -> tuple:
        """Get last sound detection time and trigger count."""
        with self._lock:
            return self._sound_time, self._trigger_count

    def cleanup(self):
        """Clean up GPIO resources."""
        if self._callback_id is not None:
            try:
                lgpio.callback_cancel(self._callback_id)
            except Exception:
                pass
        if self._handle is not None:
            try:
                lgpio.gpiochip_close(self._handle)
            except Exception:
                pass


def process_capture(processor: RollingBufferProcessor, response: str,
                    trigger_count: int, sound_to_data_ms: float,
                    pre_trigger_segments: int, swings_only: bool = False):
    """Process the I/Q buffer dump and display results."""
    pre_ms = pre_trigger_segments * SEGMENT_DURATION_MS
    post_ms = (TOTAL_SEGMENTS - pre_trigger_segments) * SEGMENT_DURATION_MS

    print()
    print("=" * 70)
    print(f"  TRIGGER #{trigger_count}")
    print("=" * 70)
    print(f"  Capture window: {pre_ms:.1f}ms pre / {post_ms:.1f}ms post (S#{pre_trigger_segments})")
    print(f"  Sound → Data latency: {sound_to_data_ms:.2f}ms")
    print(f"  Buffer size: {len(response)} bytes")

    # Parse the I/Q response
    capture = processor.parse_capture(response)

    if capture is None:
        print("  WARNING: Failed to parse I/Q data from buffer dump")
        print("=" * 70)
        print()
        return False, None

    print(f"  I/Q samples: {len(capture.i_samples)} I, {len(capture.q_samples)} Q")
    print(f"  Trigger offset: {capture.trigger_offset_ms:.1f}ms into buffer")

    # Run FFT processing
    timeline = processor.process_standard(capture)

    print()
    print(f"  Processed {len(timeline.readings)} speed readings:")
    print()

    # Show readings
    outbound_readings = []
    for reading in timeline.readings:
        direction = "OUT" if reading.is_outbound else " IN"
        marker = " <--" if reading.is_outbound and reading.speed_mph >= 15.0 else ""
        # Only show significant readings to reduce noise
        if reading.magnitude >= 10 or reading.speed_mph >= 10:
            print(f"    {reading.timestamp_ms:>6.1f}ms: {reading.speed_mph:>6.1f} mph "
                  f"{direction} (mag: {reading.magnitude:>6.1f}){marker}")
        if reading.is_outbound and reading.speed_mph >= 15.0:
            outbound_readings.append(reading)

    print()
    if not outbound_readings:
        if swings_only:
            print("  No swing detected — discarding (false trigger / nearby player)")
        else:
            print("  No swing detected (false trigger / nearby player)")
        print("=" * 70)
        print()
        return False, sound_to_data_ms

    peak_reading = max(outbound_readings, key=lambda r: r.speed_mph)
    print(f"  Peak outbound:  {peak_reading.speed_mph:.1f} mph "
          f"(at {peak_reading.timestamp_ms:.1f}ms, mag {peak_reading.magnitude:.1f})")
    print(f"  Outbound count: {len(outbound_readings)} readings >= 15 mph")
    print("=" * 70)
    print()
    return True, sound_to_data_ms


def run(port: str, input_pin: int, output_pin: int, pulse_width_us: int,
        pre_trigger_segments: int, swings_only: bool, timeout: float):
    """Connect to radar, configure rolling buffer, wait for GPIO passthrough triggers."""

    # --- Set up GPIO passthrough ---
    tester = PassthroughTriggerTester(input_pin, output_pin, pulse_width_us)
    tester.setup()

    # --- Connect to radar ---
    print()
    print("Connecting to radar...")
    radar = OPS243Radar(port=port if port else None)
    radar.connect()
    print(f"Connected on {radar.port}")

    # Get firmware info
    info = radar.get_info()
    version = info.get("Version", "unknown")
    print(f"Firmware: {version}")

    # --- Configure rolling buffer mode ---
    print(f"Configuring rolling buffer mode (S#{pre_trigger_segments})...")
    radar.configure_for_rolling_buffer()
    radar.set_trigger_split(pre_trigger_segments)

    # --- Set up FFT processor ---
    processor = RollingBufferProcessor()

    print()
    print("-" * 70)
    print("Configuration:")
    print(f"  Pre-trigger: S#{pre_trigger_segments} "
          f"({pre_trigger_segments * SEGMENT_DURATION_MS:.1f}ms pre, "
          f"{(TOTAL_SEGMENTS - pre_trigger_segments) * SEGMENT_DURATION_MS:.1f}ms post)")
    print(f"  Mode: {'swings only' if swings_only else 'all captures'}")
    print(f"  Timeout: {timeout}s")
    print()
    print("Wiring:")
    print(f"  SEN-14262 GATE → GPIO{input_pin} (physical pin {gpio_to_physical(input_pin)})")
    print(f"  GPIO{output_pin} → HOST_INT (physical pin {gpio_to_physical(output_pin)})")
    print("-" * 70)
    print()
    print("Waiting for sound trigger... (Ctrl+C to quit)")
    print()

    trigger_count = 0
    swing_count = 0
    latencies = []
    last_trigger_num = 0

    try:
        while True:
            # Wait for hardware trigger (data appears on serial when HOST_INT fires)
            response = radar.wait_for_hardware_trigger(timeout=timeout)

            # Record when data arrived
            data_time = time.perf_counter()

            # Get when sound was detected
            sound_time, current_trigger = tester.get_last_sound_time()

            # Check if this is a new trigger
            if current_trigger == last_trigger_num:
                # Timeout - no trigger received
                print(".", end="", flush=True)
                continue

            last_trigger_num = current_trigger

            if not response:
                print()
                print("WARNING: GPIO triggered but no radar data received")
                radar.rearm_rolling_buffer()
                continue

            trigger_count += 1

            # Calculate latency (sound detection to data arrival)
            if sound_time > 0:
                sound_to_data_ms = (data_time - sound_time) * 1000
            else:
                sound_to_data_ms = 0

            # Re-arm for next capture
            radar.rearm_rolling_buffer()

            # Process and display
            is_swing, latency = process_capture(
                processor, response, trigger_count, sound_to_data_ms,
                pre_trigger_segments, swings_only
            )

            if latency is not None:
                latencies.append(latency)

            if is_swing:
                swing_count += 1

            # Show running stats
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                min_latency = min(latencies)
                max_latency = max(latencies)
                print(f"Stats: {trigger_count} triggers, {swing_count} swings | "
                      f"Latency: avg={avg_latency:.1f}ms, min={min_latency:.1f}ms, max={max_latency:.1f}ms")
            else:
                print(f"Waiting for next trigger... ({trigger_count} triggers, {swing_count} swings)")
            print()

    except KeyboardInterrupt:
        print()
        print()
        print("=" * 70)
        print("  SESSION SUMMARY")
        print("=" * 70)
        print(f"  Total triggers: {trigger_count}")
        print(f"  Valid swings:   {swing_count}")
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            print()
            print("  Latency (sound detection → I/Q data received):")
            print(f"    Average: {avg_latency:.2f}ms")
            print(f"    Minimum: {min_latency:.2f}ms")
            print(f"    Maximum: {max_latency:.2f}ms")
        print("=" * 70)

    finally:
        print()
        print("Cleaning up...")
        tester.cleanup()
        radar.disable_rolling_buffer()
        radar.disconnect()
        print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="GPIO passthrough sound trigger test for SEN-14262 + OPS243-A",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Wiring:
  SEN-14262 VCC  → 3.3V (Pi or radar)
  SEN-14262 GND  → GND (shared with Pi)
  SEN-14262 GATE → Pi GPIO17 (physical pin 11) [input]
  Pi GPIO27      → OPS243-A HOST_INT J3 Pin 3 (physical pin 13) [output]

How it works:
  This script uses Pi GPIO as a hardware voltage booster. The lgpio
  callback fires in C (not Python), providing ~10μs trigger latency
  instead of ~1-18ms with the software S! trigger approach.

  When GATE goes HIGH (~2.5V, sound detected):
    1. lgpio C callback detects rising edge on GPIO17
    2. Callback immediately pulses GPIO27 HIGH (3.3V)
    3. Radar HOST_INT sees clean 3.3V edge, dumps buffer
    4. Python reads I/Q data from serial

Latency measurement:
  The script measures time from GPIO edge detection to I/Q data arrival.
  This includes: GPIO passthrough (~10μs) + radar processing + serial transfer.

Examples:
  # Default settings (GPIO17 in, GPIO27 out)
  uv run python scripts/test_sound_trigger_passthrough.py

  # Use different GPIO pins
  uv run python scripts/test_sound_trigger_passthrough.py --gpio-input 17 --gpio-output 27

  # Only show real swings
  uv run python scripts/test_sound_trigger_passthrough.py --swings-only

  # Adjust pulse width (microseconds)
  uv run python scripts/test_sound_trigger_passthrough.py --pulse-width 200
        """,
    )
    parser.add_argument(
        "--port", help="Serial port for radar (auto-detect if not specified)"
    )
    parser.add_argument(
        "--gpio-input", "-i", type=int, default=DEFAULT_INPUT_PIN,
        help=f"GPIO input pin (BCM) for GATE signal (default: {DEFAULT_INPUT_PIN})"
    )
    parser.add_argument(
        "--gpio-output", "-o", type=int, default=DEFAULT_OUTPUT_PIN,
        help=f"GPIO output pin (BCM) for HOST_INT (default: {DEFAULT_OUTPUT_PIN})"
    )
    parser.add_argument(
        "--pulse-width", "-w", type=int, default=100,
        help="Output pulse width in microseconds (default: 100)"
    )
    parser.add_argument(
        "--pre-trigger", "-p", type=int, default=12,
        help="Pre-trigger segments S#n, 0-32 (default: 12, ~51ms pre-trigger)"
    )
    parser.add_argument(
        "--swings-only", "-s", action="store_true",
        help="Only show captures with real swing data (>= 15 mph outbound)"
    )
    parser.add_argument(
        "--timeout", "-t", type=float, default=30.0,
        help="Timeout waiting for trigger in seconds (default: 30)"
    )

    args = parser.parse_args()

    if not 0 <= args.pre_trigger <= 32:
        print("Error: pre-trigger must be between 0 and 32")
        sys.exit(1)

    print()
    print("=" * 70)
    print("  OpenFlight GPIO Passthrough Sound Trigger Tester")
    print(f"  (SEN-14262 GATE → GPIO{args.gpio_input} → GPIO{args.gpio_output} → HOST_INT)")
    print("=" * 70)
    print()

    run(args.port, args.gpio_input, args.gpio_output, args.pulse_width,
        args.pre_trigger, args.swings_only, args.timeout)


if __name__ == "__main__":
    main()
