"""Unit and end-to-end integration tests for Deterministic Recommendation Engine (Sprint 7)."""

import sys
import pytest

from fieldsense.input import FieldScenario, VirtualSensorAdapter
from fieldsense.intelligence import FieldIntelligenceEngine, ValidationEngine
from fieldsense.spatial import SpatialConfig, SpatialEngine
from fieldsense.zones import Zone, ZoneConfig, ZoneDetectionEngine
from fieldsense.recommendations import (
    CarbonReadinessRule,
    MoistureRule,
    MonitoringRule,
    NutrientRule,
    Recommendation,
    RecommendationCategory,
    RecommendationConfig,
    RecommendationEngine,
    RecommendationPriority,
    RecommendationResult,
    SalinityRule,
    SoilConditionRule,
)


def make_test_zone(
    zone_id: str = "ZONE-01",
    status: str = "POOR",
    severity: str = "HIGH",
    affected: list = None,
    primary_issue: str = "nitrogen",
    confidence: str = "HIGH",
) -> Zone:
    """Helper factory for test Zone instances."""
    if affected is None:
        affected = ["nitrogen", "moisture"]
    return Zone(
        zone_id=zone_id,
        status=status,
        severity=severity,
        affected_parameters=affected,
        primary_issue=primary_issue,
        confidence=confidence,
        grid_points=[],
        sample_ids=["SMP-001"],
        centroid=(12.9716, 77.5946),
        area_estimate=400.0,
        recommendation_reference="pending_recommendation_engine",
    )


def test_recommendation_model_serialization():
    rec = Recommendation(
        recommendation_id="REC-ZONE-01-NUTRIENT-N",
        zone_id="ZONE-01",
        category=RecommendationCategory.NUTRIENT,
        priority=RecommendationPriority.HIGH,
        action_id="REVIEW_NITROGEN_MANAGEMENT",
        action="Review nitrogen availability and consider targeted nutrient management.",
        reason="Nitrogen deficiency detected.",
        affected_parameters=["nitrogen"],
        evidence={"parameter": "nitrogen", "zone_status": "POOR"},
        confidence="HIGH",
    )

    dict_repr = rec.to_dict()
    assert dict_repr["category"] == "NUTRIENT"
    assert dict_repr["priority"] == "HIGH"

    reconstructed = Recommendation.from_dict(dict_repr)
    assert reconstructed == rec


def test_nutrient_rule():
    rule = NutrientRule()
    zone = make_test_zone(affected=["nitrogen"], primary_issue="nitrogen")
    recs = rule.evaluate(zone, {})

    assert len(recs) == 1
    rec = recs[0]
    assert rec.category == RecommendationCategory.NUTRIENT
    assert rec.action_id == "REVIEW_NITROGEN_MANAGEMENT"
    # Verify NO unsupported fertilizer prescriptions (e.g. no 'urea', no '25 kg/acre')
    assert "urea" not in rec.action.lower()
    assert "kg/acre" not in rec.action.lower()


def test_moisture_rule():
    rule = MoistureRule()
    zone = make_test_zone(affected=["moisture"], primary_issue="moisture")
    recs = rule.evaluate(zone, {})

    assert len(recs) == 1
    rec = recs[0]
    assert rec.category == RecommendationCategory.WATER
    assert rec.action_id == "REVIEW_IRRIGATION_TIMING"
    # Verify NO unsupported volumetric prescriptions (e.g. no '20 L/m2')
    assert "l/m2" not in rec.action.lower()
    assert "liters" not in rec.action.lower()


def test_carbon_readiness_rule_scientific_boundary():
    rule = CarbonReadinessRule()
    zone = make_test_zone(affected=["carbon_readiness"], primary_issue="carbon_readiness")
    recs = rule.evaluate(zone, {})

    assert len(recs) == 1
    rec = recs[0]
    assert rec.category == RecommendationCategory.CARBON_READINESS
    assert rec.action_id == "EVALUATE_CARBON_PRACTICES"
    # Verify NO carbon credit or certification claims
    action_lower = rec.action.lower()
    assert "credit" not in action_lower
    assert "certif" not in action_lower
    assert "mrv" not in action_lower


