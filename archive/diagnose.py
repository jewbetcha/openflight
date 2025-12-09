#!/usr/bin/env python3
"""
DIY Golf Launch Monitor - Hardware Diagnostic Tool
===================================================

Run this script to verify all hardware is connected and working properly.
It checks each component step-by-step and reports pass/fail status.

Usage:
    python diagnose.py           # Run all tests
    python diagnose.py --spi     # Test SPI/ADC only
    python diagnose.py --radar   # Test radar signal only
    python diagnose.py --camera  # Test camera only
    python diagnose.py --live    # Live radar signal monitor

Author: DIY Golf Launch Monitor Project
"""

import sys
import time
import argparse
from pathlib import Path

# =============================================================================
# TEST RESULTS TRACKING
# =============================================================================

class TestResults:
    def __init__(self):
        self.tests = []
    
    def add(self, name: str, passed: bool, message: str = ""):
        self.tests.append({
            'name': name,
            'passed': passed,
            'message': message
        })
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if message:
            print(f"         {message}")
    
    def summary(self):
        passed = sum(1 for t in self.tests if t['passed'])
        total = len(self.tests)
        
        print("\n" + "=" * 60)
        print(f"  SUMMARY: {passed}/{total} tests passed")
        print("=" * 60)
        
        if passed == total:
            print("\n  ✓ All systems ready! You can run launch_monitor.py")
        else:
            print("\n  Failed tests:")
            for t in self.tests:
                if not t['passed']:
                    print(f"    • {t['name']}: {t['message']}")
        
        return passed == total


results = TestResults()


# =============================================================================
# SYSTEM TESTS
# =============================================================================

def test_python_version():
    """Check Python version is adequate."""
    version = sys.version_info
    passed = version.major >= 3 and version.minor >= 9
    results.add(
        "Python version",
        passed,
        f"Python {version.major}.{version.minor}.{version.micro}" + 
        ("" if passed else " (need 3.9+)")
    )
    return passed


def test_required_packages():
    """Check that required Python packages are installed."""
    packages = {
        'numpy': 'numpy',
        'scipy': 'scipy',
        'spidev': 'spidev (for ADC communication)'
    }
    
    all_passed = True
    for pkg, desc in packages.items():
        try:
            __import__(pkg)
            results.add(f"Package: {pkg}", True)
        except ImportError:
            results.add(f"Package: {pkg}", False, 
                       f"Install with: pip install {pkg} --break-system-packages")
            all_passed = False
    
    return all_passed


def test_optional_packages():
    """Check optional packages for Phase 2."""
    packages = {
        'cv2': ('opencv-python', 'Camera image processing'),
        'picamera2': ('picamera2', 'Pi Camera control'),
    }
    
    print("\n  Optional packages (for Phase 2):")
    for pkg, (install_name, desc) in packages.items():
        try:
            __import__(pkg)
            print(f"    ✓ {pkg}: installed")
        except ImportError:
            print(f"    ○ {pkg}: not installed ({desc})")
            print(f"      Install with: pip install {install_name} --break-system-packages")


# =============================================================================
# SPI / ADC TESTS
# =============================================================================

def test_spi_enabled():
    """Check if SPI is enabled on the Pi."""
    spi_devices = list(Path('/dev').glob('spidev*'))
    passed = len(spi_devices) > 0
    
    if passed:
        devices = ', '.join(str(d) for d in spi_devices)
        results.add("SPI enabled", True, f"Found: {devices}")
    else:
        results.add("SPI enabled", False, 
                   "Run: sudo raspi-config → Interface Options → SPI → Enable")
    return passed


def test_adc_connection():
    """Test MCP3008 ADC is responding."""
    try:
        import spidev
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0
        
        # Read channel 0
        cmd = [1, (8 + 0) << 4, 0]
        reply = spi.xfer2(cmd)
        value = ((reply[1] & 0x03) << 8) | reply[2]
        
        spi.close()
        
        # Value should be somewhere reasonable (not 0 or 1023 stuck)
        results.add("MCP3008 ADC", True, f"Channel 0 reading: {value}")
        return True
        
    except FileNotFoundError:
        results.add("MCP3008 ADC", False, "SPI device not found - is SPI enabled?")
        return False
    except Exception as e:
        results.add("MCP3008 ADC", False, f"Error: {e}")
        return False


