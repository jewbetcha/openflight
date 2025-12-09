#!/usr/bin/env python3
"""
DIY Golf Launch Monitor - Phase 1 (v5)
======================================
CDM324 Doppler Radar + MCP3008 ADC + Raspberry Pi 5

v5 Changes:
- Removed direction detection (not possible with single-output radar)
- Lowered thresholds for weak signals
- Added gain troubleshooting info
"""

import time
import argparse
import numpy as np
from scipy import signal
from scipy.fft import fft, fftfreq
from dataclasses import dataclass
from typing import Optional, Tuple, List
from pathlib import Path
import json

# =============================================================================
# HARDWARE DETECTION
# =============================================================================

SPI_AVAILABLE = False
try:
    import spidev
    SPI_AVAILABLE = True
except ImportError:
    print("⚠️  spidev not installed")

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class Config:
    radar_type: str = 'cdm324'
    
    @property
    def hz_per_mph(self) -> float:
        return 71.7 if self.radar_type == 'cdm324' else 31.36
    
    spi_bus: int = 0
    spi_device: int = 0
    spi_speed: int = 1000000
    adc_channel: int = 0
    
    sample_rate: int = 20000
    sample_duration: float = 0.3
    
    # Trigger - signal must deviate from baseline by this much
    trigger_threshold: int = 100
    trigger_confirmations: int = 3
    
    # FFT analysis
    min_frequency: int = 300      # ~4 mph minimum (ignore slow hand movements)
    max_frequency: int = 12000    # ~167 mph maximum
    
    # Signal must exceed noise floor by this much to be valid
    # Lower = more sensitive but more false readings
    magnitude_above_noise: float = 2000
    
    save_shots: bool = True
    output_dir: str = "shots"
    units: str = "imperial"


config = Config()


# =============================================================================
# MCP3008 ADC
# =============================================================================

class MCP3008:
    def __init__(self, bus=0, device=0, speed=1000000):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = speed
        self.spi.mode = 0
        
    def read(self, channel: int = 0) -> int:
        cmd = [1, (8 + channel) << 4, 0]
        reply = self.spi.xfer2(cmd)
        return ((reply[1] & 0x03) << 8) | reply[2]
    
    def close(self):
        self.spi.close()


# =============================================================================
# RADAR PROCESSOR
# =============================================================================

class RadarProcessor:
    def __init__(self, adc: MCP3008):
        self.adc = adc
        self.baseline = 512
        self.noise_floor = 1000
        
    def calibrate(self, duration: float = 1.5) -> dict:
        """Calibrate baseline and FFT noise floor."""
        print("    Calibrating (keep area clear)...", flush=True)
        
        # ADC baseline
        samples = []
        start = time.time()
        while time.time() - start < 0.5:
            samples.append(self.adc.read(config.adc_channel))
            time.sleep(0.001)
        
        self.baseline = np.mean(samples)
        adc_noise = np.std(samples)
        
        # FFT noise floor - take multiple measurements and average
        noise_measurements = []
        for _ in range(3):
            fft_samples = []
            for _ in range(4000):
                fft_samples.append(self.adc.read(config.adc_channel))
            
            fft_samples = np.array(fft_samples, dtype=float) - self.baseline
            sample_rate = 10000
            
            window = signal.windows.hann(len(fft_samples))
            fft_result = fft(fft_samples * window)
            frequencies = fftfreq(len(fft_samples), 1/sample_rate)
            magnitudes = np.abs(fft_result)
            
            # Get peak in our frequency range
            mask = (frequencies >= config.min_frequency) & (frequencies <= config.max_frequency)
            if np.any(mask):
                noise_measurements.append(np.max(magnitudes[mask]))
        
        self.noise_floor = np.mean(noise_measurements) if noise_measurements else 1000
        
        print(f"      ADC baseline: {self.baseline:.0f} (±{adc_noise:.0f})")
        print(f"      FFT noise floor: {self.noise_floor:.0f}")
        print(f"      Detection threshold: {self.noise_floor + config.magnitude_above_noise:.0f}")
        
        return {
            'baseline': self.baseline,
            'noise_floor': self.noise_floor
        }
    
    def wait_for_trigger(self, timeout: float = 60.0) -> bool:
        start = time.time()
        confirm_count = 0
        
        while time.time() - start < timeout:
            current = self.adc.read(config.adc_channel)
            deviation = abs(current - self.baseline)
            
            if deviation > config.trigger_threshold:
                confirm_count += 1
                if confirm_count >= config.trigger_confirmations:
                    return True
            else:
                confirm_count = 0
            
            time.sleep(0.0002)
        
        return False
    
    def capture(self) -> Tuple[np.ndarray, float]:
        num_samples = int(config.sample_rate * config.sample_duration)
        samples = np.zeros(num_samples)
        
        sample_interval = 1.0 / config.sample_rate
        start_time = time.perf_counter()
        
        for i in range(num_samples):
            samples[i] = self.adc.read(config.adc_channel)
            target_time = start_time + (i + 1) * sample_interval
            while time.perf_counter() < target_time:
                pass
        
        actual_duration = time.perf_counter() - start_time
        actual_rate = num_samples / actual_duration
        
        return samples, actual_rate
    
    def analyze(self, samples: np.ndarray, sample_rate: float) -> dict:
        """Analyze FFT to extract speed (no direction detection)."""
        samples = samples - np.mean(samples)
        
        window = signal.windows.hann(len(samples))
        fft_result = fft(samples * window)
        frequencies = fftfreq(len(samples), 1/sample_rate)
        magnitudes = np.abs(fft_result)
        
        # Only look at positive frequencies in our range
        mask = (frequencies >= config.min_frequency) & (frequencies <= config.max_frequency)
        
        if not np.any(mask):
            return {'valid': False, 'speed_mph': 0, 'magnitude': 0, 'above_noise': 0}
        
        filtered_freqs = frequencies[mask]
        filtered_mags = magnitudes[mask]
        
        # Find peak
        peak_idx = np.argmax(filtered_mags)
        peak_freq = filtered_freqs[peak_idx]
        peak_mag = filtered_mags[peak_idx]
        
        above_noise = peak_mag - self.noise_floor
        speed_mph = peak_freq / config.hz_per_mph
        speed_kmh = speed_mph * 1.60934
        
        valid = above_noise >= config.magnitude_above_noise
        
        return {
            'valid': valid,
            'speed_mph': speed_mph if valid else 0,
            'speed_kmh': speed_kmh if valid else 0,
            'frequency': peak_freq,
            'magnitude': peak_mag,
            'above_noise': above_noise,
            'sample_rate': sample_rate
        }


