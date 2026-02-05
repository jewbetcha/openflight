#!/usr/bin/env python3
"""
Software trigger sound test for SEN-14262 + OPS243-A.

When SEN-14262 GATE goes HIGH (sound detected), sends S! software trigger
to the radar and reads the I/Q buffer dump.

Wiring:
    SEN-14262 VCC  → 3.3V
    SEN-14262 GND  → GND (shared with Pi)
    SEN-14262 GATE → Pi GPIO17 (physical pin 11)

Latency measurement:
    - sound_time: When GPIO edge detected (GATE goes HIGH)
    - data_time: When I/Q data fully received
    - Difference shows total sound-to-data latency

Usage:
    uv run python scripts/test_sound_trigger_software.py
"""

import argparse
import sys
import time

sys.path.insert(0, "src")

try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False

from openflight.ops243 import OPS243Radar
from openflight.rolling_buffer.processor import RollingBufferProcessor

INPUT_PIN = 17  # BCM 17 = Physical pin 11 (GATE input)


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


def send_and_print(radar, cmd, description):
    """Send command and print response."""
    print(f"  {cmd:8} ({description})...")
    radar.serial.reset_input_buffer()

    if '=' in cmd or '#' in cmd or '>' in cmd or '<' in cmd:
        radar.serial.write(f"{cmd}\r".encode())
    else:
        radar.serial.write(cmd.encode())

    radar.serial.flush()
    time.sleep(0.15)

    response = ""
    while radar.serial.in_waiting:
        response += radar.serial.read(radar.serial.in_waiting).decode('ascii', errors='ignore')
        time.sleep(0.05)

    response = response.strip()
    print(f"           → {response if response else '(no response)'}")
    return response


def configure_rolling_buffer(radar, pre_trigger_segments=12):
    """Configure radar for rolling buffer mode."""
    print("Configuring rolling buffer mode...")

    send_and_print(radar, "PI", "power idle")
    time.sleep(0.2)
    send_and_print(radar, "GC", "rolling buffer mode")
    send_and_print(radar, "PA", "power active")
    send_and_print(radar, "S=30", "30ksps sample rate")
    send_and_print(radar, f"S#{pre_trigger_segments}", f"{pre_trigger_segments} pre-trigger segments")
    send_and_print(radar, "PA", "reactivate sampling")
    send_and_print(radar, "G?", "verify mode")
    send_and_print(radar, "P?", "verify power")

    print("  Configuration complete.")
    print()


def software_trigger_and_read(radar, timeout=10.0):
    """Send S! trigger and read I/Q response."""
    radar.serial.reset_input_buffer()

    # Send trigger and record time
    trigger_send_time = time.perf_counter()
    radar.serial.write(b"S!\r")
    radar.serial.flush()

    # Read response
    chunks = []
    while time.time() - trigger_send_time < timeout:
        if radar.serial.in_waiting:
            chunk = radar.serial.read(radar.serial.in_waiting)
            chunks.append(chunk)

            full = b''.join(chunks)
            if b'"Q"' in full and b']}' in full[full.rfind(b'"Q"'):]:
                break
        time.sleep(0.01)

    data_received_time = time.perf_counter()
    response = b''.join(chunks).decode('utf-8', errors='ignore')

    return response, trigger_send_time, data_received_time


def rearm_buffer(radar):
    """Re-arm rolling buffer for next capture."""
    radar.serial.reset_input_buffer()
    radar.serial.write(b"GC")
    radar.serial.flush()
    time.sleep(0.05)
    radar.serial.write(b"PA")
    radar.serial.flush()
    time.sleep(0.1)


