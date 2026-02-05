#!/usr/bin/env python3
"""
Quick debug script to test if the hardware trigger is working.
"""

import sys
sys.path.insert(0, "src")

from openflight.ops243 import OPS243Radar

print("Connecting to radar...")
radar = OPS243Radar()
radar.connect()
print(f"Connected on {radar.port}")

print("Configuring rolling buffer mode...")
radar.configure_for_rolling_buffer()
radar.set_trigger_split(12)

print()
print("=" * 50)
print("TEST 1: Software trigger (S!) - verifying radar is working")
print("=" * 50)
response = radar.trigger_capture(timeout=10)
if response:
    print(f"SUCCESS! S! trigger returned {len(response)} bytes")
else:
    print("FAILED - S! trigger returned nothing")
    print("Radar may not be in rolling buffer mode")
    radar.disconnect()
    sys.exit(1)

# Re-arm after S! trigger
radar.rearm_rolling_buffer()

print()
print("=" * 50)
print("TEST 2: Hardware trigger (HOST_INT) - make a loud sound!")
print("=" * 50)
print("Waiting 30s for hardware trigger...")
print()

response = radar.wait_for_hardware_trigger(timeout=30)

if response:
    print(f"SUCCESS! Hardware trigger returned {len(response)} bytes")
    print()
    print("First 500 chars:")
    print(response[:500])
else:
    print("No hardware trigger received within 30s")
    print()
    print("Possible issues:")
    print("  - GATE not connected to J3 pin 3")
    print("  - No common ground between SEN-14262 and radar")
    print("  - SEN-14262 GATE not going HIGH (check LED)")
    print("  - HOST_INT pin may need pull-down resistor")

print()
print("Disconnecting...")
radar.disconnect()
print("Done.")
