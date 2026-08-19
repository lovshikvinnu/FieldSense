"""Unit and end-to-end integration tests for Spatial Engine (Sprint 5)."""

from datetime import datetime, timezone
import pytest

from fieldsense.domain import FieldSample, SampleSource, ValidationState
from fieldsense.input import FieldScenario, VirtualSensorAdapter
from fieldsense.intelligence import FieldIntelligenceEngine, ValidationEngine
from fieldsense.spatial import (
    FieldBounds,
    IDWInterpolator,
    LocalCoordinateConverter,
    SpatialConfig,
    SpatialCoverage,
    SpatialEngine,
    SpatialFieldResult,
    SpatialLayer,
)


def test_coordinate_conversion_cardinal_directions():
    ref_lat, ref_lon = 12.9716, 77.5946
    converter = LocalCoordinateConverter(ref_lat, ref_lon)

    # Reference point itself must map to (0, 0)
    x0, y0 = converter.to_local(ref_lat, ref_lon)
    assert abs(x0) < 1e-4
    assert abs(y0) < 1e-4

    # North movement (higher latitude) -> positive y
    _, y_north = converter.to_local(ref_lat + 0.001, ref_lon)
    assert y_north > 0.0

    # South movement (lower latitude) -> negative y
    _, y_south = converter.to_local(ref_lat - 0.001, ref_lon)
    assert y_south < 0.0

    # East movement (higher longitude) -> positive x
    x_east, _ = converter.to_local(ref_lat, ref_lon + 0.001)
    assert x_east > 0.0

    # West movement (lower longitude) -> negative x
    x_west, _ = converter.to_local(ref_lat, ref_lon - 0.001)
    assert x_west < 0.0

    # Roundtrip GPS -> Local -> GPS
    lat_rt, lon_rt = converter.to_gps(x_east, y_north)
    assert abs(lat_rt - (ref_lat + 0.001)) < 1e-5
    assert abs(lon_rt - (ref_lon + 0.001)) < 1e-5


def test_idw_exact_sample_coincidence():
    interpolator = IDWInterpolator(power=2.0, max_support_distance=100.0)
    sample_points = [
        (0.0, 0.0, 0.85),
        (20.0, 0.0, 0.50),
        (0.0, 20.0, 0.60),
    ]

    # Target exactly at sample 0 (distance = 0)
    gv = interpolator.interpolate_point(0.0, 0.0, sample_points)
    assert gv.value == 0.85
    assert gv.nearest_sample_distance == 0.0
    assert gv.supporting_sample_count == 1


def test_idw_interpolation_values():
    interpolator = IDWInterpolator(power=2.0, max_support_distance=100.0)
    sample_points = [
        (0.0, 0.0, 1.0),
        (10.0, 0.0, 0.0),
    ]

    # Midpoint at (5, 0): equal distance (5m) to both points -> interpolated average = 0.5
    gv = interpolator.interpolate_point(5.0, 0.0, sample_points)
    assert gv.value == 0.5
    assert gv.nearest_sample_distance == 5.0
    assert gv.supporting_sample_count == 2


def test_insufficient_data_behavior():
    engine = SpatialEngine()
    intel_engine = FieldIntelligenceEngine()

    # 0 samples -> ValueError
    with pytest.raises(ValueError, match="0 eligible samples"):
        engine.process([], [])

    # 1 sample (< 3 minimum required) -> bounds created, but interpolation value is None
    sample1 = FieldSample(
        sample_id="SMP-1",
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=45.0, phosphorus=20.0, potassium=150.0, ph=6.5, ec=1.2, moisture=30.0, temperature=25.0,
        measurement_quality=0.9, source=SampleSource.VIRTUAL, validation_state=ValidationState.VALID,
    )
    intel1 = intel_engine.process(sample1)
    res1 = engine.process([intel1], [sample1])

    assert isinstance(res1, SpatialFieldResult)
    assert len(res1.source_sample_ids) == 1
    # Interpolation layers return None for grid values when < 3 samples
    assert res1.layers["soil_health"].grid_values[0].value is None


