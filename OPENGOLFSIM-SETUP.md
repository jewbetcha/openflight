# OpenGolfSim Setup Guide

## Current Status

The integration is working correctly - it's detecting shots and attempting to send them to OpenGolfSim.

## Steps to Get It Working

### 1. Start OpenGolfSim

Make sure OpenGolfSim is running on your PC before starting OpenLaunch.

### 2. Check OpenGolfSim's Port

The default port is 3111. Check:
- OpenGolfSim's settings -> shot data

If it uses a different port, specify it:
```bash
cargo run --release -- --mock --opengolfsim --opengolfsim-port 3112
```

### 3. Enable Developer API

OpenGolfSim may require you to enable the Developer API or Launch Monitor integration:
- Check OpenGolfSim's settings -> shot data menu
- Look for "Change Launch Monitor"
- Select "Built-In Developer API"

### 4. Try TCP Mode

Some golf simulators prefer TCP sockets over HTTP:

```bash
# add --opengolfsim-http to use http
# change port if needed --opengolfsim-port 3112
cargo run --release -- --mock --opengolfsim --live
```

### 6. Check OpenGolfSim Logs

When you run OpenLaunch, check OpenGolfSim's console/logs for:
- Incoming connection attempts
- API requests
- Any error messages about the data format

## Testing Without OpenGolfSim

If you just want to test the launch monitor without OpenGolfSim, you can:

1. **Run without integration**:
   ```bash
   cargo run --release -- --mock --live
   ```

2. **Run with integration but suppress warnings**:
   The warnings are now logged as debug messages when OpenGolfSim isn't available, so they won't show unless you enable debug logging:
   ```bash
   RUST_LOG=debug cargo run --release -- --mock --opengolfsim --opengolfsim-http --live
   ```


