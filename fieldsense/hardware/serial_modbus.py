"""Zero-dependency Modbus transport for the USB-RS485 soil probe path.

`pyproject.toml` declares `dependencies = []`, and every layer of FieldSense
honours that except one: `DirectUSBModbusTransport` imports `pyserial`, and it
was the only transport the factory could build for `source="HARDWARE"`. On a
freshly flashed UNO Q image that import resolves to None and the acquisition
path dies with "pyserial package is not installed" — the zero-dependency claim
held everywhere except the place it mattered most.

This transport closes that hole. It composes the two pieces that were already
stdlib-only and already tested, and were simply never wired to the factory:

    SerialTransport   raw 8-N-1 tty via termios       (fieldsense/hardware/transport)
    JXBSSoilAdapter   Modbus framing, CRC, registers  (fieldsense/hardware)

It also inherits `JXBSSoilAdapter`'s failure policy, which differs from
`DirectUSBModbusTransport` in a way that matters in a field: a single register
that times out degrades the sample and the other six are still read, instead of
aborting the whole measurement. A probe pushed into stony ground routinely
drops one register.
"""

from typing import Any, Optional

from .bridge_soil import soil_data_to_canonical_json
from .models import HardwareError, HardwareErrorCode
from .soil_adapter import DEFAULT_SLAVE_ID, JXBSSoilAdapter, SoilData
from .transport.base import SensorTransport

DEFAULT_SOIL_PORT = "/dev/ttyUSB0"
DEFAULT_SOIL_BAUD = 9600  # JXBS-3001 factory default, 8N1


class StdlibModbusTransport(SensorTransport):
    """USB-RS485 Modbus RTU transport built entirely on the standard library.

    Drop-in replacement for `DirectUSBModbusTransport` with the same JSON byte
    output contract, minus the third-party dependency and minus the
    all-or-nothing read.
    """

    def __init__(
        self,
        port: str = DEFAULT_SOIL_PORT,
        baudrate: int = DEFAULT_SOIL_BAUD,
        slave_id: int = DEFAULT_SLAVE_ID,
        timeout: float = 1.0,
        settle_seconds: float = 0.05,
        adapter: Optional[JXBSSoilAdapter] = None,
    ) -> None:
        """Configure the transport. No device is touched until open().

        Args:
            port: Serial device node for the RS485 dongle.
            baudrate: Line speed. JXBS default is 9600.
            slave_id: Modbus slave address. JXBS default is 0x01.
            timeout: Per-read timeout in seconds.
            settle_seconds: RS485 bus turnaround pause between write and read.
            adapter: Optional pre-built JXBSSoilAdapter, mainly for tests.
        """
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.timeout = timeout
        self.settle_seconds = settle_seconds
        self._adapter = adapter
        self._owns_adapter = adapter is None

    # ------------------------------------------------------------- lifecycle

    def _build_adapter(self) -> JXBSSoilAdapter:
        """Construct the probe adapter over a stdlib serial transport."""
        # Imported here, not at module scope: serial_port touches platform
        # specific termios and must not break an import on a machine without it.
        from .transport.serial_port import SerialTransport

        return JXBSSoilAdapter(
            SerialTransport(port=self.port, baudrate=self.baudrate, timeout=self.timeout),
            slave_id=self.slave_id,
            settle_seconds=self.settle_seconds,
        )

    def open(self) -> None:
        """Open the serial device.

        Raises:
            HardwareError: Device missing, no permission, or unconfigurable.
                The underlying SerialPortError message carries the remedy.
        """
        if self._adapter is None:
            self._adapter = self._build_adapter()
        try:
            self._adapter.initialize()
        except Exception as exc:
            raise HardwareError(
                HardwareErrorCode.TRANSPORT_ERROR,
                "Could not open soil probe on {}: {}".format(self.port, exc),
            ) from exc

    def close(self) -> None:
        """Close the serial device. Safe to call when already closed."""
        if self._adapter is None:
            return
        try:
            self._adapter.shutdown()
        except Exception:
            pass
        if self._owns_adapter:
            self._adapter = None

    @property
    def is_open(self) -> bool:
        """Return True when the underlying serial device is open."""
        return self._adapter is not None and self._adapter.transport.is_open

    # ------------------------------------------------------------- transfer

    def write(self, payload: bytes) -> None:
        """Not supported. Modbus framing is owned by JXBSSoilAdapter."""
        raise HardwareError(
            HardwareErrorCode.TRANSPORT_ERROR,
            "StdlibModbusTransport is a protocol transport; it frames its own requests.",
        )

    def read(self, length: int = 256) -> bytes:
        """Read all seven registers and return canonical JSON bytes.

        Never raises on a partial read. Failed registers are reported as 0.0
        with the detail in `_meta.read_errors`, and ValidationEngine decides
        whether the resulting sample is usable.
        """
        if not self.is_open:
            raise HardwareError(
                HardwareErrorCode.DEVICE_NOT_INITIALIZED,
                "Stdlib Modbus transport is not open.",
            )
        soil: SoilData = self._adapter.read()
        return soil_data_to_canonical_json(soil)

    def read_soil(self) -> SoilData:
        """Return the structured reading, for callers that want SoilData."""
        if not self.is_open:
            raise HardwareError(
                HardwareErrorCode.DEVICE_NOT_INITIALIZED,
                "Stdlib Modbus transport is not open.",
            )
        return self._adapter.read()

    def __enter__(self) -> "StdlibModbusTransport":
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
