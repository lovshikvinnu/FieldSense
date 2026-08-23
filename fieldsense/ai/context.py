"""Deterministic results to ExplanationContext reduction.

Implements the AI boundary described in docs/03_ARCHITECTURE.md section 22:

    Deterministic Results -> Structured Context -> Edge LLM Explainer

Nothing in this module computes, re-derives, or reinterprets a metric. It only
selects and reshapes values that upstream engines already produced.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fieldsense.domain.models import FieldSession, SampleSource
from fieldsense.recommendations.models import RecommendationResult
from fieldsense.spatial.engine import SpatialFieldResult
from fieldsense.zones.models import ZoneDetectionResult

from .models import ExplanationContext, ZoneContext

if TYPE_CHECKING:  # pragma: no cover - import kept out of runtime to avoid a cycle
    from fieldsense.presentation.models import UIFieldView


# Mirrors UIViewAdapter._classify_status so the narrative agrees with the dashboard.
_HEALTHY_THRESHOLD = 0.70
_MODERATE_THRESHOLD = 0.40


def _classify_status(score: float) -> str:
    """Map an aggregate score to the dashboard status label."""
    if score >= _HEALTHY_THRESHOLD:
        return "HEALTHY"
    if score >= _MODERATE_THRESHOLD:
        return "MODERATE"
    return "POOR"


def _layer_average(spatial: SpatialFieldResult, layer_id: str) -> float:
    """Average of supported grid values for one spatial layer."""
    layer = spatial.layers.get(layer_id)
    if not layer:
        return 0.0
    values = [gv.value for gv in layer.grid_values if gv.value is not None]
    return round(sum(values) / len(values), 2) if values else 0.0


def _zone_contexts(
    zones: ZoneDetectionResult,
    recommendations: RecommendationResult,
    max_actions_per_zone: int,
) -> List[ZoneContext]:
    """Join zones with their recommendations into compact per-zone contexts."""
    by_zone: Dict[str, List[Any]] = {}
    for rec in recommendations.recommendations:
        by_zone.setdefault(rec.zone_id, []).append(rec)

    contexts: List[ZoneContext] = []
    for zone in zones.zones:
        zone_recs = by_zone.get(zone.zone_id, [])[:max_actions_per_zone]
        contexts.append(
            ZoneContext(
                zone_id=zone.zone_id,
                status=zone.status,
                severity=zone.severity,
                primary_issue=zone.primary_issue,
                affected_parameters=list(zone.affected_parameters),
                confidence=zone.confidence,
                area_estimate=zone.area_estimate,
                action_ids=[r.action_id for r in zone_recs],
                actions=[r.action for r in zone_recs],
                categories=[
                    r.category.value if hasattr(r.category, "value") else str(r.category)
                    for r in zone_recs
                ],
                priorities=[
                    r.priority.value if hasattr(r.priority, "value") else str(r.priority)
                    for r in zone_recs
                ],
            )
        )
    return contexts


def build_explanation_context(
    session: FieldSession,
    spatial: SpatialFieldResult,
    zones: ZoneDetectionResult,
    recommendations: RecommendationResult,
    max_zones: int = 12,
    max_actions_per_zone: int = 3,
) -> ExplanationContext:
    """Reduce deterministic pipeline results to a bounded explanation context.

    Args:
        session: Raw FieldSession, including rejected samples.
        spatial: SpatialFieldResult from the spatial engine.
        zones: ZoneDetectionResult from the zone engine.
        recommendations: RecommendationResult from the recommendation engine.
        max_zones: Upper bound on zones included, to cap prompt size.
        max_actions_per_zone: Upper bound on recommendations quoted per zone.

    Returns:
        ExplanationContext ready to hand to a LocalLLMAdapter.
    """
    valid_count = len(spatial.source_sample_ids)
    total_count = session.sample_count
    rejected_count = max(0, total_count - valid_count)

    avg_soil_health = _layer_average(spatial, "soil_health")

    sample_sources = {s.source for s in session.samples}
    data_source = "VIRTUAL" if SampleSource.VIRTUAL in sample_sources or not sample_sources else "HARDWARE"

    zone_contexts = _zone_contexts(zones, recommendations, max_actions_per_zone)[:max_zones]

    return ExplanationContext(
        field_name=session.field_name or "Field-01",
        session_id=session.session_id,
        overall_soil_health=avg_soil_health,
        soil_health_status=_classify_status(avg_soil_health),
        nitrogen_score=_layer_average(spatial, "nitrogen"),
        moisture_score=_layer_average(spatial, "moisture"),
        carbon_readiness_score=_layer_average(spatial, "carbon_readiness"),
        total_samples=total_count,
        valid_samples=valid_count,
        rejected_samples=rejected_count,
        coverage_ratio=round(spatial.coverage.coverage_ratio, 2),
        zones=zone_contexts,
        evidence_level="LIMITED",
        methodology_version=spatial.methodology_version,
        data_source=data_source,
    )


def build_context_from_view(
    view: "UIFieldView",
    max_zones: int = 12,
) -> ExplanationContext:
    """Build an ExplanationContext from an already-adapted UIFieldView.

    Convenience path for callers that have run the presentation adapter and do
    not want to keep the raw engine results alive. Attribute access only, so
    this module never imports the presentation package at runtime and no import
    cycle is created.

    Args:
        view: UIFieldView produced by UIViewAdapter.
        max_zones: Upper bound on zones included.

    Returns:
        Equivalent ExplanationContext.
    """
    rec_by_zone: Dict[str, List[Any]] = {}
    for rec in view.recommendations:
        rec_by_zone.setdefault(rec.zone_id, []).append(rec)

    zone_contexts: List[ZoneContext] = []
    for zone in view.zones[:max_zones]:
        zone_recs = rec_by_zone.get(zone.zone_id, [])
        zone_contexts.append(
            ZoneContext(
                zone_id=zone.zone_id,
                status=zone.status,
                severity=zone.severity,
                primary_issue=zone.primary_issue,
                affected_parameters=list(zone.affected_parameters),
                confidence=zone.confidence,
                area_estimate=zone.area_estimate,
                action_ids=[],
                actions=[r.action for r in zone_recs],
                categories=[r.category for r in zone_recs],
                priorities=[r.priority for r in zone_recs],
            )
        )

    return ExplanationContext(
        field_name=view.field.field_name,
        session_id=view.field.session_id,
        overall_soil_health=view.health_summary.score,
        soil_health_status=view.health_summary.status,
        nitrogen_score=view.health_summary.nitrogen_score,
        moisture_score=view.health_summary.moisture_score,
        carbon_readiness_score=view.health_summary.carbon_readiness_score,
        total_samples=view.sampling_status.total_samples,
        valid_samples=view.sampling_status.valid_samples,
        rejected_samples=view.sampling_status.rejected_samples,
        coverage_ratio=round(view.field.coverage_ratio, 2),
        zones=zone_contexts,
        evidence_level=view.health_summary.evidence_level,
        methodology_version=view.field.methodology_version,
        data_source=view.system_status.data_source,
    )
