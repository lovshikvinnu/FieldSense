"""Deterministic moisture and water management recommendation rule."""

from typing import List, Dict, Any

from fieldsense.zones.models import Zone
from fieldsense.recommendations.models import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
)
from .base import RecommendationRule


class MoistureRule(RecommendationRule):
    """Rule evaluating soil moisture and irrigation conditions."""

    def evaluate(self, zone: Zone, context: Dict[str, Any]) -> List[Recommendation]:
        recs: List[Recommendation] = []

        if "moisture" in zone.affected_parameters or zone.primary_issue == "moisture":
            p_map = context.get("priority_mapping", {})
            priority_str = p_map.get(zone.severity, "MEDIUM")
            priority = RecommendationPriority[priority_str]

            action_id = "REVIEW_IRRIGATION_TIMING"
            action_text = "Review irrigation timing and soil moisture conditions in this zone."
            reason_text = f"Zone '{zone.zone_id}' exhibits moisture deficiency or imbalance (status: {zone.status})."

            rec = Recommendation(
                recommendation_id=f"REC-{zone.zone_id}-WATER",
                zone_id=zone.zone_id,
                category=RecommendationCategory.WATER,
                priority=priority,
                action_id=action_id,
                action=action_text,
                reason=reason_text,
                affected_parameters=["moisture"],
                evidence={
                    "parameter": "moisture",
                    "zone_status": zone.status,
                    "zone_severity": zone.severity,
                },
                confidence=zone.confidence,
                methodology_version=context.get("methodology_version", "0.1"),
            )
            recs.append(rec)

        return recs
