"""Unit and end-to-end integration tests for UI Presentation Layer (Sprint 8)."""

import pytest

from fieldsense.input import FieldScenario, VirtualSensorAdapter
from fieldsense.intelligence import FieldIntelligenceEngine, ValidationEngine
from fieldsense.spatial import SpatialConfig, SpatialEngine
from fieldsense.zones import ZoneDetectionEngine
from fieldsense.recommendations import RecommendationEngine
from fieldsense.presentation import (
    FieldSummary,
    GPSStatus,
    HealthSummary,
    LocalUIRenderer,
    MapPoint,
    MapView,
    SamplingStatus,
    SystemStatus,
    UIFieldView,
    UIRecommendation,
    UIViewAdapter,
    UIZone,
)


def test_ui_model_serialization():
    field_sum = FieldSummary(
        field_name="North Field",
        session_id="SES-001",
        sample_count=25,
        valid_sample_count=24,
        rejected_sample_count=1,
        coverage_ratio=0.96,
        overall_soil_health=0.72,
        soil_health_status="MODERATE",
    )
    gps_stat = GPSStatus(available=True, latitude=12.9716, longitude=77.5946, status="FIXED", mode="SIMULATED")
    samp_stat = SamplingStatus(total_samples=25, valid_samples=24, rejected_samples=1, expected_samples=25, progress_ratio=0.96)
    health_sum = HealthSummary(score=0.72, status="MODERATE", nitrogen_score=0.70, moisture_score=0.75, carbon_readiness_score=0.68)
    
    mp = MapPoint(latitude=12.9716, longitude=77.5946, value=0.75, support_distance=10.0, status="HEALTHY")
    map_view = MapView(bounds={"min_latitude": 12.9, "max_latitude": 13.0, "min_longitude": 77.5, "max_longitude": 77.6}, grid_by_layer={"soil_health": [mp]})
    
    ui_zone = UIZone(zone_id="ZONE-01", status="POOR", severity="HIGH", primary_issue="nitrogen", affected_parameters=["nitrogen"], confidence="HIGH", centroid=(12.97, 77.59), area_estimate=400.0, recommendation_count=1)
    ui_rec = UIRecommendation(recommendation_id="REC-01", zone_id="ZONE-01", category="NUTRIENT", priority="HIGH", action="Review N", reason="N deficiency", confidence="HIGH")
    sys_stat = SystemStatus(application_status="READY", data_source="VIRTUAL", processing_status="COMPLETE", offline_mode=True)

    root_view = UIFieldView(
        field=field_sum,
        gps_status=gps_stat,
        sampling_status=samp_stat,
        health_summary=health_sum,
        map=map_view,
        zones=[ui_zone],
        recommendations=[ui_rec],
        system_status=sys_stat,
    )

    dict_repr = root_view.to_dict()
    assert dict_repr["field"]["field_name"] == "North Field"
    assert dict_repr["system_status"]["offline_mode"] is True

    reconstructed = UIFieldView.from_dict(dict_repr)
    assert reconstructed.field.session_id == "SES-001"
    assert len(reconstructed.zones) == 1


def test_ui_adapter_data_integrity_and_no_recalculation():
    # Setup backend simulation
    adapter = VirtualSensorAdapter(seed=42, num_samples=25, scenario=FieldScenario.WITH_UNSTABLE)
    session = adapter.collect_session(session_id="SES-UI-TEST", field_name="UI Test Field")

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)

    intel_engine = FieldIntelligenceEngine()
    intels = intel_engine.process_many(eligible)

    spatial_engine = SpatialEngine()
    spatial = spatial_engine.process(intels, eligible)

    zone_engine = ZoneDetectionEngine()
    zones = zone_engine.process(spatial)

    rec_engine = RecommendationEngine()
    recs = rec_engine.process(zones)

    # Adapt to UI
    ui_adapter = UIViewAdapter()
    ui_view = ui_adapter.adapt(session, spatial, zones, recs, expected_samples=25)

    assert isinstance(ui_view, UIFieldView)
    assert ui_view.field.sample_count == 25
    assert ui_view.field.valid_sample_count == 24
    assert ui_view.field.rejected_sample_count == 1
    assert ui_view.system_status.offline_mode is True
    assert ui_view.system_status.data_source == "VIRTUAL"

    # Layer mapping check
    assert "soil_health" in ui_view.map.grid_by_layer
    assert "nitrogen" in ui_view.map.grid_by_layer
    assert "moisture" in ui_view.map.grid_by_layer
    assert "carbon_readiness" in ui_view.map.grid_by_layer

    # Zone and recommendation mapping check
    assert len(ui_view.zones) == len(zones.zones)
    assert len(ui_view.recommendations) == len(recs.recommendations)


def test_local_html_renderer():
    adapter = VirtualSensorAdapter(seed=42, num_samples=25)
    session = adapter.collect_session(session_id="SES-HTML-TEST")

    val_engine = ValidationEngine()
    eligible = val_engine.get_session_eligible_samples(session)
    intels = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine().process(intels, eligible)
    zones = ZoneDetectionEngine().process(spatial)
    recs = RecommendationEngine().process(zones)

    ui_view = UIViewAdapter().adapt(session, spatial, zones, recs)
    renderer = LocalUIRenderer()
    html = renderer.render_html(ui_view)

    assert "<!DOCTYPE html>" in html
    assert "FIELDSENSE AI" in html
    assert "OFFLINE MODE" in html
    assert "fieldMapSvg" in html
    assert "layerSelect" in html
    # Ensure zero external network resources (no external src=http or href=http)
    assert 'src="http' not in html
    assert 'href="http' not in html


def test_complete_end_to_end_pipeline_with_ui():
    """Complete End-to-End FieldSense AI Pipeline Integration Test (Sprints 1 through 8):

    VirtualSensorAdapter -> FieldSession -> ValidationEngine -> FieldIntelligenceEngine -> SpatialEngine -> ZoneDetectionEngine -> RecommendationEngine -> UIViewAdapter -> LocalUIRenderer
    """
    # 1. Virtual Sensor Acquisition (25 samples)
    adapter = VirtualSensorAdapter(seed=42, num_samples=25, scenario=FieldScenario.WITH_UNSTABLE)
    session = adapter.collect_session(session_id="SES-E2E-UI", field_name="Complete FieldSense Pipeline")
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
    assert spatial_result.bounds is not None

    # 5. Zone Detection Engine
    zone_engine = ZoneDetectionEngine()
    zone_result = zone_engine.process(spatial_result)
    assert len(zone_result.zones) > 0

    # 6. Recommendation Engine
    rec_engine = RecommendationEngine()
    rec_result = rec_engine.process(zone_result)
    assert rec_result is not None

    # 7. UI View Adapter
    ui_adapter = UIViewAdapter()
    ui_view = ui_adapter.adapt(session, spatial_result, zone_result, rec_result)
    assert ui_view.field.valid_sample_count == 24
    assert ui_view.field.rejected_sample_count == 1

    # 8. Local Offline HTML Renderer
    renderer = LocalUIRenderer()
    html_output = renderer.render_html(ui_view)
    assert "FIELDSENSE AI" in html_output
    assert "OFFLINE MODE" in html_output
    assert len(html_output) > 1000
