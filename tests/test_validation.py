"""Unit tests for ValidationEngine and pipeline eligibility."""

from datetime import datetime, timezone
import math
import pytest

from fieldsense.domain import (
    FieldSample,
    FieldSession,
    SampleSource,
    ValidationState,
)
from fieldsense.input import FieldScenario, VirtualSensorAdapter
from fieldsense.intelligence.validation import (
    ValidationConfig,
    ValidationEngine,
    ValidationReason,
    ValidationResult,
)


def make_valid_sample(sample_id: str = "SMP-VAL-001") -> FieldSample:
    """Helper factory to create a completely valid FieldSample."""
    return FieldSample(
        sample_id=sample_id,
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=45.0,
        phosphorus=20.0,
        potassium=150.0,
        ph=6.5,
        ec=1.2,
        moisture=30.0,
        temperature=25.0,
        measurement_quality=0.95,
        source=SampleSource.VIRTUAL,
        validation_state=ValidationState.VALID,
    )


def test_basic_valid_sample():
    engine = ValidationEngine()
    sample = make_valid_sample()
    res = engine.validate(sample)

    assert isinstance(res, ValidationResult)
    assert res.sample_id == "SMP-VAL-001"
    assert res.state == ValidationState.VALID
    assert res.pipeline_eligible is True
    assert res.reasons == []


def test_missing_data_rejection():
    engine = ValidationEngine()

    # Missing measurement value (nitrogen = None)
    sample_no_n = FieldSample(
        sample_id="SMP-NO-N",
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=None,  # type: ignore
        phosphorus=20.0,
        potassium=150.0,
        ph=6.5,
        ec=1.2,
        moisture=30.0,
        temperature=25.0,
        measurement_quality=0.95,
        source=SampleSource.VIRTUAL,
    )
    res_n = engine.validate(sample_no_n)
    assert res_n.state == ValidationState.REJECTED
    assert res_n.pipeline_eligible is False
    assert ValidationReason.MISSING_VALUE in res_n.reasons

    # Missing GPS coordinate (latitude = None)
    sample_no_gps = FieldSample(
        sample_id="SMP-NO-GPS",
        timestamp=datetime.now(timezone.utc),
        latitude=None,  # type: ignore
        longitude=77.5946,
        nitrogen=45.0,
        phosphorus=20.0,
        potassium=150.0,
        ph=6.5,
        ec=1.2,
        moisture=30.0,
        temperature=25.0,
        measurement_quality=0.95,
        source=SampleSource.VIRTUAL,
    )
    res_gps = engine.validate(sample_no_gps)
    assert res_gps.state == ValidationState.REJECTED
    assert res_gps.pipeline_eligible is False
    assert ValidationReason.MISSING_VALUE in res_gps.reasons


def test_numeric_validity_and_zero_handling():
    engine = ValidationEngine()

    # Test zero values (0.0 is valid numeric data, NOT missing)
    zero_sample = FieldSample(
        sample_id="SMP-ZERO",
        timestamp=datetime.now(timezone.utc),
        latitude=0.0,
        longitude=0.0,
        nitrogen=0.0,
        phosphorus=0.0,
        potassium=0.0,
        ph=7.0,
        ec=0.0,
        moisture=0.0,
        temperature=0.0,
        measurement_quality=0.9,
        source=SampleSource.VIRTUAL,
    )
    res_zero = engine.validate(zero_sample)
    assert res_zero.state == ValidationState.VALID
    assert res_zero.pipeline_eligible is True

    # Test NaN
    nan_sample = FieldSample(
        sample_id="SMP-NAN",
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=float("nan"),
        phosphorus=20.0,
        potassium=150.0,
        ph=6.5,
        ec=1.2,
        moisture=30.0,
        temperature=25.0,
        measurement_quality=0.95,
        source=SampleSource.VIRTUAL,
    )
    res_nan = engine.validate(nan_sample)
    assert res_nan.state == ValidationState.REJECTED
    assert res_nan.pipeline_eligible is False
    assert ValidationReason.INVALID_NUMERIC_VALUE in res_nan.reasons

    # Test Infinity
    inf_sample = FieldSample(
        sample_id="SMP-INF",
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=float("inf"),
        phosphorus=20.0,
        potassium=150.0,
        ph=6.5,
        ec=1.2,
        moisture=30.0,
        temperature=25.0,
        measurement_quality=0.95,
        source=SampleSource.VIRTUAL,
    )
    res_inf = engine.validate(inf_sample)
    assert res_inf.state == ValidationState.REJECTED
    assert res_inf.pipeline_eligible is False
    assert ValidationReason.INVALID_NUMERIC_VALUE in res_inf.reasons


