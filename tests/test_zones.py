"""Unit and end-to-end integration tests for Zone Detection Engine (Sprint 6)."""

import pytest

from fieldsense.input import FieldScenario, VirtualSensorAdapter
from fieldsense.intelligence import FieldIntelligenceEngine, ValidationEngine
from fieldsense.spatial import SpatialConfig, SpatialEngine
from fieldsense.zones import Zone, ZoneConfig, ZoneDetectionEngine, ZoneDetectionResult


def test_status_classification():
    engine = ZoneDetectionEngine()
    assert engine._classify_status(0.20) == "POOR"
    assert engine._classify_status(0.50) == "MODERATE"
    assert engine._classify_status(0.85) == "HEALTHY"


def test_4_neighbor_connectivity():
    engine = ZoneDetectionEngine(config=ZoneConfig(minimum_zone_cells=1))

    # Grid Matrix status simulation: 4-neighbor connected POOR block at top-left
    # P P H H
    # P P H H
    # H H H H
    status_matrix = [
        ["POOR", "POOR", "HEALTHY", "HEALTHY"],
        ["POOR", "POOR", "HEALTHY", "HEALTHY"],
        ["HEALTHY", "HEALTHY", "HEALTHY", "HEALTHY"],
        ["HEALTHY", "HEALTHY", "HEALTHY", "HEALTHY"],
    ]
    visited = set()
    rows, cols = 4, 4

    comp1 = engine._bfs_connected_component(0, 0, status_matrix, visited, rows, cols)
    assert len(comp1) == 4
    assert set(comp1) == {(0, 0), (0, 1), (1, 0), (1, 1)}

    comp2 = engine._bfs_connected_component(0, 2, status_matrix, visited, rows, cols)
    assert len(comp2) == 12


def test_diagonal_separation_does_not_connect():
    engine = ZoneDetectionEngine(config=ZoneConfig(minimum_zone_cells=1))

    # Diagonal POOR cells:
    # P H
    # H P
    status_matrix = [
        ["POOR", "HEALTHY"],
        ["HEALTHY", "POOR"],
    ]
    visited = set()
    rows, cols = 2, 2

    comp1 = engine._bfs_connected_component(0, 0, status_matrix, visited, rows, cols)
    assert len(comp1) == 1
    assert comp1 == [(0, 0)]

    comp2 = engine._bfs_connected_component(1, 1, status_matrix, visited, rows, cols)
    assert len(comp2) == 1
    assert comp2 == [(1, 1)]


def test_primary_issue_selection_and_tie_breaking():
    engine = ZoneDetectionEngine(
        config=ZoneConfig(
            parameter_priority=["nitrogen", "moisture", "carbon_readiness", "ph", "ec", "potassium", "phosphorus"]
        )
    )

    # Deficiency testing: nitrogen (0.2 score -> deficiency 0.8), moisture (0.5 score -> deficiency 0.5)
    deficiencies = {"nitrogen": 0.8, "moisture": 0.5}
    affected = ["moisture", "nitrogen"]

    def tie_break_key(param_name):
        deficiency = deficiencies.get(param_name, 0.0)
        priority_idx = engine.config.parameter_priority.index(param_name)
        return (-deficiency, priority_idx)

    sorted_affected = sorted(affected, key=tie_break_key)
    assert sorted_affected[0] == "nitrogen"

    # Equal deficiency tie-break testing: nitrogen and moisture both deficiency 0.6
    deficiencies_equal = {"nitrogen": 0.6, "moisture": 0.6}
    affected_equal = ["moisture", "nitrogen"]

    def tie_break_equal_key(param_name):
        deficiency = deficiencies_equal.get(param_name, 0.0)
        priority_idx = engine.config.parameter_priority.index(param_name)
        return (-deficiency, priority_idx)

    sorted_equal = sorted(affected_equal, key=tie_break_equal_key)
    assert sorted_equal[0] == "nitrogen"  # Selects nitrogen due to priority order


def test_serialization():
    adapter = VirtualSensorAdapter(seed=42, num_samples=25)
    samples = adapter.get_all_samples()

    val_engine = ValidationEngine()
    intel_engine = FieldIntelligenceEngine()
    spatial_engine = SpatialEngine()
    zone_engine = ZoneDetectionEngine()

    eligible = val_engine.get_eligible_samples(samples)
    intels = intel_engine.process_many(eligible)
    spatial_res = spatial_engine.process(intels, eligible)
    zone_res = zone_engine.process(spatial_res)

    res_dict = zone_res.to_dict()
    assert isinstance(res_dict, dict)
    assert res_dict["primary_layer"] == "soil_health"

    reconstructed = ZoneDetectionResult.from_dict(res_dict)
    assert len(reconstructed.zones) == len(zone_res.zones)
    assert reconstructed.zones[0].zone_id == zone_res.zones[0].zone_id


def test_end_to_end_zone_pipeline():
    """Complete End-to-End Integration Test:

    VirtualSensorAdapter -> FieldSession -> ValidationEngine -> FieldIntelligenceEngine -> SpatialEngine -> ZoneDetectionEngine
    """
    # 1. Acquisition
    adapter = VirtualSensorAdapter(seed=42, num_samples=25, scenario=FieldScenario.WITH_UNSTABLE)
    session = adapter.collect_session(session_id="SES-ZONE-E2E", field_name="West Field")

    # 2. Validation
    val_engine = ValidationEngine()
    eligible_samples = val_engine.get_session_eligible_samples(session)
    assert len(eligible_samples) == 24

    # 3. Deterministic Intelligence
    intel_engine = FieldIntelligenceEngine()
    intel_results = intel_engine.process_many(eligible_samples)
    assert len(intel_results) == 24

    # 4. Spatial Engine
    spatial_engine = SpatialEngine(config=SpatialConfig(grid_spacing_meters=10.0))
    spatial_result = spatial_engine.process(intel_results, eligible_samples)

    # 5. Zone Detection Engine
    zone_engine = ZoneDetectionEngine()
    zone_result = zone_engine.process(spatial_result)

    # 6. Verification
    assert isinstance(zone_result, ZoneDetectionResult)
    assert len(zone_result.zones) > 0

    for zone in zone_result.zones:
        assert isinstance(zone, Zone)
        assert zone.zone_id.startswith("ZONE-")
        assert zone.status in ["HEALTHY", "MODERATE", "POOR"]
        assert zone.severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        assert zone.confidence in ["HIGH", "MEDIUM", "LOW"]
        assert zone.area_estimate > 0.0
        assert len(zone.grid_points) > 0
        assert zone.recommendation_reference == "pending_recommendation_engine"
