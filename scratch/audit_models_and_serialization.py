"""Scratch script to perform model serialization round-trip audit across all subsystems."""

from datetime import datetime, timezone

from fieldsense.domain.models import FieldSample, FieldSession, SampleSource, ValidationState, SessionStatus
from fieldsense.hardware.models import RawSensorReading, GPSPosition, HardwareReadinessState, HardwareErrorCode, HardwareError
from fieldsense.intelligence.scoring.models import ParameterScore, SoilHealthResult, NitrogenResult, MoistureResult, CarbonReadinessResult, FieldIntelligenceResult
from fieldsense.spatial import FieldBounds, GridPoint, GridValue, SpatialLayer, SpatialCoverage, SpatialFieldResult, SpatialConfig
from fieldsense.zones import Zone, ZoneDetectionResult, ZoneConfig
from fieldsense.recommendations import Recommendation, RecommendationResult, RecommendationCategory, RecommendationPriority
from fieldsense.presentation import UIFieldView, FieldSummary, GPSStatus, SamplingStatus, HealthSummary, MapView, MapPoint, UIZone, UIRecommendation, SystemStatus


def audit_roundtrips():
    print("=== STARTING MODEL SERIALIZATION ROUND-TRIP AUDIT ===")

    dt_now = datetime(2026, 8, 9, 15, 0, 0, tzinfo=timezone.utc)

    # 1. FieldSample
    s = FieldSample(
        sample_id="SMP-001",
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
        source=SampleSource.VIRTUAL,
        validation_state=ValidationState.VALID,
        measurement_quality=0.95,
    )
    d_s = s.to_dict()
    s_rt = FieldSample.from_dict(d_s)
    assert s == s_rt, "FieldSample round-trip mismatch!"
    print("[OK] FieldSample serialization round-trip verified.")

    # 2. FieldSession
    session = FieldSession(session_id="SES-001", field_name="Test Field", created_at="2026-08-09T15:00:00Z")
    session.add_sample(s)
    d_ses = session.to_dict()
    ses_rt = FieldSession.from_dict(d_ses)
    assert session.session_id == ses_rt.session_id
    assert session.sample_count == ses_rt.sample_count == 1
    assert session.samples[0] == ses_rt.samples[0]
    print("[OK] FieldSession serialization round-trip verified.")

    # 3. RawSensorReading & GPSPosition
    raw_reading = RawSensorReading(nitrogen=10.0, phosphorus=20.0, potassium=30.0, ph=6.5, ec=1.0, moisture=25.0, temperature=20.0)
    assert raw_reading.to_dict()["nitrogen"] == 10.0
    gps_pos = GPSPosition(latitude=12.97, longitude=77.59, fix_valid=True)
    assert gps_pos.to_dict()["fix_valid"] is True
    print("[OK] RawSensorReading & GPSPosition serialization verified.")

    # 4. ParameterScore & FieldIntelligenceResult
    ps = ParameterScore(parameter="nitrogen", score=0.85, interpretation="OPTIMAL")
    assert ps.to_dict()["score"] == 0.85
    ps_rt = ParameterScore.from_dict(ps.to_dict())
    assert ps == ps_rt

    sh_res = SoilHealthResult(score=0.85, component_scores=[ps])
    n_res = NitrogenResult(score=0.80)
    m_res = MoistureResult(score=0.90)
    c_res = CarbonReadinessResult(score=0.75)
    intel_res = FieldIntelligenceResult(sample_id="SMP-001", parameter_scores=[ps], soil_health=sh_res, nitrogen=n_res, moisture=m_res, carbon_readiness=c_res)
    intel_rt = FieldIntelligenceResult.from_dict(intel_res.to_dict())
    assert intel_res.sample_id == intel_rt.sample_id
    assert intel_res.soil_health.score == intel_rt.soil_health.score
    print("[OK] Intelligence scoring models serialization round-trip verified.")

    # 5. SpatialFieldResult
    gp = GridPoint(x=0.0, y=0.0, latitude=12.97, longitude=77.59)
    gv = GridValue(value=0.85, nearest_sample_distance=5.0, supporting_sample_count=3)
    layer = SpatialLayer(layer_id="soil_health", layer_name="Soil Health", units="index", grid_values=[gv])
    cov = SpatialCoverage(sample_count=1, grid_point_count=1, covered_area_estimate=100.0, coverage_ratio=1.0)
    spatial_res = SpatialFieldResult(bounds=FieldBounds(12.96, 12.98, 77.58, 77.60), grid_points=[gp], layers={"soil_health": layer}, source_sample_ids=["SMP-001"], coverage=cov)
    d_spatial = spatial_res.to_dict()
    spatial_rt = SpatialFieldResult.from_dict(d_spatial)
    assert spatial_res.bounds.min_latitude == spatial_rt.bounds.min_latitude
    assert len(spatial_rt.grid_points) == 1
    print("[OK] SpatialFieldResult serialization round-trip verified.")

    # 6. Zone & ZoneDetectionResult
    zone = Zone(zone_id="ZONE-01", status="HEALTHY", severity="LOW", affected_parameters=["nitrogen"], primary_issue="nitrogen", confidence="HIGH", grid_points=[gp], sample_ids=["SMP-001"], centroid=(12.97, 77.59), area_estimate=100.0)
    z_res = ZoneDetectionResult(zones=[zone], primary_layer="soil_health")
    d_z = z_res.to_dict()
    z_rt = ZoneDetectionResult.from_dict(d_z)
    assert z_res.zones[0].zone_id == z_rt.zones[0].zone_id
    print("[OK] ZoneDetectionResult serialization round-trip verified.")

    # 7. Recommendation & RecommendationResult
    rec = Recommendation(recommendation_id="REC-001", zone_id="ZONE-01", category=RecommendationCategory.NUTRIENT, priority=RecommendationPriority.HIGH, action_id="REVIEW_NITROGEN", action="Consider nitrogen management", reason="Low N index", affected_parameters=["nitrogen"], evidence={"n_score": 0.3}, confidence="HIGH")
    r_res = RecommendationResult(recommendations=[rec])
    d_r = r_res.to_dict()
    r_rt = RecommendationResult.from_dict(d_r)
    assert r_res.recommendations[0].recommendation_id == r_rt.recommendations[0].recommendation_id
    print("[OK] RecommendationResult serialization round-trip verified.")

    # 8. UIFieldView
    summary = FieldSummary(field_name="Test Field", session_id="SES-001", sample_count=1, valid_sample_count=1, rejected_sample_count=0, coverage_ratio=1.0, overall_soil_health=0.85, soil_health_status="HEALTHY")
    gps_status = GPSStatus(available=True, latitude=12.97, longitude=77.59, status="FIXED")
    samp_status = SamplingStatus(total_samples=1, valid_samples=1, rejected_samples=0, expected_samples=1, progress_ratio=1.0)
    health_summary = HealthSummary(score=0.85, status="HEALTHY", nitrogen_score=0.8, moisture_score=0.9, carbon_readiness_score=0.75)
    mp = MapPoint(latitude=12.97, longitude=77.59, value=0.85, support_distance=5.0, status="HEALTHY")
    map_view = MapView(bounds={"min_lat": 12.96, "max_lat": 12.98, "min_lon": 77.58, "max_lon": 77.60}, grid_by_layer={"soil_health": [mp]})
    ui_zone = UIZone(zone_id="ZONE-01", status="HEALTHY", severity="LOW", primary_issue="None", affected_parameters=[], confidence="HIGH", centroid=(12.97, 77.59), area_estimate=100.0, recommendation_count=1)
    ui_rec = UIRecommendation(recommendation_id="REC-001", zone_id="ZONE-01", category="NUTRIENT", priority="HIGH", action="Consider nitrogen management", reason="Low N index", confidence="HIGH")
    sys_status = SystemStatus(offline_mode=True, data_source="VIRTUAL", application_status="READY")
    ui_view = UIFieldView(field=summary, gps_status=gps_status, sampling_status=samp_status, health_summary=health_summary, map=map_view, zones=[ui_zone], recommendations=[ui_rec], system_status=sys_status)
    d_ui = ui_view.to_dict()
    ui_rt = UIFieldView.from_dict(d_ui)
    assert ui_view.field.session_id == ui_rt.field.session_id
    assert ui_view.health_summary.score == ui_rt.health_summary.score
    print("[OK] UIFieldView serialization round-trip verified.")

    print("=== ALL MODEL SERIALIZATION ROUND-TRIPS PASSED CLEANLY ===")


if __name__ == "__main__":
    audit_roundtrips()