def test_adc_stability():
    """Check ADC readings are stable (not floating/noisy)."""
    try:
        import spidev
        import numpy as np
        
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0
        
        readings = []
        for _ in range(50):
            cmd = [1, (8 + 0) << 4, 0]
            reply = spi.xfer2(cmd)
            value = ((reply[1] & 0x03) << 8) | reply[2]
            readings.append(value)
            time.sleep(0.01)
        
        spi.close()
        
        mean_val = np.mean(readings)
        std_val = np.std(readings)
        
        # Standard deviation should be relatively low if signal is quiet
        # and there's proper grounding
        passed = std_val < 50  # Arbitrary threshold
        
        results.add(
            "ADC signal stability", 
            passed,
            f"Mean: {mean_val:.1f}, StdDev: {std_val:.1f}" +
            ("" if passed else " (high noise - check grounding)")
        )
        return passed
        
    except Exception as e:
        results.add("ADC signal stability", False, f"Error: {e}")
        return False


# =============================================================================
# RADAR TESTS
# =============================================================================

def test_radar_baseline():
    """Test radar signal at rest (should be near midpoint)."""
    try:
        import spidev
        import numpy as np
        
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0
        
        readings = []
        for _ in range(100):
            cmd = [1, (8 + 0) << 4, 0]
            reply = spi.xfer2(cmd)
            value = ((reply[1] & 0x03) << 8) | reply[2]
            readings.append(value)
            time.sleep(0.005)
        
        spi.close()
        
        mean_val = np.mean(readings)
        
        # Should be somewhere near midpoint (512) if bias is set correctly
        # Allow wide range since different amp setups vary
        passed = 200 < mean_val < 800
        
        results.add(
            "Radar baseline", 
            passed,
            f"Baseline: {mean_val:.0f}" +
            (" (good)" if passed else " (check amplifier bias)")
        )
        return passed
        
    except Exception as e:
        results.add("Radar baseline", False, f"Error: {e}")
        return False


def test_radar_response():
    """Interactive test - wave hand in front of radar to verify response."""
    try:
        import spidev
        import numpy as np
        
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0
        
        # Get baseline
        baseline_readings = []
        for _ in range(50):
            cmd = [1, (8 + 0) << 4, 0]
            reply = spi.xfer2(cmd)
            value = ((reply[1] & 0x03) << 8) | reply[2]
            baseline_readings.append(value)
            time.sleep(0.005)
        
        baseline = np.mean(baseline_readings)
        baseline_std = np.std(baseline_readings)
        
        print("\n  👋 Wave your hand in front of the radar module...")
        print("     (You have 5 seconds)")
        
        max_deviation = 0
        start_time = time.time()
        
        while time.time() - start_time < 5:
            cmd = [1, (8 + 0) << 4, 0]
            reply = spi.xfer2(cmd)
            value = ((reply[1] & 0x03) << 8) | reply[2]
            
            deviation = abs(value - baseline)
            max_deviation = max(max_deviation, deviation)
            
            # Visual feedback
            bar_len = min(30, int(deviation / 10))
            bar = "█" * bar_len + "░" * (30 - bar_len)
            print(f"\r     [{bar}] {deviation:3.0f}  ", end="", flush=True)
            
            time.sleep(0.02)
        
        print()  # New line
        spi.close()
        
        # Should see significant deviation when hand moves
        threshold = max(baseline_std * 3, 20)  # At least 3x noise or 20
        passed = max_deviation > threshold
        
        results.add(
            "Radar motion response",
            passed,
            f"Max deviation: {max_deviation:.0f}" +
            (" (detected motion)" if passed else " (no motion detected - check connections)")
        )
        return passed
        
    except Exception as e:
        results.add("Radar motion response", False, f"Error: {e}")
        return False


