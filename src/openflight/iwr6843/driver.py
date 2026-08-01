"""IWR6843 serial driver — the host side of the L3-dump firmware contract.

Firmware v3+ speaks a SINGLE UART (the CP2105 Enhanced interface) at
1,041,667 baud for both CLI commands and the binary dump; the dump is framed
by its "ILD1" magic plus the header-declared length, so CLI echo and payload
can share the pipe. Hardware-validated 2026-07-13 at 100% of wire rate.

Gotchas baked in (each cost a debugging session):
- DTR/RTS must be held low on open (TI EVMs tie them to reset/boot mode).
- One serial handle only — two handles on one tty steal each other's bytes.
- The CP2105 can stall a stream for seconds (cp210x -110 control timeouts)
  and resume; the reader waits out gaps up to ``stall_tolerance_s``.
"""

from __future__ import annotations

import glob
import logging
import time

import serial

from openflight.iwr6843.dump import HEADER, MAGIC, parse_header, payload_nbytes

BAUD = 1_041_667
_PORT_GLOBS = ("/dev/ttyUSB*", "/dev/tty.SLAB_USBtoUART*")

logger = logging.getLogger(__name__)


def open_port(port: str, baud: int = BAUD, timeout: float = 0.3) -> serial.Serial:
    """DTR/RTS-safe serial open."""
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, baud, timeout
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


class IWR6843Radar:
    """CLI + dump transport for the custom L3-dump firmware."""

    def __init__(self, port: str | None = None, baud: int = BAUD):
        if port is None:
            port = self.detect_port(baud)
            if port is None:
                raise RuntimeError("no IWR6843 CLI found — board on, flashed, single-port fw?")
        self.port = port
        self.ser = open_port(port, baud)

    @staticmethod
    def detect_port(baud: int = BAUD) -> str | None:
        """First serial port whose CLI answers `help` with our commands."""
        candidates: list[str] = []
        for pattern in _PORT_GLOBS:
            candidates.extend(sorted(glob.glob(pattern)))
        for cand in candidates:
            try:
                ser = open_port(cand, baud)
            except (OSError, serial.SerialException):
                continue
            try:
                ser.reset_input_buffer()
                ser.write(b"help\n")
                resp = b""
                deadline = time.time() + 1.5
                while time.time() < deadline and b"sensorStart" not in resp:
                    resp += ser.read(512)
            finally:
                ser.close()
            if b"sensorStart" in resp:
                return cand
        return None

    def cmd(self, line: str, window: float = 1.5) -> str:
        """Send one CLI line; collect the response until Done/Error/timeout."""
        self.ser.reset_input_buffer()
        self.ser.write((line + "\n").encode())
        resp = b""
        deadline = time.time() + window
        while time.time() < deadline:
            resp += self.ser.read(512)
            if b"Done" in resp or b"Error" in resp:
                break
        return resp.decode(errors="replace")

    def drain_stale_output(
        self,
        *,
        max_wait_s: float = 10.0,
        initial_quiet_s: float = 0.25,
        stream_quiet_s: float = 4.25,
    ) -> int:
        """Drain an abandoned binary dump before sending configuration commands.

        If a host process exits during ``l3dump``, the firmware can still be
        writing the old payload through the CP2105. Commands sent into that
        stream are not safe to associate with their responses. Once bytes are
        observed, tolerate the bridge's known multi-second stalls before
        declaring the stream quiet.
        """
        drained = 0
        saw_data = False
        start = time.monotonic()
        last_data = start
        while time.monotonic() - start < max_wait_s:
            waiting = self.ser.in_waiting
            if waiting:
                chunk = self.ser.read(min(waiting, 4096))
                if chunk:
                    drained += len(chunk)
                    saw_data = True
                    last_data = time.monotonic()
                    continue
            quiet_s = stream_quiet_s if saw_data else initial_quiet_s
            if time.monotonic() - last_data >= quiet_s:
                break
            time.sleep(0.01)
        if drained:
            logger.warning(
                "[IWR6843] Drained %d stale UART bytes before configuration",
                drained,
            )
        return drained

    @staticmethod
    def _require_done(command: str, response: str) -> None:
        if "Error" in response:
            raise RuntimeError(f"config rejected: {command!r}: {response.strip()}")
        if "Done" not in response:
            raise RuntimeError(
                f"IWR6843 did not acknowledge {command!r}; "
                "the firmware may be wedged (press RESET and retry)"
            )

    def send_config(self, cfg_path: str) -> None:
        """sensorStop, then stream the cfg (ends in sensorStart); raise on Error.

        The firmware's geometry guard rejects a cfg whose loops/samples don't
        match the flashed build — that surfaces here as RuntimeError.
        """
        self.drain_stale_output()
        self._require_done("sensorStop", self.cmd("sensorStop", 3.0))
        with open(cfg_path, encoding="utf-8") as cfg:
            for rawline in cfg:
                line = rawline.strip()
                if not line or line.startswith("%"):
                    continue
                window = 6.0 if line.startswith("sensorStart") else 1.5
                resp = self.cmd(line, window)
                self._require_done(line, resp)
        health = self.stats()
        self._require_done("stats", health)
        if "active=1" not in health:
            raise RuntimeError(f"IWR6843 did not enter active capture mode: {health.strip()}")

    def read_dump(self, timeout_s: float = 40.0, stall_tolerance_s: float = 4.0) -> bytes:
        """Fire `l3dump` and return one complete dump (best effort on stalls).

        Syncs on the ILD1 magic past the CLI echo and sizes the read from the
        dump's own header, so any firmware geometry works.
        """
        self.ser.reset_input_buffer()
        self.ser.write(b"l3dump\n")
        buf = b""
        expected: int | None = None
        start = time.time()
        last = start
        while time.time() - start < timeout_s:
            waiting = self.ser.in_waiting
            chunk = self.ser.read(waiting if waiting else 1)
            if chunk:
                buf += chunk
                last = time.time()
            elif buf and time.time() - last > stall_tolerance_s:
                break
            if expected is None:
                idx = buf.find(MAGIC)
                if idx >= 0 and len(buf) - idx >= HEADER.size:
                    buf = buf[idx:]
                    try:
                        metadata = parse_header(buf)
                        expected = metadata["header_nbytes"] + payload_nbytes(metadata)
                    except ValueError:
                        expected = None
            elif len(buf) >= expected:
                break
        return buf if expected is None else buf[:expected]

    def stats(self) -> str:
        """Firmware health line (frames/wraps/active/calib/rf_faults)."""
        return self.cmd("stats", 2.0)

    def close(self) -> None:
        """Release the serial port."""
        self.ser.close()

    def __enter__(self) -> "IWR6843Radar":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
