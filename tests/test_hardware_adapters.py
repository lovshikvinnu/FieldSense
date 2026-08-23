"""Unit tests for DirectUSBModbusTransport and BridgeGPSAdapter."""

import json
from unittest.mock import MagicMock, patch
import pytest

from fieldsense.hardware.models import HardwareError, HardwareErrorCode, GPSPosition
from fieldsense.hardware.transport.direct_modbus import (
    DirectUSBModbusTransport,
    modbus_crc,
    make_modbus_request,
    validate_modbus_crc,
)
from fieldsense.hardware.gps.bridge_gps import BridgeGPSAdapter, parse_nmea_coord
from fieldsense.hardware.sensor_adapter import HardwareSensorAdapter
from fieldsense.domain.models import SampleSource, ValidationState
from fieldsense.intelligence import ValidationEngine


def test_modbus_crc_calculation():
    """Verify Modbus RTU CRC calculation matches standard polynomial math."""
    data = bytes([0x01, 0x03, 0x00, 0x06, 0x00, 0x01])
    crc = modbus_crc(data)
    crc_low = crc & 0xFF
    crc_high = (crc >> 8) & 0xFF
    assert bytes([crc_low, crc_high]) == bytes([0x64, 0x0B])


def test_make_modbus_request():
    """Verify standard Modbus holding register request frame construction."""
    request = make_modbus_request(0x0006, slave_id=0x01)
    assert len(request) == 8
    assert request[:6] == bytes([0x01, 0x03, 0x00, 0x06, 0x00, 0x01])
    assert check_crc_validity(request)


def check_crc_validity(frame):
    calc = modbus_crc(frame[:-2])
    rec = frame[-2] | (frame[-1] << 8)
    return calc == rec


def test_parse_nmea_coord():
    """Verify conversion of NMEA DDMM.MMMM format to decimal degrees."""
    # Latitude North
    lat_n = parse_nmea_coord("1734.18667N", is_longitude=False)
    assert abs(lat_n - 17.5697778) < 1e-6

    # Latitude South
    lat_s = parse_nmea_coord("1734.18667S", is_longitude=False)
    assert abs(lat_s - (-17.5697778)) < 1e-6

    # Longitude East
    lon_e = parse_nmea_coord("07825.47349E", is_longitude=True)
    assert abs(lon_e - 78.4245582) < 1e-6

    # Longitude West
    lon_w = parse_nmea_coord("07825.47349W", is_longitude=True)
    assert abs(lon_w - (-78.4245582)) < 1e-6

    with pytest.raises(ValueError):
        parse_nmea_coord("INVALID", is_longitude=False)


def test_direct_usb_modbus_transport_mocked():
    """Test DirectUSBModbusTransport reading mocked 7-register responses."""
    transport = DirectUSBModbusTransport(port="COM_MOCK")

    mock_ser = MagicMock()
    mock_ser.is_open = True
    transport._ser = mock_ser

    # Return valid Modbus response 7-bytes for each of the 7 registers
    # Raw values: pH=689(6.89), M=250(25.0), T=225(22.5), EC=603(603 µS/cm -> 0.6 dS/m), N=43(43), P=60(60), K=120(120)
    raw_vals = [689, 250, 225, 603, 43, 60, 120]
    responses = []
    for val in raw_vals:
        body = bytes([0x01, 0x03, 0x02, (val >> 8) & 0xFF, val & 0xFF])
        crc = modbus_crc(body)
        frame = body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        responses.append(frame)

    mock_ser.read.side_effect = responses

    json_bytes = transport.read()
    data = json.loads(json_bytes.decode("utf-8"))

    assert data["ph"] == 6.89
    assert data["moisture"] == 25.0
    assert data["temperature"] == 22.5
    assert data["ec"] == 0.6
    assert data["nitrogen"] == 43.0
    assert data["phosphorus"] == 60.0
    assert data["potassium"] == 120.0


def test_direct_usb_modbus_transport_crc_error():
    """Test DirectUSBModbusTransport raises HardwareError on bad CRC."""
    transport = DirectUSBModbusTransport(port="COM_MOCK")
    mock_ser = MagicMock()
    mock_ser.is_open = True
    transport._ser = mock_ser

    # Bad CRC frame
    mock_ser.read.return_value = bytes([0x01, 0x03, 0x02, 0x00, 0x0A, 0x00, 0x00])

    with pytest.raises(HardwareError) as exc_info:
        transport.read()

    assert exc_info.value.error_code == HardwareErrorCode.MALFORMED_RESPONSE


def test_bridge_gps_adapter_fix_ok():
    """Test BridgeGPSAdapter parsing valid RouterBridge NMEA CSV response."""
    adapter = BridgeGPSAdapter()
    adapter.initialize()

    sample_telemetry = "FIX_OK,1734.18667N,07825.47349E,Sats:06,HDOP:1.61"

    with patch("fieldsense.hardware.gps.bridge_gps.Bridge") as mock_bridge:
        mock_bridge.call.return_value = sample_telemetry
        gps_pos = adapter.acquire_position()

        assert gps_pos.fix_valid is True
        assert abs(gps_pos.latitude - 17.5697778) < 1e-6
        assert abs(gps_pos.longitude - 78.4245582) < 1e-6
        assert gps_pos.quality["satellites"] == 6
        assert gps_pos.quality["hdop"] == 1.61


def test_bridge_gps_adapter_no_fix():
    """Test BridgeGPSAdapter handling NO_FIX status."""
    adapter = BridgeGPSAdapter()
    adapter.initialize()

    with patch("fieldsense.hardware.gps.bridge_gps.Bridge") as mock_bridge:
        mock_bridge.call.return_value = "NO_FIX,0.0,0.0,0,0.0"
        gps_pos = adapter.acquire_position()

        assert gps_pos.fix_valid is False
        assert gps_pos.latitude == 0.0
        assert gps_pos.longitude == 0.0


def test_hardware_sensor_adapter_e2e_integration():
    """Test HardwareSensorAdapter with mocked adapters produces valid FieldSample."""
    transport = DirectUSBModbusTransport(port="COM_MOCK")
    mock_ser = MagicMock()
    mock_ser.is_open = True
    transport._ser = mock_ser

    # 7-register response payload
    raw_vals = [689, 250, 225, 603, 43, 60, 120]
    responses = []
    for val in raw_vals:
        body = bytes([0x01, 0x03, 0x02, (val >> 8) & 0xFF, val & 0xFF])
        crc = modbus_crc(body)
        responses.append(body + bytes([crc & 0xFF, (crc >> 8) & 0xFF]))
    mock_ser.read.side_effect = responses

    gps_adapter = BridgeGPSAdapter()
    gps_adapter.initialize()

    hw_adapter = HardwareSensorAdapter(transport=transport, gps_adapter=gps_adapter)

    with patch("fieldsense.hardware.gps.bridge_gps.Bridge") as mock_bridge:
        mock_bridge.call.return_value = "FIX_OK,1734.18667N,07825.47349E,Sats:06,HDOP:1.61"

        sample = hw_adapter.acquire_sample()

        assert sample.source == SampleSource.HARDWARE
        assert sample.validation_state == ValidationState.VALID
        assert abs(sample.latitude - 17.5697778) < 1e-6
        assert abs(sample.longitude - 78.4245582) < 1e-6
        assert sample.ph == 6.89
        assert sample.nitrogen == 43.0
        assert sample.ec == 0.6

        # Validate against Phase 1 ValidationEngine
        val_engine = ValidationEngine()
        val_res = val_engine.validate(sample)
        assert val_res.pipeline_eligible is True
