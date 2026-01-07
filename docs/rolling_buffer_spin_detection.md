# Rolling Buffer & Spin Detection Implementation Plan

Based on guidance from OmniPreSense (January 2026).

## Overview

The OPS243-A radar can detect golf ball spin by analyzing micro-variations in the Doppler signal caused by the spinning dimpled surface. This requires:

1. **Rolling Buffer Mode (G1)** - Captures complete I/Q data for post-processing
2. **Overlapping FFT Windows** - Increases temporal resolution to see spin "waviness"
3. **Secondary FFT** - Extracts spin frequency from speed oscillations

## Current vs Rolling Buffer Approach

| Aspect | Current (Streaming) | Rolling Buffer |
|--------|---------------------|----------------|
| Mode | Continuous reporting | Triggered capture |
| Data | Processed speeds | Raw I/Q samples |
| Resolution | ~56 Hz | Up to 1 kHz |
| Spin detection | No | Yes (50-60% success) |
| Latency | Real-time | Post-processing |

## Rolling Buffer Mode Commands

```
PI    # Deactivate (idle mode)
K+    # Enable peak detection
G1    # Enable rolling buffer mode (4096 samples)
S!    # Trigger capture and dump buffer
```

## Data Format from S! Command

The sensor returns JSON with:
```json
{"sample_time": "964.003"}
{"trigger_time": "964.105"}
{"I": [4096 integer samples...]}
{"Q": [4096 integer samples...]}
```

- 4096 samples = 32 blocks × 128 samples each
- At 30ksps: ~136ms of data captured
- Trigger time indicates when the trigger event occurred within the buffer

## Triggering Strategy for Golf

The radar needs a trigger to know when to dump the buffer. Options:

1. **Speed Threshold Trigger** (Recommended)
   - Configure minimum speed threshold (e.g., 50+ mph)
   - When club head is detected above threshold, trigger fires
   - Buffer contains pre-trigger (backswing) and post-trigger (impact + ball flight)

2. **External GPIO Trigger**
   - Physical sensor (break beam, pressure mat, microphone)
   - More reliable but requires additional hardware

3. **Software Polling**
   - Continuously poll with S! and look for activity
   - Less efficient but simpler to implement

## Signal Processing Pipeline

### Step 1: Capture I/Q Data
```python
# Send trigger command
response = send_command('S!')

# Parse response
sample_time = data["sample_time"]
trigger_time = data["trigger_time"]
i_data = data["I"]  # 4096 samples
q_data = data["Q"]  # 4096 samples
```

### Step 2: Standard FFT Processing (Speed Detection)
```python
WINDOW_SIZE = 128
FFT_SIZE = 4096
NUM_BLOCKS = 32

for block_idx in range(NUM_BLOCKS):
    start = block_idx * WINDOW_SIZE
    end = start + WINDOW_SIZE

    i_block = i_data[start:end]
    q_block = q_data[start:end]

    # Remove DC, scale, apply Hanning window
    i_block = (i_block - np.mean(i_block)) * 3.3 / 4096
    q_block = (q_block - np.mean(q_block)) * 3.3 / 4096
    i_block *= np.hanning(WINDOW_SIZE)
    q_block *= np.hanning(WINDOW_SIZE)

    # FFT for speed
    complex_signal = i_block + 1j * q_block
    fft_result = np.fft.fft(complex_signal, FFT_SIZE)
    magnitude = np.abs(fft_result)

    # Find peaks, convert bins to speed
    # Speed = bin_index * 0.0063 * (SAMPLE_RATE / FFT_SIZE)
```

### Step 3: Overlapping FFT for Spin (The Key Trick)

Instead of stepping by 128 samples, step by 32 samples for 4x temporal resolution:

```python
STEP_SIZE = 32  # Instead of 128
speeds_over_time = []

for start in range(0, len(i_data) - WINDOW_SIZE, STEP_SIZE):
    end = start + WINDOW_SIZE

    # Process block (same as above)
    speed = process_block(i_data[start:end], q_data[start:end])
    speeds_over_time.append(speed)

# Result: ~1kHz speed readings instead of ~250Hz
# At 30ksps with 32-sample steps: 30000/32 = 937.5 Hz
```

### Step 4: Spin Extraction from Speed Oscillations

The ball's dimpled surface causes periodic speed variations as it spins:

