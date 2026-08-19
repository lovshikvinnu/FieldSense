"""Unit tests for FieldSession domain model."""

from datetime import datetime, timezone
import pytest

from fieldsense.domain import FieldSample, FieldSession, SampleSource, SessionStatus, ValidationState


def make_sample(sample_id: str = "SMP-001", source: SampleSource = SampleSource.VIRTUAL) -> FieldSample:
    """Helper factory for creating dummy FieldSample instances."""
    return FieldSample(
        sample_id=sample_id,
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=50.0,
        phosphorus=20.0,
        potassium=150.0,
        ph=6.5,
        ec=1.0,
        moisture=30.0,
        temperature=25.0,
        measurement_quality=0.9,
        source=source,
        validation_state=ValidationState.VALID,
    )


def test_field_session_creation():
    created_at = datetime.now(timezone.utc)
    session = FieldSession(
        session_id="SES-001",
        created_at=created_at,
        status=SessionStatus.CREATED,
        field_name="North Field",
    )

    assert session.session_id == "SES-001"
    assert session.created_at == created_at
    assert session.status == SessionStatus.CREATED
    assert session.field_name == "North Field"


def test_field_session_empty():
    session = FieldSession(
        session_id="SES-EMPTY",
        created_at=datetime.now(timezone.utc),
    )

    assert session.samples == []
    assert session.sample_count == 0
    assert session.status == SessionStatus.CREATED
    assert session.field_name is None


def test_field_session_add_sample():
    session = FieldSession(
        session_id="SES-ADD",
        created_at=datetime.now(timezone.utc),
    )
    sample = make_sample("SMP-1")
    session.add_sample(sample)

    assert len(session.samples) == 1
    assert session.sample_count == 1
    assert session.samples[0] == sample


def test_field_session_multiple_samples():
    session = FieldSession(
        session_id="SES-MULTI",
        created_at=datetime.now(timezone.utc),
        status=SessionStatus.COLLECTING,
    )

    sample1 = make_sample("SMP-1", source=SampleSource.HARDWARE)
    sample2 = make_sample("SMP-2", source=SampleSource.VIRTUAL)
    sample3 = make_sample("SMP-3", source=SampleSource.HARDWARE)

    session.add_sample(sample1)
    session.add_sample(sample2)
    session.add_sample(sample3)

    assert session.sample_count == 3
    assert len(session.samples) == 3
    assert session.samples[0].sample_id == "SMP-1"
    assert session.samples[1].sample_id == "SMP-2"
    assert session.samples[2].sample_id == "SMP-3"


def test_sample_count_is_derived_only():
    session = FieldSession(
        session_id="SES-COUNT",
        created_at=datetime.now(timezone.utc),
    )
    session.add_sample(make_sample("SMP-1"))

    assert session.sample_count == 1

    # sample_count must be a read-only property, setting it should fail
    with pytest.raises(AttributeError):
        session.sample_count = 100  # type: ignore


def test_field_session_statuses():
    statuses = [
        SessionStatus.CREATED,
        SessionStatus.COLLECTING,
        SessionStatus.READY_FOR_PROCESSING,
        SessionStatus.PROCESSED,
        SessionStatus.COMPLETED,
        SessionStatus.CANCELLED,
    ]
    for st in statuses:
        session = FieldSession(
            session_id=f"SES-{st.value}",
            created_at=datetime.now(timezone.utc),
            status=st,
        )
        assert session.status == st


def test_field_session_derived_results_do_not_alter_raw_samples():
    session = FieldSession(
        session_id="SES-DERIVED-TEST",
        created_at=datetime.now(timezone.utc),
    )
    sample = make_sample("SMP-RAW")
    session.add_sample(sample)

    # Attach dummy derived results placeholders
    session.field_result = {"soil_health_index": 82.5}
    session.spatial_result = {"grid_mesh": "placeholder"}
    session.zones = [{"zone_id": 1, "class": "Optimal"}]
    session.recommendations = [{"type": "N_SUPPLEMENT", "amount": 15}]

    # Verify raw samples are unaffected and unchanged
    assert len(session.samples) == 1
    assert session.samples[0] == sample
    assert not hasattr(session.samples[0], "soil_health_index")
    assert not hasattr(session.samples[0], "zone_id")


def test_field_session_add_invalid_sample_type():
    session = FieldSession(
        session_id="SES-TYPE-TEST",
        created_at=datetime.now(timezone.utc),
    )
    with pytest.raises(TypeError):
        session.add_sample("not a sample")  # type: ignore


def test_field_session_serialization():
    now = datetime.now(timezone.utc)
    session = FieldSession(
        session_id="SES-SERIALIZE",
        created_at=now,
        status=SessionStatus.READY_FOR_PROCESSING,
        field_name="East Pasture",
    )
    sample = make_sample("SMP-SER-1")
    session.add_sample(sample)

    serialized = session.to_dict()
    assert serialized["session_id"] == "SES-SERIALIZE"
    assert serialized["created_at"] == now.isoformat()
    assert serialized["status"] == "READY_FOR_PROCESSING"
    assert serialized["field_name"] == "East Pasture"
    assert serialized["sample_count"] == 1
    assert len(serialized["samples"]) == 1
    assert serialized["samples"][0]["sample_id"] == "SMP-SER-1"
    assert "field_result" in serialized["derived_results"]
