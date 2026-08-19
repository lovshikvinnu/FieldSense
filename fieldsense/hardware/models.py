"""Hardware boundary models, error codes, and readiness state."""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, Optional


class HardwareReadinessState(str, Enum):
    """System hardware integration readiness state."""
    SIMULATION_READY = "SIMULATION_READY"
    HARDWARE_PENDING = "HARDWARE_PENDING"
    HARDWARE_READY = "HARDWARE_READY"


class HardwareErrorCode(str, Enum):
    """Structured hardware error codes."""
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    TIMEOUT = "TIMEOUT"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    DEVICE_NOT_INITIALIZED = "DEVICE_NOT_INITIALIZED"
    DEVICE_UNAVAILABLE = "DEVICE_UNAVAILABLE"
    GPS_NO_FIX = "GPS_NO_FIX"
    INVALID_SENSOR_FRAME = "INVALID_SENSOR_FRAME"
    HARDWARE_SPEC_REQUIRED = "HARDWARE_SPEC_REQUIRED"


class HardwareError(Exception):
    """Structured Exception for hardware/transport failures."""

    def __init__(self, error_code: HardwareErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(f"[{error_code.value}] {message}")
        self.error_code = error_code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class RawSensorReading:
    """Raw unvalidated physical measurement reported directly by sensor adapter."""
    nitrogen: float
    phosphorus: float
    potassium: float
    ph: float
    ec: float
    moisture: float
    temperature: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize reading to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RawSensorReading":
        """Deserialize dictionary into a RawSensorReading."""
        return cls(**data)


@dataclass(frozen=True)
class GPSPosition:
    """Canonical GPS position fix model."""
    latitude: float
    longitude: float
    fix_valid: bool = True
    timestamp: Optional[str] = None
    quality: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize position fix to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GPSPosition":
        """Deserialize dictionary into a GPSPosition."""
        return cls(**data)
