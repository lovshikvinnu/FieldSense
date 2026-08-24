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
        cfg = cls(
            source=os.environ.get("FIELDSENSE_SOURCE", cls.source).upper(),
            sensor_port=os.environ.get("FIELDSENSE_SENSOR_PORT", cls.sensor_port),
            sensor_baudrate=int(os.environ.get("FIELDSENSE_SENSOR_BAUD", cls.sensor_baudrate)),
            sensor_slave_id=int(os.environ.get("FIELDSENSE_SENSOR_SLAVE", cls.sensor_slave_id)),
            bridge_endpoint=os.environ.get("FIELDSENSE_GPS_METHOD", cls.bridge_endpoint),
            soil_endpoint=os.environ.get("FIELDSENSE_SOIL_METHOD", cls.soil_endpoint),
            require_gps_fix=_env_flag("FIELDSENSE_REQUIRE_GPS_FIX", cls.require_gps_fix),
        )
        if overrides:
            from dataclasses import replace

            cfg = replace(cfg, **overrides)  # type: ignore[arg-type]
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
        cfg = config or DataSourceConfig()
        source = cfg.source.upper()

        if source == "VIRTUAL":
            return VirtualSensorAdapter(seed=42, num_samples=25)

        if source not in VALID_SOURCES:
            raise ValueError(
                "unknown data source {!r}. Expected one of: {}".format(
                    cfg.source, ", ".join(VALID_SOURCES)
                )
            )

        gps_adapter = BridgeGPSAdapter(bridge_endpoint=cfg.bridge_endpoint)

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
