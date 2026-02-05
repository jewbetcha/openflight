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
    # STEP 2: Configure rolling buffer mode (verbose)
    # =========================================================================
    print()
    print("-" * 70)
    print("STEP 2: Configure rolling buffer mode (verbose)")
    print("-" * 70)

    print("Sending commands manually with response checking...")
    print()

    # Set units
    print("  UC (set units)...")
    response = radar._send_command("UC")
    print(f"    Response: {response}")
    time.sleep(0.1)

    # Deactivate first
    print("  PI (deactivate)...")
    response = radar._send_command("PI")
    print(f"    Response: {response}")
    time.sleep(0.1)

    # Enable rolling buffer mode - THIS IS THE KEY COMMAND
    print("  GC (enable rolling buffer mode)...")
    response = radar._send_command("GC")
    print(f"    Response: {response}")
    time.sleep(0.1)

    # Activate sampling
    print("  PA (activate)...")
    response = radar._send_command("PA")
    print(f"    Response: {response}")
    time.sleep(0.1)

    # Set sample rate (S=30 means 30 kHz, not S=30000!)
    print("  S=30 (sample rate 30kHz)...")
    response = radar._send_command("S=30")
    print(f"    Response: {response}")
    time.sleep(0.1)

    # Set trigger split
    print("  S#12 (pre-trigger segments)...")
    response = radar._send_command("S#12")
    print(f"    Response: {response}")
    time.sleep(0.1)

    # Query current mode
    print()
    print("Verifying configuration...")
    print("  G? (query mode)...")
    response = radar._send_command("G?")
    print(f"    Response: {response}")

    print("  S? (query sample rate)...")
    response = radar._send_command("S?")
    print(f"    Response: {response}")

    print("  ?? (query all settings)...")
    response = radar._send_command("??")
    print(f"    Response: {response[:500] if response else 'None'}...")

    print()
    print("Configuration complete.")

    # =========================================================================
    # STEP 3: Test software trigger (S!)
    # =========================================================================
    print()
    print("-" * 70)
    print("STEP 3: Test software trigger (S!)")
    print("-" * 70)

    print("Using radar.trigger_capture() method...")
    start_time = time.perf_counter()

    response = radar.trigger_capture(timeout=10.0)

    elapsed = (time.perf_counter() - start_time) * 1000

    if response:
        print(f"  Response received in {elapsed:.1f}ms")
        print(f"  Response length: {len(response)} bytes")

        # Show first part of response
        preview = response[:200] + "..." if len(response) > 200 else response
        print(f"  Preview: {preview}")

        # Check for I/Q data
        has_i = '"I"' in response or '"I":' in response
        has_q = '"Q"' in response or '"Q":' in response
        print()
        print(f"  Contains I data: {has_i}")
        print(f"  Contains Q data: {has_q}")

        if has_i and has_q:
            print()
            print("  SUCCESS: Software trigger (S!) works!")
        else:
            print()
            print("  WARNING: Response received but no I/Q data found")
            print("  This suggests rolling buffer mode is not properly configured.")
            print()
            print("  Full response:")
            print(f"  {response}")
    else:
        print(f"  FAIL: No response after {elapsed:.1f}ms")
        print("  Rolling buffer mode may not be configured correctly.")
        radar.disconnect()
        return

    # Re-arm for next test
    print()
    print("Re-arming rolling buffer...")
    radar.rearm_rolling_buffer()
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
        radar.rearm_rolling_buffer()
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
            radar.rearm_rolling_buffer()
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