def test_gps_validation_limits():
    engine = ValidationEngine()
    sample = make_valid_sample()

    # Valid bounds test
    assert engine.validate(sample).state == ValidationState.VALID

    # Latitude > 90
    s_lat_high = FieldSample(**{**sample.to_dict(), "sample_id": "LAT-HIGH", "latitude": 90.001, "source": SampleSource.VIRTUAL, "validation_state": ValidationState.VALID})
    res = engine.validate(s_lat_high)
    assert res.state == ValidationState.REJECTED
    assert ValidationReason.GPS_OUT_OF_RANGE in res.reasons

    # Latitude < -90
    s_lat_low = FieldSample(**{**sample.to_dict(), "sample_id": "LAT-LOW", "latitude": -90.5, "source": SampleSource.VIRTUAL, "validation_state": ValidationState.VALID})
    assert engine.validate(s_lat_low).state == ValidationState.REJECTED

    # Longitude > 180
    s_lon_high = FieldSample(**{**sample.to_dict(), "sample_id": "LON-HIGH", "longitude": 180.1, "source": SampleSource.VIRTUAL, "validation_state": ValidationState.VALID})
    assert engine.validate(s_lon_high).state == ValidationState.REJECTED

    # Longitude < -180
    s_lon_low = FieldSample(**{**sample.to_dict(), "sample_id": "LON-LOW", "longitude": -180.1, "source": SampleSource.VIRTUAL, "validation_state": ValidationState.VALID})
    assert engine.validate(s_lon_low).state == ValidationState.REJECTED


def test_measurement_range_sanity_limits():
    engine = ValidationEngine()

    # pH out of range (< 3.0 or > 10.0)
    s_ph_low = FieldSample(**{**make_valid_sample().to_dict(), "sample_id": "PH-LOW", "ph": 2.5, "source": SampleSource.VIRTUAL, "validation_state": ValidationState.VALID})
    res_ph = engine.validate(s_ph_low)
    assert res_ph.state == ValidationState.REJECTED
    assert ValidationReason.MEASUREMENT_OUT_OF_RANGE in res_ph.reasons

    # Nitrogen above sanity range (> 500.0)
    s_n_high = FieldSample(**{**make_valid_sample().to_dict(), "sample_id": "N-HIGH", "nitrogen": 600.0, "source": SampleSource.VIRTUAL, "validation_state": ValidationState.VALID})
    res_n = engine.validate(s_n_high)
    assert res_n.state == ValidationState.REJECTED
    assert ValidationReason.MEASUREMENT_OUT_OF_RANGE in res_n.reasons


