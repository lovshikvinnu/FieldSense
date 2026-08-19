"""Deterministic Carbon Readiness decision-support recommendation rule."""

from typing import List, Dict, Any

from fieldsense.zones.models import Zone
from fieldsense.recommendations.models import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
)
from .base import RecommendationRule


class CarbonReadinessRule(RecommendationRule):
    """Rule evaluating Carbon Readiness decision-support conditions."""

    def evaluate(self, zone: Zone, context: Dict[str, Any]) -> List[Recommendation]:
        recs: List[Recommendation] = []

        if "carbon_readiness" in zone.affected_parameters or zone.primary_issue == "carbon_readiness":
            p_map = context.get("priority_mapping", {})
            priority_str = p_map.get(zone.severity, "MEDIUM")
            priority = RecommendationPriority[priority_str]

            action_id = "EVALUATE_CARBON_PRACTICES"
            action_text = "Consider evaluating soil-carbon management practices and collecting additional carbon-related soil information."
            reason_text = f"Zone '{zone.zone_id}' Carbon Readiness index suggests opportunity for management assessment."

            rec = Recommendation(
                recommendation_id=f"REC-{zone.zone_id}-CARBON",
                zone_id=zone.zone_id,
                category=RecommendationCategory.CARBON_READINESS,
                priority=priority,
                action_id=action_id,
                action=action_text,
                reason=reason_text,
                affected_parameters=["carbon_readiness"],
                evidence={
                    "parameter": "carbon_readiness",
                    "zone_status": zone.status,
                    "evidence_level": "LIMITED",
                },
                confidence=zone.confidence,
                methodology_version=context.get("methodology_version", "0.1"),
            )
            recs.append(rec)

        return recs
