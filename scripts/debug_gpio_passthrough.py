#!/usr/bin/env python3
"""
Debug script for GPIO passthrough trigger.

Tests each component separately:
1. GPIO input - is GATE signal being detected?
2. GPIO output - can we manually pulse HOST_INT?
3. Radar response - does radar respond to HOST_INT pulse?

Usage:
    uv run python scripts/debug_gpio_passthrough.py --test input   # Test GATE detection
    uv run python scripts/debug_gpio_passthrough.py --test output  # Test HOST_INT pulse
    uv run python scripts/debug_gpio_passthrough.py --test radar   # Test radar response
    uv run python scripts/debug_gpio_passthrough.py --test all     # Run all tests
"""

import argparse
import sys
import time

sys.path.insert(0, "src")

# Try to import lgpio
try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    print("WARNING: lgpio not available - GPIO tests will be skipped")

DEFAULT_INPUT_PIN = 17   # GATE input
DEFAULT_OUTPUT_PIN = 27  # HOST_INT output


def test_gpio_input(input_pin: int, duration: float = 10.0):
    """Test if we can detect GATE signal on input pin."""
    if not LGPIO_AVAILABLE:
        print("SKIP: lgpio not available")
        return False

    print(f"\n=== Testing GPIO Input (GPIO{input_pin}) ===")
    print(f"Monitoring for {duration} seconds...")
    print("Make some noise near the SEN-14262 microphone!")
    print()

    handle = lgpio.gpiochip_open(0)

    # Must use gpio_claim_alert for edge detection callbacks
    lgpio.gpio_claim_alert(handle, input_pin, lgpio.BOTH_EDGES, lgpio.SET_PULL_DOWN)

    edge_count = 0
    last_level = 0

    def on_edge(chip, gpio, level, tick):
        nonlocal edge_count, last_level
        edge_count += 1
        direction = "RISING" if level == 1 else "FALLING"
        print(f"  Edge #{edge_count}: {direction} (level={level})")
        last_level = level

    cb = lgpio.callback(handle, input_pin, lgpio.BOTH_EDGES, on_edge)

    # Also poll the current level
    print(f"Current level: {lgpio.gpio_read(handle, input_pin)}")
    print()
    print("Waiting for edges...")

    start = time.time()
    while time.time() - start < duration:
        time.sleep(0.1)
        # Print a dot every second to show we're alive
        if int(time.time() - start) != int(time.time() - start - 0.1):
            current = lgpio.gpio_read(handle, input_pin)
            print(f"  [{time.time() - start:.0f}s] level={current}, edges={edge_count}")

    cb.cancel()
    lgpio.gpiochip_close(handle)

    print()
    if edge_count > 0:
        print(f"SUCCESS: Detected {edge_count} edges on GPIO{input_pin}")
        return True
    else:
        print(f"FAIL: No edges detected on GPIO{input_pin}")
        print()
        print("Troubleshooting:")
        print("  1. Check SEN-14262 is powered (VCC → 3.3V, GND → GND)")
        print("  2. Check GATE wire is connected to correct Pi pin")
        print(f"     GPIO{input_pin} = Physical pin {gpio_to_physical(input_pin)}")
        print("  3. Try adjusting the sensitivity pot on SEN-14262")
        print("  4. Check if the GATE LED on SEN-14262 flashes with sound")
        return False


def test_gpio_output(output_pin: int):
    """Test if we can pulse the output pin."""
    if not LGPIO_AVAILABLE:
        print("SKIP: lgpio not available")
        return False

    print(f"\n=== Testing GPIO Output (GPIO{output_pin}) ===")
    print("This will pulse the output pin 5 times.")
    print("If you have an LED or multimeter on this pin, you should see it pulse.")
    print()

    handle = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(handle, output_pin, 0)

    print(f"Initial state: LOW")

    for i in range(5):
        print(f"  Pulse {i+1}/5: HIGH...", end="", flush=True)
        lgpio.gpio_write(handle, output_pin, 1)
        time.sleep(0.5)
        print(" LOW")
        lgpio.gpio_write(handle, output_pin, 0)
        time.sleep(0.5)

    lgpio.gpiochip_close(handle)

    print()
    print(f"SUCCESS: Pulsed GPIO{output_pin} 5 times")
    print(f"If HOST_INT is connected, radar should have received 5 trigger pulses")
    return True


