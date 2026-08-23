"""Data source configuration and SensorAdapterFactory."""

from dataclasses import dataclass
from typing import Optional

from fieldsense.domain.contracts.sensor import SensorAdapter
from fieldsense.input.virtual_sensor import VirtualSensorAdapter
from fieldsense.hardware.sensor_adapter import HardwareSensorAdapter


@dataclass(frozen=True)
class DataSourceConfig:
    """Active data acquisition source configuration."""
    source: str = "VIRTUAL"                       # VIRTUAL, HARDWARE


class SensorAdapterFactory:
    """Factory for creating active SensorAdapter implementations.

    Demonstrates that changing the active data source (VIRTUAL vs HARDWARE)
    does not alter downstream validation, intelligence, spatial, zone, recommendation, or UI pipelines.
    """

    @staticmethod
    def create_adapter(config: Optional[DataSourceConfig] = None) -> SensorAdapter:
        """Create SensorAdapter instance based on DataSourceConfig.

        Args:
            config: Optional DataSourceConfig.

        Returns:
            SensorAdapter instance (VirtualSensorAdapter or HardwareSensorAdapter).
        """
        cfg = config or DataSourceConfig()

        if cfg.source.upper() == "HARDWARE":
            adapter = HardwareSensorAdapter()
            adapter.initialize()
            return adapter
        else:
            return VirtualSensorAdapter(seed=42, num_samples=25)
