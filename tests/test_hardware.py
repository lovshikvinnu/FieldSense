"""Unit and end-to-end integration tests for Hardware Integration Boundary (Sprint 9)."""

import pytest

from fieldsense.domain.contracts.sensor import SensorAdapter
from fieldsense.domain.models import SampleSource, FieldSession
from fieldsense.input import VirtualSensorAdapter
from fieldsense.intelligence import ValidationEngine, FieldIntelligenceEngine
from fieldsense.spatial import SpatialEngine
from fieldsense.zones import ZoneDetectionEngine
from fieldsense.recommendations import RecommendationEngine
from fieldsense.presentation import UIViewAdapter, LocalUIRenderer
from fieldsense.hardware import (
    DataSourceConfig,
    GPSPosition,
    HARDWARE_SPEC_REQUIRED,
    HardwareConfig,
    HardwareError,
    HardwareErrorCode,
    HardwareGPSAdapter,
    HardwareReadinessState,
    HardwareSensorAdapter,
    MockHardwareTransport,
    RawSensorReading,
    SensorAdapterFactory,
    VirtualGPSAdapter,
)


def test_sensor_adapter_contract_compliance():
    hw_adapter = HardwareSensorAdapter()
    assert isinstance(hw_adapter, SensorAdapter)


def test_hardware_adapter_lifecycle_and_acquisition():
    mock_transport = MockHardwareTransport(mode="NORMAL")
    gps_adapter = VirtualGPSAdapter(latitude=13.0, longitude=77.6, fix_valid=True)
    hw_adapter = HardwareSensorAdapter(transport=mock_transport, gps_adapter=gps_adapter)

    hw_adapter.initialize()
    sample = hw_adapter.acquire_sample()

    assert sample.source == SampleSource.HARDWARE
    assert sample.sample_id.startswith("HW-SMP-")
    assert sample.latitude == 13.0
    assert sample.longitude == 77.6
    assert sample.nitrogen == 45.0
    assert sample.ph == 6.8
    assert sample.ec == 1.2

    hw_adapter.shutdown()
    assert not mock_transport.is_open


def test_hardware_error_handling_timeout():
    mock_transport = MockHardwareTransport(mode="TIMEOUT")
    hw_adapter = HardwareSensorAdapter(transport=mock_transport)
    hw_adapter.initialize()

    with pytest.raises(HardwareError) as exc_info:
        hw_adapter.acquire_sample()
    assert exc_info.value.error_code == HardwareErrorCode.TIMEOUT


def test_hardware_error_handling_malformed():
    mock_transport = MockHardwareTransport(mode="MALFORMED")
    hw_adapter = HardwareSensorAdapter(transport=mock_transport)
    hw_adapter.initialize()

    with pytest.raises(HardwareError) as exc_info:
        hw_adapter.acquire_sample()
    assert exc_info.value.error_code == HardwareErrorCode.MALFORMED_RESPONSE


def test_hardware_error_handling_gps_no_fix():
    mock_transport = MockHardwareTransport(mode="NORMAL")
    gps_adapter = VirtualGPSAdapter(fix_valid=False)
    hw_adapter = HardwareSensorAdapter(transport=mock_transport, gps_adapter=gps_adapter)
    hw_adapter.initialize()

    with pytest.raises(HardwareError) as exc_info:
        hw_adapter.acquire_sample()
    assert exc_info.value.error_code == HardwareErrorCode.GPS_NO_FIX


def test_hardware_spec_required_boundary():
    config = HardwareConfig()
    assert config.sensor_port == HARDWARE_SPEC_REQUIRED
    assert config.sensor_baudrate == HARDWARE_SPEC_REQUIRED
    assert config.gps_port == HARDWARE_SPEC_REQUIRED
    assert config.readiness_state == HardwareReadinessState.HARDWARE_PENDING

    stub_gps = HardwareGPSAdapter()
    with pytest.raises(HardwareError) as exc_info:
        stub_gps.initialize()
    assert exc_info.value.error_code == HardwareErrorCode.HARDWARE_SPEC_REQUIRED


def test_sensor_adapter_factory():
    v_adapter = SensorAdapterFactory.create_adapter(DataSourceConfig(source="VIRTUAL"))
    assert isinstance(v_adapter, VirtualSensorAdapter)

    hw_adapter = SensorAdapterFactory.create_adapter(DataSourceConfig(source="HARDWARE"))
    assert isinstance(hw_adapter, HardwareSensorAdapter)
    hw_adapter.shutdown()


def test_same_pipeline_virtual_vs_hardware_compatibility():
    """Same Pipeline Compatibility Test:

    Proves that VirtualSensorAdapter and HardwareSensorAdapter feed into the EXACT SAME
    Validation -> Intelligence -> Spatial -> Zones -> Recommendations -> UI pipeline.
    """
    # Pipeline execution function
    def run_pipeline(adapter: SensorAdapter, session_id: str):
        if isinstance(adapter, VirtualSensorAdapter):
            session = adapter.collect_session(session_id=session_id)
        else:
            session = FieldSession(session_id=session_id, field_name="Pipeline Test Field", created_at="2026-08-09T15:00:00Z")
            for _ in range(5):
                session.add_sample(adapter.acquire_sample())

        val_engine = ValidationEngine()
        eligible = val_engine.get_session_eligible_samples(session)
        intels = FieldIntelligenceEngine().process_many(eligible)
        spatial = SpatialEngine().process(intels, eligible)
        zones = ZoneDetectionEngine().process(spatial)
        recs = RecommendationEngine().process(zones)
        ui_view = UIViewAdapter().adapt(session, spatial, zones, recs)
        html = LocalUIRenderer().render_html(ui_view)

        return session, ui_view, html

    # 1. Virtual Pipeline
    v_adapter = VirtualSensorAdapter(seed=42, num_samples=10)
    v_session, v_ui, v_html = run_pipeline(v_adapter, "SES-VIRTUAL")

    # 2. Hardware Pipeline
    mock_transport = MockHardwareTransport(mode="NORMAL")
    hw_adapter = HardwareSensorAdapter(transport=mock_transport)
    hw_adapter.initialize()
    hw_session, hw_ui, hw_html = run_pipeline(hw_adapter, "SES-HARDWARE")
    hw_adapter.shutdown()

    # 3. Assertions
    assert v_session.samples[0].source == SampleSource.VIRTUAL
    assert hw_session.samples[0].source == SampleSource.HARDWARE

    assert v_ui.system_status.data_source == "VIRTUAL"
    assert hw_ui.system_status.data_source == "HARDWARE"

    assert "FIELDSENSE AI" in v_html
    assert "FIELDSENSE AI" in hw_html
