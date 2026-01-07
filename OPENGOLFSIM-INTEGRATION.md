# OpenGolfSim Integration

This guide explains how to integrate OpenLaunch Rust with OpenGolfSim.

## Overview

OpenLaunch can send shot data to OpenGolfSim running on the same PC via **persistent TCP socket** (recommended) or HTTP API. The integration maintains a persistent connection to OpenGolfSim and automatically handles reconnection if the connection is lost.

**Key Features:**
- Persistent TCP connection (no connection overhead per shot)
- Automatic reconnection if connection is lost
- Device status messages (ready/busy) sent automatically
- Automatic retry on first shot if OpenGolfSim isn't running at startup
- Correct data format matching OpenGolfSim API specification

## Usage

### Basic Integration (TCP - Recommended)

```bash
# Navigate to Rust directory
cd rust

# Run with OpenGolfSim integration via TCP (default port 3111)
cargo run --release -- --opengolfsim

# Custom host and port
cargo run --release -- --opengolfsim --opengolfsim-host localhost --opengolfsim-port 3111
```

**Note:** OpenGolfSim uses port **3111** by default (per [OpenGolfSim API documentation](https://help.opengolfsim.com/desktop/apis/shot-data/)). The integration maintains a persistent TCP connection, so there's no connection overhead for each shot.

### HTTP Integration (Not Recommended)

OpenGolfSim uses TCP by default. HTTP mode will automatically fall back to TCP if HTTP fails with version errors.

```bash
cd rust

# HTTP will auto-fallback to TCP if needed
cargo run --release -- --opengolfsim --opengolfsim-http

# Use TCP directly (recommended)
cargo run --release -- --opengolfsim --opengolfsim-port 3111
```

**Note:** OpenGolfSim's Developer API uses TCP sockets, not HTTP. The HTTP mode is provided for compatibility but will automatically fall back to TCP when it detects the "invalid HTTP version" error.

### With Mock Mode (Testing)

```bash
cd rust

# Test integration without hardware (generates shots every 20 seconds by default)
cargo run --release -- --mock --opengolfsim --live

# Custom shot interval (e.g., every 10 seconds)
cargo run --release -- --mock --mock-interval 10.0 --opengolfsim --live
```

**Mock Mode Defaults:**
- Shot interval: **20 seconds** (configurable with `--mock-interval`)
- Automatically generates realistic golf shot data
- Perfect for testing OpenGolfSim integration without hardware

## Data Format

OpenLaunch sends shot data in the exact format required by OpenGolfSim API:

```json
{
  "type": "shot",
  "unit": "imperial",
  "shot": {
    "ballSpeed": 142.3
  }
}
```

**Current fields sent:**
- `ballSpeed` (mph) - Required, always sent
- `type: "shot"` - Message type identifier
- `unit: "imperial"` - Units (mph for ball speed)

**Fields available but not yet implemented:**
- `verticalLaunchAngle` - Will be added when camera integration is complete
- `horizontalLaunchAngle` - Will be added when camera integration is complete
- `spinSpeed` - Requires spin detection hardware
- `spinAxis` - Requires spin detection hardware

**Device Status Messages:**
The integration automatically sends device status messages:
- `{"type": "device", "status": "ready"}` - Sent when connection is established
- `{"type": "device", "status": "busy"}` - Sent when shutting down

See [OpenGolfSim API Documentation](https://help.opengolfsim.com/desktop/apis/shot-data/) for full details.

## OpenGolfSim Configuration

### TCP Mode (Default - Recommended)

OpenGolfSim uses **persistent TCP sockets** on port **3111** (default). The integration maintains a single connection throughout the session, eliminating connection overhead for each shot.

**Connection Details:**
- Host: `127.0.0.1` (localhost) or `localhost`
- Port: `3111` (default, per OpenGolfSim API docs)
- Protocol: Persistent TCP socket
- Data format: JSON string followed by newline (`\n`)

**Connection Lifecycle:**
1. **On Startup:** Connects to OpenGolfSim → sends "ready" status → waits 500ms for OpenGolfSim to be ready
2. **During Operation:** Uses persistent connection for all shots
3. **On Error:** Automatically reconnects if connection is lost
4. **On Shutdown:** Sends "busy" status → disconnects cleanly

**Device Status Messages:**
The integration automatically sends device status:
- `{"type": "device", "status": "ready"}` - Sent when connection is established (after 100ms delay)
- `{"type": "device", "status": "busy"}` - Sent when shutting down

**Retry Logic:**
- If OpenGolfSim isn't running at startup, the integration will retry connecting when the first shot is detected
- If connection is lost during operation, it automatically reconnects on the next shot

### HTTP Mode

OpenGolfSim should expose an HTTP endpoint. The integration tries these endpoints in order:
- `POST http://localhost:8080/api/shot`
- `POST http://localhost:8080/shot`
- `POST http://localhost:8080/api/launch-monitor/shot`

The shot data is sent as JSON in the request body.

**Note**: If you get timeout errors, ensure:
1. OpenGolfSim is running
2. The port matches OpenGolfSim's configuration
3. OpenGolfSim's Developer API is enabled
4. Check OpenGolfSim's documentation for the correct endpoint URL

## Troubleshooting

### Connection Refused at Startup

If you see "connection refused" at startup, OpenGolfSim isn't running yet:

1. **Start OpenGolfSim first** - Make sure OpenGolfSim is running before starting OpenLaunch
2. **Automatic retry** - The integration will automatically retry connecting when the first shot is detected
3. **Check the port** - Verify OpenGolfSim is listening on port 3111 (default)

**Expected behavior:**
- If OpenGolfSim is running: `[OPENGOLFSIM] Connected to localhost:3111`
- If not running: `[OPENGOLFSIM] OpenGolfSim not available at startup... Will retry when shots are detected.`

### Invalid HTTP Version Error

If you see "invalid HTTP version parsed", OpenGolfSim is using TCP instead of HTTP:

1. **Use TCP mode directly** (recommended):
   ```bash
   cd rust
   # Remove --opengolfsim-http to use TCP
   cargo run --release -- --mock --opengolfsim --opengolfsim-port 3111
   ```

2. **Auto-fallback**: If HTTP fails with version errors, it will automatically try TCP

3. **OpenGolfSim uses TCP**: The Developer API uses raw TCP sockets, not HTTP

### HTTP Request Timeout

This usually means OpenGolfSim isn't running or the endpoint is incorrect:

1. **Check if OpenGolfSim is running**
   - Look for the OpenGolfSim process
   - Check if the UI is open

2. **Verify the endpoint**
   - Check OpenGolfSim's Developer API documentation
   - The integration tries multiple common endpoints automatically
   - You may need to check OpenGolfSim's logs to see what endpoint it expects

3. **Check the port**
   - Default is 8080, but OpenGolfSim might use a different port
   - Check OpenGolfSim's settings/configuration

4. **Enable Developer API**
   - Make sure OpenGolfSim's Developer API is enabled
   - Some simulators require explicit API enablement

### Connection Lost During Operation

If the connection is lost during operation (e.g., OpenGolfSim restarted):

1. **Automatic reconnection** - The integration will automatically reconnect on the next shot
2. **Check logs** - Look for `[OPENGOLFSIM] Connection lost, attempting to reconnect...`
3. **Verify OpenGolfSim is running** - Make sure OpenGolfSim is still running

### Data Not Received by OpenGolfSim

If shots aren't appearing in OpenGolfSim:

1. **Check connection status** - Look for `[OPENGOLFSIM] Connected to localhost:3111` in logs
2. **Enable debug logging**:
   ```bash
   cd rust
   $env:RUST_LOG="debug"; cargo run --release -- --mock --opengolfsim --live
   ```
3. **Verify data format** - Check that shots are being sent: `[OPENGOLFSIM] Shot sent successfully`
4. **Check OpenGolfSim logs** - Look for incoming connections in OpenGolfSim's console/logs
5. **Verify port** - Make sure OpenGolfSim is listening on port 3111 (check OpenGolfSim settings)

### Connection Issues

- **Ensure OpenGolfSim is running** - The integration needs OpenGolfSim to be running
- **Check port** - Default is 3111, verify in OpenGolfSim settings
- **Firewall** - Ensure firewall isn't blocking localhost connections
- **Try TCP mode** - Use `--opengolfsim` (without `--opengolfsim-http`) for direct TCP connection

### Testing

Use mock mode to test the integration:

```bash
cd rust

# Default: shots every 20 seconds
cargo run --release -- --mock --opengolfsim --live

# Custom interval: shots every 10 seconds
cargo run --release -- --mock --mock-interval 10.0 --opengolfsim --live

# With debug logging to see all connection details
$env:RUST_LOG="debug"; cargo run --release -- --mock --opengolfsim --live
```

This will:
1. Generate test shots every 20 seconds (or custom interval)
2. Send each shot to OpenGolfSim via persistent TCP connection
3. Display shot data in the console
4. Show connection status and shot transmission logs

**What to look for:**
- `[OPENGOLFSIM] Connected to localhost:3111` - Connection established
- `[OPENGOLFSIM] Device status: ready` - Ready status sent
- `[OPENGOLFSIM] Shot sent successfully` - Shot transmitted successfully

## API Compatibility

The current implementation follows the [OpenGolfSim Developer API specification](https://help.opengolfsim.com/desktop/apis/shot-data/) exactly:

✅ **Correct Format:**
- `type: "shot"` - Message type
- `unit: "imperial"` - Units (mph)
- `shot: { ballSpeed: ... }` - Shot data object

✅ **Persistent TCP Connection:**
- Maintains single connection throughout session
- Automatic reconnection on connection loss
- Device status messages (ready/busy)

✅ **Port Configuration:**
- Default port: 3111 (per OpenGolfSim API docs)
- Configurable via `--opengolfsim-port`

**Future Enhancements:**
If you need to add additional fields (launch angles, spin), modify the `format_shot_data()` function in `rust/src/opengolfsim.rs`. The structure is ready for:
- `verticalLaunchAngle` - When camera integration is added
- `horizontalLaunchAngle` - When camera integration is added
- `spinSpeed` - When spin detection hardware is added
- `spinAxis` - When spin detection hardware is added

## Implementation Details

### Connection Management

The integration uses a **persistent TCP connection** with the following features:

- **Single Connection**: One TCP socket maintained for the entire session
- **Automatic Reconnection**: If connection is lost, automatically reconnects on next shot
- **Thread-Safe**: Uses `Arc<Mutex<>>` for safe concurrent access
- **Error Recovery**: Detects broken connections and clears them for reconnection

### Shot Transmission

- Shots are sent in background threads to avoid blocking the main radar loop
- Each shot is sent as a JSON message with newline terminator
- Connection errors are logged but don't stop the main application

### Configuration

**Command-Line Options:**
- `--opengolfsim` - Enable OpenGolfSim integration
- `--opengolfsim-host <host>` - OpenGolfSim host (default: localhost)
- `--opengolfsim-port <port>` - OpenGolfSim port (default: 3111)
- `--opengolfsim-http` - Use HTTP instead of TCP (not recommended, auto-falls back to TCP)

## Next Steps

1. ✅ **API Format**: Matches OpenGolfSim specification exactly
2. ✅ **Connection**: Persistent TCP connection implemented
3. ✅ **Testing**: Use mock mode to verify integration
4. **Future**: Add launch angle and spin data when hardware is available

