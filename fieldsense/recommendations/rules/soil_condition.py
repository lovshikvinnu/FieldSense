"""Deterministic soil condition recommendation rule."""

from typing import List, Dict, Any

from fieldsense.zones.models import Zone
from fieldsense.recommendations.models import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
)
from .base import RecommendationRule


class SoilConditionRule(RecommendationRule):
    """Rule evaluating overall poor/moderate soil condition zones."""

    def evaluate(self, zone: Zone, context: Dict[str, Any]) -> List[Recommendation]:
        recs: List[Recommendation] = []

        if zone.status in ["POOR", "MODERATE"]:
            p_map = context.get("priority_mapping", {})
            priority_str = p_map.get(zone.severity, "MEDIUM")
            priority = RecommendationPriority[priority_str]

            action_id = "PRIORITIZE_SOIL_ASSESSMENT"
            action_text = "Prioritize this zone for detailed soil assessment and management review."
            reason_text = f"Zone '{zone.zone_id}' exhibits {zone.status.lower()} overall soil condition status."

            rec = Recommendation(
                recommendation_id=f"REC-{zone.zone_id}-SOIL-CONDITION",
                zone_id=zone.zone_id,
                category=RecommendationCategory.SOIL_CONDITION,
                priority=priority,
                action_id=action_id,
                action=action_text,
                reason=reason_text,
                affected_parameters=list(zone.affected_parameters),
                evidence={
                    "parameter": zone.primary_issue or "soil_health",
                    "zone_status": zone.status,
                    "zone_severity": zone.severity,
                },
                confidence=zone.confidence,
                methodology_version=context.get("methodology_version", "0.1"),
            )
            recs.append(rec)

        return recs
