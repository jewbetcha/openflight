#!/usr/bin/env python3
"""Test script to read raw radar output."""

import serial
import serial.tools.list_ports

# List all ports
print("Available serial ports:")
for p in serial.tools.list_ports.comports():
    print(f"  {p.device}: vid={p.vid} desc={p.description}")

# Find radar port (try common names)
port = None
for p in serial.tools.list_ports.comports():
    if 'ACM' in p.device or 'usbmodem' in p.device:
        port = p.device
        break

if not port:
    print("\nNo radar port found. Specify manually:")
    print("  python scripts/test_radar_raw.py /dev/ttyACM0")
    exit(1)

print(f"\nConnecting to {port}...")
s = serial.Serial(port, 57600, timeout=2)

print("Reading 20 lines (wave your hand in front of radar):\n")
for i in range(20):
    data = s.readline()
    print(f"{i:2d}: {data!r}")

s.close()
print("\nDone.")
