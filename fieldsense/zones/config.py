"""Centralized configuration for zone detection engine."""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ZoneConfig:
    """Configuration structure for zone detection engine.

    PROTOTYPE_ONLY - Zone Detection Configuration.
    """
    primary_layer: str = "soil_health"
    minimum_zone_cells: int = 2
    concern_threshold: float = 0.70
    healthy_threshold: float = 0.70
    moderate_threshold: float = 0.40
    parameter_priority: List[str] = field(
        default_factory=lambda: [
            "nitrogen",
            "moisture",
            "carbon_readiness",
            "ph",
            "ec",
            "potassium",
            "phosphorus",
        ]
    )
    methodology_version: str = "0.1"
