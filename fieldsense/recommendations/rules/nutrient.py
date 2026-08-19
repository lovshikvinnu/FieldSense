"""Deterministic nutrient management recommendation rule."""

from typing import List, Dict, Any

from fieldsense.zones.models import Zone
from fieldsense.recommendations.models import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
)
from .base import RecommendationRule


class NutrientRule(RecommendationRule):
    """Rule evaluating nutrient management conditions (N, P, K)."""

    def evaluate(self, zone: Zone, context: Dict[str, Any]) -> List[Recommendation]:
        recs: List[Recommendation] = []
        nutrient_params = {"nitrogen", "phosphorus", "potassium"}
        affected = set(zone.affected_parameters).intersection(nutrient_params)

        if "nitrogen" in zone.affected_parameters or zone.primary_issue == "nitrogen" or affected:
            p_map = context.get("priority_mapping", {})
            priority_str = p_map.get(zone.severity, "HIGH")
            priority = RecommendationPriority[priority_str]

            action_id = "REVIEW_NITROGEN_MANAGEMENT"
            action_text = "Review nitrogen availability and consider targeted nutrient management."
            reason_text = f"Zone '{zone.zone_id}' exhibits nitrogen availability concern (status: {zone.status})."

            rec = Recommendation(
                recommendation_id=f"REC-{zone.zone_id}-NUTRIENT-N",
                zone_id=zone.zone_id,
                category=RecommendationCategory.NUTRIENT,
                priority=priority,
                action_id=action_id,
                action=action_text,
                reason=reason_text,
                affected_parameters=list(affected if affected else ["nitrogen"]),
                evidence={
                    "parameter": zone.primary_issue or "nitrogen",
                    "zone_status": zone.status,
                    "zone_severity": zone.severity,
                },
                confidence=zone.confidence,
                methodology_version=context.get("methodology_version", "0.1"),
            )
            recs.append(rec)

        return recs
