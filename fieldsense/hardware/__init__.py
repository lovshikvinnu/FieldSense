"""Hardware integration boundary package."""

from .models import (
    RawSensorReading,
    GPSPosition,
    HardwareReadinessState,
    HardwareErrorCode,
    HardwareError,
)
from .config import HardwareConfig, HARDWARE_SPEC_REQUIRED
from .transport import SensorTransport, MockHardwareTransport
from .gps import GPSAdapter, VirtualGPSAdapter, HardwareGPSAdapter
from .sensor_adapter import HardwareSensorAdapter
from .factory import DataSourceConfig, SensorAdapterFactory

__all__ = [
    # Models & Exceptions
    "RawSensorReading",
    "GPSPosition",
    "HardwareReadinessState",
    "HardwareErrorCode",
    "HardwareError",
    # Config
    "HardwareConfig",
    "HARDWARE_SPEC_REQUIRED",
    # Transport
    "SensorTransport",
    "MockHardwareTransport",
    # GPS
    "GPSAdapter",
    "VirtualGPSAdapter",
    "HardwareGPSAdapter",
    # Adapter
    "HardwareSensorAdapter",
    # Factory
    "DataSourceConfig",
    "SensorAdapterFactory",
]
