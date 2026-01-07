# Testing Guide

This guide explains how to test the OpenLaunch Rust implementation without hardware.

## Mock Mode

The Rust implementation includes a **mock radar** that simulates realistic golf shot readings. This allows you to test the entire shot detection pipeline without needing the OPS243-A hardware.

### Basic Usage

```bash
cd rust

# Run in mock mode (auto-generates shots every 20 seconds by default)
cargo run --release -- --mock

# Custom shot interval (e.g., every 3 seconds)
cargo run --release -- --mock --mock-interval 3.0

# Show live readings in mock mode
cargo run --release -- --mock --live

# Show mock radar info
cargo run --release -- --mock --info
```

### What Mock Mode Does

The mock radar generates realistic shot sequences:

1. **Club readings** (2-5 readings)
   - Speed: 60-120 mph (ramps up during downswing)
   - Magnitude: 800-1500 (higher RCS = club head)
   - Timing: 50-200ms before ball impact
   - Direction: Outbound

2. **Ball readings** (5-12 readings)
   - Speed: 80-180 mph (decays slightly due to drag)
   - Magnitude: 200-600 (lower RCS = golf ball)
   - Timing: 100-300ms after impact
   - Direction: Outbound

3. **Shot variation**
   - Every 5th shot: "Big hit" (150-180 mph)
   - Every 3rd shot: "Weak hit" (80-110 mph)
   - Normal shots: 110-150 mph

### Example Output

```
==================================================
  OpenLaunch - Golf Launch Monitor (Rust)
  Using MOCK Radar (Simulation Mode)
==================================================

Connected to: OPS243-MOCK
Firmware: 1.0.0-MOCK
Mode: Simulation

Mock mode: Auto-generating shots every 5.0 seconds
Press Ctrl+C to stop

[MOCK] Simulating shot #1...

----------------------------------------
  Club Speed:   95.2 mph
  Ball Speed:   142.3 mph
  Smash Factor: 1.50
  Est. Carry:   234 yards
  Range:        211-257 yards
  Signal:       1250
----------------------------------------

[MOCK] Simulating shot #2...
...
```

## Testing Scenarios

### Test Fast Shots
The mock automatically generates fast shots every 5th shot. Watch for:
- Ball speeds 150-180 mph
- Higher estimated carry distances
- Smash factors around 1.45-1.55

### Test Slow Shots
Every 3rd shot is a "weak hit". Watch for:
- Ball speeds 80-110 mph
- Lower estimated carry distances
- Still valid smash factors

### Test Shot Detection
The mock generates realistic timing:
- Club readings appear first (before impact)
- Ball readings follow (after impact)
- 0.5s gap triggers shot processing

## Comparison with Real Hardware

| Feature | Mock Mode | Real Hardware |
|---------|-----------|---------------|
| Shot generation | Automatic | Manual (swing) |
| Timing | Fixed intervals | Variable |
| Speed range | 80-180 mph | 15-220 mph |
| Readings | Simulated | Actual radar |
| Magnitude | Random (realistic) | Actual signal strength |

## Debugging

Enable debug logging to see detailed processing:

```bash
cd rust
RUST_LOG=debug cargo run --release -- --mock
```

This will show:
- Filtered readings
- Shot analysis steps
- Club detection logic
- Timing information

## Integration Testing

You can use mock mode to:
1. Test the shot detection algorithm
2. Verify distance estimation
3. Check club/ball separation logic
4. Validate output formatting
5. Test error handling

## Next Steps

Once mock mode works correctly, you can:
1. Test with real hardware (remove `--mock` flag)
2. Compare mock vs real shot detection
3. Tune detection parameters
4. Add more test scenarios

