#!/usr/bin/env python3
"""
Debug script for GPIO passthrough trigger.

Comprehensive debugging for HOST_INT triggering:
1. Reset radar to clean state
2. Test software S! trigger (verify rolling buffer works)
3. Test GPIO pulse to HOST_INT

Usage:
    python scripts/debug_gpio_passthrough.py
"""

import sys
import time

sys.path.insert(0, "src")

# Try to import lgpio
try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    print("WARNING: lgpio not available")

DEFAULT_OUTPUT_PIN = 27  # HOST_INT output


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


def main():
    from openflight.ops243 import OPS243Radar

    output_pin = DEFAULT_OUTPUT_PIN

    print("=" * 70)
    print("  GPIO Passthrough HOST_INT Debugger")
    print("=" * 70)
    print()
    print(f"GPIO Output Pin: GPIO{output_pin} (physical pin {gpio_to_physical(output_pin)})")
    print()

    # =========================================================================
    # STEP 1: Connect and reset radar
    # =========================================================================
    print("-" * 70)
    print("STEP 1: Connect and reset radar")
    print("-" * 70)

    print("Connecting to radar...")
    radar = OPS243Radar()
    radar.connect()
    print(f"  Connected on: {radar.port}")

    # Get firmware info
    info = radar.get_info()
    print(f"  Firmware: {info.get('Version', 'unknown')}")
    print(f"  Product: {info.get('Product', 'unknown')}")

    # Full reset
    print()
    print("Resetting radar to clean state...")
    print("  Sending OX (factory reset)...")
    response = radar._send_command("OX")
    print(f"    Response: {response[:100] if response else 'None'}")
    time.sleep(0.5)

    print("  Sending PI (deactivate)...")
    response = radar._send_command("PI")
    print(f"    Response: {response[:100] if response else 'None'}")
    time.sleep(0.2)

    print()
    print("Radar reset complete.")

    # =========================================================================
    # STEP 2: Configure rolling buffer mode
    # =========================================================================
    print()
    print("-" * 70)
    print("STEP 2: Configure rolling buffer mode")
    print("-" * 70)

    print("Sending configuration commands...")

    print("  UC (set units to MPH)...")
    radar._send_command("UC")
    time.sleep(0.1)

    print("  PI (deactivate)...")
    radar._send_command("PI")
    time.sleep(0.1)

    # Try G1 (rolling buffer mode) instead of GC (continuous sampling)
    print("  G1 (enable rolling buffer mode - single capture)...")
    response = radar._send_command("G1")
    print(f"    Response: {response[:100] if response else 'None'}")
    time.sleep(0.1)

    print("  K+ (enable peak detection)...")
    response = radar._send_command("K+")
    print(f"    Response: {response[:100] if response else 'None'}")
    time.sleep(0.1)

    print("  S=30000 (set sample rate 30ksps)...")
    response = radar._send_command("S=30000")
    print(f"    Response: {response[:100] if response else 'None'}")
    time.sleep(0.1)

    print("  S#12 (set pre-trigger segments)...")
    response = radar._send_command("S#12")
    print(f"    Response: {response[:100] if response else 'None'}")
    time.sleep(0.1)

    print("  PA (activate)...")
    response = radar._send_command("PA")
    print(f"    Response: {response[:100] if response else 'None'}")
    time.sleep(0.2)

    # Verify configuration
    print()
    print("Verifying configuration...")
    print("  S? (query sample rate)...")
    response = radar._send_command("S?")
    print(f"    Response: {response}")

    print("  G? (query mode)...")
    response = radar._send_command("G?")
    print(f"    Response: {response}")

    print()
    print("Rolling buffer mode configured.")

    # =========================================================================
    # STEP 3: Test software trigger (S!)
    # =========================================================================
    print()
    print("-" * 70)
    print("STEP 3: Test software trigger (S!)")
    print("-" * 70)

    print("Sending S! command...")
    start_time = time.perf_counter()

    # Clear buffer first
    radar.serial.reset_input_buffer()

    # Send S! and read response
    radar.serial.write(b"S!\r")
    radar.serial.flush()

    # Read response with timeout
    response_lines = []
    deadline = time.time() + 5.0

    while time.time() < deadline:
        if radar.serial.in_waiting > 0:
            line = radar.serial.readline().decode('utf-8', errors='ignore').strip()
            if line:
                response_lines.append(line)
                # Check if we got I/Q data
                if '"Q"' in line:
                    break
        else:
            time.sleep(0.01)

    elapsed = (time.perf_counter() - start_time) * 1000

    if response_lines:
        print(f"  Response received in {elapsed:.1f}ms")
        print(f"  Lines received: {len(response_lines)}")
        for i, line in enumerate(response_lines):
            preview = line[:80] + "..." if len(line) > 80 else line
            print(f"    [{i}]: {preview}")

        # Check for I/Q data
        full_response = '\n'.join(response_lines)
        has_i = '"I"' in full_response or '"I":' in full_response
        has_q = '"Q"' in full_response or '"Q":' in full_response
        print()
        print(f"  Contains I data: {has_i}")
        print(f"  Contains Q data: {has_q}")

        if has_i and has_q:
            print()
            print("  SUCCESS: Software trigger (S!) works!")
        else:
            print()
            print("  WARNING: Response received but no I/Q data found")
    else:
        print(f"  FAIL: No response after {elapsed:.1f}ms")
        print("  Rolling buffer mode may not be configured correctly.")
        radar.disconnect()
        return

    # Re-arm for next test
    print()
    print("Re-arming rolling buffer (sending GC)...")
    radar._send_command("G1")
    time.sleep(0.2)
    radar._send_command("PA")
    time.sleep(0.2)

    # =========================================================================
    # STEP 4: Test GPIO pulse to HOST_INT
    # =========================================================================
    print()
    print("-" * 70)
    print("STEP 4: Test GPIO pulse to HOST_INT")
    print("-" * 70)

    if not LGPIO_AVAILABLE:
        print("SKIP: lgpio not available")
        radar.disconnect()
        return

    print(f"Setting up GPIO{output_pin}...")
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, output_pin, 0)
    print(f"  GPIO{output_pin} configured as output, currently LOW")

    # Clear serial buffer
    radar.serial.reset_input_buffer()

    # Test 1: Rising edge (LOW -> HIGH)
    print()
    print("Test 4a: Rising edge trigger (LOW → HIGH → LOW)")
    print(f"  Pulsing GPIO{output_pin} HIGH for 10ms...")

    start_time = time.perf_counter()
    lgpio.gpio_write(h, output_pin, 1)
    time.sleep(0.010)  # 10ms pulse
    lgpio.gpio_write(h, output_pin, 0)
    print("  Pulse sent!")

    # Wait for response
    print("  Waiting for radar response (3s timeout)...")
    response_lines = []
    deadline = time.time() + 3.0

    while time.time() < deadline:
        if radar.serial.in_waiting > 0:
            line = radar.serial.readline().decode('utf-8', errors='ignore').strip()
            if line:
                response_lines.append(line)
                if '"Q"' in line:
                    break
        else:
            time.sleep(0.01)

    elapsed = (time.perf_counter() - start_time) * 1000

    if response_lines:
        print(f"  Response received in {elapsed:.1f}ms!")
        print(f"  Lines: {len(response_lines)}")
        for i, line in enumerate(response_lines[:5]):
            preview = line[:60] + "..." if len(line) > 60 else line
            print(f"    [{i}]: {preview}")
        print()
        print("  SUCCESS: Rising edge trigger works!")
    else:
        print(f"  No response after {elapsed:.1f}ms")

        # Re-arm and try falling edge
        print()
        print("Re-arming rolling buffer...")
        radar._send_command("G1")
        time.sleep(0.2)
        radar._send_command("PA")
        time.sleep(0.2)
        radar.serial.reset_input_buffer()

        print()
        print("Test 4b: Falling edge trigger (HIGH → LOW → HIGH)")
        lgpio.gpio_write(h, output_pin, 1)
        time.sleep(0.1)  # Start HIGH
        print(f"  GPIO{output_pin} now HIGH, pulsing LOW for 10ms...")

        start_time = time.perf_counter()
        lgpio.gpio_write(h, output_pin, 0)
        time.sleep(0.010)
        lgpio.gpio_write(h, output_pin, 1)
        print("  Pulse sent!")

        # Wait for response
        print("  Waiting for radar response (3s timeout)...")
        response_lines = []
        deadline = time.time() + 3.0

        while time.time() < deadline:
            if radar.serial.in_waiting > 0:
                line = radar.serial.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    response_lines.append(line)
                    if '"Q"' in line:
                        break
            else:
                time.sleep(0.01)

        elapsed = (time.perf_counter() - start_time) * 1000

        if response_lines:
            print(f"  Response received in {elapsed:.1f}ms!")
            print(f"  Lines: {len(response_lines)}")
            print()
            print("  SUCCESS: Falling edge trigger works!")
        else:
            print(f"  No response after {elapsed:.1f}ms")

            # Try level-triggered (hold HIGH)
            print()
            print("Re-arming rolling buffer...")
            radar._send_command("G1")
            time.sleep(0.2)
            radar._send_command("PA")
            time.sleep(0.2)
            radar.serial.reset_input_buffer()

            print()
            print("Test 4c: Level trigger (hold HIGH for 500ms)")
            lgpio.gpio_write(h, output_pin, 0)
            time.sleep(0.1)

            start_time = time.perf_counter()
            print(f"  Setting GPIO{output_pin} HIGH and holding...")
            lgpio.gpio_write(h, output_pin, 1)

            # Wait for response while holding HIGH
            response_lines = []
            deadline = time.time() + 3.0

            while time.time() < deadline:
                if radar.serial.in_waiting > 0:
                    line = radar.serial.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        response_lines.append(line)
                        if '"Q"' in line:
                            break
                else:
                    time.sleep(0.01)

            lgpio.gpio_write(h, output_pin, 0)
            elapsed = (time.perf_counter() - start_time) * 1000

            if response_lines:
                print(f"  Response received in {elapsed:.1f}ms!")
                print()
                print("  SUCCESS: Level trigger works!")
            else:
                print(f"  No response after {elapsed:.1f}ms")
                print()
                print("  FAIL: HOST_INT not responding to GPIO pulse")
                print()
                print("  Troubleshooting:")
                print("    1. Verify wire is connected to J3 PIN 3 (HOST_INT)")
                print("       J3 pinout: Pin1=GND, Pin2=TRIG_OUT, Pin3=HOST_INT, Pin4=VCC")
                print("    2. Add direct GND jumper: Pi GND (pin 6) → J3 Pin 1")
                print("    3. Check for loose connections")
                print("    4. Try a different GPIO pin")

    lgpio.gpiochip_close(h)

    # =========================================================================
    # Summary
    # =========================================================================
    print()
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print("  Software trigger (S!): WORKS")
    if response_lines:
        print("  Hardware trigger (HOST_INT): WORKS")
    else:
        print("  Hardware trigger (HOST_INT): FAILED")
        print()
        print("  The radar responds to S! but not to HOST_INT pulse.")
        print("  This suggests a wiring issue or HOST_INT configuration issue.")

    radar.disconnect()
    print()
    print("Done.")


if __name__ == "__main__":
    main()
