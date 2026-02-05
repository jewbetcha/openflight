#!/usr/bin/env python3
"""
Minimal rolling buffer debug script.

Tests the exact sequence from OmniPreSense API doc AN-010-AD:
1. PI - reset to idle
2. GC - enter rolling buffer mode
3. PA - activate sampling
4. S=30 - set sample rate
5. S#n - set trigger split
6. PA - reactivate (in case settings interrupted sampling)
7. Wait for buffer to fill
8. S! - trigger and read I/Q data
"""

import sys
import time

sys.path.insert(0, "src")

from openflight.ops243 import OPS243Radar


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


def main():
    print("=" * 70)
    print("  Rolling Buffer Debug (API Doc Sequence)")
    print("=" * 70)
    print()

    radar = OPS243Radar()
    radar.connect()
    print(f"Connected: {radar.port}")

    info = radar.get_info()
    print(f"Firmware: {info.get('Version', 'unknown')}")
    print()

    # Step 1: Query current mode
    print("-" * 70)
    print("Step 1: Query current state")
    print("-" * 70)
    send_and_print(radar, "G?", "query operation mode")
    send_and_print(radar, "S?", "query sample settings")
    send_and_print(radar, "P?", "query power mode")

    # Step 2: Reset to known state
    print()
    print("-" * 70)
    print("Step 2: Reset to idle (PI)")
    print("-" * 70)
    send_and_print(radar, "PI", "power idle")
    time.sleep(0.2)

    # Step 3: Enter rolling buffer mode
    print()
    print("-" * 70)
    print("Step 3: Enter rolling buffer mode (GC)")
    print("-" * 70)
    send_and_print(radar, "GC", "rolling buffer mode")
    send_and_print(radar, "G?", "verify mode")

    # Step 4: Activate sampling
    print()
    print("-" * 70)
    print("Step 4: Activate sampling (PA)")
    print("-" * 70)
    send_and_print(radar, "PA", "power active")
    send_and_print(radar, "P?", "verify power mode")

    # Step 5: Configure sample rate
    print()
    print("-" * 70)
    print("Step 5: Set sample rate (S=30)")
    print("-" * 70)
    send_and_print(radar, "S=30", "30ksps sample rate")
    send_and_print(radar, "S?", "verify sample rate")

    # Step 6: Set trigger split
    print()
    print("-" * 70)
    print("Step 6: Set trigger split (S#12)")
    print("-" * 70)
    send_and_print(radar, "S#12", "12 pre-trigger segments")

    # Step 7: Reactivate sampling (critical!)
    print()
    print("-" * 70)
    print("Step 7: Reactivate sampling after config changes (PA)")
    print("-" * 70)
    send_and_print(radar, "PA", "power active")
    send_and_print(radar, "P?", "verify power mode")
    send_and_print(radar, "G?", "verify still in rolling buffer mode")

    # Step 8: Wait for buffer to fill
    print()
    print("-" * 70)
    print("Step 8: Wait for buffer to fill (1 second)")
    print("-" * 70)
    print("  Waiting...")
    time.sleep(1.0)
    print("  Done.")

    # Step 9: Trigger capture
    print()
    print("-" * 70)
    print("Step 9: Trigger capture (S!)")
    print("-" * 70)

    # Clear buffer
    radar.serial.reset_input_buffer()

    # Send trigger
    print("  Sending S!...")
    radar.serial.write(b"S!\r")
    radar.serial.flush()

    # Read response with timeout
    start = time.time()
    chunks = []
    timeout = 10.0

    while time.time() - start < timeout:
        if radar.serial.in_waiting:
            chunk = radar.serial.read(radar.serial.in_waiting)
            chunks.append(chunk)

            # Check for complete response
            full = b''.join(chunks)
            if b'"Q"' in full and b']}' in full[full.rfind(b'"Q"'):]:
                break
        time.sleep(0.05)

    elapsed = time.time() - start
    response = b''.join(chunks).decode('utf-8', errors='ignore')

    print(f"  Response time: {elapsed*1000:.0f}ms")
    print(f"  Response length: {len(response)} bytes")

    # Analyze response
    has_i = '"I"' in response
    has_q = '"Q"' in response
    has_sample_time = '"sample_time"' in response or '"1st Sample Time"' in response
    has_trigger_time = '"trigger_time"' in response or '"Trigger time"' in response

    print()
    print("  Response analysis:")
    print(f"    Contains I array: {has_i}")
    print(f"    Contains Q array: {has_q}")
    print(f"    Contains sample_time: {has_sample_time}")
    print(f"    Contains trigger_time: {has_trigger_time}")

    if len(response) < 500:
        print()
        print(f"  Full response: {response}")
    else:
        print()
        print(f"  First 500 chars: {response[:500]}...")

    if has_i and has_q:
        print()
        print("  SUCCESS: Received I/Q data!")
    else:
        print()
        print("  FAIL: No I/Q data received")
        print()
        print("  Troubleshooting:")
        print("    1. Check firmware version supports GC mode (1.2.3+)")
        print("    2. Try power cycling the radar")
        print("    3. Check if HOST_INT pin is floating/grounded")

    # Cleanup
    print()
    print("-" * 70)
    print("Cleanup")
    print("-" * 70)
    send_and_print(radar, "PI", "return to idle")
    radar.disconnect()
    print()
    print("Done.")


if __name__ == "__main__":
    main()