def main():
    parser = argparse.ArgumentParser(
        description="Software trigger sound test for SEN-14262 + OPS243-A"
    )
    parser.add_argument(
        "--gpio-input", "-i", type=int, default=INPUT_PIN,
        help=f"GPIO input pin (BCM) for GATE signal (default: {INPUT_PIN})"
    )
    parser.add_argument(
        "--pre-trigger", "-p", type=int, default=12,
        help="Pre-trigger segments S#n, 0-32 (default: 12)"
    )
    parser.add_argument(
        "--timeout", "-t", type=float, default=60.0,
        help="Timeout waiting for sound in seconds (default: 60)"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  Software Trigger Sound Test")
    print("  (SEN-14262 GATE → GPIO → S! command)")
    print("=" * 70)
    print()

    if not LGPIO_AVAILABLE:
        print("ERROR: lgpio not available")
        print("Install with: pip install lgpio")
        sys.exit(1)

    # Set up GPIO input
    print(f"Setting up GPIO{args.gpio_input} (physical pin {gpio_to_physical(args.gpio_input)}) as input...")
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_input(h, args.gpio_input, lgpio.SET_PULL_DOWN)
    print("  GPIO configured with pull-down")
    print()

    # Connect to radar
    print("Connecting to radar...")
    radar = OPS243Radar()
    radar.connect()
    print(f"  Connected on: {radar.port}")

    info = radar.get_info()
    print(f"  Firmware: {info.get('Version', 'unknown')}")
    print()

    # Configure rolling buffer
    configure_rolling_buffer(radar, args.pre_trigger)

    # Wait for buffer to fill
    print("Waiting 1 second for buffer to fill...")
    time.sleep(1.0)
    print()

    # Set up processor
    processor = RollingBufferProcessor()

    print("-" * 70)
    print("Ready for sound triggers!")
    print(f"  GPIO{args.gpio_input} (physical pin {gpio_to_physical(args.gpio_input)}) ← SEN-14262 GATE")
    print(f"  Pre-trigger: S#{args.pre_trigger}")
    print()
    print("Make a sound near the sensor... (Ctrl+C to quit)")
    print("-" * 70)
    print()

    trigger_count = 0
    latencies = []

    try:
        while True:
            # Poll for GPIO high (sound detected)
            while lgpio.gpio_read(h, args.gpio_input) == 0:
                time.sleep(0.001)  # 1ms polling

            # Sound detected!
            sound_time = time.perf_counter()
            trigger_count += 1

            print(f"[{trigger_count}] Sound detected! Sending S! trigger...")

            # Send software trigger
            response, trigger_send_time, data_received_time = software_trigger_and_read(radar)

            # Calculate latencies
            gpio_to_trigger_ms = (trigger_send_time - sound_time) * 1000
            trigger_to_data_ms = (data_received_time - trigger_send_time) * 1000
            total_latency_ms = (data_received_time - sound_time) * 1000

            print(f"  GPIO → S! sent:    {gpio_to_trigger_ms:.2f}ms")
            print(f"  S! → data received: {trigger_to_data_ms:.2f}ms")
            print(f"  Total latency:      {total_latency_ms:.2f}ms")
            print(f"  Response size:      {len(response)} bytes")

            # Parse and analyze
            if response and '"I"' in response and '"Q"' in response:
                capture = processor.parse_capture(response)
                if capture:
                    print(f"  I/Q samples:        {len(capture.i_samples)} I, {len(capture.q_samples)} Q")
                    latencies.append(total_latency_ms)
                    print("  SUCCESS!")
                else:
                    print("  WARNING: Failed to parse I/Q data")
            else:
                print("  WARNING: No I/Q data in response")
                print(f"  Response: {response[:200] if response else '(empty)'}...")

            # Re-arm for next capture
            print("  Re-arming buffer...")
            rearm_buffer(radar)
            time.sleep(0.5)  # Debounce + buffer fill time

            print()

            # Show running stats
            if latencies:
                avg = sum(latencies) / len(latencies)
                min_lat = min(latencies)
                max_lat = max(latencies)
                print(f"  Stats: {len(latencies)} captures | "
                      f"Latency: avg={avg:.1f}ms, min={min_lat:.1f}ms, max={max_lat:.1f}ms")
                print()

    except KeyboardInterrupt:
        print()
        print()
        print("=" * 70)
        print("  SESSION SUMMARY")
        print("=" * 70)
        print(f"  Total triggers: {trigger_count}")
        print(f"  Successful captures: {len(latencies)}")
        if latencies:
            avg = sum(latencies) / len(latencies)
            min_lat = min(latencies)
            max_lat = max(latencies)
            print()
            print("  Latency (sound detection → I/Q data received):")
            print(f"    Average: {avg:.2f}ms")
            print(f"    Minimum: {min_lat:.2f}ms")
            print(f"    Maximum: {max_lat:.2f}ms")
        print("=" * 70)

    finally:
        print()
        print("Cleaning up...")
        lgpio.gpiochip_close(h)
        radar.serial.write(b"PI")
        radar.disconnect()
        print("Done.")


if __name__ == "__main__":
    main()
