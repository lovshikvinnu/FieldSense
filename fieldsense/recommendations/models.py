"""Recommendation engine models and enums."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any


class RecommendationCategory(str, Enum):
    """Controlled category for FieldSense recommendations."""
    NUTRIENT = "NUTRIENT"
    WATER = "WATER"
    SOIL_CONDITION = "SOIL_CONDITION"
    SALINITY = "SALINITY"
    CARBON_READINESS = "CARBON_READINESS"
    MONITORING = "MONITORING"


class RecommendationPriority(str, Enum):
    """Priority level for recommendations."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Recommendation:
    """Structured, traceable, rule-based recommendation for a management zone."""
    recommendation_id: str
    zone_id: str
    category: RecommendationCategory
    priority: RecommendationPriority
    action_id: str
    action: str
    reason: str
    affected_parameters: List[str]
    evidence: Dict[str, Any]
    confidence: str                              # HIGH, MEDIUM, LOW
    methodology_version: str = "0.1"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Recommendation to dictionary format."""
        return {
            "recommendation_id": self.recommendation_id,
            "zone_id": self.zone_id,
            "category": self.category.value if isinstance(self.category, Enum) else self.category,
            "priority": self.priority.value if isinstance(self.priority, Enum) else self.priority,
            "action_id": self.action_id,
            "action": self.action,
            "reason": self.reason,
            "affected_parameters": list(self.affected_parameters),
            "evidence": dict(self.evidence),
            "confidence": self.confidence,
            "methodology_version": self.methodology_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Recommendation":
        """Deserialize dictionary to Recommendation."""
        category = RecommendationCategory(data["category"]) if isinstance(data["category"], str) else data["category"]
        priority = RecommendationPriority(data["priority"]) if isinstance(data["priority"], str) else data["priority"]
        return cls(
            recommendation_id=data["recommendation_id"],
            zone_id=data["zone_id"],
            category=category,
            priority=priority,
            action_id=data["action_id"],
            action=data["action"],
            reason=data["reason"],
            affected_parameters=list(data.get("affected_parameters", [])),
            evidence=dict(data.get("evidence", {})),
            confidence=data.get("confidence", "MEDIUM"),
            methodology_version=data.get("methodology_version", "0.1"),
        )


@dataclass(frozen=True)
class RecommendationResult:
    """Complete recommendation output for a field assessment."""
    recommendations: List[Recommendation]
    methodology_version: str = "0.1"
    summary_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize RecommendationResult to dictionary."""
        return {
            "recommendations": [r.to_dict() for r in self.recommendations],
            "methodology_version": self.methodology_version,
            "summary_metadata": dict(self.summary_metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecommendationResult":
        """Deserialize dictionary to RecommendationResult."""
        recs = [Recommendation.from_dict(r) for r in data.get("recommendations", [])]
        return cls(
            recommendations=recs,
            methodology_version=data.get("methodology_version", "0.1"),
            summary_metadata=dict(data.get("summary_metadata", {})),
        )
