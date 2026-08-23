"""POSIX serial transport implementing the frozen SensorTransport contract.

Uses the standard library `termios` interface so `dependencies = []` holds.
If `pyserial` happens to be installed it is used instead, which helps on
platforms where `termios` is unavailable (Windows). Neither is imported at
module scope in a way that can fail on an unsupported platform.

This is a TRANSPORT only. It moves bytes. Framing, CRC, and register decoding
belong to the protocol adapters that sit above it.
"""

import os
import select
from typing import Optional

from .base import SensorTransport

try:  # POSIX only
    import termios

    _HAVE_TERMIOS = True
except ImportError:  # pragma: no cover - platform dependent
    termios = None  # type: ignore
    _HAVE_TERMIOS = False


class SerialPortError(Exception):
    """Raised when the serial device cannot be opened or configured."""


def _baud_constant(baudrate: int) -> int:
    """Map a numeric baud rate to its termios constant."""
    name = "B{}".format(baudrate)
    if not _HAVE_TERMIOS or not hasattr(termios, name):
        raise SerialPortError("unsupported baud rate: {}".format(baudrate))
    return getattr(termios, name)


class SerialTransport(SensorTransport):
    """Raw 8-N-1 serial transport over a POSIX tty device."""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        timeout: float = 1.0,
    ) -> None:
        """Configure the transport. No device is touched until open().

        Args:
            port: Device node, e.g. '/dev/ttyUSB0' or '/dev/ttyS0'.
            baudrate: Line speed. JXBS and NEO-M8N both default to 9600.
            timeout: Seconds to wait for bytes in read().
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._fd: Optional[int] = None
        self._pyserial = None

    # ------------------------------------------------------------- lifecycle

    def open(self) -> None:
        """Open and configure the device for raw 8-N-1 I/O.

        Raises:
            SerialPortError: Device missing, no permission, or unconfigurable.
        """
        if self.is_open:
            return

        if not _HAVE_TERMIOS:
            self._open_pyserial()
            return

        try:
            fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except FileNotFoundError:
            raise SerialPortError(
                "serial device not found: {}\n"
                "List available devices with:  ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyS*".format(self.port)
            )
        except PermissionError:
            raise SerialPortError(
                "permission denied opening {}. Add yourself to the 'dialout' group:\n"
                "  sudo usermod -aG dialout $USER   (then log out and back in)".format(self.port)
            )
        except OSError as exc:
            raise SerialPortError("could not open {}: {}".format(self.port, exc))

        try:
            speed = _baud_constant(self.baudrate)
            attrs = termios.tcgetattr(fd)
            iflag, oflag, cflag, lflag, _ispeed, _ospeed, cc = attrs

            # Raw mode: no canonical processing, echo, or translation.
            iflag = 0
            oflag = 0
            lflag = 0
            # 8 data bits, receiver on, ignore modem control lines.
            # PARENB absent -> no parity. CSTOPB absent -> one stop bit. 8-N-1.
            cflag = termios.CS8 | termios.CREAD | termios.CLOCAL

            cc = list(cc)
            cc[termios.VMIN] = 0
            cc[termios.VTIME] = 0

            termios.tcsetattr(fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, speed, speed, cc])
            termios.tcflush(fd, termios.TCIOFLUSH)
        except (termios.error, OSError) as exc:
            os.close(fd)
            raise SerialPortError("could not configure {}: {}".format(self.port, exc))

        self._fd = fd

    def _open_pyserial(self) -> None:  # pragma: no cover - non-POSIX fallback
        """Fall back to pyserial where termios is unavailable."""
        try:
            import serial  # type: ignore
        except ImportError:
            raise SerialPortError(
                "no serial backend available. This platform lacks termios; install pyserial:\n"
                "  python3 -m pip install pyserial"
            )
        try:
            self._pyserial = serial.Serial(
                port=self.port, baudrate=self.baudrate, timeout=self.timeout
            )
        except Exception as exc:
            raise SerialPortError("could not open {}: {}".format(self.port, exc))

    def close(self) -> None:
        """Close the device. Safe to call when already closed."""
        if self._pyserial is not None:  # pragma: no cover
            try:
                self._pyserial.close()
            finally:
                self._pyserial = None
            return
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    @property
    def is_open(self) -> bool:
        """Return True when the device is open."""
        return self._fd is not None or self._pyserial is not None

    # ------------------------------------------------------------- transfer

    def write(self, payload: bytes) -> None:
        """Write bytes to the device.

        Raises:
            SerialPortError: Transport not open, or the write failed.
        """
        if not self.is_open:
            raise SerialPortError("transport is not open")
        if self._pyserial is not None:  # pragma: no cover
            self._pyserial.write(payload)
            self._pyserial.flush()
            return
        try:
            written = 0
            while written < len(payload):
                written += os.write(self._fd, payload[written:])
            termios.tcdrain(self._fd)
        except OSError as exc:
            raise SerialPortError("write failed on {}: {}".format(self.port, exc))

    def read(self, length: int = 256) -> bytes:
        """Read up to `length` bytes, waiting at most `timeout` seconds in total.

        Returns whatever arrived, which may be fewer bytes than requested and
        may be empty. Callers are responsible for framing.
        """
        if not self.is_open:
            raise SerialPortError("transport is not open")
        if self._pyserial is not None:  # pragma: no cover
            return self._pyserial.read(length)

        import time

        deadline = time.monotonic() + self.timeout
        buffer = bytearray()
        while len(buffer) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _, _ = select.select([self._fd], [], [], remaining)
            if not ready:
                break
            try:
                chunk = os.read(self._fd, length - len(buffer))
            except BlockingIOError:  # pragma: no cover
                continue
            except OSError as exc:
                raise SerialPortError("read failed on {}: {}".format(self.port, exc))
            if not chunk:
                break
            buffer += chunk
        return bytes(buffer)

    def read_line(self, terminator: bytes = b"\n", max_bytes: int = 512) -> bytes:
        """Read one terminated line. Used by the NMEA GPS adapter.

        Returns the line without its terminator, or b'' on timeout.
        """
        import time

        deadline = time.monotonic() + self.timeout
        buffer = bytearray()
        while len(buffer) < max_bytes:
            if time.monotonic() > deadline:
                break
            chunk = self.read(1)
            if not chunk:
                continue
            if chunk == terminator:
                break
            buffer += chunk
        return bytes(buffer).rstrip(b"\r")

    def __enter__(self) -> "SerialTransport":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