# =============================================================================
# CARRY ESTIMATION
# =============================================================================

def estimate_carry(ball_speed_mph: float, launch_angle_deg: float = 12.0) -> Tuple[float, float]:
    if ball_speed_mph <= 0:
        return 0.0, 0.0
    
    v0 = ball_speed_mph * 0.44704
    angle = np.radians(launch_angle_deg)
    g = 9.81
    
    t_flight = (2 * v0 * np.sin(angle)) / g
    range_m = v0 * np.cos(angle) * t_flight * 0.65
    range_m = min(range_m, 300)
    
    return range_m * 1.09361, range_m


# =============================================================================
# LAUNCH MONITOR
# =============================================================================

class LaunchMonitor:
    def __init__(self):
        self.adc: Optional[MCP3008] = None
        self.radar: Optional[RadarProcessor] = None
        self.shots: List[dict] = []
    
    def initialize(self) -> bool:
        print("\n" + "=" * 60)
        print("  🏌️  DIY GOLF LAUNCH MONITOR")
        print("=" * 60)
        print(f"\n  Radar: {config.radar_type.upper()} ({config.hz_per_mph:.1f} Hz/mph)")
        
        print("\n  Initializing...")
        
        if not SPI_AVAILABLE:
            print("    ✗ SPI not available")
            return False
        
        try:
            self.adc = MCP3008(
                bus=config.spi_bus,
                device=config.spi_device,
                speed=config.spi_speed
            )
            print("    ✓ MCP3008 ADC connected")
        except Exception as e:
            print(f"    ✗ ADC failed: {e}")
            return False
        
        self.radar = RadarProcessor(self.adc)
        self.radar.calibrate()
        
        if config.save_shots:
            Path(config.output_dir).mkdir(exist_ok=True)
        
        print("\n" + "-" * 60)
        return True
    
    def capture_shot(self) -> Optional[dict]:
        print("\n  🏌️  Ready - swing when ready...")
        
        if not self.radar.wait_for_trigger(timeout=120):
            print("    ⏱️  Timeout")
            return None
        
        print("    ⚡ Motion detected! Capturing...")
        
        samples, sample_rate = self.radar.capture()
        result = self.radar.analyze(samples, sample_rate)
        
        if not result['valid']:
            print(f"    ⚠️  Signal too weak")
            print(f"       Peak: {result['magnitude']:.0f}, Need: {self.radar.noise_floor + config.magnitude_above_noise:.0f}")
            return None
        
        carry_yards, carry_meters = estimate_carry(result['speed_mph'])
        result['carry_yards'] = carry_yards
        result['carry_meters'] = carry_meters
        result['timestamp'] = time.time()
        
        self.shots.append(result)
        return result
    
    def display_shot(self, shot: dict, shot_num: int):
        print("\n" + "=" * 60)
        print(f"  📊 SHOT #{shot_num}")
        print("=" * 60)
        
        if config.units == 'imperial':
            print(f"\n    ⚡ Speed:     {shot['speed_mph']:.1f} mph")
            print(f"    📍 Est Carry: {shot['carry_yards']:.0f} yards")
        else:
            print(f"\n    ⚡ Speed:     {shot['speed_kmh']:.1f} km/h")
            print(f"    📍 Est Carry: {shot['carry_meters']:.0f} meters")
        
        # Signal strength indicator
        strength = min(5, max(1, int(shot['above_noise'] / 2000)))
        bar = "█" * strength + "░" * (5 - strength)
        print(f"\n    📶 Signal:   [{bar}]")
        
        print("\n" + "-" * 60)
    
    def run(self):
        if not self.initialize():
            return
        
        print("\n  System ready! Swing to measure speed.")
        print("  Press Ctrl+C to exit.\n")
        
        shot_count = 0
        
        try:
            while True:
                shot = self.capture_shot()
                
                if shot:
                    shot_count += 1
                    self.display_shot(shot, shot_count)
                
                time.sleep(0.3)
                
        except KeyboardInterrupt:
            print("\n\n  Shutting down...")
        finally:
            self.cleanup()
    
    def cleanup(self):
        if self.adc:
            self.adc.close()
        
        if self.shots and config.save_shots:
            filepath = Path(config.output_dir) / f"session_{int(time.time())}.json"
            data = {'shots': self.shots}
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"\n  📁 Session saved: {filepath}")


