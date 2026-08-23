"""Deterministic Intelligence Layer for FieldSense AI."""

from .validation import (
    ValidationReason,
    ValidationConfig,
    MeasurementRange,
    ValidationResult,
    ValidationEngine,
)
from .normalization import (
    NormalizedSample,
    Normalizer,
    StandardNormalizer,
)
from .scoring import (
    ParameterScore,
    SoilHealthResult,
    NitrogenResult,
    MoistureResult,
    CarbonReadinessResult,
    FieldIntelligenceResult,
    ParameterScoringBand,
    NormalizationConfig,
    ScoringConfig,
    SoilHealthConfig,
    CarbonReadinessConfig,
    IntelligenceConfig,
    optimum_range_score,
    upper_limit_penalty_score,
    adequacy_band_score,
    interpret_score,
)
from .engine import FieldIntelligenceEngine

__all__ = [
    # Validation
    "ValidationReason",
    "ValidationConfig",
    "MeasurementRange",
    "ValidationResult",
    "ValidationEngine",
    # Normalization
    "NormalizedSample",
    "Normalizer",
    "StandardNormalizer",
    # Scoring & Intelligence Models
    "ParameterScore",
    "SoilHealthResult",
    "NitrogenResult",
    "MoistureResult",
    "CarbonReadinessResult",
    "FieldIntelligenceResult",
    # Intelligence Configuration
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
    # Engine Interface
    "FieldIntelligenceEngine",
]