def test_rejected_data_exclusion():
    engine = SpatialEngine()
    intel_engine = FieldIntelligenceEngine()

    sample_valid = FieldSample(
        sample_id="SMP-VALID",
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716, longitude=77.5946,
        nitrogen=45.0, phosphorus=20.0, potassium=150.0, ph=6.5, ec=1.2, moisture=30.0, temperature=25.0,
        measurement_quality=0.95, source=SampleSource.VIRTUAL, validation_state=ValidationState.VALID,
    )
    sample_rejected = FieldSample(
        sample_id="SMP-REJ",
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716, longitude=77.5946,
        nitrogen=45.0, phosphorus=20.0, potassium=150.0, ph=6.5, ec=1.2, moisture=30.0, temperature=25.0,
        measurement_quality=0.10, source=SampleSource.VIRTUAL, validation_state=ValidationState.VALID,
    )
    intel_valid = intel_engine.process(sample_valid)

    # Process with 1 valid + 1 rejected sample: rejected sample is excluded
    res = engine.process([intel_valid], [sample_valid, sample_rejected])
    assert res.source_sample_ids == ["SMP-VALID"]


def test_spatial_result_serialization():
    adapter = VirtualSensorAdapter(seed=42, num_samples=5)
    samples = adapter.get_all_samples()

    val_engine = ValidationEngine()
    intel_engine = FieldIntelligenceEngine()
    spatial_engine = SpatialEngine()

    eligible_samples = val_engine.get_eligible_samples(samples)
    intels = intel_engine.process_many(eligible_samples)
    spatial_res = spatial_engine.process(intels, eligible_samples)

    res_dict = spatial_res.to_dict()
    assert isinstance(res_dict, dict)
    assert res_dict["methodology_version"] == "0.1"

    reconstructed = SpatialFieldResult.from_dict(res_dict)
    assert reconstructed.bounds == spatial_res.bounds
    assert len(reconstructed.grid_points) == len(spatial_res.grid_points)
    assert list(reconstructed.layers.keys()) == list(spatial_res.layers.keys())


def test_end_to_end_pipeline_integration():
    """Complete End-to-End Pipeline Integration Test:

    VirtualSensorAdapter -> FieldSession -> ValidationEngine -> FieldIntelligenceEngine -> SpatialEngine
    """
    # 1. Virtual Sensor Adapter Acquisition
    adapter = VirtualSensorAdapter(seed=42, num_samples=25, scenario=FieldScenario.WITH_UNSTABLE)
    session = adapter.collect_session(session_id="SES-E2E-001", field_name="North Field Grid")
    assert session.sample_count == 25

    # 2. Validation Gatekeeper Evaluation
    val_engine = ValidationEngine()
    val_results = val_engine.validate_session(session)
    assert len(val_results) == 25
    eligible_samples = val_engine.get_session_eligible_samples(session)
    assert len(eligible_samples) == 24  # 1 unstable sample rejected

    # 3. Deterministic Intelligence Processing
    intel_engine = FieldIntelligenceEngine()
    intel_results = intel_engine.process_many(eligible_samples)
    assert len(intel_results) == 24

    # 4. Spatial Intelligence Engine Processing
    spatial_engine = SpatialEngine(config=SpatialConfig(grid_spacing_meters=10.0))
    spatial_result = spatial_engine.process(intel_results, eligible_samples)

    # 5. Verify Complete Spatial Result Output
    assert isinstance(spatial_result, SpatialFieldResult)
    assert len(spatial_result.source_sample_ids) == 24
    assert spatial_result.coverage.sample_count == 24

    # Verify bounds cover all eligible sample locations
    assert spatial_result.bounds.min_latitude <= spatial_result.bounds.max_latitude
    assert spatial_result.bounds.min_longitude <= spatial_result.bounds.max_longitude

    # Verify required spatial layers
    required_layers = ["soil_health", "nitrogen", "moisture", "carbon_readiness"]
    for l_id in required_layers:
        assert l_id in spatial_result.layers
        layer = spatial_result.layers[l_id]
        assert layer.layer_id == l_id
        assert len(layer.grid_values) == len(spatial_result.grid_points)

    # Verify coverage metrics
    assert spatial_result.coverage.grid_point_count > 0
    assert spatial_result.coverage.coverage_ratio > 0.0
