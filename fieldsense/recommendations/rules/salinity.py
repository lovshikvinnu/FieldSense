"""Deterministic salinity and electrical conductivity recommendation rule."""

from typing import List, Dict, Any

from fieldsense.zones.models import Zone
from fieldsense.recommendations.models import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
)
from .base import RecommendationRule


class SalinityRule(RecommendationRule):
    """Rule evaluating soil salinity / EC concern conditions."""

    def evaluate(self, zone: Zone, context: Dict[str, Any]) -> List[Recommendation]:
        recs: List[Recommendation] = []

        if "ec" in zone.affected_parameters or zone.primary_issue == "ec":
            p_map = context.get("priority_mapping", {})
            priority_str = p_map.get(zone.severity, "HIGH")
            priority = RecommendationPriority[priority_str]

            action_id = "INVESTIGATE_SALINITY"
            action_text = "Investigate elevated salinity conditions and review irrigation/drainage management."
            reason_text = f"Zone '{zone.zone_id}' exhibits elevated electrical conductivity concern (status: {zone.status})."

            rec = Recommendation(
                recommendation_id=f"REC-{zone.zone_id}-SALINITY",
                zone_id=zone.zone_id,
                category=RecommendationCategory.SALINITY,
                priority=priority,
                action_id=action_id,
                action=action_text,
                reason=reason_text,
                affected_parameters=["ec"],
                evidence={
                    "parameter": "ec",
                    "zone_status": zone.status,
                    "zone_severity": zone.severity,
                },
                confidence=zone.confidence,
                methodology_version=context.get("methodology_version", "0.1"),
            )
            recs.append(rec)

        return recs
