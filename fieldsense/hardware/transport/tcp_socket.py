"""TCP transport implementing the frozen SensorTransport contract.

WHY THIS EXISTS

On the Arduino UNO Q there is no serial device the host can open to reach the
STM32. `Serial` in a UNO Q sketch is not a UART: Arduino_RouterBridge aliases
it to `Monitor`, a BridgeMonitor Stream carried over MsgPack-RPC (the
`mon/read` / `mon/write` method pair). Linux side, the arduino-router daemon
holds /dev/ttyHS1 open exclusively and re-exposes that stream as a TCP
listener, by default on 127.0.0.1:7500:

    /usr/bin/arduino-router --unix-port /var/run/arduino-router.sock \
                            --serial-port /dev/ttyHS1 --serial-baudrate 115200

So SerialTransport has nothing to open. /dev/ttyGS0 does not exist on this
board, and /dev/ttyHS1 is taken by the daemon - opening it would fight the
router for the same UART rather than talk to the sketch. Note also that
/dev/ttyUSB0 on an assembled FieldSense unit is the FTDI FT232R behind the
MAX485 RS485 transceiver, i.e. the soil sensor bus. Streaming a frame there
would jam Modbus, not draw pixels.

This is a TRANSPORT only. It moves bytes. The frame protocol - header, CRC,
chunking, ACK/NAK - lives in display_bridge.py and is identical over either
transport, which is the point: stream_frame_to_mcu() takes an injected
transport and never learns which one it got.

BAUD DOES NOT APPLY HERE. The router fixes the line speed on its own serial
port. Passing --baud changes nothing over TCP; it must still match LINK_BAUD
in the sketch for the router's own link to work, but this class ignores it.
"""

import socket
import time
from typing import Optional

from .base import SensorTransport

DEFAULT_HOST = "127.0.0.1"
DEFAULT_MONITOR_PORT = 7500


class TcpTransportError(Exception):
    """Raised when the TCP endpoint cannot be reached or used."""


def parse_endpoint(spec: str) -> Optional[tuple]:
    """Split a 'host:port' string into (host, port), or None if it is a path.

    Lets one --port flag carry either form. A leading '/' always means a
    device node, so '/dev/ttyGS0' is never mistaken for a hostname.

    Args:
        spec: Either a device path or a 'host:port' endpoint.

    Returns:
        (host, port) tuple, or None when `spec` is a device path.
    """
    if not spec or spec.startswith("/"):
        return None
    if ":" not in spec:
        return None
    host, _, port_text = spec.rpartition(":")
    if not host or not port_text.isdigit():
        return None
    return (host, int(port_text))


class TcpTransport(SensorTransport):
    """Byte transport over a TCP socket, for the UNO Q monitor proxy."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_MONITOR_PORT,
        timeout: float = 5.0,
    ) -> None:
        """Configure the transport. No socket is created until open().

        Args:
            host: Listener address. The router binds loopback only.
            port: Listener port. arduino-router defaults to 7500.
            timeout: Seconds to wait for bytes in read(), and to connect.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    # ------------------------------------------------------------- lifecycle

    def open(self) -> None:
        """Connect to the listener.

        Raises:
            TcpTransportError: Nothing listening, or the connect failed.
        """
        if self.is_open:
            return
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except ConnectionRefusedError:
            raise TcpTransportError(
                "nothing listening on {}:{}. Is arduino-router running?\n"
                "  ps aux | grep arduino-router\n"
                "  ss -lntp | grep {}".format(self.host, self.port, self.port)
            )
        except OSError as exc:
            raise TcpTransportError(
                "could not connect to {}:{}: {}".format(self.host, self.port, exc))

        sock.settimeout(self.timeout)
        # The frame is a long run of small ACK-gated writes. Nagle would sit on
        # each one waiting for company that never comes, since the host does not
        # send again until the MCU answers - one added RTT per chunk, 38 times.
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:  # pragma: no cover - not fatal if unsupported
            pass
        self._sock = sock

    def close(self) -> None:
        """Close the socket. Safe to call when already closed."""
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    @property
    def is_open(self) -> bool:
        """Return True when the socket is connected."""
        return self._sock is not None

    # ------------------------------------------------------------- transfer

    def write(self, payload: bytes) -> None:
        """Send every byte of `payload`.

        Raises:
            TcpTransportError: Transport not open, or the send failed.
        """
        if not self.is_open:
            raise TcpTransportError("transport is not open")
        try:
            self._sock.sendall(payload)
        except (OSError, socket.timeout) as exc:
            raise TcpTransportError(
                "write failed to {}:{}: {}".format(self.host, self.port, exc))

    def read(self, length: int = 256) -> bytes:
        """Read up to `length` bytes, waiting at most `timeout` seconds in total.

        Returns whatever arrived, possibly fewer bytes than asked for and
        possibly empty, matching SerialTransport.read(). Callers do the framing.

        A single recv() is not enough: TCP may deliver the payload in pieces,
        and the caller asking for N bytes means N bytes. The deadline is over
        the whole call, not per recv, so a trickling peer cannot extend it.
        """
        if not self.is_open:
            raise TcpTransportError("transport is not open")

        deadline = time.monotonic() + self.timeout
        buffer = bytearray()
        while len(buffer) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._sock.settimeout(remaining)
            try:
                chunk = self._sock.recv(length - len(buffer))
            except socket.timeout:
                break
            except OSError as exc:
                raise TcpTransportError(
                    "read failed from {}:{}: {}".format(self.host, self.port, exc))
            if not chunk:
                break  # peer closed
            buffer += chunk
        return bytes(buffer)

    def __enter__(self) -> "TcpTransport":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
