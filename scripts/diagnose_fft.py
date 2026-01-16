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
    print(f"I samples: {len(i_samples)}, range: {i_samples.min()}-{i_samples.max()}, mean: {i_samples.mean():.1f}, std: {np.std(i_samples):.1f}")
    print(f"Q samples: {len(q_samples)}, range: {q_samples.min()}-{q_samples.max()}, mean: {q_samples.mean():.1f}, std: {np.std(q_samples):.1f}")

    # Full 4096-sample FFT
    # Swap I/Q to match radar convention (Q + jI instead of I + jQ)
    i_centered = i_samples - np.mean(i_samples)
    q_centered = q_samples - np.mean(q_samples)
    complex_signal = q_centered + 1j * i_centered  # SWAPPED

    fft_result = np.fft.fft(complex_signal)
    magnitude = np.abs(fft_result)

    half = FFT_SIZE // 2

    # Skip DC region (bins 0-50 = 0-5 mph) to avoid low-freq noise
    DC_SKIP = 50  # Skip first 50 bins (~5 mph)

    print(f"\n=== FFT Peaks (skipping DC, bins < {DC_SKIP}) ===")

    # Find peaks in positive frequencies ABOVE DC region
    pos_mags = magnitude[DC_SKIP:half]
    pos_top_indices = np.argsort(pos_mags)[-5:][::-1] + DC_SKIP

    print("Top 5 POSITIVE freq peaks (>5 mph, inbound):")
    for idx in pos_top_indices:
        mph = bin_to_mph(idx)
        print(f"  Bin {idx}: {magnitude[idx]:.1f} mag -> {mph:.1f} mph")

    # Find peaks in negative frequencies ABOVE DC region
    # Negative freqs are at bins 2048-4095, so skip bins 4046-4095 (equiv to -50 to -1)
    neg_mags = magnitude[half+1:FFT_SIZE-DC_SKIP]
    neg_top_indices = np.argsort(neg_mags)[-5:][::-1] + half + 1

    print("Top 5 NEGATIVE freq peaks (>5 mph, outbound):")
    for idx in neg_top_indices:
        neg_bin = idx - FFT_SIZE
        mph = bin_to_mph(neg_bin)
        print(f"  Bin {neg_bin} ({idx}): {magnitude[idx]:.1f} mag -> {mph:.1f} mph")

    # Also show overall max in each half to see signal strength
    pos_max_bin = np.argmax(magnitude[1:half]) + 1
    neg_max_bin = np.argmax(magnitude[half+1:]) + half + 1
    print(f"\nOverall max: POS bin {pos_max_bin} ({bin_to_mph(pos_max_bin):.1f} mph, {magnitude[pos_max_bin]:.1f}), "
          f"NEG bin {neg_max_bin-FFT_SIZE} ({bin_to_mph(neg_max_bin-FFT_SIZE):.1f} mph, {magnitude[neg_max_bin]:.1f})")

    # Check for signal in golf speed range (50-200 mph = bins 490-1960)
    GOLF_MIN_BIN = 490   # ~50 mph
    GOLF_MAX_BIN = 1960  # ~200 mph

    pos_golf = magnitude[GOLF_MIN_BIN:GOLF_MAX_BIN]
    neg_golf = magnitude[FFT_SIZE-GOLF_MAX_BIN:FFT_SIZE-GOLF_MIN_BIN]

    pos_golf_max_idx = np.argmax(pos_golf) + GOLF_MIN_BIN
    neg_golf_max_idx = FFT_SIZE - GOLF_MAX_BIN + np.argmax(neg_golf)

    print(f"\n=== Golf Speed Range ({GOLF_MIN_BIN}-{GOLF_MAX_BIN} bins, 50-200 mph) ===")
    print(f"POS max in range: bin {pos_golf_max_idx} -> {bin_to_mph(pos_golf_max_idx):.1f} mph, mag {magnitude[pos_golf_max_idx]:.1f}")
    print(f"NEG max in range: bin {neg_golf_max_idx-FFT_SIZE} -> {bin_to_mph(neg_golf_max_idx-FFT_SIZE):.1f} mph, mag {magnitude[neg_golf_max_idx]:.1f}")
    print(f"Noise floor in golf range: {np.median(pos_golf):.1f} (pos), {np.median(neg_golf):.1f} (neg)")

    # Sample rate diagnostic: if peaks are at low bins, what sample rate would that imply?
    # For a 45 mph swing: f_doppler = 2 * 20.1 m/s / 0.01243 = 3235 Hz
    # At 30 kHz: bin = 3235 * 4096 / 30000 = 442
    # At 10 kHz: bin = 3235 * 4096 / 10000 = 1325
    # At 1 kHz: bin = 3235 * 4096 / 1000 = 13256 (wraps around)
    print(f"\n=== Sample Rate Diagnostic ===")
    print("Expected bins for 45 mph at different sample rates:")
    for rate in [10000, 20000, 30000, 50000, 100000]:
        expected_bin = int(3235 * 4096 / rate)
        print(f"  {rate/1000:.0f} kHz: bin {expected_bin}")

    # If we're seeing peaks at bin ~30, back-calculate what sample rate that implies
    # for a 45 mph signal
    if pos_max_bin > 10:
        implied_rate = 3235 * 4096 / pos_max_bin
        print(f"\nIf bin {pos_max_bin} is 45 mph, implied sample rate: {implied_rate/1000:.1f} kHz")

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

        sig = q_w + 1j * i_w  # SWAPPED to match radar convention
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
