"""Data source configuration and SensorAdapterFactory.

The factory is the single place that decides where measurements come from. Four
sources, covering every wiring the hardware log records:

    VIRTUAL        deterministic virtual sensor, no hardware              (default)
    HARDWARE       JXBS via USB-RS485 on the Linux side, GPS via STM32 Bridge
                   Standard library only — no pyserial, no compiler.
    BRIDGE         JXBS *and* GPS both via the STM32 RouterBridge. This is the
                   wiring the MAX485 bench sketch verified, where the probe is
                   on the MCU's Serial1 and Linux never sees a tty at all.
    USB_PYSERIAL   the original DirectUSBModbusTransport path. Retained because
                   it is the one exercised on the bench dongle, but it needs
                   pyserial, which `dependencies = []` does not install.

Configuration is resolvable from the environment so an unattended boot service
can select a source without editing code:

    FIELDSENSE_SOURCE=HARDWARE
    FIELDSENSE_SENSOR_PORT=/dev/ttyUSB0
    FIELDSENSE_SENSOR_BAUD=9600
    FIELDSENSE_GPS_METHOD=get_gps_data
    FIELDSENSE_SOIL_METHOD=get_soil_data
    FIELDSENSE_REQUIRE_GPS_FIX=0
"""

import os
from dataclasses import dataclass
from typing import Optional

from fieldsense.domain.contracts.sensor import SensorAdapter
from fieldsense.input.virtual_sensor import VirtualSensorAdapter
from fieldsense.hardware.sensor_adapter import HardwareSensorAdapter
from fieldsense.hardware.transport import DirectUSBModbusTransport
from fieldsense.hardware.gps import BridgeGPSAdapter

VALID_SOURCES = ("VIRTUAL", "HARDWARE", "BRIDGE", "USB_PYSERIAL")


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment flag, tolerating the usual spellings."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class DataSourceConfig:
    """Active data acquisition source configuration."""
    source: str = "VIRTUAL"                       # see VALID_SOURCES
    sensor_port: str = "/dev/ttyUSB0"
    sensor_baudrate: int = 9600                   # JXBS factory default, 8N1
    sensor_slave_id: int = 0x01
    bridge_endpoint: str = "get_gps_data"         # GPS Bridge method
    soil_endpoint: str = "get_soil_data"          # soil Bridge method
    require_gps_fix: bool = False
    gps_gateway_host: Optional[str] = None
    gps_gateway_port: Optional[int] = None
    """Whether a missing GPS fix aborts acquisition.

    False by default for hardware sources. A receiver needs minutes for its
    first fix after a cold boot; aborting until then means an unattended unit
    records nothing. A no-fix sample instead carries a low measurement_quality
    and the ValidationEngine decides its fate.
    """

    @classmethod
    def from_env(cls, **overrides: object) -> "DataSourceConfig":
        """Build a configuration from environment variables.

        Explicit keyword overrides win over the environment, which wins over
        the dataclass defaults. Lets a systemd unit steer acquisition with
        `Environment=` lines instead of a code change.
        """
        def _resolve(field_name: str, env_name: str, default: Any, converter: Optional[Any] = None) -> Any:
            if field_name in overrides and overrides[field_name] is not None:
                raw_val = overrides[field_name]
            elif env_name in os.environ:
                raw_val = os.environ[env_name]
            else:
                raw_val = default

            if converter is not None and raw_val is not None:
                return converter(raw_val)
            return raw_val

        if "require_gps_fix" in overrides and overrides["require_gps_fix"] is not None:
            raw_fix = overrides["require_gps_fix"]
            if isinstance(raw_fix, str):
                fix_val = raw_fix.strip().lower() in ("1", "true", "yes", "on")
            else:
                fix_val = bool(raw_fix)
        else:
            fix_val = _env_flag("FIELDSENSE_REQUIRE_GPS_FIX", cls.require_gps_fix)

        if "gps_gateway_port" in overrides and overrides["gps_gateway_port"] is not None:
            port_val = int(overrides["gps_gateway_port"])  # type: ignore[arg-type]
        elif "FIELDSENSE_GPS_GATEWAY_PORT" in os.environ and os.environ["FIELDSENSE_GPS_GATEWAY_PORT"].strip():
            port_val = int(os.environ["FIELDSENSE_GPS_GATEWAY_PORT"])
        else:
            port_val = cls.gps_gateway_port

        cfg = cls(
            source=_resolve("source", "FIELDSENSE_SOURCE", cls.source, lambda s: str(s).upper()),
            sensor_port=_resolve("sensor_port", "FIELDSENSE_SENSOR_PORT", cls.sensor_port, str),
            sensor_baudrate=_resolve("sensor_baudrate", "FIELDSENSE_SENSOR_BAUD", cls.sensor_baudrate, int),
            sensor_slave_id=_resolve("sensor_slave_id", "FIELDSENSE_SENSOR_SLAVE", cls.sensor_slave_id, int),
            bridge_endpoint=_resolve("bridge_endpoint", "FIELDSENSE_GPS_METHOD", cls.bridge_endpoint, str),
            soil_endpoint=_resolve("soil_endpoint", "FIELDSENSE_SOIL_METHOD", cls.soil_endpoint, str),
            require_gps_fix=fix_val,
            gps_gateway_host=_resolve("gps_gateway_host", "FIELDSENSE_GPS_GATEWAY_HOST", cls.gps_gateway_host, str),
            gps_gateway_port=port_val,
        )

        known_fields = {
            "source", "sensor_port", "sensor_baudrate", "sensor_slave_id",
            "bridge_endpoint", "soil_endpoint", "require_gps_fix",
            "gps_gateway_host", "gps_gateway_port"
        }
        extra_overrides = {k: v for k, v in overrides.items() if k not in known_fields and v is not None}
        if extra_overrides:
            from dataclasses import replace

            cfg = replace(cfg, **extra_overrides)  # type: ignore[arg-type]
        return cfg


