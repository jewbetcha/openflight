# GSPro

OpenFlight streams shots into [GSPro](https://gsprogolf.com/) using the
**OpenConnect V1** API — the de-facto open standard for launch-monitor → sim
integrations.

See the connector architecture in [README.md](README.md). This page covers
requirements and setup specific to GSPro.

## Requirements

- **A GSPro license.** GSPro is paid software (subscription). The OpenConnect
  API is included with a standard license — there is no separate add-on.
- **The GSPro Connect window.** GSPro exposes the API through its built-in
  "GSPro Connect" / OpenAPI interface, which listens on **TCP port 921**.
- **Network reachability.** OpenFlight (the Raspberry Pi) and the PC running
  GSPro must be on the same LAN. You need the GSPro PC's IP address.
- No account/credentials are sent by OpenFlight — OpenConnect V1 has no auth.

## Setup

1. **Find the GSPro PC's IP address** (e.g. `192.168.1.50`).
   - Windows: `ipconfig` → IPv4 Address.

2. **Configure OpenFlight.** Copy the example config if you haven't already:
   ```bash
   cp config/sim.example.json config/sim.json
   ```
   Set the GSPro connector:
   ```jsonc
   {
     "connectors": [
       {
         "type": "gspro",
         "enabled": true,
         "host": "192.168.1.50",
         "port": 921,
         "device_id": "OpenFlight",
         "units": "Yards",
         "heartbeat_interval_s": 5
       }
     ]
   }
   ```
   Then enable simulator connectors at launch with `--sim` (off by default):
   ```bash
   scripts/start-kiosk.sh --kld7 --sim
   ```

3. **Open GSPro and start a round**, then open the **GSPro Connect** window
   (the OpenAPI interface). It should report "Waiting for connection".

4. **Start OpenFlight.** The header GSPro pill should turn **green**
   (connected). GSPro Connect should show the device connected.

5. **Hit a shot.** It appears in GSPro within a few milliseconds, and the
   "Sent to GSPro" panel in OpenFlight shows the values sent with
   measured/estimated badges.

## What gets sent

| GSPro field | Source |
|---|---|
| `BallData.Speed` | measured ball speed (required — shot dropped if missing) |
| `BallData.VLA` / `HLA` | measured launch angles, else model fallback |
| `BallData.TotalSpin` | measured spin if high-confidence, else per-club model |
| `BallData.SpinAxis` | measured spin axis, else `0` |
| `BallData.BackSpin` / `SideSpin` | derived from total spin + axis |
| `BallData.CarryDistance` | OpenFlight's carry estimate |
| `ClubData.Speed` / `Path` | measured if available (`ContainsClubData` set accordingly) |

## Club selection

When you change clubs in GSPro, it sends a player update (code 201). OpenFlight
applies it: the current club used for shot tagging and the carry/spin model
follows GSPro. Putts (`PT`) are out of scope and ignored.

## Troubleshooting

- **Pill stays amber (reconnecting):** OpenFlight can't reach `host:port`.
  Check the IP, that GSPro Connect is open, and that no firewall blocks 921.
  OpenFlight retries automatically with backoff (1→2→4→…→30s).
- **Pill red (error):** GSPro returned an error code; hover the pill for the
  message. The connection stays up.
- **Shots don't appear in GSPro:** confirm a round is active and the Connect
  window shows the device connected. Check `sim_send` entries in the session
  log to confirm OpenFlight is sending.

## References

- [GSPro OpenConnect V1 spec](https://gsprogolf.com/GSProConnectV1.html)
