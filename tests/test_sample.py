"""Unit tests for FieldSample domain model."""

from datetime import datetime, timezone
import pytest

from fieldsense.domain import FieldSample, SampleSource, ValidationState


def test_field_sample_valid_construction():
    now = datetime.now(timezone.utc)
    sample = FieldSample(
        sample_id="SMP-001",
        timestamp=now,
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=45.2,
        phosphorus=18.5,
        potassium=120.0,
        ph=6.8,
        ec=1.2,
        moisture=32.5,
        temperature=24.0,
        measurement_quality=0.95,
        source=SampleSource.VIRTUAL,
        validation_state=ValidationState.VALID,
    )

    assert sample.sample_id == "SMP-001"
    assert sample.timestamp == now
    assert sample.latitude == 12.9716
    assert sample.longitude == 77.5946
    assert sample.nitrogen == 45.2
    assert sample.phosphorus == 18.5
    assert sample.potassium == 120.0
    assert sample.ph == 6.8
    assert sample.ec == 1.2
    assert sample.moisture == 32.5
    assert sample.temperature == 24.0
    assert sample.measurement_quality == 0.95
    assert sample.source == SampleSource.VIRTUAL
    assert sample.validation_state == ValidationState.VALID


def test_field_sample_virtual_source():
    sample = FieldSample(
        sample_id="SMP-VIRTUAL-1",
        timestamp=datetime.now(timezone.utc),
        latitude=0.0,
        longitude=0.0,
        nitrogen=10.0,
        phosphorus=10.0,
        potassium=10.0,
        ph=7.0,
        ec=1.0,
        moisture=20.0,
        temperature=20.0,
        measurement_quality=1.0,
        source=SampleSource.VIRTUAL,
    )
    assert sample.source == SampleSource.VIRTUAL
    assert sample.source.value == "VIRTUAL"


def test_field_sample_hardware_source():
    sample = FieldSample(
        sample_id="SMP-HW-1",
        timestamp=datetime.now(timezone.utc),
        latitude=15.0,
        longitude=75.0,
        nitrogen=25.0,
        phosphorus=12.0,
        potassium=80.0,
        ph=6.5,
        ec=0.9,
        moisture=28.0,
        temperature=22.5,
        measurement_quality=0.88,
        source=SampleSource.HARDWARE,
    )
    assert sample.source == SampleSource.HARDWARE
    assert sample.source.value == "HARDWARE"


def test_field_sample_validation_states():
    now = datetime.now(timezone.utc)
    s1 = FieldSample(
        sample_id="S1", timestamp=now, latitude=0.0, longitude=0.0,
        nitrogen=0.0, phosphorus=0.0, potassium=0.0, ph=7.0, ec=0.0,
        moisture=0.0, temperature=0.0, measurement_quality=1.0,
        source=SampleSource.VIRTUAL, validation_state=ValidationState.VALID
    )
    s2 = FieldSample(
        sample_id="S2", timestamp=now, latitude=0.0, longitude=0.0,
        nitrogen=0.0, phosphorus=0.0, potassium=0.0, ph=7.0, ec=0.0,
        moisture=0.0, temperature=0.0, measurement_quality=0.5,
        source=SampleSource.HARDWARE, validation_state=ValidationState.VALID_WITH_WARNING
    )
    s3 = FieldSample(
        sample_id="S3", timestamp=now, latitude=0.0, longitude=0.0,
        nitrogen=0.0, phosphorus=0.0, potassium=0.0, ph=7.0, ec=0.0,
        moisture=0.0, temperature=0.0, measurement_quality=0.1,
        source=SampleSource.HARDWARE, validation_state=ValidationState.REJECTED
    )

    assert s1.validation_state == ValidationState.VALID
    assert s2.validation_state == ValidationState.VALID_WITH_WARNING
    assert s3.validation_state == ValidationState.REJECTED


def test_field_sample_immutability():
    sample = FieldSample(
        sample_id="SMP-IMMUTABLE",
        timestamp=datetime.now(timezone.utc),
        latitude=10.0,
        longitude=10.0,
        nitrogen=20.0,
        phosphorus=20.0,
        potassium=20.0,
        ph=7.0,
        ec=1.0,
        moisture=15.0,
        temperature=25.0,
        measurement_quality=0.9,
        source=SampleSource.VIRTUAL,
    )
    with pytest.raises(AttributeError):
        sample.nitrogen = 99.0  # type: ignore


def test_field_sample_serialization():
    now = datetime.now(timezone.utc)
    sample = FieldSample(
        sample_id="SMP-SERIALIZE",
        timestamp=now,
        latitude=13.0,
        longitude=78.0,
        nitrogen=30.0,
        phosphorus=15.0,
        potassium=90.0,
        ph=6.9,
        ec=1.1,
        moisture=25.0,
        temperature=23.0,
        measurement_quality=0.92,
        source=SampleSource.VIRTUAL,
        validation_state=ValidationState.VALID,
    )

    dict_repr = sample.to_dict()
    assert dict_repr["sample_id"] == "SMP-SERIALIZE"
    assert dict_repr["timestamp"] == now.isoformat()
    assert dict_repr["source"] == "VIRTUAL"
    assert dict_repr["validation_state"] == "VALID"

    reconstructed = FieldSample.from_dict(dict_repr)
    assert reconstructed == sample
