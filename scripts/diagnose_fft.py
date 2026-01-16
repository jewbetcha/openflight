#!/usr/bin/env python3
"""
Diagnostic script to analyze raw I/Q data from rolling buffer.
Run this while swinging a club to see what the FFT actually shows.
"""

import numpy as np
import json
import time
from openflight.ops243 import OPS243Radar

# Constants
SAMPLE_RATE = 30000
FFT_SIZE = 4096
WAVELENGTH_M = 0.01243
MPS_TO_MPH = 2.23694

def bin_to_mph(bin_idx):
    """Convert FFT bin to speed in mph."""
    freq_hz = abs(bin_idx) * SAMPLE_RATE / FFT_SIZE
    speed_mps = freq_hz * WAVELENGTH_M / 2
    return speed_mps * MPS_TO_MPH

def analyze_capture(response: str):
    """Analyze a single capture."""
    # Parse JSON
    i_samples = None
    q_samples = None

    for line in response.strip().split('\n'):
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            data = json.loads(line)
            if "I" in data:
                i_samples = np.array(data["I"])
            elif "Q" in data:
                q_samples = np.array(data["Q"])
        except json.JSONDecodeError:
            continue

    if i_samples is None or q_samples is None:
        print("Failed to parse I/Q data")
        return

    print(f"\n=== I/Q Data Stats ===")
    print(f"I samples: {len(i_samples)}, range: {i_samples.min()}-{i_samples.max()}, mean: {i_samples.mean():.1f}")
    print(f"Q samples: {len(q_samples)}, range: {q_samples.min()}-{q_samples.max()}, mean: {q_samples.mean():.1f}")

    # Method 1: Full 4096-sample FFT (no windowing)
    print(f"\n=== Full 4096-sample FFT ===")
    i_centered = i_samples - np.mean(i_samples)
    q_centered = q_samples - np.mean(q_samples)
    complex_signal = i_centered + 1j * q_centered

    fft_result = np.fft.fft(complex_signal)
    magnitude = np.abs(fft_result)

    # Find top 5 peaks in positive frequencies (bins 1 to 2047)
    half = FFT_SIZE // 2
    pos_mags = magnitude[1:half]
    pos_top_indices = np.argsort(pos_mags)[-5:][::-1] + 1

    print("Top 5 POSITIVE freq peaks (inbound/toward radar):")
    for idx in pos_top_indices:
        mph = bin_to_mph(idx)
        print(f"  Bin {idx}: {magnitude[idx]:.1f} mag -> {mph:.1f} mph")

    # Find top 5 peaks in negative frequencies (bins 2048 to 4095)
    neg_mags = magnitude[half+1:]
    neg_top_indices = np.argsort(neg_mags)[-5:][::-1] + half + 1

    print("Top 5 NEGATIVE freq peaks (outbound/away from radar):")
    for idx in neg_top_indices:
        # Convert to negative bin for display
        neg_bin = idx - FFT_SIZE
        mph = bin_to_mph(neg_bin)
        print(f"  Bin {neg_bin} ({idx}): {magnitude[idx]:.1f} mag -> {mph:.1f} mph")

    # Method 2: Windowed approach (like our processor)
    print(f"\n=== Windowed 128-sample blocks (first 5 blocks) ===")
    window = np.hanning(128)

    for block_idx in range(min(5, len(i_samples) // 128)):
        start = block_idx * 128
        i_block = i_samples[start:start+128]
        q_block = q_samples[start:start+128]

        i_c = i_block - np.mean(i_block)
        q_c = q_block - np.mean(q_block)

        i_w = i_c * window * (3.3/4096)
        q_w = q_c * window * (3.3/4096)

        sig = i_w + 1j * q_w
        fft_w = np.fft.fft(sig, FFT_SIZE)
        mag_w = np.abs(fft_w)

        # Find peak in positive and negative
        pos_peak = np.argmax(mag_w[1:half]) + 1
        neg_peak = np.argmax(mag_w[half+1:]) + half + 1

        pos_mph = bin_to_mph(pos_peak)
        neg_mph = bin_to_mph(neg_peak - FFT_SIZE)

        winner = "POS (inbound)" if mag_w[pos_peak] >= mag_w[neg_peak] else "NEG (outbound)"

        print(f"Block {block_idx}: pos_peak bin {pos_peak} ({pos_mph:.1f} mph, mag {mag_w[pos_peak]:.4f}) | "
              f"neg_peak bin {neg_peak-FFT_SIZE} ({neg_mph:.1f} mph, mag {mag_w[neg_peak]:.4f}) -> {winner}")


def main():
    print("=== OpenFlight FFT Diagnostic ===")
    print("Connecting to radar...")

    radar = OPS243Radar()
    radar.connect()

    # Configure for rolling buffer
    print("Configuring rolling buffer mode...")
    radar.configure_for_rolling_buffer()

    print("\nSwing a club in front of the radar!")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            # Trigger capture
            response = radar.trigger_capture(timeout=10.0)
            radar.rearm_rolling_buffer()

            if len(response) > 1000:  # Got actual data
                analyze_capture(response)
            else:
                print(".", end="", flush=True)

            time.sleep(0.3)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        radar.disconnect()


if __name__ == "__main__":
    main()
