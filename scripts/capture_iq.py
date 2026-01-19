#!/usr/bin/env python3
"""
Capture raw I/Q data from continuous streaming mode and save to pickle file.
This allows offline analysis and debugging of signal processing.

Usage:
    python scripts/capture_iq.py [output_file.pkl]

Default output: ~/openflight_sessions/iq_captures_YYYYMMDD_HHMMSS.pkl
"""

import pickle
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import List

import numpy as np

from openflight.ops243 import IQBlock, OPS243Radar


# Capture settings
SAMPLE_RATE = 30000  # Hz
WINDOW_SIZE = 128    # Samples per block


def block_to_capture(block: IQBlock, start_time: float) -> dict:
    """
    Convert an IQBlock to the capture dict format expected by analysis scripts.

    Args:
        block: IQBlock from streaming
        start_time: Reference time for calculating sample_time

    Returns:
        Dict with complex_signal, sample_time, and raw data
    """
    i_samples = np.array(block.i_samples, dtype=np.int16)
    q_samples = np.array(block.q_samples, dtype=np.int16)

    # Compute derived values (same as streaming/processor.py)
    i_centered = i_samples.astype(np.float64) - np.mean(i_samples)
    q_centered = q_samples.astype(np.float64) - np.mean(q_samples)

    # Scale to voltage (12-bit ADC, 3.3V reference)
    i_scaled = i_centered * (3.3 / 4096)
    q_scaled = q_centered * (3.3 / 4096)

    # Complex signal (standard I + jQ)
    complex_signal = i_scaled + 1j * q_scaled

    # sample_time is relative to capture start (what analysis script expects)
    sample_time = block.timestamp - start_time

    return {
        "sample_time": sample_time,
        "i_raw": i_samples,
        "q_raw": q_samples,
        "i_centered": i_centered,
        "q_centered": q_centered,
        "i_scaled": i_scaled,
        "q_scaled": q_scaled,
        "complex_signal": complex_signal,
        "capture_timestamp": datetime.now().isoformat(),
        "block_timestamp": block.timestamp,
    }


def main():
    # Output file - save to ~/openflight_sessions by default
    if len(sys.argv) > 1:
        output_path = Path(sys.argv[1]).expanduser().resolve()
    else:
        output_dir = Path.home() / "openflight_sessions"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"iq_captures_{timestamp}.pkl"

    print("=== I/Q Capture Tool (Streaming Mode) ===")
    print(f"Output file: {output_path}")
    print("Connecting to radar...")

    radar = OPS243Radar()
    radar.connect()

    # Get radar info
    info = radar.get_info()
    print(f"Radar: {info.get('Product', 'unknown')} v{info.get('Version', 'unknown')}")

    # Configure for I/Q streaming
    print("Configuring for continuous I/Q streaming...")
    radar.configure_for_iq_streaming()

    captures: List[dict] = []
    start_time: float = 0
    stop_event = Event()

    metadata = {
        "radar_info": info,
        "capture_start": datetime.now().isoformat(),
        "sample_rate": SAMPLE_RATE,
        "fft_size": 4096,
        "window_size": WINDOW_SIZE,
        "mode": "iq_streaming",
    }

    # Stats tracking
    block_count = 0
    last_print_time = time.time()
    blocks_since_print = 0

    def on_block(block: IQBlock):
        nonlocal block_count, start_time, last_print_time, blocks_since_print

        # Set start time on first block
        if block_count == 0:
            start_time = block.timestamp

        block_count += 1
        blocks_since_print += 1

        # Convert and store
        capture = block_to_capture(block, start_time)
        captures.append(capture)

        # Show stats every second
        now = time.time()
        if now - last_print_time >= 1.0:
            # Calculate activity from recent blocks
            recent = captures[-blocks_since_print:] if blocks_since_print > 0 else []
            if recent:
                i_ranges = [c['i_raw'].max() - c['i_raw'].min() for c in recent]
                q_ranges = [c['q_raw'].max() - c['q_raw'].min() for c in recent]
                max_range = max(max(i_ranges), max(q_ranges))

                if max_range > 1000:
                    activity = "HIGH ACTIVITY"
                elif max_range > 200:
                    activity = "medium"
                else:
                    activity = "low/noise"
            else:
                activity = "..."

            elapsed = now - (start_time if start_time else now)
            rate = blocks_since_print / (now - last_print_time)
            print(f"[{block_count:5d} blocks, {elapsed:6.1f}s] {rate:5.1f} blocks/sec - {activity}")

            last_print_time = now
            blocks_since_print = 0

    def on_error(error: str):
        print(f"[ERROR] {error}")

    print("\nCapturing I/Q data continuously.")
    print("Swing a club or hit balls to capture motion data.")
    print("Press Ctrl+C to stop and save\n")

    try:
        radar.start_iq_streaming(callback=on_block, error_callback=on_error)

        # Wait for Ctrl+C
        while not stop_event.is_set():
            time.sleep(0.1)

    except KeyboardInterrupt:
        print(f"\n\nStopping... captured {block_count} blocks")
    finally:
        radar.stop_streaming()
        radar.disconnect()

    # Save to pickle
    if captures:
        metadata["capture_end"] = datetime.now().isoformat()
        metadata["total_blocks"] = len(captures)
        metadata["duration_seconds"] = captures[-1]["sample_time"] if captures else 0

        output_data = {
            "metadata": metadata,
            "captures": captures,
        }

        with open(output_path, "wb") as f:
            pickle.dump(output_data, f)

        print(f"\nSaved {len(captures)} captures to {output_path}")
        print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")
        print(f"Duration: {metadata['duration_seconds']:.1f} seconds")

        print("\nTo analyze:")
        print(f"  cd src/analysis && python analyze_capture.py")
        print(f"  # or load directly:")
        print(f"  import pickle")
        print(f"  with open('{output_path}', 'rb') as f:")
        print(f"      data = pickle.load(f)")
        print(f"  # data['captures'][i]['complex_signal'] - complex I/Q signal")
        print(f"  # data['captures'][i]['sample_time'] - time offset in seconds")
    else:
        print("\nNo captures to save.")


if __name__ == "__main__":
    main()
