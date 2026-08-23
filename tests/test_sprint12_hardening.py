"""Final Architecture Audit, Serialization Round-Trip, and Contract Hardening Tests (Sprint 12)."""

from datetime import datetime, timezone

from fieldsense.domain.models import FieldSample, FieldSession, SampleSource, ValidationState, SessionStatus
from fieldsense.hardware.models import RawSensorReading, GPSPosition
from fieldsense.intelligence import ValidationEngine, FieldIntelligenceEngine
from fieldsense.intelligence.scoring.models import ParameterScore, SoilHealthResult, NitrogenResult, MoistureResult, CarbonReadinessResult, FieldIntelligenceResult
from fieldsense.spatial import FieldBounds, GridPoint, GridValue, SpatialLayer, SpatialCoverage, SpatialFieldResult, SpatialEngine
from fieldsense.zones import Zone, ZoneDetectionResult, ZoneDetectionEngine
from fieldsense.recommendations import Recommendation, RecommendationResult, RecommendationCategory, RecommendationPriority, RecommendationEngine
from fieldsense.presentation import UIFieldView, FieldSummary, GPSStatus, SamplingStatus, HealthSummary, MapView, MapPoint, UIZone, UIRecommendation, SystemStatus, UIViewAdapter
from fieldsense.hardware import HardwareSensorAdapter, MockHardwareTransport, VirtualGPSAdapter, DataSourceConfig, SensorAdapterFactory
from fieldsense.input import VirtualSensorAdapter


def test_field_sample_and_session_serialization_round_trip():
    dt_now = datetime(2026, 8, 9, 15, 0, 0, tzinfo=timezone.utc)
    sample = FieldSample(
        sample_id="SMP-AUDIT-01",
        timestamp=dt_now,
        latitude=12.9715,
        longitude=77.5945,
        nitrogen=45.0,
        phosphorus=25.0,
        potassium=150.0,
        ph=6.8,
        ec=1.2,
        moisture=30.0,
        temperature=22.0,
        source=SampleSource.HARDWARE,
        validation_state=ValidationState.VALID,
        measurement_quality=0.95,
    )
    d_sample = sample.to_dict()
    sample_rt = FieldSample.from_dict(d_sample)
    assert sample == sample_rt

    session = FieldSession(session_id="SES-AUDIT-01", field_name="Audit Field", created_at="2026-08-09T15:00:00Z")
    session.add_sample(sample)
    d_session = session.to_dict()
    session_rt = FieldSession.from_dict(d_session)
    assert session.session_id == session_rt.session_id
    assert session.sample_count == session_rt.sample_count == 1
    assert session.samples[0] == session_rt.samples[0]


