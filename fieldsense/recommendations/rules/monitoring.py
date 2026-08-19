"""Deterministic monitoring fallback recommendation rule."""

from typing import List, Dict, Any

from fieldsense.zones.models import Zone
from fieldsense.recommendations.models import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
)
from .base import RecommendationRule


class MonitoringRule(RecommendationRule):
    """Rule evaluating spatial data support and routine monitoring needs."""

    def evaluate(self, zone: Zone, context: Dict[str, Any]) -> List[Recommendation]:
        recs: List[Recommendation] = []

        if zone.confidence == "LOW" or not zone.affected_parameters:
            priority = RecommendationPriority.LOW if zone.status == "HEALTHY" else RecommendationPriority.MEDIUM
            action_id = "COLLECT_ADDITIONAL_SAMPLES" if zone.confidence == "LOW" else "ROUTINE_MONITORING"
            action_text = (
                "Collect additional samples in this zone before making a stronger management decision."
                if zone.confidence == "LOW"
                else "Maintain routine soil monitoring and periodic health assessment for this zone."
            )
            reason_text = (
                f"Zone '{zone.zone_id}' has low spatial data support confidence."
                if zone.confidence == "LOW"
                else f"Zone '{zone.zone_id}' condition is healthy; routine monitoring recommended."
            )

            rec = Recommendation(
                recommendation_id=f"REC-{zone.zone_id}-MONITORING",
                zone_id=zone.zone_id,
                category=RecommendationCategory.MONITORING,
                priority=priority,
                action_id=action_id,
                action=action_text,
                reason=reason_text,
                affected_parameters=list(zone.affected_parameters),
                evidence={
                    "zone_confidence": zone.confidence,
                    "zone_status": zone.status,
                },
                confidence=zone.confidence,
                methodology_version=context.get("methodology_version", "0.1"),
            )
            recs.append(rec)

        return recs
