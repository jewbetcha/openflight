#!/usr/bin/env python3
"""
Debug script for GPIO passthrough trigger.

Uses the exact same radar setup sequence that works in debug_rolling_buffer.py:
1. PI - reset to idle
2. GC - enter rolling buffer mode
3. PA - activate sampling
4. S=30 - set sample rate
5. S#n - set trigger split
6. PA - reactivate (critical after settings changes)
7. Wait for buffer to fill
8. Test software trigger (S!)
9. Test hardware trigger (GPIO pulse to HOST_INT)
"""

import sys
import time

sys.path.insert(0, "src")

try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    print("WARNING: lgpio not available")

from openflight.ops243 import OPS243Radar
from openflight.rolling_buffer.processor import RollingBufferProcessor

OUTPUT_PIN = 27  # HOST_INT output


def gpio_to_physical(bcm_pin: int) -> int:
    bcm_to_physical = {
        17: 11, 27: 13, 22: 15, 5: 29, 6: 31, 13: 33,
    }
    return bcm_to_physical.get(bcm_pin, 0)


def send_and_print(radar, cmd, description):
    """Send command and print response."""
    print(f"  {cmd:8} ({description})...")

    # Clear buffer first
    radar.serial.reset_input_buffer()

    # Send command with carriage return for commands that need it
    if '=' in cmd or '#' in cmd or '>' in cmd or '<' in cmd:
        radar.serial.write(f"{cmd}\r".encode())
    else:
        radar.serial.write(cmd.encode())

    radar.serial.flush()
    time.sleep(0.15)

    # Read response
    response = ""
    while radar.serial.in_waiting:
        response += radar.serial.read(radar.serial.in_waiting).decode('ascii', errors='ignore')
        time.sleep(0.05)

    response = response.strip()
    print(f"           → {response if response else '(no response)'}")
    return response


def configure_rolling_buffer_manual(radar, pre_trigger_segments=12):
    """
    Configure rolling buffer using the exact sequence that works.

    This bypasses the OPS243Radar methods to ensure we use the exact
    working sequence from debug_rolling_buffer.py.
    """
    print("Configuring rolling buffer mode (manual sequence)...")

    # Step 1: Reset to idle
    send_and_print(radar, "PI", "power idle")
    time.sleep(0.2)

    # Step 2: Enter rolling buffer mode
    send_and_print(radar, "GC", "rolling buffer mode")

    # Step 3: Activate sampling
    send_and_print(radar, "PA", "power active")

    # Step 4: Set sample rate
    send_and_print(radar, "S=30", "30ksps sample rate")

    # Step 5: Set trigger split
    send_and_print(radar, f"S#{pre_trigger_segments}", f"{pre_trigger_segments} pre-trigger segments")

    # Step 6: CRITICAL - Reactivate after settings changes
    send_and_print(radar, "PA", "reactivate sampling")

    # Step 7: Verify mode
    send_and_print(radar, "G?", "verify mode")
    send_and_print(radar, "P?", "verify power")

    print("  Configuration complete.")
    print()


def trigger_and_read(radar, timeout=10.0):
    """Send S! trigger and read response."""
    radar.serial.reset_input_buffer()

    radar.serial.write(b"S!\r")
    radar.serial.flush()

    start = time.time()
    chunks = []

    while time.time() - start < timeout:
        if radar.serial.in_waiting:
            chunk = radar.serial.read(radar.serial.in_waiting)
            chunks.append(chunk)

            full = b''.join(chunks)
            if b'"Q"' in full and b']}' in full[full.rfind(b'"Q"'):]:
                break
        time.sleep(0.05)

    return b''.join(chunks).decode('utf-8', errors='ignore')


