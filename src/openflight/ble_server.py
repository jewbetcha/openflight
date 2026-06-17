"""
BLE GATT peripheral server for OpenFlight.

Characteristics
---------------
Shot       (notify + read)  – new shots pushed to connected phones
Command    (write)          – phones send {"cmd": "get_session" | "clear_session" | "set_club", ...}
Status     (notify + read)  – Pi pushes events like {"event": "session_cleared"}
Challenge  (notify + read)  – Pi writes a fresh nonce here; client reads and responds with HMAC

Authentication
--------------
On startup the server is given a 32-byte pairing secret (loaded from disk by server.py).
When a client connects it reads the Challenge characteristic to get the current nonce (64-char
hex string), computes HMAC-SHA256(pairing_secret, nonce_utf8_bytes), and writes
  {"cmd": "auth_challenge", "hmac": "<64-char hex>"}
to the Command characteristic.  The Pi verifies with hmac.compare_digest (constant-time).

The nonce is refreshed every 4 minutes.  A newly connected client always sees a valid nonce.
Auth grants access for 1 hour; after that the client must re-authenticate.

If no pairing_secret is supplied (development / no-BLE-auth mode) all commands are accepted.

UUIDs
-----
Service:   4fafc201-1fb5-459e-8fcc-c5c9c331914b
Shot:      beb5483e-36e1-4688-b7f5-ea07361b26a8
Command:   beb5483e-36e1-4688-b7f5-ea07361b26a9
Status:    beb5483e-36e1-4688-b7f5-ea07361b26aa
Challenge: beb5483e-36e1-4688-b7f5-ea07361b26ab
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from typing import Callable, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

OPENFLIGHT_SERVICE_UUID    = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
SHOT_CHARACTERISTIC_UUID      = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
COMMAND_CHARACTERISTIC_UUID   = "beb5483e-36e1-4688-b7f5-ea07361b26a9"
STATUS_CHARACTERISTIC_UUID    = "beb5483e-36e1-4688-b7f5-ea07361b26aa"
CHALLENGE_CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26ab"

# Truncate at 512 bytes; fall back to slim encoding before truncating
_MAX_PAYLOAD_BYTES = 512
# Slim encoding: short key → full Shot field name (8 most-displayed fields)
_SLIM_FIELDS = {
    "b": "ball_speed_mph",
    "c": "estimated_carry_yards",
    "l": "launch_angle_vertical",
    "s": "spin_rpm",
    "q": "club",
    "t": "timestamp",
    "sp": "club_speed_mph",
    "sm": "smash_factor",
    "cs": "carry_spin_adjusted",
}
# Minimum seconds between accepted write commands (per-server rate limit)
_COMMAND_RATE_LIMIT_S = 1.0
# Nonce refresh interval — 4 minutes; nonce valid for 5 minutes.
_NONCE_REFRESH_S = 240
_NONCE_TTL_S = 300


@runtime_checkable
class BLEBackend(Protocol):
    """
    Minimal interface that the real bless BlessServer satisfies.
    Inject a mock in tests to avoid needing real Bluetooth hardware.
    """

    async def start(self) -> None:
        """Start advertising and bring up the GATT server"""

    async def stop(self) -> None:
        """Tear down the GATT server and stop advertising"""

    async def update_value(self, service_uuid: str, char_uuid: str) -> None:
        """Push the characteristic's current value to its subscribers"""

    def get_characteristic(self, char_uuid: str):
        """Return the backend characteristic object for a uuid"""


def _slim_shot(shot_data: dict) -> dict:
    return {short: shot_data.get(full) for short, full in _SLIM_FIELDS.items()}


