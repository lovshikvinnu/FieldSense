"""JXBS-3001-TR 7-in-1 soil probe adapter — Modbus RTU to structured telemetry.

    JXBS probe ──RS485──> MAX485 / FT232 ──> SensorTransport ──> SoilData
                                                                     │
                                                          to_raw_reading()
                                                                     ▼
                                                          RawSensorReading (frozen)

The probe answers Modbus RTU function 0x03 one holding register at a time.
Register addresses and scale factors below are the empirically verified map
from docs/HARDWARE.md section 4 — not datasheet guesses.

UNIT BOUNDARY, IMPORTANT
------------------------
The probe reports electrical conductivity in microsiemens per centimetre.
The FieldSense validation contract expects decisiemens per metre, bounded
0.0 to 10.0 (`fieldsense/intelligence/validation/config.py`). A normal soil
reading of 210 uS/cm forwarded unconverted becomes 210, far outside that
bound, and EVERY sample would be rejected. This adapter divides by 1000.
Converting units at the boundary is the reason this layer exists.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .models import RawSensorReading
from .transport.base import SensorTransport

# Modbus RTU
MODBUS_READ_HOLDING = 0x03
DEFAULT_SLAVE_ID = 0x01
RESPONSE_LENGTH = 7  # slave, function, byte count, data hi, data lo, crc lo, crc hi

# Verified register map: parameter -> (address, divisor, unit, signed)
JXBS_REGISTERS: Dict[str, Tuple[int, float, str, bool]] = {
    "ph":          (0x0006, 100.0, "pH",     False),
    "moisture":    (0x0012,  10.0, "%",      False),
    "temperature": (0x0013,  10.0, "degC",   True),   # can read below zero
    "ec":          (0x0015,   1.0, "uS/cm",  False),
    "nitrogen":    (0x001E,   1.0, "mg/kg",  False),
    "phosphorus":  (0x001F,   1.0, "mg/kg",  False),
    "potassium":   (0x0020,   1.0, "mg/kg",  False),
}

# 1 dS/m == 1000 uS/cm
US_CM_PER_DS_M = 1000.0


class ModbusError(Exception):
    """Raised when a Modbus exchange is structurally invalid."""


# --------------------------------------------------------------------- framing


def modbus_crc16(payload: bytes) -> int:
    """Compute the Modbus CRC-16 (polynomial 0xA001) of a frame body."""
    crc = 0xFFFF
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def build_read_request(register: int, slave_id: int = DEFAULT_SLAVE_ID, count: int = 1) -> bytes:
    """Build an 8-byte Modbus RTU read-holding-registers request.

    Layout: slave, function, address hi/lo, count hi/lo, crc lo, crc hi.
    """
    body = bytes([
        slave_id, MODBUS_READ_HOLDING,
        (register >> 8) & 0xFF, register & 0xFF,
        (count >> 8) & 0xFF, count & 0xFF,
    ])
    crc = modbus_crc16(body)
    return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def parse_read_response(frame: bytes, slave_id: int = DEFAULT_SLAVE_ID, signed: bool = False) -> int:
    """Validate a single-register response frame and return its raw value.

    Raises:
        ModbusError: Short frame, wrong slave, exception response, or bad CRC.
    """
    if len(frame) < RESPONSE_LENGTH:
        raise ModbusError("short response: {} bytes, expected {}".format(len(frame), RESPONSE_LENGTH))
    frame = frame[:RESPONSE_LENGTH]

    if frame[0] != slave_id:
        raise ModbusError("wrong slave id: got 0x{:02X}, expected 0x{:02X}".format(frame[0], slave_id))
    if frame[1] & 0x80:
        raise ModbusError("modbus exception response, code 0x{:02X}".format(frame[2]))
    if frame[1] != MODBUS_READ_HOLDING:
        raise ModbusError("unexpected function code 0x{:02X}".format(frame[1]))
    if frame[2] != 2:
        raise ModbusError("unexpected byte count {}".format(frame[2]))

    received = frame[5] | (frame[6] << 8)
    expected = modbus_crc16(frame[:5])
    if received != expected:
        raise ModbusError("CRC mismatch: got 0x{:04X}, expected 0x{:04X}".format(received, expected))

    raw = (frame[3] << 8) | frame[4]
    if signed and raw >= 0x8000:
        raw -= 0x10000
    return raw


def scale_register(parameter: str, raw: int) -> float:
    """Apply the verified scale factor for one parameter."""
    _address, divisor, _unit, _signed = JXBS_REGISTERS[parameter]
    return raw / divisor


def us_cm_to_ds_m(microsiemens_per_cm: float) -> float:
    """Convert electrical conductivity from uS/cm to dS/m."""
    return microsiemens_per_cm / US_CM_PER_DS_M


# --------------------------------------------------------------------- model


@dataclass(frozen=True)
class SoilData:
    """Structured soil telemetry in the units the software contract expects.

    `ec` is dS/m, already converted from the probe's uS/cm.
    """
    ph: Optional[float] = None
    moisture: Optional[float] = None          # %
    temperature: Optional[float] = None       # degC
    ec: Optional[float] = None                # dS/m (converted)
    nitrogen: Optional[float] = None          # mg/kg
    phosphorus: Optional[float] = None        # mg/kg
    potassium: Optional[float] = None         # mg/kg
    ec_raw_us_cm: Optional[float] = None      # as reported by the probe
    raw_registers: Dict[str, int] = field(default_factory=dict)
    read_errors: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """True when all seven parameters were read successfully."""
        return not self.read_errors and all(
            getattr(self, p) is not None for p in JXBS_REGISTERS
        )

    @property
    def parameters_read(self) -> int:
        """How many of the seven parameters returned a value."""
        return sum(1 for p in JXBS_REGISTERS if getattr(self, p) is not None)

    def to_raw_reading(self) -> RawSensorReading:
        """Convert to the frozen RawSensorReading contract."""
        return RawSensorReading(
            nitrogen=self.nitrogen or 0.0,
            phosphorus=self.phosphorus or 0.0,
            potassium=self.potassium or 0.0,
            ph=self.ph or 0.0,
            ec=self.ec or 0.0,
            moisture=self.moisture or 0.0,
            temperature=self.temperature or 0.0,
            metadata={
                "ec_raw_us_cm": self.ec_raw_us_cm,
                "raw_registers": dict(self.raw_registers),
                "read_errors": list(self.read_errors),
                "parameters_read": self.parameters_read,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SoilData to a dictionary."""
        return {
            "ph": self.ph,
            "moisture": self.moisture,
            "temperature": self.temperature,
            "ec": self.ec,
            "nitrogen": self.nitrogen,
            "phosphorus": self.phosphorus,
            "potassium": self.potassium,
            "ec_raw_us_cm": self.ec_raw_us_cm,
            "raw_registers": dict(self.raw_registers),
            "read_errors": list(self.read_errors),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SoilData":
        """Deserialize a dictionary into SoilData."""
        return cls(
            ph=data.get("ph"),
            moisture=data.get("moisture"),
            temperature=data.get("temperature"),
            ec=data.get("ec"),
            nitrogen=data.get("nitrogen"),
            phosphorus=data.get("phosphorus"),
            potassium=data.get("potassium"),
            ec_raw_us_cm=data.get("ec_raw_us_cm"),
            raw_registers=dict(data.get("raw_registers", {})),
            read_errors=list(data.get("read_errors", [])),
        )


# --------------------------------------------------------------------- adapter


class JXBSSoilAdapter:
    """Reads the JXBS 7-in-1 probe over any SensorTransport.

    Transport-agnostic by design: the same adapter drives a bench FT232
    USB-RS485 dongle, a MAX485 on the UNO Q, or `MockHardwareTransport`.
    """

    def __init__(
        self,
        transport: SensorTransport,
        slave_id: int = DEFAULT_SLAVE_ID,
        settle_seconds: float = 0.05,
    ) -> None:
        """Build the adapter around an open-able transport.

        Args:
            transport: Any SensorTransport implementation.
            slave_id: Modbus slave address. JXBS default is 0x01.
            settle_seconds: Pause between request and response read, giving the
                RS485 bus time to turn around.
        """
        self.transport = transport
        self.slave_id = slave_id
        self.settle_seconds = settle_seconds

    def initialize(self) -> None:
        """Open the underlying transport."""
        if not self.transport.is_open:
            self.transport.open()

    def shutdown(self) -> None:
        """Close the underlying transport."""
        if self.transport.is_open:
            self.transport.close()

    def read_register(self, parameter: str) -> int:
        """Read one parameter's raw register value.

        Raises:
            ModbusError: On any framing, CRC, or addressing failure.
        """
        if parameter not in JXBS_REGISTERS:
            raise ModbusError("unknown parameter: {}".format(parameter))
        address, _divisor, _unit, signed = JXBS_REGISTERS[parameter]

        self.transport.write(build_read_request(address, self.slave_id))
        if self.settle_seconds:
            import time

            time.sleep(self.settle_seconds)
        frame = self.transport.read(RESPONSE_LENGTH)
        return parse_read_response(frame, self.slave_id, signed=signed)

    def read(self) -> SoilData:
        """Read all seven parameters and return converted telemetry.

        A failure on one register is recorded and the remaining registers are
        still attempted, so a single bad read degrades the sample instead of
        losing the whole measurement. Never raises.
        """
        values: Dict[str, Optional[float]] = {}
        raw_registers: Dict[str, int] = {}
        errors: List[str] = []

        for parameter in JXBS_REGISTERS:
            try:
                raw = self.read_register(parameter)
                raw_registers[parameter] = raw
                values[parameter] = scale_register(parameter, raw)
            except Exception as exc:
                values[parameter] = None
                errors.append("{}: {}".format(parameter, exc))

        ec_us_cm = values.get("ec")
        return SoilData(
            ph=values.get("ph"),
            moisture=values.get("moisture"),
            temperature=values.get("temperature"),
            # unit conversion at the boundary — see module docstring
            ec=us_cm_to_ds_m(ec_us_cm) if ec_us_cm is not None else None,
            nitrogen=values.get("nitrogen"),
            phosphorus=values.get("phosphorus"),
            potassium=values.get("potassium"),
            ec_raw_us_cm=ec_us_cm,
            raw_registers=raw_registers,
            read_errors=errors,
        )

    @classmethod
    def from_serial(
        cls,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        timeout: float = 1.0,
        slave_id: int = DEFAULT_SLAVE_ID,
    ) -> "JXBSSoilAdapter":
        """Build an adapter over a USB-RS485 or MAX485 serial device."""
        from .transport.serial_port import SerialTransport

        return cls(
            SerialTransport(port=port, baudrate=baudrate, timeout=timeout),
            slave_id=slave_id,
        )

    def __enter__(self) -> "JXBSSoilAdapter":
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()
