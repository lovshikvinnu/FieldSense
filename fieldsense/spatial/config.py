"""Centralized configuration for spatial engine and interpolation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SpatialConfig:
    """Centralized configuration for FieldSense spatial engine.

    PROTOTYPE_ONLY - Spatial interpolation configuration.
    """
    grid_spacing_meters: float = 10.0
    idw_power: float = 2.0
    minimum_samples_for_interpolation: int = 3
    max_support_distance_meters: float = 100.0
    methodology_version: str = "0.1"
