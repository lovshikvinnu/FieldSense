"""Versioned configuration structures for deterministic intelligence methodologies.

PROTOTYPE_ONLY
AGRONOMIC_VALIDATION_REQUIRED
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class ParameterScoringBand:
    """Prototype reference band parameters for a parameter scoring function.

    PROTOTYPE_ONLY - AGRONOMIC_VALIDATION_REQUIRED
    """
    low_bound: float
    target_min: float
    target_max: float
    high_bound: float
    description: str = "FieldSense Prototype Reference Band v0.1 (PROTOTYPE_ONLY)"


@dataclass(frozen=True)
class NormalizationConfig:
    """Configuration structure for sample normalization methodology."""
    methodology_version: str = "0.1"
    convert_ec_us_to_ds: bool = True


@dataclass(frozen=True)
class ScoringConfig:
    """Configuration for parameter scoring functions.

    PROTOTYPE_ONLY - AGRONOMIC_VALIDATION_REQUIRED
    """
    methodology_version: str = "0.1"

    # pH optimum band: opt [6.0, 7.5], low 4.0, high 9.0
    ph_band: ParameterScoringBand = field(
        default_factory=lambda: ParameterScoringBand(
            low_bound=4.0, target_min=6.0, target_max=7.5, high_bound=9.0,
            description="FieldSense Prototype General-Purpose pH Reference"
        )
    )

    # EC salinity penalty: ideal <= 2.0 dS/m, severe penalty >= 4.0 dS/m
    ec_ideal_max: float = 2.0
    ec_severe_max: float = 4.0

    # Moisture optimum band: opt [25.0, 45.0]%, low 10.0%, high 65.0%
    moisture_band: ParameterScoringBand = field(
        default_factory=lambda: ParameterScoringBand(
            low_bound=10.0, target_min=25.0, target_max=45.0, high_bound=65.0,
            description="FieldSense Prototype Moisture Optimum Range"
        )
    )

    # Nitrogen (N): adeq [30.0, 90.0] mg/kg, low 0.0, high 180.0
    n_band: ParameterScoringBand = field(
        default_factory=lambda: ParameterScoringBand(
            low_bound=0.0, target_min=30.0, target_max=90.0, high_bound=180.0,
            description="FieldSense Prototype Nitrogen Reference Band v0.1"
        )
    )

    # Phosphorus (P): adeq [15.0, 45.0] mg/kg, low 0.0, high 90.0
    p_band: ParameterScoringBand = field(
        default_factory=lambda: ParameterScoringBand(
            low_bound=0.0, target_min=15.0, target_max=45.0, high_bound=90.0,
            description="FieldSense Prototype Phosphorus Reference Band v0.1"
        )
    )

    # Potassium (K): adeq [100.0, 250.0] mg/kg, low 0.0, high 450.0
    k_band: ParameterScoringBand = field(
        default_factory=lambda: ParameterScoringBand(
            low_bound=0.0, target_min=100.0, target_max=250.0, high_bound=450.0,
            description="FieldSense Prototype Potassium Reference Band v0.1"
        )
    )


@dataclass(frozen=True)
class SoilHealthConfig:
    """Configuration for Soil Health deterministic weighted aggregation.

    PROTOTYPE_ONLY - AGRONOMIC_VALIDATION_REQUIRED
    """
    methodology_version: str = "0.1"
    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "nitrogen": 0.20,
            "phosphorus": 0.15,
            "potassium": 0.15,
            "ph": 0.20,
            "ec": 0.10,
            "moisture": 0.20,
        }
    )


@dataclass(frozen=True)
class CarbonReadinessConfig:
    """Configuration for Carbon Readiness MCDA proxy methodology.

    PROTOTYPE_ONLY - AGRONOMIC_VALIDATION_REQUIRED
    """
    methodology_version: str = "0.1"
    w_soil_condition: float = 0.50
    w_moisture_condition: float = 0.25
    w_nutrient_balance: float = 0.25


@dataclass(frozen=True)
class IntelligenceConfig:
    """Versioned container for all deterministic intelligence configs."""
    methodology_version: str = "0.1"
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    soil_health: SoilHealthConfig = field(default_factory=SoilHealthConfig)
    carbon_readiness: CarbonReadinessConfig = field(default_factory=CarbonReadinessConfig)