def test_measurement_quality_thresholds():
    engine = ValidationEngine()
    base = make_valid_sample()

    # Good quality (>= 0.70) -> VALID, eligible
    s_good = FieldSample(**{**base.to_dict(), "sample_id": "Q-GOOD", "measurement_quality": 0.85, "source": SampleSource.VIRTUAL, "validation_state": ValidationState.VALID})
    res_g = engine.validate(s_good)
    assert res_g.state == ValidationState.VALID
    assert res_g.pipeline_eligible is True

    # Low quality warning (0.30 <= q < 0.70) -> VALID_WITH_WARNING, eligible
    s_warn = FieldSample(**{**base.to_dict(), "sample_id": "Q-WARN", "measurement_quality": 0.50, "source": SampleSource.VIRTUAL, "validation_state": ValidationState.VALID})
    res_w = engine.validate(s_warn)
    assert res_w.state == ValidationState.VALID_WITH_WARNING
    assert res_w.pipeline_eligible is True
    assert ValidationReason.LOW_MEASUREMENT_QUALITY in res_w.reasons

    # Unusable quality (< 0.30) -> REJECTED, not eligible
    s_unusable = FieldSample(**{**base.to_dict(), "sample_id": "Q-UNUSABLE", "measurement_quality": 0.15, "source": SampleSource.VIRTUAL, "validation_state": ValidationState.VALID})
    res_u = engine.validate(s_unusable)
    assert res_u.state == ValidationState.REJECTED
    assert res_u.pipeline_eligible is False
    assert ValidationReason.UNSTABLE_MEASUREMENT in res_u.reasons


def test_unstable_simulator_scenario():
    # Sprint 2 simulator in WITH_UNSTABLE scenario
    adapter = VirtualSensorAdapter(seed=42, num_samples=25, scenario=FieldScenario.WITH_UNSTABLE)
    samples = adapter.get_all_samples()

    engine = ValidationEngine()
    results = engine.validate_many(samples)

    unstable_idx = adapter.unstable_index
    assert unstable_idx is not None

    unstable_res = results[unstable_idx]
    assert unstable_res.state == ValidationState.REJECTED
    assert unstable_res.pipeline_eligible is False
    assert ValidationReason.UNSTABLE_MEASUREMENT in unstable_res.reasons


def test_multiple_validation_failures():
    engine = ValidationEngine()

    # Sample with invalid GPS, out of range pH, and unusable measurement quality
    bad_sample = FieldSample(
        sample_id="SMP-BAD-MULTI",
        timestamp=datetime.now(timezone.utc),
        latitude=100.0,       # GPS out of range
        longitude=77.5946,
        nitrogen=45.0,
        phosphorus=20.0,
        potassium=150.0,
        ph=1.5,               # Measurement out of range
        ec=1.2,
        moisture=30.0,
        temperature=25.0,
        measurement_quality=0.10, # Unstable measurement
        source=SampleSource.VIRTUAL,
    )

    res = engine.validate(bad_sample)
    assert res.state == ValidationState.REJECTED
    assert res.pipeline_eligible is False
    assert ValidationReason.GPS_OUT_OF_RANGE in res.reasons
    assert ValidationReason.MEASUREMENT_OUT_OF_RANGE in res.reasons
    assert ValidationReason.UNSTABLE_MEASUREMENT in res.reasons


def test_validation_precedence_and_immutability():
    engine = ValidationEngine()
    sample = make_valid_sample("SMP-IMMUTABLE-TEST")

    # Verify sample is not mutated
    res = engine.validate(sample)
    assert sample.sample_id == "SMP-IMMUTABLE-TEST"
    assert sample.validation_state == ValidationState.VALID

    with pytest.raises(AttributeError):
        sample.ph = 99.0  # type: ignore


def test_batch_validation_and_session_integration():
    adapter = VirtualSensorAdapter(seed=42, num_samples=25, scenario=FieldScenario.WITH_UNSTABLE)
    session = adapter.collect_session(session_id="SES-VAL-TEST")

    engine = ValidationEngine()
    results = engine.validate_session(session)

    assert len(results) == 25
    assert len(session.samples) == 25  # Raw samples remain intact in session

    eligible_samples = engine.get_session_eligible_samples(session)
    # 24 samples should be eligible, 1 rejected (the unstable one)
    assert len(eligible_samples) == 24
    assert len(session.samples) == 25  # Rejection does NOT delete raw sample from session!
