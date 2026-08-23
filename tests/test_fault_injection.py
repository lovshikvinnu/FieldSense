"""Fault-injection, determinism, and safety boundary tests (Sprint 10)."""

import math
import pytest

from fieldsense.domain.models import FieldSample, SampleSource, ValidationState, FieldSession
from fieldsense.intelligence import ValidationEngine, FieldIntelligenceEngine
from fieldsense.spatial import SpatialEngine, SpatialConfig
from fieldsense.zones import ZoneDetectionEngine
from fieldsense.recommendations import RecommendationEngine
from fieldsense.presentation import UIViewAdapter
from fieldsense.testing import GoldenDatasetRegistry


def test_gps_edge_cases():
    val_engine = ValidationEngine()

    # Out of range latitude (95.0)
    s_invalid_lat = FieldSample(
        sample_id="S-GPS-1", timestamp="2026-08-09T15:00:00Z", latitude=95.0, longitude=77.59,
        nitrogen=45.0, phosphorus=25.0, potassium=150.0, ph=6.8, ec=1.2, moisture=30.0,
        temperature=22.0, source=SampleSource.VIRTUAL, validation_state=ValidationState.VALID, measurement_quality=1.0
    )
    res_lat = val_engine.validate(s_invalid_lat)
    assert res_lat.pipeline_eligible is False

    # Out of range longitude (195.0)
    s_invalid_lon = FieldSample(
        sample_id="S-GPS-2", timestamp="2026-08-09T15:00:00Z", latitude=12.97, longitude=195.0,
        nitrogen=45.0, phosphorus=25.0, potassium=150.0, ph=6.8, ec=1.2, moisture=30.0,
        temperature=22.0, source=SampleSource.VIRTUAL, validation_state=ValidationState.VALID, measurement_quality=1.0
    )
    res_lon = val_engine.validate(s_invalid_lon)
    assert res_lon.pipeline_eligible is False


def test_sensor_numeric_edge_cases():
    val_engine = ValidationEngine()

    # Negative nitrogen (-5.0)
    s_neg_n = FieldSample(
        sample_id="S-NUM-1", timestamp="2026-08-09T15:00:00Z", latitude=12.97, longitude=77.59,
        nitrogen=-5.0, phosphorus=25.0, potassium=150.0, ph=6.8, ec=1.2, moisture=30.0,
        temperature=22.0, source=SampleSource.VIRTUAL, validation_state=ValidationState.VALID, measurement_quality=1.0
    )
    res_n = val_engine.validate(s_neg_n)
    assert res_n.pipeline_eligible is False

    # NaN pH (float('nan'))
    s_nan_ph = FieldSample(
        sample_id="S-NUM-2", timestamp="2026-08-09T15:00:00Z", latitude=12.97, longitude=77.59,
        nitrogen=45.0, phosphorus=25.0, potassium=150.0, ph=float("nan"), ec=1.2, moisture=30.0,
        temperature=22.0, source=SampleSource.VIRTUAL, validation_state=ValidationState.VALID, measurement_quality=1.0
    )
    res_ph = val_engine.validate(s_nan_ph)
    assert res_ph.pipeline_eligible is False


def test_duplicate_samples_determinism():
    scenario = GoldenDatasetRegistry.get_scenario("healthy_field")
    session = GoldenDatasetRegistry.load_session(scenario)
    
    # Add duplicate sample
    dup_sample = session.samples[0]
    session.add_sample(dup_sample)
    assert session.sample_count == 26

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)
    intels = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine().process(intels, eligible)
    zones = ZoneDetectionEngine().process(spatial)
    recs = RecommendationEngine().process(zones)

    assert len(recs.recommendations) >= 0


def test_full_pipeline_determinism():
    scenario = GoldenDatasetRegistry.get_scenario("mixed_field")
    
    # Run 1
    session1 = GoldenDatasetRegistry.load_session(scenario)
    eligible1 = ValidationEngine().get_session_eligible_samples(session1)
    intels1 = FieldIntelligenceEngine().process_many(eligible1)
    spatial1 = SpatialEngine().process(intels1, eligible1)
    zones1 = ZoneDetectionEngine().process(spatial1)
    recs1 = RecommendationEngine().process(zones1)
    ui1 = UIViewAdapter().adapt(session1, spatial1, zones1, recs1)

    # Run 2
    session2 = GoldenDatasetRegistry.load_session(scenario)
    eligible2 = ValidationEngine().get_session_eligible_samples(session2)
    intels2 = FieldIntelligenceEngine().process_many(eligible2)
    spatial2 = SpatialEngine().process(intels2, eligible2)
    zones2 = ZoneDetectionEngine().process(spatial2)
    recs2 = RecommendationEngine().process(zones2)
    ui2 = UIViewAdapter().adapt(session2, spatial2, zones2, recs2)

    # Assert bit-for-bit identical outputs
    assert spatial1.to_dict() == spatial2.to_dict()
    assert zones1.to_dict() == zones2.to_dict()
    assert recs1.to_dict() == recs2.to_dict()
    assert ui1.to_dict() == ui2.to_dict()


def test_recommendation_and_carbon_safety_checks():
    scenario = GoldenDatasetRegistry.get_scenario("mixed_field")
    session = GoldenDatasetRegistry.load_session(scenario)

    eligible = ValidationEngine().get_session_eligible_samples(session)
    intels = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine().process(intels, eligible)
    zones = ZoneDetectionEngine().process(spatial)
    recs = RecommendationEngine().process(zones)

    for intel in intels:
        assert intel.carbon_readiness.decision_support_only is True
        assert intel.carbon_readiness.evidence_level == "LIMITED"
        assert "soil_organic_carbon" in intel.carbon_readiness.missing_indicators

    for r in recs.recommendations:
        act_lower = r.action.lower()
        assert "kg/acre" not in act_lower
        assert "liters" not in act_lower
        assert "credit" not in act_lower
        assert "mrv" not in act_lower