# =============================================================================
# LIVE MONITOR
# =============================================================================

def live_monitor():
    print("\n" + "=" * 60)
    print("  📡 LIVE SPEED MONITOR")
    print("=" * 60)
    print(f"\n  Radar: {config.radar_type.upper()}")
    print("  Press Ctrl+C to exit\n")
    
    adc = MCP3008()
    
    # Calibrate
    print("  Calibrating...", end="", flush=True)
    samples = []
    for _ in range(200):
        samples.append(adc.read(config.adc_channel))
        time.sleep(0.005)
    baseline = np.mean(samples)
    
    # Noise floor
    samples = []
    for _ in range(4000):
        samples.append(adc.read(config.adc_channel))
    
    samples = np.array(samples, dtype=float) - baseline
    sample_rate = 10000
    
    window = signal.windows.hann(len(samples))
    fft_result = fft(samples * window)
    frequencies = fftfreq(len(samples), 1/sample_rate)
    magnitudes = np.abs(fft_result)
    
    mask = (frequencies >= config.min_frequency) & (frequencies <= config.max_frequency)
    noise_floor = np.max(magnitudes[mask]) if np.any(mask) else 1000
    
    print(f" noise floor={noise_floor:.0f}\n")
    
    sample_count = 3000
    
    try:
        while True:
            samples = []
            for _ in range(sample_count):
                samples.append(adc.read(config.adc_channel))
            
            samples = np.array(samples, dtype=float) - baseline
            
            window = signal.windows.hann(len(samples))
            fft_result = fft(samples * window)
            frequencies = fftfreq(len(samples), 1/sample_rate)
            magnitudes = np.abs(fft_result)
            
            mask = (frequencies >= config.min_frequency) & (frequencies <= config.max_frequency)
            
            if np.any(mask):
                filtered_freqs = frequencies[mask]
                filtered_mags = magnitudes[mask]
                
                idx = np.argmax(filtered_mags)
                peak_freq = filtered_freqs[idx]
                peak_mag = filtered_mags[idx]
                above_noise = peak_mag - noise_floor
                
                speed = peak_freq / config.hz_per_mph
                
                # Visual bar based on signal above noise
                bar_len = min(30, max(0, int(above_noise / 200)))
                bar = "█" * bar_len + "░" * (30 - bar_len)
                
                valid = "✓" if above_noise >= config.magnitude_above_noise else " "
                
                print(f"\r  {speed:6.1f} mph | {peak_freq:5.0f} Hz | [{bar}] +{above_noise:5.0f} {valid}  ", 
                      end="", flush=True)
            
            time.sleep(0.03)
            
    except KeyboardInterrupt:
        print("\n\n  Stopped.")
    finally:
        adc.close()


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DIY Golf Launch Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launch_monitor.py              Run the launch monitor
  python launch_monitor.py --live       Live speed display
  python launch_monitor.py --sensitivity 1000   More sensitive (more false readings)
  python launch_monitor.py --sensitivity 5000   Less sensitive (misses weak signals)
        """
    )
    parser.add_argument('--live', action='store_true', help='Live signal monitor')
    parser.add_argument('--radar', choices=['cdm324', 'hb100'], default='cdm324')
    parser.add_argument('--trigger', type=int, default=100, help='ADC trigger threshold')
    parser.add_argument('--sensitivity', type=float, default=2000, 
                        help='Signal above noise threshold (lower=more sensitive)')
    parser.add_argument('--units', choices=['imperial', 'metric'], default='imperial')
    
    args = parser.parse_args()
    
    config.radar_type = args.radar
    config.units = args.units
    config.trigger_threshold = args.trigger
    config.magnitude_above_noise = args.sensitivity
    
    if args.live:
        live_monitor()
    else:
        monitor = LaunchMonitor()
        monitor.run()


if __name__ == "__main__":
    main()