```python
# Filter to just ball speed readings (after impact)
ball_speeds = extract_ball_speeds(speeds_over_time)

# Remove trend (average speed)
detrended = ball_speeds - np.mean(ball_speeds)

# FFT to find oscillation frequency
spin_fft = np.fft.fft(detrended)
frequencies = np.fft.fftfreq(len(detrended), d=1/937.5)  # 937.5 Hz sample rate

# Find dominant frequency = spin rate
peak_idx = np.argmax(np.abs(spin_fft[1:len(spin_fft)//2])) + 1
spin_hz = abs(frequencies[peak_idx])
spin_rpm = spin_hz * 60

print(f"Detected spin: {spin_rpm:.0f} RPM")
```

## Expected Spin Signal

For a golf ball at ~3000 RPM (50 Hz):
- At 1kHz sampling: ~20 samples per revolution
- Should see clear sinusoidal pattern in detrended speed

```
Speed (detrended)
    +0.5 |    *           *           *
         |   * *         * *         * *
       0 |--*---*-------*---*-------*---*---
         | *     *     *     *     *     *
    -0.5 |*       *   *       *   *
         +--------------------------------→ Time
              20ms     40ms     60ms
              ↑________↑
              One revolution at 3000 RPM
```

## Quality Assessment

OmniPreSense reports 50-60% success rate. Implement quality checks:

```python
def assess_spin_quality(spin_fft, spin_rpm):
    """Determine if spin calculation is reliable."""

    # Check 1: Clear dominant peak
    peak_magnitude = np.max(np.abs(spin_fft))
    noise_floor = np.median(np.abs(spin_fft))
    snr = peak_magnitude / noise_floor

    if snr < 3.0:
        return False, "Weak spin signal"

    # Check 2: Reasonable RPM range for golf
    if spin_rpm < 1000 or spin_rpm > 10000:
        return False, f"Spin {spin_rpm} outside expected range"

    # Check 3: Consistent over multiple windows
    # (implementation depends on data structure)

    return True, "Good quality"
```

## Implementation Phases

### Phase 2A: Basic Rolling Buffer Capture
- Add G1 mode initialization
- Implement S! trigger and I/Q parsing
- Process blocks for speed (standard method)
- Compare accuracy to streaming mode

### Phase 2B: Trigger Optimization
- Implement speed threshold trigger
- Tune pre/post trigger timing
- Handle trigger timeout (no swing detected)

### Phase 3A: Overlapping FFT
- Implement 32-sample stepping
- Store high-resolution speed timeline
- Identify ball vs club in timeline

### Phase 3B: Spin Extraction
- Implement secondary FFT on ball speeds
- Add quality assessment
- Report spin only when confident

## Code Structure Suggestion

```python
class RollingBufferProcessor:
    """Handles rolling buffer capture and spin detection."""

    def __init__(self, radar: OPS243Radar):
        self.radar = radar
        self.window_size = 128
        self.fft_size = 4096
        self.step_size = 32  # For spin detection

    def enable_rolling_buffer(self):
        """Switch radar to G1 mode."""
        self.radar._send_command("PI")  # Idle
        self.radar._send_command("K+")  # Peak detection
        self.radar._send_command("G1")  # Rolling buffer

    def trigger_capture(self) -> Optional[CaptureResult]:
        """Trigger and retrieve buffer data."""
        response = self.radar._send_command("S!")
        return self._parse_capture(response)

    def process_for_speed(self, capture: CaptureResult) -> List[SpeedReading]:
        """Standard 128-sample block processing."""
        pass

    def process_for_spin(self, capture: CaptureResult) -> Optional[SpinResult]:
        """Overlapping FFT for spin detection."""
        pass

    def disable_rolling_buffer(self):
        """Return to normal streaming mode."""
        self.radar._send_command("PI")
        self.radar.configure_for_golf()
```

## References

- OmniPreSense Rolling Buffer Code: https://github.com/omnipresense/rolling_buffer
- OmniPreSense AN-027: Rolling Buffer Application Note
- OmniPreSense Sports Ball Detection Presentation

## Notes from OmniPreSense

> "Spin is much more difficult to detect accurately and repeatably... What we have seen is if you have very fine resolution in the speed reports, you can see a slight waviness in the ball speed signal. If you take the FFT of that data, you can get a good spin value."

> "The issue we've seen is maybe only 50-60% of the time does the data captured provide a nice-looking signal set and a solid calculation. Other times the signal looks 'sloppy' and the resulting FFT calculation is not that good."

> "Note that the spin calculated is the combined back spin and side spin but since majority of hits are predominately backspin you can call it that."
