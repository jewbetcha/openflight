#!/usr/bin/env python3
"""Average a stationary LIS3DH and print its recommended zero-offset flag."""

import argparse
import statistics
import time

from openflight.inclinometer import LIS3DH
from openflight.inclinometer.service import pitch_degrees


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus", type=int, default=1)
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x18)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument(
        "--reference-pitch",
        type=float,
        default=0.0,
        help="Known pitch of the supporting surface in degrees (default: level/0)",
    )
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("--samples must be at least 2")

    sensor = LIS3DH(bus_number=args.bus, address=args.address)
    sensor.initialize()
    pitches = []
    try:
        print(f"Keep the enclosure still while collecting {args.samples} samples...")
        for _ in range(args.samples):
            pitches.append(pitch_degrees(sensor.read()))
            time.sleep(args.interval)
    finally:
        sensor.close()

    raw_pitch = statistics.mean(pitches)
    std_pitch = statistics.pstdev(pitches)
    offset = args.reference_pitch - raw_pitch
    print(f"Raw pitch mean: {raw_pitch:+.3f}deg (std dev {std_pitch:.3f}deg)")
    print(f"Reference pitch: {args.reference_pitch:+.3f}deg")
    print(f"Recommended flag: --inclinometer-zero-offset {offset:+.3f}")


if __name__ == "__main__":
    main()
