"""
Real-time I/Q streaming processor with CFAR-based detection.

Processes continuous raw I/Q data from the radar into speed readings.
Uses a two-stage detection approach:
1. Fast SNR-based peak detection (every block)
2. Full 2D CFAR validation (periodic)
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

from ..ops243 import Direction, IQBlock, SpeedReading
from ..session_logger import get_session_logger
from .cfar import CFAR2DDetector, CFARConfig


@dataclass
class StreamingConfig:
    """Configuration for the streaming processor."""

    sample_rate: int = 30000        # Sample rate in Hz
    window_size: int = 128          # Samples per FFT window
    fft_size: int = 4096            # Zero-padded FFT size
    min_speed_mph: float = 35       # Minimum speed to report (club speeds start ~40 mph)
    max_speed_mph: float = 220      # Maximum speed to report

    # Radar constants
    wavelength_m: float = 0.01243   # 24.125 GHz wavelength
    mps_to_mph: float = 2.23694     # Conversion factor

    # CFAR configuration
    cfar: CFARConfig = field(default_factory=CFARConfig)


class StreamingIQProcessor:
    """
    Processes raw I/Q blocks into speed readings using FFT with CFAR detection.

    Processing pipeline:
    1. Receive I/Q block (128 samples)
    2. Remove DC offset, scale to voltage, apply window
    3. Compute FFT magnitude spectrum
    4. Fast path: SNR-based peak detection
    5. Periodic: Full 2D CFAR validation
    6. Convert to SpeedReading if valid
    """

    def __init__(self, config: Optional[StreamingConfig] = None, debug: bool = False):
        self.config = config or StreamingConfig()
        self.debug = debug
        self.hanning_window = np.hanning(self.config.window_size)

        # Pre-compute bin-to-speed lookup
        cfg = self.config
        bin_freqs = np.arange(cfg.fft_size) * cfg.sample_rate / cfg.fft_size
        self.bin_to_mph = bin_freqs * cfg.wavelength_m / 2 * cfg.mps_to_mph

        # CFAR detector
        self.cfar = CFAR2DDetector(cfg.cfar, cfg.fft_size)

        # Rolling spectrogram buffer
        self.spectrogram_buffer: deque = deque(maxlen=cfg.cfar.spectrogram_length)
        self.timestamp_buffer: deque = deque(maxlen=cfg.cfar.spectrogram_length)
        self._block_count = 0
        self._last_debug_time = 0

    def _compute_spectrum(self, block: IQBlock) -> Optional[np.ndarray]:
        """Compute FFT magnitude spectrum from I/Q block."""
        cfg = self.config
        i_samples = np.array(block.i_samples, dtype=np.float64)
        q_samples = np.array(block.q_samples, dtype=np.float64)

        if len(i_samples) != cfg.window_size or len(q_samples) != cfg.window_size:
            return None

        # Remove DC, scale to voltage, apply window
        i_centered = (i_samples - np.mean(i_samples)) * (3.3 / 4096)
        q_centered = (q_samples - np.mean(q_samples)) * (3.3 / 4096)
        complex_signal = (i_centered + 1j * q_centered) * self.hanning_window

        # FFT
        return np.abs(np.fft.fft(complex_signal, cfg.fft_size))

    def process_block(self, block: IQBlock) -> Optional[SpeedReading]:
        """
        Process a single I/Q block into a speed reading.

        Uses fast SNR-based detection with periodic CFAR validation.
        """
        import time as _time
        cfg = self.config

        magnitude = self._compute_spectrum(block)
        if magnitude is None:
            return None

        # Add to spectrogram buffer
        self.spectrogram_buffer.append(magnitude)
        self.timestamp_buffer.append(block.timestamp)
        self._block_count += 1

        # Fast path: find peak outside DC region
        half = cfg.fft_size // 2
        dc_mask = cfg.cfar.dc_mask_bins

        # Positive frequencies (outbound)
        pos_region = magnitude[dc_mask:half]
        pos_peak_bin = np.argmax(pos_region) + dc_mask
        pos_peak_mag = magnitude[pos_peak_bin]

        # Negative frequencies (inbound)
        neg_region = magnitude[half:cfg.fft_size - dc_mask]
        neg_peak_bin = np.argmax(neg_region) + half
        neg_peak_mag = magnitude[neg_peak_bin]

        # Choose strongest peak
        if pos_peak_mag >= neg_peak_mag:
            peak_bin, peak_mag = pos_peak_bin, pos_peak_mag
            direction = Direction.OUTBOUND
        else:
            peak_bin, peak_mag = neg_peak_bin, neg_peak_mag
            direction = Direction.INBOUND

        # Compute SNR (signal-to-noise ratio)
        valid_bins = np.concatenate([magnitude[dc_mask:half], magnitude[half:-dc_mask]])
        noise_floor = np.median(valid_bins)
        snr = peak_mag / max(noise_floor, 1e-10)

        # Convert bin to speed (for debug output)
        if peak_bin < half:
            speed_mph = self.bin_to_mph[peak_bin]
        else:
            speed_mph = self.bin_to_mph[abs(peak_bin - cfg.fft_size)]

        # Debug output - show FFT analysis (throttled or when interesting)
        if self.debug:
            now = _time.time()
            snr_status = "PASS" if snr >= cfg.cfar.threshold_factor else "fail"
            speed_status = "PASS" if cfg.min_speed_mph <= speed_mph <= cfg.max_speed_mph else "fail"

            # Print if: SNR passes threshold, OR every 100 blocks for status
            interesting = snr >= cfg.cfar.threshold_factor
            periodic = (self._block_count % 100 == 0)

            if interesting or periodic:
                marker = ">>>" if interesting else "   "
                print(f"{marker}[FFT] blk={self._block_count} peak={peak_mag:.4f} noise={noise_floor:.4f} "
                      f"SNR={snr:.1f}({snr_status}) speed={speed_mph:.1f}mph({speed_status}) "
                      f"dir={direction.value} bin={peak_bin}")

        # Fast rejection if SNR too low
        if snr < cfg.cfar.threshold_factor:
            return None

        # Speed filter
        if not (cfg.min_speed_mph <= speed_mph <= cfg.max_speed_mph):
            if self.debug:
                print(f"[FFT] REJECTED: speed {speed_mph:.1f} outside {cfg.min_speed_mph}-{cfg.max_speed_mph}")
            return None

        # Track if CFAR validated
        cfar_validated = False

        # Periodic CFAR validation (every 8 blocks when buffer full)
        if (len(self.spectrogram_buffer) >= cfg.cfar.spectrogram_length
                and self._block_count % 8 == 0):
            spectrogram = np.array(self.spectrogram_buffer)
            detections = self.cfar.detect(spectrogram)

            if self.debug:
                print(f"[CFAR] Running CFAR on {len(spectrogram)} frames, detections={len(detections)}")

            if not detections:
                if self.debug:
                    print(f"[CFAR] REJECTED: no CFAR detections")
                return None  # CFAR says no valid detection

            cfar_validated = True

            # Use CFAR result
            t_idx, freq_bin, cfar_mag, threshold = detections[0]

            if self.debug:
                print(f"[CFAR] Detection: t={t_idx} bin={freq_bin} mag={cfar_mag:.4f} thresh={threshold:.4f}")

            # Only report recent detections
            if t_idx < len(spectrogram) - 3:
                if self.debug:
                    print(f"[CFAR] REJECTED: detection too old (t={t_idx}, need >= {len(spectrogram)-3})")
                return None

            # Update from CFAR
            if freq_bin < half:
                direction = Direction.OUTBOUND
                speed_mph = self.bin_to_mph[freq_bin]
            else:
                direction = Direction.INBOUND
                speed_mph = self.bin_to_mph[abs(freq_bin - cfg.fft_size)]

            if not (cfg.min_speed_mph <= speed_mph <= cfg.max_speed_mph):
                if self.debug:
                    print(f"[CFAR] REJECTED: CFAR speed {speed_mph:.1f} outside range")
                return None

            if self.debug:
                print(f"[CFAR] ACCEPTED: {speed_mph:.1f} mph {direction.value}")

        # Store detection metadata for logging (convert numpy to native Python types)
        self._last_snr = float(snr)
        self._last_peak_bin = int(peak_bin)
        self._last_cfar_validated = cfar_validated

        return SpeedReading(
            speed=float(speed_mph),
            direction=direction,
            magnitude=float(peak_mag),
            timestamp=block.timestamp,
            unit="mph"
        )


class StreamingSpeedDetector:
    """
    High-level wrapper for continuous I/Q streaming with callbacks.

    Wraps StreamingIQProcessor, tracks statistics, and maintains an I/Q buffer
    for post-session analysis.
    """

    # Keep 2 seconds of I/Q data at ~234 blocks/sec (30000 / 128)
    IQ_BUFFER_SIZE = 500

    def __init__(
        self,
        callback: Callable[[SpeedReading], None],
        config: Optional[StreamingConfig] = None,
        capture_iq: bool = True,
        debug: bool = False
    ):
        """
        Initialize the streaming speed detector.

        Args:
            callback: Called when a speed reading is detected
            config: Streaming configuration
            capture_iq: If True, maintain rolling buffer of I/Q blocks for logging
            debug: If True, print verbose FFT/CFAR debug output
        """
        self.callback = callback
        self.processor = StreamingIQProcessor(config, debug=debug)
        self.debug = debug
        self.blocks_processed = 0
        self.readings_emitted = 0

        # I/Q block capture for logging
        self._capture_iq = capture_iq
        self._iq_buffer: deque = deque(maxlen=self.IQ_BUFFER_SIZE) if capture_iq else None

    def on_block(self, block: IQBlock):
        """Process an incoming I/Q block."""
        self.blocks_processed += 1

        # Capture I/Q data for logging
        if self._capture_iq and self._iq_buffer is not None:
            self._iq_buffer.append({
                "timestamp": block.timestamp,
                "i_samples": list(block.i_samples),
                "q_samples": list(block.q_samples),
            })

        reading = self.processor.process_block(block)
        if reading:
            self.readings_emitted += 1

            # Log to session logger with detection metadata
            logger = get_session_logger()
            if logger:
                logger.log_iq_reading(
                    speed_mph=reading.speed,
                    direction=reading.direction.value,
                    magnitude=reading.magnitude or 0.0,
                    snr=getattr(self.processor, '_last_snr', 0.0),
                    peak_bin=getattr(self.processor, '_last_peak_bin', 0),
                    cfar_validated=getattr(self.processor, '_last_cfar_validated', False),
                    block_count=self.blocks_processed,
                )

            self.callback(reading)

    def get_recent_iq_blocks(self, count: Optional[int] = None) -> List[dict]:
        """
        Get recent I/Q blocks from the buffer.

        Args:
            count: Number of blocks to return (default: all in buffer)

        Returns:
            List of I/Q block dicts with timestamp, i_samples, q_samples
        """
        if not self._capture_iq or self._iq_buffer is None:
            return []

        blocks = list(self._iq_buffer)
        if count is not None:
            blocks = blocks[-count:]
        return blocks

    def log_iq_for_shot(self, shot_number: int, blocks_before: int = 100):
        """
        Log I/Q blocks for a detected shot.

        Args:
            shot_number: Shot number to tag the data with
            blocks_before: Number of blocks to save (captures pre-shot data)
        """
        logger = get_session_logger()
        if logger and self._capture_iq:
            blocks = self.get_recent_iq_blocks(blocks_before)
            if blocks:
                logger.log_iq_blocks(shot_number, blocks)

    def get_stats(self) -> dict:
        """Get processing statistics."""
        return {
            "blocks_processed": self.blocks_processed,
            "readings_emitted": self.readings_emitted,
            "hit_rate": self.readings_emitted / max(1, self.blocks_processed),
            "iq_buffer_size": len(self._iq_buffer) if self._iq_buffer else 0,
        }