def wait_for_hardware_response(radar, timeout=5.0):
    """Wait for hardware trigger response (data appears on serial)."""
    radar.serial.reset_input_buffer()

    start = time.time()
    chunks = []
    last_data_time = None

    while time.time() - start < timeout:
        if radar.serial.in_waiting:
            chunk = radar.serial.read(radar.serial.in_waiting)
            chunks.append(chunk)
            last_data_time = time.time()

            full = b''.join(chunks)
            if b'"Q"' in full and b']}' in full[full.rfind(b'"Q"'):]:
                break
            time.sleep(0.01)
        else:
            # If we've received data and no more coming, check if complete
            if last_data_time and (time.time() - last_data_time) > 0.5:
                full = b''.join(chunks)
                if b'"Q"' in full:
                    break
            time.sleep(0.02)

    return b''.join(chunks).decode('utf-8', errors='ignore') if chunks else ""


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
    print("=" * 70)
    print("  GPIO Passthrough HOST_INT Debugger")
    print("=" * 70)
    print()

    # =========================================================================
    # Connect to radar
    # =========================================================================
    print("Connecting to radar...")
    radar = OPS243Radar()
    radar.connect()
    print(f"  Connected on: {radar.port}")

    info = radar.get_info()
    print(f"  Firmware: {info.get('Version', 'unknown')}")
    print(f"  Product: {info.get('Product', 'unknown')}")
    print()

    # =========================================================================
    # Configure rolling buffer using working sequence
    # =========================================================================
    configure_rolling_buffer_manual(radar, pre_trigger_segments=12)

    # Wait for buffer to fill
    print("Waiting 1 second for buffer to fill...")
    time.sleep(1.0)
    print()

    # =========================================================================
    # Test software trigger S!
    # =========================================================================
    print("-" * 70)
    print("TEST 1: Software trigger (S!)")
    print("-" * 70)

    processor = RollingBufferProcessor()

    print("Sending S! trigger...")
    start = time.perf_counter()
    response = trigger_and_read(radar, timeout=10.0)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"  Response time: {elapsed_ms:.0f}ms")
    print(f"  Response length: {len(response) if response else 0} bytes")

    sw_trigger_works = False
    if response and len(response) > 100:
        has_i = '"I"' in response
        has_q = '"Q"' in response
        print(f"  Contains I array: {has_i}")
        print(f"  Contains Q array: {has_q}")

        if has_i and has_q:
            # Try to parse
            capture = processor.parse_capture(response)
            if capture:
                print(f"  I samples: {len(capture.i_samples)}")
                print(f"  Q samples: {len(capture.q_samples)}")
                print("  SUCCESS: Software trigger works!")
                sw_trigger_works = True
            else:
                print(f"  Failed to parse. Response preview: {response[:200]}")
        else:
            print(f"  Response preview: {response[:300]}")
    else:
        print(f"  FAIL: Response too short or empty")
        print(f"  Response: {response}")

    if not sw_trigger_works:
        print()
        print("Software trigger not working. Cannot test hardware trigger.")
        radar.serial.write(b"PI")
        radar.disconnect()
        return

    # Re-arm for hardware trigger test
    print()
    print("Re-arming buffer for hardware trigger test...")
    rearm_buffer(radar)
    time.sleep(0.5)  # Let buffer fill

    # =========================================================================
    # Test hardware trigger via GPIO
    # =========================================================================
    print()
    print("-" * 70)
    print("TEST 2: Hardware trigger (GPIO pulse to HOST_INT)")
    print("-" * 70)

    if not LGPIO_AVAILABLE:
        print("SKIP: lgpio not available")
        radar.serial.write(b"PI")
        radar.disconnect()
        return

    print(f"Setting up GPIO{OUTPUT_PIN} (physical pin {gpio_to_physical(OUTPUT_PIN)})...")
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, OUTPUT_PIN, 0)
    print("  GPIO configured as output, currently LOW")

    # Clear any pending serial data
    radar.serial.reset_input_buffer()

    # Test rising edge
    print()
    print("Sending rising edge pulse (LOW → HIGH for 10ms → LOW)...")
    start = time.perf_counter()

    lgpio.gpio_write(h, OUTPUT_PIN, 1)
    time.sleep(0.010)
    lgpio.gpio_write(h, OUTPUT_PIN, 0)

    print("  Pulse sent, waiting for response...")

    # Read response
    response = wait_for_hardware_response(radar, timeout=5.0)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"  Response time: {elapsed_ms:.0f}ms")
    print(f"  Response length: {len(response) if response else 0} bytes")

    if response and len(response) > 100:
        has_i = '"I"' in response
        has_q = '"Q"' in response
        print(f"  Contains I array: {has_i}")
        print(f"  Contains Q array: {has_q}")

        if has_i and has_q:
            capture = processor.parse_capture(response)
            if capture:
                print(f"  I samples: {len(capture.i_samples)}")
                print(f"  Q samples: {len(capture.q_samples)}")
                print("  SUCCESS: Hardware trigger (rising edge) works!")
            else:
                print(f"  Response received but parse failed: {response[:200]}")
        else:
            print(f"  Response preview: {response[:300]}")
    else:
        print("  FAIL: No I/Q data from rising edge trigger")

        # Try falling edge
        print()
        print("Trying falling edge (HIGH → LOW for 10ms → HIGH)...")
        rearm_buffer(radar)
        time.sleep(0.5)
        radar.serial.reset_input_buffer()

        lgpio.gpio_write(h, OUTPUT_PIN, 1)
        time.sleep(0.1)

        start = time.perf_counter()
        lgpio.gpio_write(h, OUTPUT_PIN, 0)
        time.sleep(0.010)
        lgpio.gpio_write(h, OUTPUT_PIN, 1)

        response = wait_for_hardware_response(radar, timeout=5.0)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"  Response time: {elapsed_ms:.0f}ms")
        print(f"  Response length: {len(response) if response else 0} bytes")

        if response and len(response) > 100:
            has_i = '"I"' in response
            has_q = '"Q"' in response
            if has_i and has_q:
                print("  SUCCESS: Hardware trigger (falling edge) works!")
            else:
                print(f"  Response preview: {response[:300]}")
        else:
            print("  FAIL: No I/Q data from falling edge trigger")
            print()
            print("  Troubleshooting:")
            print("    1. Verify GPIO27 is connected to J3 Pin 3 (HOST_INT)")
            print("    2. Verify GND is shared between Pi and radar")
            print("    3. Measure voltage on HOST_INT during pulse (should be 3.3V)")
            print("    4. Try longer pulse width (100ms instead of 10ms)")

    lgpio.gpiochip_close(h)
    radar.serial.write(b"PI")
    radar.disconnect()
    print()
    print("Done.")


if __name__ == "__main__":
    main()
