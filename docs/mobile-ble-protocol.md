# BLE Protocol

The mobile app talks to the Pi over a custom BLE GATT service when Wi-Fi is unavailable. This
documents the service, the authentication handshake, and the command/notification payloads.

- Client: `mobile/src/hooks/useBLEConnection.ts` (react-native-ble-plx)
- Server: `src/openflight/ble_server.py` (`bless`, GATT peripheral on a daemon asyncio thread)

The two files declare the same UUIDs and JSON shapes. Change one, change the other.

## GATT service

Advertised name: `OpenFlight`. Service UUID `4fafc201-1fb5-459e-8fcc-c5c9c331914b`.

| Characteristic | UUID suffix | Properties | Direction |
|----------------|-------------|------------|-----------|
| Shot | `…26a8` | read, notify | Pi → phone: new shots |
| Command | `…26a9` | write | phone → Pi: commands |
| Status | `…26aa` | read, notify | Pi → phone: events (e.g. `session_cleared`) |
| Challenge | `…26ab` | read, notify | Pi → phone: current auth nonce |

All payloads are UTF-8 JSON. On the wire, react-native-ble-plx base64-encodes values, so the
client wraps writes in `btoa(JSON.stringify(...))` and unwraps notifications with
`JSON.parse(atob(value))`. All Command-characteristic writes go through a single
`sendCommand(device, payload)` helper in `useBLEConnection.ts`.

## Pairing ceremony (one time)

1. The kiosk browser fetches `/api/pair-qr` (localhost-only) and renders a QR code holding
   `{ v, s, h, p }`: protocol version, the 32-byte pairing secret as hex, the Pi LAN IP, and the
   port.
2. The phone scans the QR and stores the secret hex in SecureStore under
   `openflight.ble-pairing-secret` (Keychain/Keystore, hardware-backed where available).

The secret never crosses the LAN. The QR endpoint returns 403 to any non-localhost caller.

## Authentication (every connection)

The Pi holds a 32-byte secret. The phone holds the same secret from pairing. They prove a shared
secret without sending it, using an HMAC challenge:

1. The Pi writes a fresh 64-char hex nonce (`secrets.token_hex(32)`) to the Challenge
   characteristic. It refreshes every 240s; each nonce is valid for 300s.
2. On connect the phone reads the Challenge nonce and computes
   `HMAC-SHA256(secret_bytes, nonce_utf8)` as a 64-char lowercase hex digest. The digest comes from
   the pure-JS `computeHmac` in `mobile/src/utils/hmac.ts`, not `crypto.subtle` - Hermes ships no
   WebCrypto. That module is verified against RFC 4231 vectors in `__tests__/utils/hmac.test.ts`.
3. The phone writes `{"cmd": "auth_challenge", "hmac": "<hex>"}` to the Command characteristic.
4. The Pi verifies with `hmac.compare_digest` (constant-time). On success the client is
   authenticated until the current nonce expires (≤5 min); after that it re-authenticates.

If the Pi starts with no pairing secret, it runs in open mode and accepts every command. That path
is for development only.

```
Phone                          Pi (ble_server.py)
  │   read Challenge  ───────────►│  returns nonce (hex)
  │◄──────────  nonce             │
  │  HMAC-SHA256(secret, nonce)   │
  │  write Command:auth_challenge ►│  compare_digest(expected, provided)
  │◄────────  (authenticated)     │  auth valid until nonce expiry
```

## Commands (phone → Pi, Command characteristic)

JSON written to the Command characteristic. The server rate-limits accepted writes to one per
second and dispatches the handler on a worker thread.

| Command | Payload | Effect |
|---------|---------|--------|
| `auth_challenge` | `{cmd, hmac}` | Authenticate (above). |
| `get_session` | `{cmd}` | Ask the Pi to push current session shots. |
| `clear_session` | `{cmd}` | Clear the active session. |
| `set_club` | `{cmd, club}` | Set the active club label. |
| `set_prefs` | `{cmd, accessibility}` | Relay client accessibility prefs to the kiosk. |

The client sends `get_session` and `set_prefs` automatically right after a successful auth.

## Notifications (Pi → phone)

- **Shot** characteristic: a full `Shot` JSON object. If the JSON exceeds 512 bytes, the Pi falls
  back to a slim encoding with short keys before truncating. The slim map (`_SLIM_FIELDS` in
  `ble_server.py`):

  | Short | Field |
  |-------|-------|
  | `b` | `ball_speed_mph` |
  | `c` | `estimated_carry_yards` |
  | `l` | `launch_angle_vertical` |
  | `s` | `spin_rpm` |
  | `q` | `club` |
  | `t` | `timestamp` |
  | `sp` | `club_speed_mph` |
  | `sm` | `smash_factor` |
  | `cs` | `carry_spin_adjusted` |

- **Status** characteristic: event objects such as `{"event": "session_cleared"}`. The client
  clears its local shot list when it sees that event.

The client drops any shot that fails `isValidShot` and increments `malformedCount` for diagnostics.

## Client connection lifecycle

`useBLEConnection` status moves through `idle → scanning → connecting → connected`, with
`disconnected` and `error` branches. On an unexpected disconnect it auto-reconnects with a 3s/6s/12s
backoff for up to 3 attempts. Android requests `BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`, and
`ACCESS_FINE_LOCATION` before scanning (API 31+ splits the scan/connect permissions).