def test_radar_response(port: str = None, output_pin: int = DEFAULT_OUTPUT_PIN):
    """Test if radar responds to HOST_INT pulse."""
    print(f"\n=== Testing Radar Response to HOST_INT ===")

    from openflight.ops243 import OPS243Radar

    print("Connecting to radar...")
    radar = OPS243Radar(port=port if port else None)
    radar.connect()
    print(f"Connected on {radar.port}")

    # Get firmware info
    info = radar.get_info()
    print(f"Firmware: {info.get('Version', 'unknown')}")

    # Configure rolling buffer mode
    print()
    print("Configuring rolling buffer mode...")
    radar.configure_for_rolling_buffer()
    radar.set_trigger_split(12)  # 12 pre-trigger segments
    print("Radar configured for rolling buffer with hardware trigger")

    if LGPIO_AVAILABLE:
        print()
        print(f"Setting up GPIO{output_pin} for HOST_INT pulse...")
        handle = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(handle, output_pin, 0)

        print()
        print("Sending manual trigger pulse to HOST_INT...")
        lgpio.gpio_write(handle, output_pin, 1)
        time.sleep(0.0001)  # 100μs pulse
        lgpio.gpio_write(handle, output_pin, 0)
        print("Pulse sent!")

        lgpio.gpiochip_close(handle)
    else:
        print()
        print("lgpio not available - sending S! software trigger instead...")
        # Fall back to software trigger
        radar._send_command("S!")

    print()
    print("Waiting for radar response (5 second timeout)...")

    response = radar.wait_for_hardware_trigger(timeout=5.0)

    radar.disable_rolling_buffer()
    radar.disconnect()

    if response:
        print()
        print(f"SUCCESS: Radar responded with {len(response)} bytes of I/Q data!")
        print(f"First 100 chars: {response[:100]}...")
        return True
    else:
        print()
        print("FAIL: No response from radar")
        print()
        print("Troubleshooting:")
        print("  1. Check HOST_INT wiring:")
        print(f"     GPIO{output_pin} (physical pin {gpio_to_physical(output_pin)}) → J3 Pin 3 on radar")
        print("  2. Ensure GND is shared between Pi and radar")
        print("  3. Check radar firmware supports rolling buffer mode")
        print("  4. Try the S! software trigger as fallback:")
        print("     uv run python -c \"from openflight.ops243 import OPS243Radar; r=OPS243Radar(); r.connect(); r.configure_for_rolling_buffer(); print(r._send_command('S!')[:200])\"")
        return False


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
    parser = argparse.ArgumentParser(
        description="Debug GPIO passthrough trigger components",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--test", "-t",
        choices=["input", "output", "radar", "all"],
        default="all",
        help="Which test to run (default: all)"
    )
    parser.add_argument(
        "--gpio-input", "-i", type=int, default=DEFAULT_INPUT_PIN,
        help=f"GPIO input pin for GATE (default: {DEFAULT_INPUT_PIN})"
    )
    parser.add_argument(
        "--gpio-output", "-o", type=int, default=DEFAULT_OUTPUT_PIN,
        help=f"GPIO output pin for HOST_INT (default: {DEFAULT_OUTPUT_PIN})"
    )
    parser.add_argument(
        "--port", "-p",
        help="Serial port for radar (auto-detect if not specified)"
    )
    parser.add_argument(
        "--duration", "-d", type=float, default=10.0,
        help="Duration for input test in seconds (default: 10)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  GPIO Passthrough Trigger Debugger")
    print("=" * 60)
    print()
    print("Pin Configuration:")
    print(f"  Input:  GPIO{args.gpio_input} (physical pin {gpio_to_physical(args.gpio_input)}) ← GATE")
    print(f"  Output: GPIO{args.gpio_output} (physical pin {gpio_to_physical(args.gpio_output)}) → HOST_INT")

    results = {}

    if args.test in ["input", "all"]:
        results["input"] = test_gpio_input(args.gpio_input, args.duration)

    if args.test in ["output", "all"]:
        results["output"] = test_gpio_output(args.gpio_output)

    if args.test in ["radar", "all"]:
        results["radar"] = test_radar_response(args.port, args.gpio_output)

    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "PASS ✓" if passed else "FAIL ✗"
        print(f"  {test_name}: {status}")

    if all(results.values()):
        print()
        print("All tests passed! The passthrough trigger should work.")
    else:
        print()
        print("Some tests failed. Check the troubleshooting info above.")


if __name__ == "__main__":
    main()
