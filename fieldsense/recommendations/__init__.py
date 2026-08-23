"""Recommendations package containing RecommendationEngine, models, config, and rules."""

from .models import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
    RecommendationResult,
)
from .config import RecommendationConfig
from .rules import (
    RecommendationRule,
    NutrientRule,
    MoistureRule,
    SalinityRule,
    SoilConditionRule,
    CarbonReadinessRule,
    MonitoringRule,
)
from .engine import RecommendationEngine

__all__ = [
    # Models
    "Recommendation",
    "RecommendationCategory",
    "RecommendationPriority",
    "RecommendationResult",
    # Config
    "RecommendationConfig",
    # Rules
    "RecommendationRule",
    "NutrientRule",
    "MoistureRule",
    "SalinityRule",
    "SoilConditionRule",
    "CarbonReadinessRule",
    "MonitoringRule",
    # Engine Interface
    "RecommendationEngine",
]
