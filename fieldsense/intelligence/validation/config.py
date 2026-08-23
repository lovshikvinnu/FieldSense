"""Centralized configuration for FieldSense validation bounds and quality limits."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class MeasurementRange:
    """Engineering sanity range bounds [min_val, max_val] for sensor validation."""
    min_val: float
    max_val: float

    def is_valid(self, val: float) -> bool:
        """Check if numeric value is within inclusive sanity bounds."""
        return self.min_val <= val <= self.max_val


@dataclass(frozen=True)
class ValidationConfig:
    """Centralized configuration for FieldSense validation engine.

    IMPORTANT NOTE:
    These bounds are engineering sanity limits for simulated/sensor data validation,
    NOT agronomic recommendation thresholds or soil health scoring criteria.
    """
    # Latitude / Longitude limits
    lat_range: MeasurementRange = field(default_factory=lambda: MeasurementRange(-90.0, 90.0))
    lon_range: MeasurementRange = field(default_factory=lambda: MeasurementRange(-180.0, 180.0))

    # Measurement quality thresholds:
    # quality >= 0.70 -> Good (VALID)
    # 0.30 <= quality < 0.70 -> Warning (VALID_WITH_WARNING, pipeline_eligible = True)
    # quality < 0.30 -> Unusable / Unstable (REJECTED, pipeline_eligible = False)
    quality_warning_threshold: float = 0.70
    quality_reject_threshold: float = 0.30

    # Sensor measurement sanity limits
    measurement_ranges: Dict[str, MeasurementRange] = field(default_factory=lambda: {
        "ph": MeasurementRange(3.0, 10.0),
        "ec": MeasurementRange(0.0, 10.0),            # dS/m
        "moisture": MeasurementRange(0.0, 100.0),      # %
        "temperature": MeasurementRange(-10.0, 60.0),  # °C
        "nitrogen": MeasurementRange(0.0, 500.0),      # mg/kg
        "phosphorus": MeasurementRange(0.0, 300.0),    # mg/kg
        "potassium": MeasurementRange(0.0, 1000.0),    # mg/kg
    })
