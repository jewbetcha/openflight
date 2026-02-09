#!/usr/bin/env python3
"""
Direct hardware sound trigger test for SEN-14262 + Level Shifter + OPS243-A.

This tests the direct hardware trigger path:
    SEN-14262 GATE → Level Shifter → OPS243-A HOST_INT (J3 Pin 3)

No Pi GPIO involved in the trigger path - purely hardware.
The Pi just reads the I/Q data after the radar triggers.

Wiring:
    SEN-14262 VCC  → 3.3V (shared with level shifter LV)
    SEN-14262 GND  → GND (shared)
    SEN-14262 GATE → Level Shifter LV1 (input)

    Level Shifter LV  → 3.3V
    Level Shifter HV  → 3.3V
    Level Shifter GND → GND
    Level Shifter HV1 → OPS243-A HOST_INT (J3 Pin 3)

Usage:
    uv run python scripts/test_sound_trigger_hardware.py
"""

import argparse
import sys
import time

sys.path.insert(0, "src")

from openflight.ops243 import OPS243Radar
from openflight.rolling_buffer.processor import RollingBufferProcessor


def main():
    parser = argparse.ArgumentParser(
        description="Direct hardware sound trigger test"
    )
    parser.add_argument(
        "--pre-trigger", "-p", type=int, default=12,
        help="Pre-trigger segments S#n, 0-32 (default: 12)"
    )
    parser.add_argument(
        "--timeout", "-t", type=float, default=60.0,
        help="Timeout waiting for trigger in seconds (default: 60)"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  Direct Hardware Sound Trigger Test")
    print("  (SEN-14262 GATE → Level Shifter → HOST_INT)")
    print("=" * 70)
    print()
    print("Wiring check:")
    print("  SEN-14262 GATE → Level Shifter LV1")
    print("  Level Shifter HV1 → OPS243-A HOST_INT (J3 Pin 3)")
    print("  All GND connected together")
    print("  Level Shifter LV and HV both → 3.3V")
    print()

    # Connect to radar
    print("Connecting to radar...")
    radar = OPS243Radar()
    radar.connect()
    print(f"  Connected on: {radar.port}")

    info = radar.get_info()
    print(f"  Firmware: {info.get('Version', 'unknown')}")
    print()

    # Configure rolling buffer mode using the consolidated method
    print(f"Configuring rolling buffer mode (S#{args.pre_trigger})...")
    radar.configure_for_rolling_buffer(pre_trigger_segments=args.pre_trigger)
    print()

    # Set up processor
    processor = RollingBufferProcessor()

    print("-" * 70)
    print("Ready for hardware sound triggers!")
    print(f"  Trigger: SEN-14262 → Level Shifter → HOST_INT")
    print(f"  Pre-trigger: S#{args.pre_trigger}")
    print()
    print("Make a sound near the sensor... (Ctrl+C to quit)")
    print("-" * 70)
    print()

    trigger_count = 0
    successful_captures = 0
    latencies = []

    try:
        while True:
            print(f"[{trigger_count + 1}] Waiting for hardware trigger (timeout={args.timeout}s)...")

            wait_start = time.perf_counter()

            # Wait for hardware trigger - radar dumps buffer when HOST_INT goes HIGH
            response = radar.wait_for_hardware_trigger(timeout=args.timeout)

            trigger_time = time.perf_counter()
            wait_duration = trigger_time - wait_start

            if not response:
                print(f"  Timeout after {wait_duration:.1f}s - no trigger received")
                print("  Check wiring: Is the level shifter connected correctly?")
                print()
                continue

            trigger_count += 1
            print(f"  TRIGGER RECEIVED after {wait_duration:.2f}s!")
            print(f"  Response size: {len(response)} bytes")

            # Parse and analyze
            if response and '"I"' in response and '"Q"' in response:
                capture = processor.parse_capture(response)
                if capture:
                    print(f"  I/Q samples: {len(capture.i_samples)} I, {len(capture.q_samples)} Q")

                    # Analyze for swing detection
                    timeline = processor.process_standard(capture)
                    all_readings = timeline.readings
                    outbound = [r for r in all_readings if r.is_outbound]
                    inbound = [r for r in all_readings if not r.is_outbound]
                    outbound_fast = [r for r in outbound if r.speed_mph >= 15.0]

                    print(f"  Total readings: {len(all_readings)}")
                    print(f"  Outbound: {len(outbound)} (peak: {max((r.speed_mph for r in outbound), default=0):.1f} mph)")
                    print(f"  Inbound: {len(inbound)} (peak: {max((r.speed_mph for r in inbound), default=0):.1f} mph)")

                    if outbound_fast:
                        peak = max(r.speed_mph for r in outbound_fast)
                        print(f"  SWING DETECTED: {len(outbound_fast)} readings >= 15 mph, peak {peak:.1f} mph")
                        successful_captures += 1
                        latencies.append(wait_duration * 1000)  # Convert to ms for stats
                    else:
                        print("  NO SWING: No outbound readings >= 15 mph (false trigger from sound)")
                else:
                    print("  WARNING: Failed to parse I/Q data")
                    print(f"  Response preview: {response[:200]}...")
            else:
                print("  WARNING: Response missing I/Q data")
                print(f"  Response: {response[:500] if len(response) > 500 else response}")

            # Re-arm for next capture
            print("  Re-arming buffer...")
            radar.rearm_rolling_buffer()
            time.sleep(0.3)  # Brief delay for buffer to fill

            print()

            # Show running stats
            if successful_captures > 0:
                print(f"  Stats: {successful_captures}/{trigger_count} valid captures")
                print()

    except KeyboardInterrupt:
        print()
        print()
        print("=" * 70)
        print("  SESSION SUMMARY")
        print("=" * 70)
        print(f"  Total triggers received: {trigger_count}")
        print(f"  Successful captures (swing detected): {successful_captures}")
        if trigger_count > 0:
            print(f"  Success rate: {successful_captures/trigger_count*100:.1f}%")
        print("=" * 70)

    finally:
        print()
        print("Cleaning up...")
        radar.serial.write(b"PI")
        radar.disconnect()
        print("Done.")


if __name__ == "__main__":
    main()
