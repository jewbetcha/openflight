#!/usr/bin/env python3
"""
Replay raw I/Q captures from session logs through the FFT pipeline.

Reads rolling_buffer_capture entries from a session JSONL file, runs each
through the processor, and prints detailed FFT analysis showing what the
processor sees at each step. This is the primary tool for debugging why
real golf swings aren't being detected.

Usage:
    uv run python scripts/replay_captures.py session_logs/session_*.jsonl
    uv run python scripts/replay_captures.py session_logs/session_*.jsonl --capture 3
    uv run python scripts/replay_captures.py session_logs/session_*.jsonl --fft-detail
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openflight.rolling_buffer.processor import RollingBufferProcessor
from openflight.rolling_buffer.types import IQCapture


def load_captures(filepath: str) -> list[dict]:
    """Load rolling_buffer_capture entries from a JSONL session file."""
    captures = []
    with open(filepath) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("type") == "rolling_buffer_capture":
                    entry["_line"] = line_num
                    captures.append(entry)
            except json.JSONDecodeError:
                continue
    return captures


def analyze_block_detail(processor: RollingBufferProcessor, i_block, q_block, block_idx: int):
    """Run FFT on a single block and print detailed spectrum info."""
    i_block = np.array(i_block, dtype=np.float64)
    q_block = np.array(q_block, dtype=np.float64)

    # Reproduce the processor's pipeline step by step
    i_centered = i_block - np.mean(i_block)
    q_centered = q_block - np.mean(q_block)
    i_scaled = i_centered * (processor.VOLTAGE_REF / processor.ADC_RANGE)
    q_scaled = q_centered * (processor.VOLTAGE_REF / processor.ADC_RANGE)
    i_windowed = i_scaled * processor.hanning_window
    q_windowed = q_scaled * processor.hanning_window
    complex_signal = i_windowed + 1j * q_windowed

    fft_result = np.fft.fft(complex_signal, processor.FFT_SIZE)
    magnitude = np.abs(fft_result)

    half = processor.FFT_SIZE // 2
    dc_mask = processor.DC_MASK_BINS

    # Find top 5 peaks in positive frequencies (outbound)
    pos_mags = magnitude[1:half].copy()
    pos_peaks = []
    for _ in range(5):
        idx = np.argmax(pos_mags) + 1  # +1 because we start from bin 1
        mag = pos_mags[idx - 1]
        if mag < 1.0:
            break
        freq_hz = idx * processor.SAMPLE_RATE / processor.FFT_SIZE
        speed_mps = freq_hz * processor.WAVELENGTH_M / 2
        speed_mph = speed_mps * processor.MPS_TO_MPH
        masked = idx < dc_mask
        pos_peaks.append((idx, mag, speed_mph, masked))
        # Zero out nearby bins to find next peak
        lo = max(0, idx - 1 - 20)
        hi = min(half - 1, idx - 1 + 20)
        pos_mags[lo:hi] = 0

    # Find top 5 peaks in negative frequencies (inbound)
    neg_start = half + 1
    neg_end = processor.FFT_SIZE - dc_mask
    neg_mags = magnitude[neg_start:neg_end].copy() if neg_start < neg_end else np.array([])
    neg_peaks = []
    for _ in range(5):
        if len(neg_mags) == 0:
            break
        idx_rel = np.argmax(neg_mags)
        mag = neg_mags[idx_rel]
        if mag < 1.0:
            break
        abs_bin = idx_rel + neg_start
        freq_bin = processor.FFT_SIZE - abs_bin
        freq_hz = freq_bin * processor.SAMPLE_RATE / processor.FFT_SIZE
        speed_mps = freq_hz * processor.WAVELENGTH_M / 2
        speed_mph = speed_mps * processor.MPS_TO_MPH
        neg_peaks.append((abs_bin, mag, speed_mph, False))
        lo = max(0, idx_rel - 20)
        hi = min(len(neg_mags), idx_rel + 20)
        neg_mags[lo:hi] = 0

    # Also check what's in the DC-masked negative region (near bin FFT_SIZE-1)
    dc_neg_mags = magnitude[processor.FFT_SIZE - dc_mask:] if dc_mask > 0 else np.array([])
    dc_neg_peak_mag = np.max(dc_neg_mags) if len(dc_neg_mags) > 0 else 0
    dc_neg_peak_bin = np.argmax(dc_neg_mags) + (processor.FFT_SIZE - dc_mask) if len(dc_neg_mags) > 0 else 0

    timestamp_ms = (block_idx * processor.STEP_SIZE_STANDARD / processor.SAMPLE_RATE) * 1000

    print(f"  Block {block_idx:3d} (t={timestamp_ms:6.1f}ms):")

    if pos_peaks:
        print(f"    OUTBOUND (pos freq) top peaks:")
        for bin_idx, mag, speed, masked in pos_peaks:
            mask_tag = " [DC MASKED]" if masked else ""
            thresh_tag = " [< threshold]" if mag < processor.MAGNITUDE_THRESHOLD else ""
            print(f"      bin {bin_idx:5d}  mag {mag:8.1f}  {speed:6.1f} mph{mask_tag}{thresh_tag}")
    else:
        print(f"    OUTBOUND: no peaks above 1.0")

    if neg_peaks:
        print(f"    INBOUND (neg freq) top peaks:")
        for bin_idx, mag, speed, masked in neg_peaks:
            thresh_tag = " [< threshold]" if mag < processor.MAGNITUDE_THRESHOLD else ""
            print(f"      bin {bin_idx:5d}  mag {mag:8.1f}  {speed:6.1f} mph{thresh_tag}")
    else:
        print(f"    INBOUND: no peaks above 1.0")

    if dc_neg_peak_mag > 1.0:
        freq_bin = processor.FFT_SIZE - dc_neg_peak_bin
        speed_mps = freq_bin * processor.SAMPLE_RATE / processor.FFT_SIZE * processor.WAVELENGTH_M / 2
        speed_mph = speed_mps * processor.MPS_TO_MPH
        print(f"    DC-MASKED NEG: bin {dc_neg_peak_bin} mag {dc_neg_peak_mag:.1f} ({speed_mph:.1f} mph)")


def analyze_capture(
    processor: RollingBufferProcessor,
    capture_data: dict,
    capture_idx: int,
    fft_detail: bool = False,
):
    """Analyze a single capture through the full pipeline."""
    i_samples = capture_data["i_samples"]
    q_samples = capture_data["q_samples"]
    sample_time = capture_data.get("sample_time", 0)
    trigger_time = capture_data.get("trigger_time", 0)
    trigger_offset_ms = capture_data.get("trigger_offset_ms", (trigger_time - sample_time) * 1000)

    print(f"\n{'='*80}")
    print(f"CAPTURE #{capture_idx} (line {capture_data.get('_line', '?')})")
    print(f"  sample_time={sample_time:.3f}  trigger_time={trigger_time:.3f}")
    print(f"  trigger_offset_ms={trigger_offset_ms:.1f}")
    print(f"  samples: {len(i_samples)} I, {len(q_samples)} Q")

    # Basic I/Q stats
    i_arr = np.array(i_samples)
    q_arr = np.array(q_samples)
    print(f"  I: mean={i_arr.mean():.0f}  std={i_arr.std():.1f}  min={i_arr.min()}  max={i_arr.max()}")
    print(f"  Q: mean={q_arr.mean():.0f}  std={q_arr.std():.1f}  min={q_arr.min()}  max={q_arr.max()}")

    capture = IQCapture(
        sample_time=sample_time,
        trigger_time=trigger_time,
        i_samples=i_samples,
        q_samples=q_samples,
    )

    # Standard processing (what the trigger uses for validation)
    print(f"\n--- Standard Processing (128-sample blocks, no overlap) ---")
    timeline_std = processor.process_standard(capture)
    outbound = [r for r in timeline_std.readings if r.is_outbound]
    inbound = [r for r in timeline_std.readings if not r.is_outbound]

    print(f"  Total readings: {len(timeline_std.readings)}")
    print(f"  Outbound: {len(outbound)}")
    print(f"  Inbound:  {len(inbound)}")

    if outbound:
        speeds = sorted(set(f"{r.speed_mph:.1f}" for r in outbound))
        peak = max(outbound, key=lambda r: r.speed_mph)
        peak_mag = max(outbound, key=lambda r: r.magnitude)
        print(f"  Outbound peak speed: {peak.speed_mph:.1f} mph (mag {peak.magnitude:.1f})")
        print(f"  Outbound peak magnitude: {peak_mag.magnitude:.1f} at {peak_mag.speed_mph:.1f} mph")
        print(f"  Outbound speed values: {', '.join(speeds)}")
        above_15 = [r for r in outbound if r.speed_mph >= 15.0]
        print(f"  Outbound >= 15 mph: {len(above_15)}")

    if inbound:
        speeds = sorted(set(f"{r.speed_mph:.1f}" for r in inbound))
        peak = max(inbound, key=lambda r: r.speed_mph)
        print(f"  Inbound peak speed: {peak.speed_mph:.1f} mph (mag {peak.magnitude:.1f})")
        print(f"  Inbound speed values: {', '.join(speeds)}")

    # Overlapping processing (what the main pipeline uses)
    print(f"\n--- Overlapping Processing (32-sample steps) ---")
    timeline_ovr = processor.process_overlapping(capture)
    outbound_ovr = [r for r in timeline_ovr.readings if r.is_outbound]
    inbound_ovr = [r for r in timeline_ovr.readings if not r.is_outbound]

    print(f"  Total readings: {len(timeline_ovr.readings)}")
    print(f"  Outbound: {len(outbound_ovr)}")
    print(f"  Inbound:  {len(inbound_ovr)}")

    if outbound_ovr:
        peak = max(outbound_ovr, key=lambda r: r.speed_mph)
        above_15 = [r for r in outbound_ovr if r.speed_mph >= 15.0]
        print(f"  Outbound peak speed: {peak.speed_mph:.1f} mph (mag {peak.magnitude:.1f})")
        print(f"  Outbound >= 15 mph: {len(above_15)}")

    # Full pipeline
    print(f"\n--- Full Pipeline (process_capture) ---")
    result = processor.process_capture(capture)
    if result:
        print(f"  Ball speed: {result.ball_speed_mph:.1f} mph")
        print(f"  Club speed: {result.club_speed_mph:.1f} mph" if result.club_speed_mph else "  Club speed: not detected")
        print(f"  Spin: {result.spin}")
    else:
        print(f"  RESULT: None (no valid shot detected)")

    # Detailed per-block FFT analysis
    if fft_detail:
        print(f"\n--- Per-Block FFT Detail ---")
        print(f"  DC_MASK_BINS={processor.DC_MASK_BINS} (~{processor.DC_MASK_BINS * processor.SAMPLE_RATE / processor.FFT_SIZE * processor.WAVELENGTH_M / 2 * processor.MPS_TO_MPH:.1f} mph)")
        print(f"  MAGNITUDE_THRESHOLD={processor.MAGNITUDE_THRESHOLD}")

        num_blocks = (len(i_samples) - processor.WINDOW_SIZE) // processor.STEP_SIZE_STANDARD + 1
        for block_idx in range(num_blocks):
            start = block_idx * processor.STEP_SIZE_STANDARD
            i_block = i_samples[start:start + processor.WINDOW_SIZE]
            q_block = q_samples[start:start + processor.WINDOW_SIZE]
            analyze_block_detail(processor, i_block, q_block, block_idx)


def main():
    parser = argparse.ArgumentParser(
        description="Replay raw I/Q captures through FFT pipeline"
    )
    parser.add_argument("session_file", help="Path to session JSONL file")
    parser.add_argument("--capture", type=int, default=None,
                       help="Analyze only capture N (1-indexed)")
    parser.add_argument("--fft-detail", action="store_true",
                       help="Show per-block FFT peaks with bin numbers and magnitudes")
    parser.add_argument("--summary", action="store_true",
                       help="Show only one-line summary per capture")
    args = parser.parse_args()

    captures = load_captures(args.session_file)

    if not captures:
        print(f"No rolling_buffer_capture entries found in {args.session_file}")
        print(f"\nThis session may not have I/Q logging enabled.")
        print(f"Deploy the latest code and re-test to capture raw I/Q data.")
        sys.exit(1)

    print(f"Found {len(captures)} captures in {args.session_file}")
    print(f"Processor: DC_MASK_BINS={RollingBufferProcessor.DC_MASK_BINS}, "
          f"MAGNITUDE_THRESHOLD={RollingBufferProcessor.MAGNITUDE_THRESHOLD}, "
          f"FFT_SIZE={RollingBufferProcessor.FFT_SIZE}")

    processor = RollingBufferProcessor()

    if args.capture is not None:
        if args.capture < 1 or args.capture > len(captures):
            print(f"Capture {args.capture} out of range (1-{len(captures)})")
            sys.exit(1)
        analyze_capture(processor, captures[args.capture - 1], args.capture,
                       fft_detail=args.fft_detail)
        return

    for idx, capture_data in enumerate(captures, 1):
        if args.summary:
            # Quick one-line summary
            i_samples = capture_data["i_samples"]
            q_samples = capture_data["q_samples"]
            capture = IQCapture(
                sample_time=capture_data.get("sample_time", 0),
                trigger_time=capture_data.get("trigger_time", 0),
                i_samples=i_samples,
                q_samples=q_samples,
            )
            timeline = processor.process_standard(capture)
            outbound = [r for r in timeline.readings if r.is_outbound]
            inbound = [r for r in timeline.readings if not r.is_outbound]
            peak_out = max((r.speed_mph for r in outbound), default=0)
            peak_in = max((r.speed_mph for r in inbound), default=0)
            out_above_15 = sum(1 for r in outbound if r.speed_mph >= 15.0)
            result = processor.process_capture(capture)
            ball = f"{result.ball_speed_mph:.0f}" if result else "-"
            print(f"  #{idx:3d}: out={len(outbound):3d} (>15mph: {out_above_15:3d}, "
                  f"peak {peak_out:5.1f})  in={len(inbound):3d} (peak {peak_in:5.1f})  "
                  f"ball={ball} mph")
        else:
            analyze_capture(processor, capture_data, idx, fft_detail=args.fft_detail)


if __name__ == "__main__":
    main()