class BLEServer:
    """
    BLE GATT peripheral.  Runs its own asyncio loop on a daemon thread so
    the Flask server is not blocked.  All public methods are thread-safe.

    Parameters
    ----------
    on_command:
        Optional callback invoked (in the BLE event loop thread) when a
        mobile client writes to the command characteristic.  The argument
        is the parsed JSON dict, e.g. {"cmd": "get_session"}.
    pairing_secret:
        32-byte secret shared with the mobile app during the QR pairing
        ceremony.  If None the server runs in open mode (no auth required).
    """

    def __init__(
        self,
        on_command: Optional[Callable[[dict], None]] = None,
        pairing_secret: Optional[bytes] = None,
    ) -> None:
        self._on_command = on_command
        self._pairing_secret = pairing_secret
        # Open mode: no secret → always authenticated
        self._authenticated: bool = pairing_secret is None
        self._auth_expiry: float = float("inf") if pairing_secret is None else 0.0
        self._current_nonce: str = ""        # 64-char hex string written to CHALLENGE char
        self._nonce_expiry: float = 0.0
        self._nonce_refresh_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._last_command_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API (thread-safe)
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the BLE peripheral on a background thread.  Returns True on success."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("BLE server already running; ignoring duplicate start()")
            return self._server is not None
        self._ready.clear()
        try:
            from bless import (  # pylint: disable=import-outside-toplevel
                BlessServer,
                GATTAttributePermissions,
                GATTCharacteristicProperties,
            )
        except ImportError:
            logger.error(
                "BLE support requires the 'bless' package. "
                "Install it with: uv pip install 'openflight[ble]'"
            )
            return False

        self._thread = threading.Thread(
            target=self._run_loop,
            args=(BlessServer, GATTCharacteristicProperties, GATTAttributePermissions),
            daemon=True,
            name="ble-server",
        )
        self._thread.start()

        if not self._ready.wait(timeout=10):
            logger.error("BLE server did not start within 10 seconds")
            return False

        return self._server is not None

    def notify_shot(self, shot_data: dict) -> None:
        """Push a shot to all connected BLE centrals (thread-safe)."""
        if self._server is None or self._loop is None:
            return

        payload = json.dumps(shot_data).encode("utf-8")
        if len(payload) > _MAX_PAYLOAD_BYTES:
            slim = json.dumps(_slim_shot(shot_data)).encode("utf-8")
            logger.debug(
                "BLE: full shot %d bytes > limit; using slim encoding (%d bytes)",
                len(payload),
                len(slim),
            )
            payload = slim

        asyncio.run_coroutine_threadsafe(
            self._push(SHOT_CHARACTERISTIC_UUID, bytearray(payload)), self._loop
        )

    def notify_event(self, event_data: dict) -> None:
        """Push a status event to all connected BLE centrals (thread-safe)."""
        if self._server is None or self._loop is None:
            return
        payload = json.dumps(event_data).encode("utf-8")
        asyncio.run_coroutine_threadsafe(
            self._push(STATUS_CHARACTERISTIC_UUID, bytearray(payload)), self._loop
        )

    def stop(self) -> None:
        """Gracefully stop the server."""
        if self._server and self._loop:
            if self._nonce_refresh_task:
                self._loop.call_soon_threadsafe(self._nonce_refresh_task.cancel)
            future = asyncio.run_coroutine_threadsafe(self._server.stop(), self._loop)
            try:
                future.result(timeout=5)
            except Exception:  # pylint: disable=broad-except
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(
        self,
        BlessServer,
        GATTCharacteristicProperties,
        GATTAttributePermissions,
    ) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(
                self._setup(BlessServer, GATTCharacteristicProperties, GATTAttributePermissions)
            )
            loop.run_forever()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("BLE server loop crashed: %s", exc)
            self._ready.set()
        finally:
            loop.close()

    async def _setup(
        self,
        BlessServer,
        GATTCharacteristicProperties,
        GATTAttributePermissions,
    ) -> None:
        server = BlessServer(name="OpenFlight", loop=self._loop)
        server.write_request_func = self._handle_write

        gatt = {
            OPENFLIGHT_SERVICE_UUID: {
                SHOT_CHARACTERISTIC_UUID: {
                    "Properties": (
                        GATTCharacteristicProperties.read
                        | GATTCharacteristicProperties.notify
                    ),
                    "Permissions": GATTAttributePermissions.readable,
                    "Value": bytearray(b""),
                },
                COMMAND_CHARACTERISTIC_UUID: {
                    "Properties": GATTCharacteristicProperties.write,
                    "Permissions": GATTAttributePermissions.writeable,
                    "Value": bytearray(b""),
                },
                STATUS_CHARACTERISTIC_UUID: {
                    "Properties": (
                        GATTCharacteristicProperties.read
                        | GATTCharacteristicProperties.notify
                    ),
                    "Permissions": GATTAttributePermissions.readable,
                    "Value": bytearray(b""),
                },
                CHALLENGE_CHARACTERISTIC_UUID: {
                    "Properties": (
                        GATTCharacteristicProperties.read
                        | GATTCharacteristicProperties.notify
                    ),
                    "Permissions": GATTAttributePermissions.readable,
                    "Value": bytearray(b""),
                },
            }
        }

        await server.add_gatt(gatt)
        await server.start()
        self._server = server
        # Write the first nonce before signalling ready so connecting clients always
        # see a valid challenge immediately.
        await self._refresh_nonce()
        self._nonce_refresh_task = asyncio.ensure_future(self._nonce_refresh_loop())
        logger.info("BLE server started — advertising as 'OpenFlight'")
        self._ready.set()

    async def _refresh_nonce(self) -> None:
        """Generate a fresh 32-byte nonce and write it to the Challenge characteristic.

        Also resets auth state so any inherited session from a previous BLE client
        is invalidated — the next client must prove possession of the pairing secret
        with the new nonce.
        """
        self._current_nonce = secrets.token_hex(32)   # 64-char hex string
        self._nonce_expiry = time.monotonic() + _NONCE_TTL_S
        if self._pairing_secret is not None:
            self._authenticated = False
            self._auth_expiry = 0.0
        if self._server:
            char = self._server.get_characteristic(CHALLENGE_CHARACTERISTIC_UUID)
            if char:
                char.value = bytearray(self._current_nonce.encode())
                try:
                    await self._server.update_value(
                        OPENFLIGHT_SERVICE_UUID, CHALLENGE_CHARACTERISTIC_UUID
                    )
                except Exception:  # pylint: disable=broad-except
                    pass

    async def _nonce_refresh_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(_NONCE_REFRESH_S)
                await self._refresh_nonce()
        except asyncio.CancelledError:
            pass

    async def _push(self, char_uuid: str, payload: bytearray) -> None:
        if self._server is None:
            return
        char = self._server.get_characteristic(char_uuid)
        if char is None:
            return
        try:
            char.value = payload
            await self._server.update_value(OPENFLIGHT_SERVICE_UUID, char_uuid)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("BLE notify failed (…%s): %s", char_uuid[-4:], exc)

    def _verify_hmac(self, provided_hex: str) -> bool:
        """Constant-time HMAC-SHA256 verification against the current nonce."""
        if not self._pairing_secret:
            return True
        if not self._current_nonce or time.monotonic() > self._nonce_expiry:
            logger.warning("BLE: auth attempt with expired or missing nonce")
            return False
        nonce_bytes = self._current_nonce.encode()
        expected = hmac.new(self._pairing_secret, nonce_bytes, hashlib.sha256).hexdigest()
        try:
            return hmac.compare_digest(expected, provided_hex.lower())
        except (ValueError, TypeError):
            return False

    def _dispatch_command(self, cmd: dict) -> None:
        try:
            self._on_command(cmd)  # type: ignore[misc]
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("BLE on_command handler error: %s", exc)

    def _handle_write(self, characteristic, value: bytearray, **_kwargs) -> None:
        """Rate-limited write handler; dispatches on_command to a daemon thread."""
        try:
            char_uuid = str(characteristic.uuid).lower()
        except Exception:  # pylint: disable=broad-except
            return
        if char_uuid != COMMAND_CHARACTERISTIC_UUID.lower():
            return

        now = time.monotonic()
        if now - self._last_command_time < _COMMAND_RATE_LIMIT_S:
            logger.debug("BLE command rate-limited")
            return
        self._last_command_time = now

        try:
            cmd = json.loads(bytes(value).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            logger.warning("BLE: malformed command payload")
            return

        if cmd.get("cmd") == "auth_challenge":
            provided = cmd.get("hmac", "")
            if self._verify_hmac(provided):
                self._authenticated = True
                # Auth is tied to the nonce window (≤5 min).  When the nonce
                # rotates, _nonce_expiry advances and any NEW connection must
                # re-auth; an old connection's auth expires with its nonce.
                self._auth_expiry = self._nonce_expiry
                logger.info("BLE: client authenticated via HMAC-SHA256")
            else:
                logger.warning("BLE: auth failed — invalid HMAC or expired nonce")
            return

        if not self._authenticated or time.monotonic() > self._auth_expiry:
            logger.warning("BLE: command rejected — not authenticated")
            return

        if self._on_command is not None:
            threading.Thread(
                target=self._dispatch_command, args=(cmd,), daemon=True, name="ble-cmd"
            ).start()
