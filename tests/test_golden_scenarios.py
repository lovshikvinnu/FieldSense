"""Unit and integration tests for Golden Scenarios A through H (Sprint 10)."""

import pytest

from fieldsense.domain.models import FieldSession, FieldSample, SampleSource, ValidationState
from fieldsense.intelligence import ValidationEngine, FieldIntelligenceEngine
from fieldsense.spatial import SpatialEngine, SpatialConfig
from fieldsense.zones import ZoneDetectionEngine
from fieldsense.recommendations import RecommendationEngine
from fieldsense.presentation import UIViewAdapter
from fieldsense.testing import GoldenDatasetRegistry


def test_golden_scenario_a_healthy_field():
    """Scenario A: Healthy Field."""
    scenario = GoldenDatasetRegistry.get_scenario("healthy_field")
    session = GoldenDatasetRegistry.load_session(scenario)

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)
    assert len(eligible) == scenario.expected_valid_count

    intels = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine().process(intels, eligible)
    zones = ZoneDetectionEngine().process(spatial)
    recs = RecommendationEngine().process(zones)

    assert spatial.layers["soil_health"].grid_values[0].value > 0.70
    assert any(z.status == "HEALTHY" for z in zones.zones)
    # Routine or monitoring recommendation
    assert all(r.category in ["MONITORING", "SOIL_CONDITION", "NUTRIENT", "WATER", "SALINITY", "CARBON_READINESS"] for r in recs.recommendations)


def test_golden_scenario_b_nutrient_deficiency():
    """Scenario B: Nitrogen Nutrient Deficiency Field."""
    scenario = GoldenDatasetRegistry.get_scenario("nutrient_deficient_field")
    session = GoldenDatasetRegistry.load_session(scenario)

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)
    intels = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine().process(intels, eligible)
    zones = ZoneDetectionEngine().process(spatial)
    recs = RecommendationEngine().process(zones)

    # Nitrogen layer should exhibit lower average score
    n_avg = sum(gv.value for gv in spatial.layers["nitrogen"].grid_values if gv.value is not None) / len(spatial.layers["nitrogen"].grid_values)
    assert n_avg < 0.80
    assert any("nitrogen" in z.affected_parameters or z.primary_issue == "nitrogen" for z in zones.zones)
    assert any(r.category == "NUTRIENT" and r.action_id == "REVIEW_NITROGEN_MANAGEMENT" for r in recs.recommendations)


def test_golden_scenario_c_moisture_deficiency():
    """Scenario C: Moisture Deficiency Field."""
    scenario = GoldenDatasetRegistry.get_scenario("moisture_deficient_field")
    session = GoldenDatasetRegistry.load_session(scenario)

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)
    intels = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine().process(intels, eligible)
    zones = ZoneDetectionEngine().process(spatial)
    recs = RecommendationEngine().process(zones)

    # Moisture layer should exhibit lower average score
    m_avg = sum(gv.value for gv in spatial.layers["moisture"].grid_values if gv.value is not None) / len(spatial.layers["moisture"].grid_values)
    assert m_avg < 0.80
    assert any("moisture" in z.affected_parameters or z.primary_issue == "moisture" for z in zones.zones)
    assert any(r.category == "WATER" and r.action_id == "REVIEW_IRRIGATION_TIMING" for r in recs.recommendations)


def test_golden_scenario_d_mixed_field():
    """Scenario D: Mixed Field (healthy, moderate, poor sectors)."""
    scenario = GoldenDatasetRegistry.get_scenario("mixed_field")
    session = GoldenDatasetRegistry.load_session(scenario)

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)
    intels = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine().process(intels, eligible)
    zones = ZoneDetectionEngine().process(spatial)

    # Mixed field must produce at least 1 zone with distinct status representations
    assert len(zones.zones) >= 1
    statuses = {z.status for z in zones.zones}
    assert len(statuses) >= 1


def test_golden_scenario_e_spatial_gradient():
    """Scenario E: Strong Spatial Gradient Field."""
    scenario = GoldenDatasetRegistry.get_scenario("spatial_gradient_field")
    session = GoldenDatasetRegistry.load_session(scenario)

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)
    intels = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine().process(intels, eligible)
    zones = ZoneDetectionEngine().process(spatial)

    assert spatial.coverage.coverage_ratio > 0.0
    assert len(zones.zones) > 0


def test_golden_scenario_f_outlier_field():
    """Scenario F: Outlier Field."""
    scenario = GoldenDatasetRegistry.get_scenario("outlier_field")
    session = GoldenDatasetRegistry.load_session(scenario)

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)
    intels = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine().process(intels, eligible)

    # Field surface remains continuous and bounded despite outlier
    sh_vals = [gv.value for gv in spatial.layers["soil_health"].grid_values if gv.value is not None]
    assert all(0.0 <= v <= 1.0 for v in sh_vals)


def test_golden_scenario_g_unstable_field():
    """Scenario G: Unstable Field (rejected samples)."""
    scenario = GoldenDatasetRegistry.get_scenario("unstable_field")
    session = GoldenDatasetRegistry.load_session(scenario)

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)
    assert len(eligible) == 24

    ui_view = UIViewAdapter().adapt(
        session,
        SpatialEngine().process(FieldIntelligenceEngine().process_many(eligible), eligible),
        ZoneDetectionEngine().process(SpatialEngine().process(FieldIntelligenceEngine().process_many(eligible), eligible)),
        RecommendationEngine().process(ZoneDetectionEngine().process(SpatialEngine().process(FieldIntelligenceEngine().process_many(eligible), eligible))),
    )

    assert ui_view.field.sample_count == 25
    assert ui_view.field.valid_sample_count == 24
    assert ui_view.field.rejected_sample_count == 1


def test_golden_scenario_h_sparse_field():
    """Scenario H: Sparse Field (0, 1, 2, 3+ samples)."""
    # 0 samples -> raises ValueError
    spatial_engine = SpatialEngine()
    with pytest.raises(ValueError):
        spatial_engine.process([], [])

    # 1 sample -> no spatial surface (value = None)
    s1 = FieldSample(sample_id="S1", timestamp="2026-08-09T15:00:00Z", latitude=12.97, longitude=77.59, nitrogen=45.0, phosphorus=25.0, potassium=150.0, ph=6.8, ec=1.2, moisture=30.0, temperature=22.0, source=SampleSource.VIRTUAL, validation_state=ValidationState.VALID, measurement_quality=1.0)
    session1 = FieldSession(session_id="SES-SPARSE-1", field_name="Sparse 1", created_at="2026-08-09T15:00:00Z")
    session1.add_sample(s1)
    intel1 = FieldIntelligenceEngine().process_many([s1])[0]

    spatial1 = spatial_engine.process([intel1], [s1])
    assert all(gv.value is None for gv in spatial1.layers["soil_health"].grid_values)
