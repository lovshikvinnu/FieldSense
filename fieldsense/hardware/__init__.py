"""Hardware integration boundary package.

Two layers live here:

    Device access   SensorTransport implementations, GPS and sensor adapters
    Contract        HardwareSampleAdapter, the single point where physical
                    telemetry becomes a canonical FieldSample

Three physical soil wirings are supported, all producing the same FieldSample:

    StdlibModbusTransport   JXBS -> MAX485 -> USB dongle -> Linux, stdlib only
    DirectUSBModbusTransport  the same wiring via pyserial (optional extra)
    BridgeSoilTransport     JXBS -> MAX485 -> STM32 -> RouterBridge -> Linux

Both sides of that boundary are frozen. This package adapts between them and
never reimplements either. See docs/INTEGRATION_RUNBOOK.md.
"""

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

# v1 adapter & contract layer
from .gps_adapter import (
    GPSData,
    GPSParseError,
    NMEAGPSAdapter,
    ddmm_to_decimal,
    nmea_checksum_valid,
    parse_nmea_sentence,
    parse_nmea_stream,
)
from .soil_adapter import (
    JXBS_REGISTERS,
    JXBSSoilAdapter,
    ModbusError,
    SoilData,
    build_read_request,
    modbus_crc16,
    parse_read_response,
    us_cm_to_ds_m,
)
from .hardware_sample_adapter import (
    HardwareSampleAdapter,
    QualityPolicy,
    derive_measurement_quality,
)
from .bridge_soil import (
    BRIDGE_SOIL_METHOD,
    BridgeSoilAdapter,
    BridgeSoilTransport,
    normalise_bridge_payload,
    soil_data_to_canonical_json,
)
from .serial_modbus import StdlibModbusTransport

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
    # GPS acquisition adapter
    "GPSData",
    "GPSParseError",
    "NMEAGPSAdapter",
    "parse_nmea_sentence",
    "parse_nmea_stream",
    "ddmm_to_decimal",
    "nmea_checksum_valid",
    # Soil acquisition adapter
    "SoilData",
    "JXBSSoilAdapter",
    "JXBS_REGISTERS",
    "ModbusError",
    "modbus_crc16",
    "build_read_request",
    "parse_read_response",
    "us_cm_to_ds_m",
    # Contract adapter
    "HardwareSampleAdapter",
    "QualityPolicy",
    "derive_measurement_quality",
    # STM32 RouterBridge soil path
    "BridgeSoilAdapter",
    "BridgeSoilTransport",
    "BRIDGE_SOIL_METHOD",
    "normalise_bridge_payload",
    "soil_data_to_canonical_json",
    # Zero-dependency USB-RS485 path
    "StdlibModbusTransport",
]
