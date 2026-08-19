"""Scoring package containing models, configuration, and scoring functions."""

from .models import (
    ParameterScore,
    SoilHealthResult,
    NitrogenResult,
    MoistureResult,
    CarbonReadinessResult,
    FieldIntelligenceResult,
)
from .config import (
    ParameterScoringBand,
    NormalizationConfig,
    ScoringConfig,
    SoilHealthConfig,
    CarbonReadinessConfig,
    IntelligenceConfig,
)
from .functions import (
    optimum_range_score,
    upper_limit_penalty_score,
    adequacy_band_score,
    interpret_score,
)

__all__ = [
    # Models
    "ParameterScore",
    "SoilHealthResult",
    "NitrogenResult",
    "MoistureResult",
    "CarbonReadinessResult",
    "FieldIntelligenceResult",
    # Config
    "ParameterScoringBand",
    "NormalizationConfig",
    "ScoringConfig",
    "SoilHealthConfig",
    "CarbonReadinessConfig",
    "IntelligenceConfig",
    # Functions
    "optimum_range_score",
    "upper_limit_penalty_score",
    "adequacy_band_score",
    "interpret_score",
]
