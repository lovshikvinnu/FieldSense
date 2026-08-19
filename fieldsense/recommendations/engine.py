"""Deterministic Recommendation Engine implementation."""

from typing import List, Dict, Tuple, Set, Optional, Any

from fieldsense.zones.models import ZoneDetectionResult, Zone
from .config import RecommendationConfig
from .models import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
    RecommendationResult,
)
from .rules import (
    RecommendationRule,
    NutrientRule,
    MoistureRule,
    SalinityRule,
    SoilConditionRule,
    CarbonReadinessRule,
    MonitoringRule,
)


class RecommendationEngine:
    """Deterministic Rule-Based Recommendation Engine.

    Transforms ZoneDetectionResult into structured, traceable decision-support recommendations.
    Does NOT use AI/LLMs or generate unsupported fertilizer/irrigation prescriptions.
    """

    def __init__(
        self,
        config: Optional[RecommendationConfig] = None,
        rules: Optional[List[RecommendationRule]] = None,
    ) -> None:
        """Initialize recommendation engine with configuration and rules."""
        self.config = config or RecommendationConfig()

        if rules is not None:
            self.rules = rules
        else:
            # Default rule pipeline
            self.rules = [
                NutrientRule(),
                MoistureRule(),
                SalinityRule(),
                SoilConditionRule(),
                CarbonReadinessRule(),
                MonitoringRule(),
            ]

    def process(self, zone_detection_result: ZoneDetectionResult) -> RecommendationResult:
        """Process ZoneDetectionResult and produce structured RecommendationResult.

        Args:
            zone_detection_result: Target ZoneDetectionResult.

        Returns:
            RecommendationResult containing structured recommendations.
        """
        context = {
            "priority_mapping": self.config.priority_mapping,
            "methodology_version": self.config.methodology_version,
        }

        all_recommendations: List[Recommendation] = []

        for zone in zone_detection_result.zones:
            zone_recs = self._process_zone(zone, context)
            all_recommendations.extend(zone_recs)

        return RecommendationResult(
            recommendations=all_recommendations,
            methodology_version=self.config.methodology_version,
            summary_metadata={
                "zone_count": len(zone_detection_result.zones),
                "recommendation_count": len(all_recommendations),
            },
        )

    def _process_zone(self, zone: Zone, context: Dict[str, Any]) -> List[Recommendation]:
        """Evaluate rules for a single zone, apply primary issue ordering, deduplicate, and cap length."""
        candidate_recs: List[Recommendation] = []

        for rule in self.rules:
            rule_recs = rule.evaluate(zone, context)
            candidate_recs.extend(rule_recs)

        if not candidate_recs:
            return []

        # Deduplicate recommendations by (zone_id, category, action_id)
        seen_keys: Set[Tuple[str, str, str]] = set()
        unique_recs: List[Recommendation] = []
        for rec in candidate_recs:
            key = (rec.zone_id, rec.category.value, rec.action_id)
            if key not in seen_keys:
                seen_keys.add(key)
                unique_recs.append(rec)

        # Primary issue driver sorting:
        # Recommendations addressing zone.primary_issue or zone's primary category come FIRST (rank 0)
        def primary_sort_key(rec: Recommendation) -> Tuple[int, int]:
            is_primary = 1
            if zone.primary_issue:
                if (
                    zone.primary_issue in rec.affected_parameters
                    or zone.primary_issue.lower() in rec.action_id.lower()
                    or (zone.primary_issue == "moisture" and rec.category == RecommendationCategory.WATER)
                    or (zone.primary_issue == "nitrogen" and rec.category == RecommendationCategory.NUTRIENT)
                ):
                    is_primary = 0
            priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            p_val = priority_order.get(rec.priority.value, 4)
            return (is_primary, p_val)

        unique_recs.sort(key=primary_sort_key)

        # Cap recommendations per zone
        max_recs = self.config.max_recommendations_per_zone
        return unique_recs[:max_recs]
