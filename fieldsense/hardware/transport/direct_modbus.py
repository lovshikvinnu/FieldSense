"""Direct USB-RS485 Modbus RTU Transport implementation for JXBS 7-in-1 sensor."""

import json
import time
from typing import Optional, Dict, Any

try:
    import serial
except ImportError:
    serial = None

from fieldsense.hardware.models import HardwareError, HardwareErrorCode
from .base import SensorTransport

# 1 dS/m == 1000 uS/cm. Single source of truth lives in soil_adapter; repeated
# here as a literal because that module imports this package's base.
US_CM_PER_DS_M = 1000.0


def modbus_crc(data: bytes) -> int:
    """Calculate 16-bit Modbus RTU CRC."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc


def make_modbus_request(register: int, slave_id: int = 0x01) -> bytes:
    """Construct 8-byte Modbus RTU request frame for holding register."""
    frame = bytes([
        slave_id & 0xFF,
        0x03,  # Function: Read Holding Registers
        (register >> 8) & 0xFF,
        register & 0xFF,
        0x00,
        0x01,  # Quantity: 1 register
    ])
    crc = modbus_crc(frame)
    return frame + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def validate_modbus_crc(response: bytes) -> bool:
    """Validate 16-bit Modbus RTU response CRC."""
    if len(response) != 7:
        return False
    received_crc = response[-2] | (response[-1] << 8)
    calculated_crc = modbus_crc(response[:-2])
    return received_crc == calculated_crc


class DirectUSBModbusTransport(SensorTransport):
    """Physical USB-RS485 Modbus RTU transport for JXBS 7-in-1 soil sensor.

    Queries all 7 holding registers, validates CRC-16, decodes parameters,
    and returns UTF-8 encoded JSON bytes matching RawSensorReading expectations.
    """

    # JXBS 7-in-1 Register Map & Divisor Scalings
    REGISTER_MAP = [
        ("ph", 0x0006, 100.0),
        ("moisture", 0x0012, 10.0),
        ("temperature", 0x0013, 10.0),
        ("ec", 0x0015, 1.0),
        ("nitrogen", 0x001E, 1.0),
        ("phosphorus", 0x001F, 1.0),
        ("potassium", 0x0020, 1.0),
    ]

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        slave_id: int = 0x01,
        timeout: float = 1.0,
        inter_query_delay: float = 0.05,
    ) -> None:
        """Initialize Modbus transport.

        Args:
            port: Serial port device path (default '/dev/ttyUSB0').
            baudrate: Baud rate (default 9600).
            slave_id: Modbus Slave ID (default 0x01).
            timeout: Read timeout in seconds (default 1.0).
            inter_query_delay: Pause between register requests in seconds (default 0.05).
        """
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.timeout = timeout
        self.inter_query_delay = inter_query_delay
        self._ser: Optional[Any] = None

    def open(self) -> None:
        """Open physical serial port connection."""
        if serial is None:
            raise HardwareError(
                HardwareErrorCode.TRANSPORT_ERROR,
                "pyserial package is not installed.",
            )

        if self._ser is not None and self._ser.is_open:
            return

        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
        except (serial.SerialException, OSError) as err:
            raise HardwareError(
                HardwareErrorCode.TRANSPORT_ERROR,
                f"Failed to open serial port '{self.port}': {err}",
            ) from err

    def read(self, length: int = 256) -> bytes:
        """Query all 7 JXBS registers, decode values, and return UTF-8 JSON bytes."""
        if not self.is_open:
            raise HardwareError(
                HardwareErrorCode.DEVICE_NOT_INITIALIZED,
                "USB-RS485 transport is not open.",
            )

        sensor_data: Dict[str, float] = {}


        for param_name, reg_addr, scale in self.REGISTER_MAP:
            request_frame = make_modbus_request(reg_addr, slave_id=self.slave_id)

            try:
                self._ser.reset_input_buffer()
                self._ser.write(request_frame)
                self._ser.flush()

                response = self._ser.read(7)
            except (serial.SerialException, OSError) as err:
                raise HardwareError(
                    HardwareErrorCode.TRANSPORT_ERROR,
                    f"Serial communication error on '{self.port}': {err}",
                ) from err

            if len(response) == 0:
                raise HardwareError(
                    HardwareErrorCode.TIMEOUT,
                    f"Modbus response timeout reading register 0x{reg_addr:04X} ({param_name}).",
                )

            if len(response) != 7:
                raise HardwareError(
                    HardwareErrorCode.INVALID_SENSOR_FRAME,
                    f"Invalid Modbus response length ({len(response)} bytes, expected 7) for register 0x{reg_addr:04X}.",
                )

            if not validate_modbus_crc(response):
                raise HardwareError(
                    HardwareErrorCode.MALFORMED_RESPONSE,
                    f"Modbus CRC check failed for register 0x{reg_addr:04X} ({param_name}). Response hex: {response.hex()}",
                )

            raw_val = (response[3] << 8) | response[4]
            if raw_val >= 0x8000:
                raw_val -= 0x10000

            decoded_val = raw_val / scale

            # EC unit boundary. The probe always reports microsiemens per
            # centimetre; the validation contract always expects decisiemens
            # per metre. The conversion is therefore UNCONDITIONAL.
            #
            # This used to be gated on `decoded_val >= 20.0`, which was wrong
            # in both directions: a genuinely low reading of 15 uS/cm passed
            # through as 15 dS/m and was rejected by the 0.0-10.0 bound, while
            # a saline 25000 uS/cm became 25 dS/m and was also rejected. Both
            # failures looked like sensor faults rather than a unit bug.
            if param_name == "ec":
                sensor_data["ec_raw_us_cm"] = round(decoded_val, 2)
                decoded_val = decoded_val / US_CM_PER_DS_M

            sensor_data[param_name] = round(decoded_val, 3)

            if self.inter_query_delay > 0:
                time.sleep(self.inter_query_delay)

        return json.dumps(sensor_data).encode("utf-8")

    def write(self, payload: bytes) -> None:
        """Write raw bytes to serial port."""
        if not self.is_open:
            raise HardwareError(
                HardwareErrorCode.DEVICE_NOT_INITIALIZED,
                "USB-RS485 transport is not open.",
            )
        try:
            self._ser.write(payload)
            self._ser.flush()
        except (serial.SerialException, OSError) as err:
            raise HardwareError(
                HardwareErrorCode.TRANSPORT_ERROR,
                f"Failed to write bytes to serial port '{self.port}': {err}",
            ) from err

    def close(self) -> None:
        """Close physical serial connection."""
        if self._ser is not None and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    @property
    def is_open(self) -> bool:
        """Return boolean connection status."""
        return self._ser is not None and self._ser.is_open
