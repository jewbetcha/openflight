"""
2D CFAR (Constant False Alarm Rate) detector for Doppler spectrogram.

CFAR adaptively sets detection thresholds based on local noise estimates,
making it robust to varying noise conditions while maintaining a constant
probability of false alarm.
"""

from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass
class CFARConfig:
    """Configuration for 2D CFAR detector."""

    # CFAR window sizes (in cells)
    guard_cells_time: int = 2       # Guard cells in time dimension
    guard_cells_freq: int = 4       # Guard cells in frequency dimension
    training_cells_time: int = 8    # Training cells in time dimension
    training_cells_freq: int = 16   # Training cells in frequency dimension

    # Detection threshold (SNR)
    # Signal must exceed noise floor by this factor
    # Tuned from data: noise max SNR ~10, swing SNR can reach 600+
    threshold_factor: float = 12.0

    # Minimum absolute threshold (0 = pure SNR-based detection)
    # Note: FFT magnitudes are voltage-scaled (0-3.3V range), so this should be small
    threshold_offset: float = 0.0

    # DC/low speed masking - bins to ignore around zero Doppler
    # At 30ksps with 4096 FFT: bin 150 ≈ 15 mph
    # This masks out stationary clutter and slow movements
    dc_mask_bins: int = 150         # Mask bins 0-150 and 3946-4095 (~15 mph)

    # Edge masking - don't detect near spectrogram edges
    edge_mask_time: int = 4         # Mask first/last N time windows
    edge_mask_freq: int = 50        # Mask first/last N frequency bins

    # Spectrogram buffer size
    spectrogram_length: int = 32    # Number of time windows to maintain


class CFAR2DDetector:
    """
    2D Cell-Averaging CFAR detector using vectorized convolution.

    Processing steps:
    1. Use convolution to compute sum of training cells efficiently
    2. Subtract guard cell region to get proper CFAR noise estimate
    3. Set threshold = noise_estimate * threshold_factor
    4. Detection if signal > threshold

    Masking:
    - DC mask: Ignore bins around 0 Doppler (stationary clutter, low speeds)
    - Edge mask: Ignore edges where CFAR window doesn't fit
    """

    def __init__(self, config: CFARConfig, fft_size: int):
        """
        Initialize the CFAR detector.

        Args:
            config: CFAR configuration parameters
            fft_size: Size of FFT (number of frequency bins)
        """
        self.config = config
        self.fft_size = fft_size
        self.half_fft = fft_size // 2

        # Create frequency mask (True = valid for detection)
        self.freq_mask = self._create_frequency_mask()

        # Pre-compute CFAR kernels for fast convolution
        self._build_cfar_kernels()

    def _create_frequency_mask(self) -> np.ndarray:
        """Create mask for valid frequency bins (excludes DC region)."""
        cfg = self.config
        mask = np.ones(self.fft_size, dtype=bool)

        # Mask DC region (low frequencies / low speeds)
        mask[:cfg.dc_mask_bins] = False           # Positive frequencies near DC
        mask[-cfg.dc_mask_bins:] = False          # Negative frequencies near DC

        return mask

    def _build_cfar_kernels(self):
        """Build convolution kernels for efficient CFAR computation."""
        cfg = self.config

        # Total window size (training + guard + CUT)
        win_t = 2 * (cfg.training_cells_time + cfg.guard_cells_time) + 1
        win_f = 2 * (cfg.training_cells_freq + cfg.guard_cells_freq) + 1

        # Create outer kernel (full window)
        outer_kernel = np.ones((win_t, win_f))

        # Create inner kernel (guard region to subtract)
        guard_t = 2 * cfg.guard_cells_time + 1
        guard_f = 2 * cfg.guard_cells_freq + 1
        inner_kernel = np.zeros((win_t, win_f))

        # Position of guard region within outer kernel
        gt_start = cfg.training_cells_time
        gf_start = cfg.training_cells_freq
        inner_kernel[gt_start:gt_start + guard_t, gf_start:gf_start + guard_f] = 1

        # Training kernel = outer - inner (ring of training cells)
        self.training_kernel = outer_kernel - inner_kernel
        self.n_training_cells = np.sum(self.training_kernel)

    def detect(
        self,
        spectrogram: np.ndarray,
        return_all_detections: bool = False
    ) -> List[tuple]:
        """
        Run 2D CFAR detection on a spectrogram.

        Args:
            spectrogram: 2D array of shape (time_windows, freq_bins)
            return_all_detections: If True, return all; if False, return strongest only

        Returns:
            List of (time_idx, freq_bin, magnitude, threshold) tuples
        """
        from scipy.ndimage import convolve

        cfg = self.config
        n_time, n_freq = spectrogram.shape

        # Check if we have enough data for CFAR
        min_time = 2 * (cfg.guard_cells_time + cfg.training_cells_time) + 1
        if n_time < min_time:
            return []

        # Compute noise estimate using convolution (sum of training cells)
        noise_sum = convolve(spectrogram, self.training_kernel, mode='constant', cval=0)
        noise_estimate = noise_sum / self.n_training_cells

        # Compute adaptive threshold
        threshold_map = noise_estimate * cfg.threshold_factor + cfg.threshold_offset

        # Find detections (where signal exceeds threshold)
        detection_mask = spectrogram > threshold_map

        # Apply frequency mask (exclude DC and edges)
        detection_mask[:, ~self.freq_mask] = False

        # Apply edge masking in time
        edge_t = max(cfg.edge_mask_time, cfg.guard_cells_time + cfg.training_cells_time)
        detection_mask[:edge_t, :] = False
        detection_mask[-edge_t:, :] = False

        # Apply edge masking in frequency
        edge_f = max(cfg.edge_mask_freq, cfg.guard_cells_freq + cfg.training_cells_freq)
        detection_mask[:, :edge_f] = False
        detection_mask[:, -edge_f:] = False

        # Get detection coordinates
        det_times, det_freqs = np.where(detection_mask)

        if len(det_times) == 0:
            return []

        # Build detection list
        detections = [
            (int(t), int(f), float(spectrogram[t, f]), float(threshold_map[t, f]))
            for t, f in zip(det_times, det_freqs)
        ]

        if return_all_detections:
            return detections

        # Return only the strongest detection
        strongest = max(detections, key=lambda x: x[2])
        return [strongest]