def test_monitoring_rule():
    rule = MonitoringRule()
    zone = make_test_zone(confidence="LOW")
    recs = rule.evaluate(zone, {})

    assert len(recs) == 1
    assert recs[0].category == RecommendationCategory.MONITORING
    assert recs[0].action_id == "COLLECT_ADDITIONAL_SAMPLES"


def test_primary_issue_ordering_and_max_recommendations_limit():
    engine = RecommendationEngine(config=RecommendationConfig(max_recommendations_per_zone=2))
    zone = make_test_zone(affected=["nitrogen", "moisture", "ec"], primary_issue="moisture")

    # Pass dummy ZoneDetectionResult
    from fieldsense.zones import ZoneDetectionResult
    zone_res = ZoneDetectionResult(zones=[zone])
    res = engine.process(zone_res)

    assert len(res.recommendations) == 2
    # Moisture recommendation must be first because primary_issue == 'moisture'
    assert res.recommendations[0].category == RecommendationCategory.WATER
    assert res.recommendations[0].action_id == "REVIEW_IRRIGATION_TIMING"


def test_deduplication():
    # Duplicate rule passed to engine
    engine = RecommendationEngine(rules=[NutrientRule(), NutrientRule()])
    zone = make_test_zone(affected=["nitrogen"], primary_issue="nitrogen")

    from fieldsense.zones import ZoneDetectionResult
    res = engine.process(ZoneDetectionResult(zones=[zone]))

    # Deduplicated to 1 recommendation
    assert len(res.recommendations) == 1


def test_no_ai_library_dependencies():
    ai_libs = ["openai", "google.generativeai", "gemini", "langchain"]
    for lib in ai_libs:
        assert lib not in sys.modules


def test_end_to_end_recommendation_pipeline():
    """Complete End-to-End Integration Test (Sprints 1 through 7):

    VirtualSensorAdapter -> FieldSession -> ValidationEngine -> FieldIntelligenceEngine -> SpatialEngine -> ZoneDetectionEngine -> RecommendationEngine
    """
    # 1. Virtual Sensor Acquisition (25 points with unstable sample)
    adapter = VirtualSensorAdapter(seed=42, num_samples=25, scenario=FieldScenario.WITH_UNSTABLE)
    session = adapter.collect_session(session_id="SES-E2E-REC", field_name="Complete Pipeline Field")
    assert session.sample_count == 25

    # 2. Validation Engine
    val_engine = ValidationEngine()
    eligible_samples = val_engine.get_session_eligible_samples(session)
    assert len(eligible_samples) == 24

    # 3. Deterministic Intelligence Engine
    intel_engine = FieldIntelligenceEngine()
    intel_results = intel_engine.process_many(eligible_samples)
    assert len(intel_results) == 24

    # 4. Spatial Engine
    spatial_engine = SpatialEngine(config=SpatialConfig(grid_spacing_meters=10.0))
    spatial_result = spatial_engine.process(intel_results, eligible_samples)

    # 5. Zone Detection Engine
    zone_engine = ZoneDetectionEngine()
    zone_result = zone_engine.process(spatial_result)
    assert len(zone_result.zones) > 0

    # 6. Deterministic Recommendation Engine
    rec_engine = RecommendationEngine()
    rec_result = rec_engine.process(zone_result)

    # 7. Complete Pipeline Verifications
    assert isinstance(rec_result, RecommendationResult)
    assert len(rec_result.recommendations) > 0

    valid_zone_ids = {z.zone_id for z in zone_result.zones}
    for rec in rec_result.recommendations:
        assert isinstance(rec, Recommendation)
        assert rec.zone_id in valid_zone_ids
        assert rec.recommendation_id.startswith("REC-ZONE-")
        assert rec.evidence is not None
        assert rec.confidence in ["HIGH", "MEDIUM", "LOW"]
        # Confirm no unsupported chemical / dosage numbers
        assert "kg/acre" not in rec.action.lower()
        assert "liters" not in rec.action.lower()