class SensorAdapterFactory:
    """Factory for creating active SensorAdapter implementations.

    Demonstrates that changing the active data source does not alter downstream
    validation, intelligence, spatial, zone, recommendation, or UI pipelines.
    """

    @staticmethod
    def create_adapter(config: Optional[DataSourceConfig] = None) -> SensorAdapter:
        """Create a SensorAdapter for the configured source.

        Args:
            config: Optional DataSourceConfig. Defaults to VIRTUAL.

        Returns:
            SensorAdapter instance. Nothing is opened yet; call initialize().

        Raises:
            ValueError: The configured source name is not recognised. Failing
                loudly beats silently falling back to simulated data on a
                deployed unit, which would fabricate a field dataset.
        """
        cfg = config or DataSourceConfig.from_env()
        source = cfg.source.upper()

        if source == "VIRTUAL":
            return VirtualSensorAdapter(seed=42, num_samples=25)

        if source not in VALID_SOURCES:
            raise ValueError(
                "unknown data source {!r}. Expected one of: {}".format(
                    cfg.source, ", ".join(VALID_SOURCES)
                )
            )

        gps_adapter = BridgeGPSAdapter(
            host=cfg.gps_gateway_host,
            port=cfg.gps_gateway_port,
            bridge_endpoint=cfg.bridge_endpoint,
        )

        if source == "BRIDGE":
            # Probe hangs off the STM32; Linux never opens a serial device.
            from fieldsense.hardware.bridge_soil import BridgeSoilTransport

            transport = BridgeSoilTransport(method=cfg.soil_endpoint)
        elif source == "USB_PYSERIAL":
            transport = DirectUSBModbusTransport(
                port=cfg.sensor_port,
                baudrate=cfg.sensor_baudrate,
                slave_id=cfg.sensor_slave_id,
            )
        else:  # HARDWARE — stdlib serial, the default physical path
            from fieldsense.hardware.serial_modbus import StdlibModbusTransport

            transport = StdlibModbusTransport(
                port=cfg.sensor_port,
                baudrate=cfg.sensor_baudrate,
                slave_id=cfg.sensor_slave_id,
            )

        return HardwareSensorAdapter(
            transport=transport,
            gps_adapter=gps_adapter,
            require_gps_fix=cfg.require_gps_fix,
        )

    @staticmethod
    def describe_source(config: Optional[DataSourceConfig] = None) -> str:
        """Report the resolved acquisition path, for logs and the runbook."""
        cfg = config or DataSourceConfig()
        source = cfg.source.upper()
        if source == "VIRTUAL":
            return "VIRTUAL (deterministic virtual sensor, no hardware)"
        if source == "BRIDGE":
            return "BRIDGE (soil {} + GPS {} over STM32 RouterBridge)".format(
                cfg.soil_endpoint, cfg.bridge_endpoint
            )
        if source == "USB_PYSERIAL":
            return "USB_PYSERIAL (pyserial on {} @ {} 8N1)".format(
                cfg.sensor_port, cfg.sensor_baudrate
            )
        return "HARDWARE (stdlib Modbus on {} @ {} 8N1 + GPS {} over Bridge)".format(
            cfg.sensor_port, cfg.sensor_baudrate, cfg.bridge_endpoint
        )