def test_intelligence_spatial_zones_recommendations_ui_serialization_round_trip():
    # ParameterScore & FieldIntelligenceResult
    ps = ParameterScore(parameter="nitrogen", score=0.85, interpretation="OPTIMAL")
    sh_res = SoilHealthResult(score=0.85, component_scores=[ps])
    n_res = NitrogenResult(score=0.80)
    m_res = MoistureResult(score=0.90)
    c_res = CarbonReadinessResult(score=0.75)
    intel_res = FieldIntelligenceResult(sample_id="SMP-01", parameter_scores=[ps], soil_health=sh_res, nitrogen=n_res, moisture=m_res, carbon_readiness=c_res)
    intel_rt = FieldIntelligenceResult.from_dict(intel_res.to_dict())
    assert intel_res.sample_id == intel_rt.sample_id

    # SpatialFieldResult
    gp = GridPoint(x=0.0, y=0.0, latitude=12.97, longitude=77.59)
    gv = GridValue(value=0.85, nearest_sample_distance=5.0, supporting_sample_count=3)
    layer = SpatialLayer(layer_id="soil_health", layer_name="Soil Health", units="index", grid_values=[gv])
    cov = SpatialCoverage(sample_count=1, grid_point_count=1, covered_area_estimate=100.0, coverage_ratio=1.0)
    spatial_res = SpatialFieldResult(bounds=FieldBounds(12.96, 12.98, 77.58, 77.60), grid_points=[gp], layers={"soil_health": layer}, source_sample_ids=["SMP-01"], coverage=cov)
    spatial_rt = SpatialFieldResult.from_dict(spatial_res.to_dict())
    assert spatial_res.bounds.min_latitude == spatial_rt.bounds.min_latitude

    # ZoneDetectionResult
    zone = Zone(zone_id="ZONE-01", status="HEALTHY", severity="LOW", affected_parameters=["nitrogen"], primary_issue="nitrogen", confidence="HIGH", grid_points=[gp], sample_ids=["SMP-01"], centroid=(12.97, 77.59), area_estimate=100.0)
    z_res = ZoneDetectionResult(zones=[zone], primary_layer="soil_health")
    z_rt = ZoneDetectionResult.from_dict(z_res.to_dict())
    assert z_res.zones[0].zone_id == z_rt.zones[0].zone_id

    # RecommendationResult
    rec = Recommendation(recommendation_id="REC-01", zone_id="ZONE-01", category=RecommendationCategory.NUTRIENT, priority=RecommendationPriority.HIGH, action_id="REVIEW_N", action="Review nitrogen", reason="Low N", affected_parameters=["nitrogen"], evidence={}, confidence="HIGH")
    r_res = RecommendationResult(recommendations=[rec])
    r_rt = RecommendationResult.from_dict(r_res.to_dict())
    assert r_res.recommendations[0].recommendation_id == r_rt.recommendations[0].recommendation_id

    # UIFieldView
    summary = FieldSummary(field_name="Audit Field", session_id="SES-01", sample_count=1, valid_sample_count=1, rejected_sample_count=0, coverage_ratio=1.0, overall_soil_health=0.85, soil_health_status="HEALTHY")
    gps_status = GPSStatus(available=True, latitude=12.97, longitude=77.59, status="FIXED")
    samp_status = SamplingStatus(total_samples=1, valid_samples=1, rejected_samples=0, expected_samples=1, progress_ratio=1.0)
    health_summary = HealthSummary(score=0.85, status="HEALTHY", nitrogen_score=0.8, moisture_score=0.9, carbon_readiness_score=0.75)
    mp = MapPoint(latitude=12.97, longitude=77.59, value=0.85, support_distance=5.0, status="HEALTHY")
    map_view = MapView(bounds={"min_lat": 12.96, "max_lat": 12.98, "min_lon": 77.58, "max_lon": 77.60}, grid_by_layer={"soil_health": [mp]})
    ui_zone = UIZone(zone_id="ZONE-01", status="HEALTHY", severity="LOW", primary_issue="None", affected_parameters=[], confidence="HIGH", centroid=(12.97, 77.59), area_estimate=100.0, recommendation_count=1)
    ui_rec = UIRecommendation(recommendation_id="REC-01", zone_id="ZONE-01", category="NUTRIENT", priority="HIGH", action="Review nitrogen", reason="Low N", confidence="HIGH")
    sys_status = SystemStatus(offline_mode=True, data_source="VIRTUAL", application_status="READY")
    ui_view = UIFieldView(field=summary, gps_status=gps_status, sampling_status=samp_status, health_summary=health_summary, map=map_view, zones=[ui_zone], recommendations=[ui_rec], system_status=sys_status)
    ui_rt = UIFieldView.from_dict(ui_view.to_dict())
    assert ui_view.field.session_id == ui_rt.field.session_id


def test_end_to_end_contract_adapter_independence():
    """Verify that VirtualSensorAdapter and HardwareSensorAdapter feed into the EXACT SAME downstream pipeline."""
    v_adapter = SensorAdapterFactory.create_adapter(DataSourceConfig(source="VIRTUAL"))
    hw_adapter = HardwareSensorAdapter(transport=MockHardwareTransport(mode="NORMAL"), gps_adapter=VirtualGPSAdapter())
    hw_adapter.initialize()

    v_session = v_adapter.collect_session(session_id="SES-VIRT")
    hw_session = FieldSession(session_id="SES-HW", field_name="Hardware Field", created_at="2026-08-09T15:00:00Z")
    for _ in range(5):
        hw_session.add_sample(hw_adapter.acquire_sample())

    val_engine = ValidationEngine()
    v_eligible = val_engine.get_session_eligible_samples(v_session)
    hw_eligible = val_engine.get_session_eligible_samples(hw_session)

    v_intels = FieldIntelligenceEngine().process_many(v_eligible)
    hw_intels = FieldIntelligenceEngine().process_many(hw_eligible)

    v_spatial = SpatialEngine().process(v_intels, v_eligible)
    hw_spatial = SpatialEngine().process(hw_intels, hw_eligible)

    v_zones = ZoneDetectionEngine().process(v_spatial)
    hw_zones = ZoneDetectionEngine().process(hw_spatial)

    v_recs = RecommendationEngine().process(v_zones)
    hw_recs = RecommendationEngine().process(hw_zones)

    v_ui = UIViewAdapter().adapt(v_session, v_spatial, v_zones, v_recs)
    hw_ui = UIViewAdapter().adapt(hw_session, hw_spatial, hw_zones, hw_recs)

    assert v_ui.system_status.data_source == "VIRTUAL"
    assert hw_ui.system_status.data_source == "HARDWARE"
