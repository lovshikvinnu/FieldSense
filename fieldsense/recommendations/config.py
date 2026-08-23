"""Centralized configuration for Recommendation Engine."""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass(frozen=True)
class RecommendationConfig:
    """Centralized configuration for Recommendation Engine.

    PROTOTYPE_ONLY - Decision-Support Rule Configuration.
    """
    max_recommendations_per_zone: int = 3
    priority_mapping: Dict[str, str] = field(
        default_factory=lambda: {
            "CRITICAL": "CRITICAL",
            "HIGH": "HIGH",
            "MEDIUM": "MEDIUM",
            "LOW": "LOW",
        }
    )
    rule_enablement: Dict[str, bool] = field(
        default_factory=lambda: {
            "nutrient": True,
            "moisture": True,
            "salinity": True,
            "soil_condition": True,
            "carbon_readiness": True,
            "monitoring": True,
        }
    )
    methodology_version: str = "0.1"