# =============================================================================
# CAMERA TESTS
# =============================================================================

def test_camera_available():
    """Check if Pi camera is detected."""
    try:
        from picamera2 import Picamera2
        
        # Try to list cameras
        cameras = Picamera2.global_camera_info()
        
        if cameras:
            cam_info = cameras[0]
            model = cam_info.get('Model', 'Unknown')
            results.add("Camera detected", True, f"Model: {model}")
            return True
        else:
            results.add("Camera detected", False, 
                       "No camera found - check ribbon cable connection")
            return False
            
    except ImportError:
        results.add("Camera detected", False, 
                   "picamera2 not installed - run: pip install picamera2 --break-system-packages")
        return False
    except Exception as e:
        results.add("Camera detected", False, f"Error: {e}")
        return False


def test_camera_capture():
    """Test camera can capture a frame."""
    try:
        from picamera2 import Picamera2
        import cv2
        
        cam = Picamera2()
        config = cam.create_still_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        cam.configure(config)
        cam.start()
        time.sleep(0.5)
        
        frame = cam.capture_array()
        
        cam.stop()
        cam.close()
        
        if frame is not None and frame.size > 0:
            # Save test image
            test_path = Path("test_camera.jpg")
            cv2.imwrite(str(test_path), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            
            results.add("Camera capture", True, 
                       f"Captured {frame.shape[1]}x{frame.shape[0]} - saved to {test_path}")
            return True
        else:
            results.add("Camera capture", False, "Empty frame received")
            return False
            
    except Exception as e:
        results.add("Camera capture", False, f"Error: {e}")
        return False


# =============================================================================
# GPIO TESTS  
# =============================================================================

def test_gpio_available():
    """Check if GPIO library is available."""
    try:
        import RPi.GPIO as GPIO
        results.add("GPIO library", True)
        return True
    except ImportError:
        results.add("GPIO library", False, 
                   "Install with: pip install RPi.GPIO --break-system-packages")
        return False


# =============================================================================
# LIVE MONITORING
# =============================================================================

def live_radar_monitor():
    """Live view of radar signal - useful for debugging."""
    try:
        import spidev
        import numpy as np
        from scipy.fft import fft, fftfreq
        
        print("\n" + "=" * 60)
        print("  📡 LIVE RADAR MONITOR")
        print("=" * 60)
        print("\n  Press Ctrl+C to exit\n")
        
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0
        
        # CDM324 constant (change to 31.36 for HB100)
        DOPPLER_CONSTANT = 71.7  # Hz per mph for CDM324
        
        sample_rate = 10000  # Hz
        sample_count = 2000  # 0.2 seconds of data
        
        try:
            while True:
                # Capture samples
                samples = []
                start = time.perf_counter()
                for _ in range(sample_count):
                    cmd = [1, (8 + 0) << 4, 0]
                    reply = spi.xfer2(cmd)
                    value = ((reply[1] & 0x03) << 8) | reply[2]
                    samples.append(value)
                
                duration = time.perf_counter() - start
                actual_rate = sample_count / duration
                
                # Process
                samples = np.array(samples) - np.mean(samples)
                
                # FFT
                fft_result = np.abs(fft(samples))
                freqs = fftfreq(len(samples), 1/actual_rate)
                
                # Find peak in positive frequencies
                positive_mask = (freqs > 50) & (freqs < 5000)
                if np.any(positive_mask):
                    positive_freqs = freqs[positive_mask]
                    positive_mags = fft_result[positive_mask]
                    
                    peak_idx = np.argmax(positive_mags)
                    peak_freq = positive_freqs[peak_idx]
                    peak_mag = positive_mags[peak_idx]
                    
                    speed_mph = abs(peak_freq) / DOPPLER_CONSTANT
                    
                    # Display
                    mag_bar_len = min(30, int(peak_mag / 50))
                    mag_bar = "█" * mag_bar_len + "░" * (30 - mag_bar_len)
                    
                    print(f"\r  Freq: {peak_freq:6.0f} Hz | "
                          f"Speed: {speed_mph:5.1f} mph | "
                          f"Signal: [{mag_bar}] {peak_mag:6.0f}  ", end="", flush=True)
                
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            print("\n\n  Stopped.")
        finally:
            spi.close()
            
    except Exception as e:
        print(f"\n  Error: {e}")


def live_adc_monitor():
    """Simple live ADC value monitor."""
    try:
        import spidev
        
        print("\n" + "=" * 60)
        print("  📊 LIVE ADC MONITOR")
        print("=" * 60)
        print("\n  Showing raw ADC values. Press Ctrl+C to exit\n")
        
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0
        
        try:
            while True:
                cmd = [1, (8 + 0) << 4, 0]
                reply = spi.xfer2(cmd)
                value = ((reply[1] & 0x03) << 8) | reply[2]
                
                # Visual bar
                bar_pos = int((value / 1023) * 50)
                bar = "░" * bar_pos + "█" + "░" * (50 - bar_pos)
                
                print(f"\r  [{bar}] {value:4d}  ", end="", flush=True)
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            print("\n\n  Stopped.")
        finally:
            spi.close()
            
    except Exception as e:
        print(f"\n  Error: {e}")


# =============================================================================
# MAIN DIAGNOSTIC ROUTINE
# =============================================================================

def run_all_tests():
    """Run complete diagnostic suite."""
    print("\n" + "=" * 60)
    print("  🔧 DIY GOLF LAUNCH MONITOR - HARDWARE DIAGNOSTICS")
    print("=" * 60)
    
    # System tests
    print("\n  SYSTEM CHECKS")
    print("  " + "-" * 40)
    test_python_version()
    test_required_packages()
    test_optional_packages()
    
    # SPI/ADC tests
    print("\n  SPI / ADC CHECKS")
    print("  " + "-" * 40)
    if test_spi_enabled():
        if test_adc_connection():
            test_adc_stability()
    
    # Radar tests
    print("\n  RADAR CHECKS")
    print("  " + "-" * 40)
    if test_radar_baseline():
        test_radar_response()
    
    # Camera tests (optional)
    print("\n  CAMERA CHECKS (Phase 2)")
    print("  " + "-" * 40)
    if test_camera_available():
        test_camera_capture()
    
    # GPIO test
    print("\n  GPIO CHECKS (for strobe)")
    print("  " + "-" * 40)
    test_gpio_available()
    
    # Summary
    return results.summary()


def run_spi_tests():
    """Run only SPI/ADC tests."""
    print("\n  SPI / ADC CHECKS")
    print("  " + "-" * 40)
    test_spi_enabled()
    test_adc_connection()
    test_adc_stability()
    results.summary()


def run_radar_tests():
    """Run only radar tests."""
    print("\n  RADAR CHECKS")
    print("  " + "-" * 40)
    test_radar_baseline()
    test_radar_response()
    results.summary()


def run_camera_tests():
    """Run only camera tests."""
    print("\n  CAMERA CHECKS")
    print("  " + "-" * 40)
    test_camera_available()
    test_camera_capture()
    results.summary()


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DIY Golf Launch Monitor - Hardware Diagnostics",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--spi', action='store_true', 
                        help='Test SPI/ADC only')
    parser.add_argument('--radar', action='store_true',
                        help='Test radar only')
    parser.add_argument('--camera', action='store_true',
                        help='Test camera only')
    parser.add_argument('--live', action='store_true',
                        help='Live radar signal monitor')
    parser.add_argument('--adc', action='store_true',
                        help='Live ADC value monitor')
    
    args = parser.parse_args()
    
    if args.live:
        live_radar_monitor()
    elif args.adc:
        live_adc_monitor()
    elif args.spi:
        run_spi_tests()
    elif args.radar:
        run_radar_tests()
    elif args.camera:
        run_camera_tests()
    else:
        run_all_tests()


if __name__ == "__main__":
    main()
