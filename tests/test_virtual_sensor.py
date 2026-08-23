"""Unit tests for SensorAdapter contract and VirtualSensorAdapter implementation."""

import pytest
from fieldsense.domain import (
    FieldSample,
    FieldSession,
    SampleSource,
    SensorAdapter,
    ValidationState,
)
from fieldsense.input import FieldScenario, VirtualSensorAdapter


def test_sensor_adapter_contract_implementation():
    adapter = VirtualSensorAdapter(seed=42)
    assert isinstance(adapter, SensorAdapter)

    # Test context manager interface
    with VirtualSensorAdapter(seed=42) as ctx_adapter:
        assert ctx_adapter.initialized
        sample = ctx_adapter.acquire_sample()
        assert isinstance(sample, FieldSample)

    assert not ctx_adapter.initialized


def test_virtual_adapter_lifecycle():
    adapter = VirtualSensorAdapter(seed=42)
    assert not adapter.initialized

    adapter.initialize()
    assert adapter.initialized

    sample = adapter.acquire_sample()
    assert isinstance(sample, FieldSample)

    adapter.shutdown()
    assert not adapter.initialized


def test_field_generation_properties():
    num_samples = 25
    adapter = VirtualSensorAdapter(seed=42, num_samples=num_samples)
    samples = adapter.get_all_samples()

    assert len(samples) == num_samples

    sample_ids = set()
    for sample in samples:
        assert isinstance(sample, FieldSample)
        assert sample.source == SampleSource.VIRTUAL
        assert sample.sample_id not in sample_ids
        sample_ids.add(sample.sample_id)

        # Verify valid coordinate bounds around base lat/lon
        assert 12.90 <= sample.latitude <= 13.05
        assert 77.50 <= sample.longitude <= 77.65

        # Verify chemical & physical measurement presence
        assert sample.nitrogen >= 0.0
        assert sample.phosphorus >= 0.0
        assert sample.potassium >= 0.0
        assert 0.0 <= sample.ph <= 14.0
        assert sample.ec >= 0.0
        assert sample.moisture >= 0.0
        assert sample.temperature > -50.0
        assert 0.0 <= sample.measurement_quality <= 1.0


def test_seed_repeatability():
    adapter1 = VirtualSensorAdapter(seed=42, num_samples=20)
    samples1 = adapter1.get_all_samples()

    adapter2 = VirtualSensorAdapter(seed=42, num_samples=20)
    samples2 = adapter2.get_all_samples()

    assert len(samples1) == len(samples2)
    for s1, s2 in zip(samples1, samples2):
        # Ignore timestamp diffs if generated at slightly different microseconds,
        # but compare sample attributes
        assert s1.sample_id == s2.sample_id
        assert s1.latitude == s2.latitude
        assert s1.longitude == s2.longitude
        assert s1.nitrogen == s2.nitrogen
        assert s1.phosphorus == s2.phosphorus
        assert s1.potassium == s2.potassium
        assert s1.ph == s2.ph
        assert s1.ec == s2.ec
        assert s1.moisture == s2.moisture
        assert s1.temperature == s2.temperature
        assert s1.measurement_quality == s2.measurement_quality


def test_different_seeds_produce_different_datasets():
    adapter_a = VirtualSensorAdapter(seed=42, num_samples=20)
    samples_a = adapter_a.get_all_samples()

    adapter_b = VirtualSensorAdapter(seed=123, num_samples=20)
    samples_b = adapter_b.get_all_samples()

    assert len(samples_a) == len(samples_b)
    # Datasets should differ in values or IDs
    sample_a_n = [s.nitrogen for s in samples_a]
    sample_b_n = [s.nitrogen for s in samples_b]
    assert sample_a_n != sample_b_n


def test_spatial_coherence():
    # 25 samples grid: index 0 is top-left (healthy), index 24 is bottom-right (poor)
    adapter = VirtualSensorAdapter(seed=42, num_samples=25)
    samples = adapter.get_all_samples()

    top_left = samples[0]
    adjacent = samples[1]
    bottom_right = samples[24]

    # Adjacent point measurements should be much closer to top-left than distant bottom-right
    diff_adjacent_n = abs(top_left.nitrogen - adjacent.nitrogen)
    diff_distant_n = abs(top_left.nitrogen - bottom_right.nitrogen)

    assert diff_adjacent_n < diff_distant_n

    diff_adjacent_ph = abs(top_left.ph - adjacent.ph)
    diff_distant_ph = abs(top_left.ph - bottom_right.ph)

    assert diff_adjacent_ph < diff_distant_ph


def test_outlier_scenario():
    adapter = VirtualSensorAdapter(seed=42, num_samples=25, scenario=FieldScenario.WITH_OUTLIER)
    samples = adapter.get_all_samples()

    outlier_idx = adapter.outlier_index
    assert outlier_idx is not None

    outlier_sample = samples[outlier_idx]
    assert outlier_sample.nitrogen == 350.0
    assert outlier_sample.ph == 3.1


def test_unstable_sample_scenario():
    adapter = VirtualSensorAdapter(seed=42, num_samples=25, scenario=FieldScenario.WITH_UNSTABLE)
    samples = adapter.get_all_samples()

    unstable_idx = adapter.unstable_index
    assert unstable_idx is not None

    unstable_sample = samples[unstable_idx]
    assert unstable_sample.measurement_quality == 0.15
    assert unstable_sample.validation_state == ValidationState.VALID_WITH_WARNING


def test_field_session_integration():
    adapter = VirtualSensorAdapter(seed=99, num_samples=30)
    session = adapter.collect_session(session_id="SES-VIRT-001", field_name="West Farm")

    assert isinstance(session, FieldSession)
    assert session.session_id == "SES-VIRT-001"
    assert session.field_name == "West Farm"
    assert session.sample_count == 30
    assert len(session.samples) == 30

    for sample in session.samples:
        assert isinstance(sample, FieldSample)
        assert sample.source == SampleSource.VIRTUAL
