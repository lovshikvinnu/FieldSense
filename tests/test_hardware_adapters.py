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
    # Raw values: pH=689(6.89), M=250(25.0), T=225(22.5), EC=603(603 uS/cm -> 0.603 dS/m), N=43(43), P=60(60), K=120(120)
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
    assert data["ec"] == 0.603
    assert data["ec_raw_us_cm"] == 603.0
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


def test_bridge_gps_adapter_env_configuration(monkeypatch):
    """Test BridgeGPSAdapter configures host and port from environment variables."""
    monkeypatch.setenv("FIELDSENSE_GPS_GATEWAY_HOST", "172.22.0.2")
    monkeypatch.setenv("FIELDSENSE_GPS_GATEWAY_PORT", "9876")

    adapter = BridgeGPSAdapter()
    assert adapter.host == "172.22.0.2"
    assert adapter.port == 9876


def test_bridge_gps_adapter_default_fallback(monkeypatch):
    """Test BridgeGPSAdapter falls back to 127.0.0.1:9876 when env vars are unset."""
    monkeypatch.delenv("FIELDSENSE_GPS_GATEWAY_HOST", raising=False)
    monkeypatch.delenv("FIELDSENSE_GPS_GATEWAY_PORT", raising=False)

    adapter = BridgeGPSAdapter()
    assert adapter.host == "127.0.0.1"
    assert adapter.port == 9876


def test_bridge_gps_adapter_explicit_override(monkeypatch):
    """Test explicit constructor arguments override environment variables."""
    monkeypatch.setenv("FIELDSENSE_GPS_GATEWAY_HOST", "172.22.0.2")
    monkeypatch.setenv("FIELDSENSE_GPS_GATEWAY_PORT", "9876")

    adapter = BridgeGPSAdapter(host="10.0.0.5", port=1234)
    assert adapter.host == "10.0.0.5"
    assert adapter.port == 1234


def test_factory_gps_gateway_env_pass_through(monkeypatch):
    """Test SensorAdapterFactory resolves GPS gateway host and port from environment."""
    monkeypatch.setenv("FIELDSENSE_SOURCE", "HARDWARE")
    monkeypatch.setenv("FIELDSENSE_GPS_GATEWAY_HOST", "172.22.0.2")
    monkeypatch.setenv("FIELDSENSE_GPS_GATEWAY_PORT", "9876")

    from fieldsense.hardware.factory import DataSourceConfig, SensorAdapterFactory

    cfg = DataSourceConfig.from_env()
    assert cfg.gps_gateway_host == "172.22.0.2"
    assert cfg.gps_gateway_port == 9876

    adapter = SensorAdapterFactory.create_adapter()
    assert hasattr(adapter, "gps_adapter")
    assert adapter.gps_adapter.host == "172.22.0.2"
    assert adapter.gps_adapter.port == 9876


def test_data_source_config_from_env_no_overrides_uses_env(monkeypatch):
    """from_env() with no overrides uses environment variables."""
    monkeypatch.setenv("FIELDSENSE_SOURCE", "BRIDGE")
    monkeypatch.setenv("FIELDSENSE_SENSOR_PORT", "/dev/ttyUSB2")

    from fieldsense.hardware.factory import DataSourceConfig

    cfg = DataSourceConfig.from_env()
    assert cfg.source == "BRIDGE"
    assert cfg.sensor_port == "/dev/ttyUSB2"


def test_data_source_config_from_env_explicit_source_overrides_env(monkeypatch):
    """from_env(source="HARDWARE") overrides FIELDSENSE_SOURCE=VIRTUAL."""
    monkeypatch.setenv("FIELDSENSE_SOURCE", "VIRTUAL")

    from fieldsense.hardware.factory import DataSourceConfig

    cfg = DataSourceConfig.from_env(source="HARDWARE")
    assert cfg.source == "HARDWARE"


def test_data_source_config_from_env_explicit_port_overrides_env(monkeypatch):
    """from_env(sensor_port="/dev/ttyUSB0") overrides FIELDSENSE_SENSOR_PORT."""
    monkeypatch.setenv("FIELDSENSE_SENSOR_PORT", "/dev/ttyUSB99")

    from fieldsense.hardware.factory import DataSourceConfig

    cfg = DataSourceConfig.from_env(sensor_port="/dev/ttyUSB0")
    assert cfg.sensor_port == "/dev/ttyUSB0"


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
        assert sample.ec == 0.603

        # Validate against Phase 1 ValidationEngine
        val_engine = ValidationEngine()
        val_res = val_engine.validate(sample)
        assert val_res.pipeline_eligible is True
"""Tests for the v1 hardware adapter & contract layer.

All hardware-free. The adapters are transport-agnostic by design, so a fake
`SensorTransport` and a fake NMEA source exercise the full path from raw
telemetry to a validated `FieldSample`.
"""

from datetime import datetime, timezone

import pytest

from fieldsense.domain.models import FieldSample, SampleSource, ValidationState
from fieldsense.hardware import (
    JXBS_REGISTERS,
    GPSData,
    HardwareSampleAdapter,
    JXBSSoilAdapter,
    ModbusError,
    NMEAGPSAdapter,
    QualityPolicy,
    SoilData,
    build_read_request,
    ddmm_to_decimal,
    derive_measurement_quality,
    modbus_crc16,
    nmea_checksum_valid,
    parse_nmea_sentence,
    parse_nmea_stream,
    parse_read_response,
    us_cm_to_ds_m,
)
from fieldsense.hardware.gps_adapter import _bridge_payload_to_nmea, best_fix
from fieldsense.hardware.models import GPSPosition, RawSensorReading
from fieldsense.hardware.transport.base import SensorTransport
from fieldsense.intelligence import ValidationEngine


def nmea(body):
    """Append a correct NMEA checksum to a sentence body."""
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return "${}*{:02X}".format(body, checksum)


GOOD_GGA = nmea("GNGGA,123519.00,1258.2960,N,07735.6760,E,1,09,0.8,545.4,M,46.9,M,,")


class FakeProbe(SensorTransport):
    """Modbus slave that answers with configurable raw register values."""

    DEFAULT = {0x0006: 680, 0x0012: 312, 0x0013: 243, 0x0015: 210,
               0x001E: 42, 0x001F: 18, 0x0020: 95}

    def __init__(self, raw=None, fail_registers=(), corrupt_crc=False):
        self.raw = dict(raw or self.DEFAULT)
        self.fail_registers = set(fail_registers)
        self.corrupt_crc = corrupt_crc
        self._open = False
        self._pending = b""

    def open(self): self._open = True
    def close(self): self._open = False
    @property
    def is_open(self): return self._open

    def write(self, payload):
        register = (payload[2] << 8) | payload[3]
        if register in self.fail_registers:
            self._pending = b""
            return
        value = self.raw[register]
        body = bytes([payload[0], 0x03, 2, (value >> 8) & 0xFF, value & 0xFF])
        crc = modbus_crc16(body)
        if self.corrupt_crc:
            crc ^= 0xFFFF
        self._pending = body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    def read(self, length=256):
        out, self._pending = self._pending, b""
        return out


# ------------------------------------------------------------------ Modbus


@pytest.mark.parametrize("parameter,expected_hex", [
    ("ph",          "010300060001640B"),
    ("moisture",    "01030012000124 0F".replace(" ", "")),
    ("temperature", "010300130001 75CF".replace(" ", "")),
    # The bench record carried a one-byte CRC typo here (95 CD). The correct
    # CRC-16/MODBUS trailer is 95 CE, confirmed by two independent
    # implementations and by the other six frames matching exactly.
    ("ec",          "010300150001 95CE".replace(" ", "")),
    ("nitrogen",    "0103001E0001 E40C".replace(" ", "")),
    ("phosphorus",  "0103001F0001 B5CC".replace(" ", "")),
    ("potassium",   "010300200001 85C0".replace(" ", "")),
])
def test_request_frames_match_hardware_verified_bytes(parameter, expected_hex):
    """Generated frames must equal the bytes recorded during bench testing.

    These exact frames are in docs/HARDWARE.md and were confirmed against the
    physical probe, so this validates the CRC implementation against reality
    rather than against itself.
    """
    address = JXBS_REGISTERS[parameter][0]
    assert build_read_request(address).hex().upper() == expected_hex


def test_crc16_is_symmetric_with_parser():
    frame_body = bytes([0x01, 0x03, 0x02, 0x02, 0xA8])
    crc = modbus_crc16(frame_body)
    frame = frame_body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    assert parse_read_response(frame) == 680


def test_parse_response_rejects_bad_crc():
    body = bytes([0x01, 0x03, 0x02, 0x02, 0xA8])
    with pytest.raises(ModbusError, match="CRC"):
        parse_read_response(body + b"\x00\x00")


def test_parse_response_rejects_wrong_slave_and_short_frame():
    body = bytes([0x02, 0x03, 0x02, 0x02, 0xA8])
    crc = modbus_crc16(body)
    with pytest.raises(ModbusError, match="slave"):
        parse_read_response(body + bytes([crc & 0xFF, (crc >> 8) & 0xFF]))
    with pytest.raises(ModbusError, match="short"):
        parse_read_response(b"\x01\x03")


def test_parse_response_surfaces_modbus_exception():
    body = bytes([0x01, 0x83, 0x02, 0x00, 0x00])
    crc = modbus_crc16(body)
    with pytest.raises(ModbusError, match="exception"):
        parse_read_response(body + bytes([crc & 0xFF, (crc >> 8) & 0xFF]))


def test_temperature_register_decodes_negative_values():
    """Sub-zero soil must not read as +6529 degrees."""
    body = bytes([0x01, 0x03, 0x02, 0xFF, 0x9C])  # -100 -> -10.0 degC
    crc = modbus_crc16(body)
    frame = body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    assert parse_read_response(frame, signed=True) == -100
    assert parse_read_response(frame, signed=False) == 65436


# ------------------------------------------------------------------ units


def test_ec_conversion_microsiemens_to_decisiemens():
    assert us_cm_to_ds_m(1000.0) == 1.0
    assert us_cm_to_ds_m(210.0) == pytest.approx(0.21)


def test_soil_adapter_converts_ec_into_the_software_contract_domain():
    """EC must arrive as dS/m, not the probe's uS/cm."""
    adapter = JXBSSoilAdapter(FakeProbe(), settle_seconds=0)
    adapter.initialize()
    data = adapter.read()
    assert data.ec_raw_us_cm == 210.0
    assert data.ec == pytest.approx(0.21)


def test_ec_conversion_is_load_bearing_for_validation():
    """Regression guard: without the uS/cm -> dS/m conversion every sample is rejected.

    The validation contract bounds EC to 0.0-10.0 dS/m. A routine 210 uS/cm
    reading forwarded unconverted lands at 210 and is rejected. If someone
    removes the conversion, this test fails loudly instead of the instrument
    silently discarding every field sample.
    """
    gps = parse_nmea_sentence(GOOD_GGA)
    builder = HardwareSampleAdapter()
    engine = ValidationEngine()

    converted = SoilData(ph=6.8, moisture=31.2, temperature=24.3,
                         ec=us_cm_to_ds_m(210.0), nitrogen=42.0,
                         phosphorus=18.0, potassium=95.0,
                         raw_registers={k: 1 for k in JXBS_REGISTERS})
    unconverted = SoilData(ph=6.8, moisture=31.2, temperature=24.3,
                           ec=210.0, nitrogen=42.0, phosphorus=18.0,
                           potassium=95.0,
                           raw_registers={k: 1 for k in JXBS_REGISTERS})

    assert engine.validate(builder.build_sample(gps, converted)).pipeline_eligible is True
    assert engine.validate(builder.build_sample(gps, unconverted)).pipeline_eligible is False


# ------------------------------------------------------------------ soil adapter


def test_soil_adapter_reads_all_seven_parameters():
    adapter = JXBSSoilAdapter(FakeProbe(), settle_seconds=0)
    with adapter:
        data = adapter.read()
    assert data.complete is True
    assert data.parameters_read == 7
    assert (data.ph, data.moisture, data.temperature) == (6.8, 31.2, 24.3)
    assert (data.nitrogen, data.phosphorus, data.potassium) == (42.0, 18.0, 95.0)


def test_soil_adapter_degrades_on_partial_failure():
    """One dead register must not lose the other six."""
    adapter = JXBSSoilAdapter(FakeProbe(fail_registers=[0x001E]), settle_seconds=0)
    adapter.initialize()
    data = adapter.read()
    assert data.nitrogen is None
    assert data.ph == 6.8
    assert data.parameters_read == 6
    assert any("nitrogen" in e for e in data.read_errors)
    assert data.complete is False


def test_soil_adapter_records_crc_failures_without_raising():
    adapter = JXBSSoilAdapter(FakeProbe(corrupt_crc=True), settle_seconds=0)
    adapter.initialize()
    data = adapter.read()
    assert data.parameters_read == 0
    assert len(data.read_errors) == 7


def test_soil_data_converts_to_frozen_raw_reading():
    adapter = JXBSSoilAdapter(FakeProbe(), settle_seconds=0)
    adapter.initialize()
    reading = adapter.read().to_raw_reading()
    assert isinstance(reading, RawSensorReading)
    assert reading.ph == 6.8
    assert reading.metadata["ec_raw_us_cm"] == 210.0


def test_soil_data_round_trips():
    original = SoilData(ph=6.5, moisture=30.0, ec=0.2, read_errors=["x"])
    assert SoilData.from_dict(original.to_dict()).to_dict() == original.to_dict()


# ------------------------------------------------------------------ NMEA


@pytest.mark.parametrize("raw,hemisphere,expected", [
    ("1258.2960", "N", 12.9716),
    ("07735.6760", "E", 77.5946),
    ("1258.2960", "S", -12.9716),
    ("07735.6760", "W", -77.5946),
    ("4807.038", "N", 48.1173),
])
def test_ddmm_to_decimal_degrees(raw, hemisphere, expected):
    """Two degree digits for latitude, three for longitude, minutes over 60."""
    assert ddmm_to_decimal(raw, hemisphere) == pytest.approx(expected, abs=1e-4)


def test_ddmm_handles_empty_field():
    assert ddmm_to_decimal("", "N") is None


def test_checksum_validation():
    assert nmea_checksum_valid(GOOD_GGA) is True
    assert nmea_checksum_valid(GOOD_GGA[:-2] + "00") is False
    # A sentence with no checksum is accepted; the Bridge forwards such payloads.
    assert nmea_checksum_valid("$GNGGA,123519.00,1258.2960,N") is True


def test_parse_gga_extracts_full_telemetry():
    data = parse_nmea_sentence(GOOD_GGA)
    assert data.latitude == pytest.approx(12.9716, abs=1e-4)
    assert data.longitude == pytest.approx(77.5946, abs=1e-4)
    assert (data.fix_quality, data.satellites) == (1, 9)
    assert data.hdop == 0.8
    assert data.altitude_m == 545.4
    assert (data.talker, data.sentence_type) == ("GN", "GGA")
    assert data.fix_valid is True


def test_parse_rmc_and_void_fix():
    active = parse_nmea_sentence(nmea("GPRMC,123519,A,1258.2960,N,07735.6760,E,0.0,0.0,230826,,"))
    void = parse_nmea_sentence(nmea("GPRMC,123519,V,1258.2960,N,07735.6760,E,0.0,0.0,230826,,"))
    assert active.fix_valid is True and active.sentence_type == "RMC"
    assert void.fix_valid is False


@pytest.mark.parametrize("talker", ["GN", "GP", "GL", "GA", "BD"])
def test_all_neo_m8n_talkers_accepted(talker):
    sentence = nmea(talker + "GGA,123519.00,1258.2960,N,07735.6760,E,1,09,0.8,545.4,M,46.9,M,,")
    assert parse_nmea_sentence(sentence) is not None


def test_parser_ignores_noise_without_raising():
    for junk in ["", "not nmea", "$GNGSV,3,1,11,01,05,040,", GOOD_GGA[:-2] + "00", "$XXGGA,1,2"]:
        assert parse_nmea_sentence(junk) is None


def test_parse_stream_and_best_fix_prefers_valid_gga():
    stream = "\n".join([
        "$GNGSV,3,1,11,01,05,040,",
        nmea("GPRMC,123519,V,1258.2960,N,07735.6760,E,0.0,0.0,230826,,"),
        GOOD_GGA,
    ])
    parsed = parse_nmea_stream(stream)
    assert len(parsed) == 2
    chosen = best_fix(parsed)
    assert chosen.sentence_type == "GGA" and chosen.fix_valid


def test_gps_data_converts_to_frozen_position():
    position = parse_nmea_sentence(GOOD_GGA).to_gps_position()
    assert isinstance(position, GPSPosition)
    assert position.fix_valid is True
    assert position.quality["satellites"] == 9


def test_gps_data_round_trips():
    original = parse_nmea_sentence(GOOD_GGA)
    assert GPSData.from_dict(original.to_dict()).to_dict() == original.to_dict()


# ------------------------------------------------------------------ GPS adapter


def test_gps_adapter_acquires_fix_from_source():
    adapter = NMEAGPSAdapter(lambda: GOOD_GGA)
    adapter.initialize()
    data = adapter.acquire_gps_data()
    assert data.fix_valid
    assert isinstance(adapter.acquire_position(), GPSPosition)


def test_gps_adapter_returns_empty_data_when_source_is_silent():
    """An unplugged antenna degrades the sample; it must not raise."""
    adapter = NMEAGPSAdapter(lambda: "", max_attempts=3)
    data = adapter.acquire_gps_data()
    assert data.fix_valid is False and data.fix_quality == 0


def test_gps_adapter_survives_a_throwing_source():
    def broken():
        raise OSError("device disappeared")
    data = NMEAGPSAdapter(broken, max_attempts=2).acquire_gps_data()
    assert data.fix_valid is False


def test_gps_adapter_implements_frozen_contract():
    from fieldsense.hardware.gps.base import GPSAdapter
    assert issubclass(NMEAGPSAdapter, GPSAdapter)


def test_bridge_payload_accepts_raw_and_json():
    assert _bridge_payload_to_nmea(GOOD_GGA).startswith("$GNGGA")
    assert _bridge_payload_to_nmea('{"nmea": "%s"}' % GOOD_GGA).startswith("$GNGGA")
    synth = _bridge_payload_to_nmea('{"lat": 12.9716, "lon": 77.5946, "fix": 1, "sats": 9}')
    parsed = parse_nmea_sentence(synth)
    assert parsed.latitude == pytest.approx(12.9716, abs=1e-4)
    assert parsed.longitude == pytest.approx(77.5946, abs=1e-4)
    assert _bridge_payload_to_nmea(None) == ""


# ------------------------------------------------------------------ quality


def test_quality_is_high_for_a_clean_acquisition():
    adapter = JXBSSoilAdapter(FakeProbe(), settle_seconds=0)
    adapter.initialize()
    quality = derive_measurement_quality(parse_nmea_sentence(GOOD_GGA), adapter.read())
    assert quality >= 0.70  # ValidationConfig treats >= 0.70 as good


def test_quality_collapses_without_a_gps_fix():
    adapter = JXBSSoilAdapter(FakeProbe(), settle_seconds=0)
    adapter.initialize()
    quality = derive_measurement_quality(GPSData(), adapter.read())
    assert quality < 0.70


def test_quality_degrades_with_missing_soil_registers():
    gps = parse_nmea_sentence(GOOD_GGA)
    full = JXBSSoilAdapter(FakeProbe(), settle_seconds=0)
    full.initialize()
    partial = JXBSSoilAdapter(FakeProbe(fail_registers=[0x001E, 0x001F]), settle_seconds=0)
    partial.initialize()
    assert derive_measurement_quality(gps, partial.read()) < derive_measurement_quality(gps, full.read())


def test_quality_is_zero_without_soil_data():
    assert derive_measurement_quality(parse_nmea_sentence(GOOD_GGA), None) == 0.0


def test_quality_policy_is_configurable():
    strict = QualityPolicy(no_fix_factor=0.05)
    adapter = JXBSSoilAdapter(FakeProbe(), settle_seconds=0)
    adapter.initialize()
    assert derive_measurement_quality(GPSData(), adapter.read(), strict) < 0.30


# ------------------------------------------------------------------ contract


def test_build_sample_produces_a_valid_hardware_fieldsample():
    adapter = JXBSSoilAdapter(FakeProbe(), settle_seconds=0)
    adapter.initialize()
    sample = HardwareSampleAdapter().build_sample(
        parse_nmea_sentence(GOOD_GGA), adapter.read(),
        timestamp=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc))

    assert isinstance(sample, FieldSample)
    assert sample.source == SampleSource.HARDWARE
    assert sample.validation_state == ValidationState.VALID
    assert sample.latitude == pytest.approx(12.9716, abs=1e-4)
    assert sample.ec == pytest.approx(0.21)
    assert sample.sample_id.startswith("HW-")
    assert FieldSample.from_dict(sample.to_dict()).to_dict() == sample.to_dict()


def test_build_sample_tolerates_missing_telemetry():
    """No GPS and no soil must still yield a well-formed, low-quality sample."""
    sample = HardwareSampleAdapter().build_sample(None, None)
    assert isinstance(sample, FieldSample)
    assert sample.measurement_quality == 0.0
    assert sample.latitude == 0.0


def test_adapter_does_not_pre_judge_validity():
    """Gatekeeping belongs to ValidationEngine, not this adapter."""
    impossible = SoilData(ph=99.0, moisture=-5.0, temperature=500.0, ec=0.2,
                          nitrogen=0.0, phosphorus=0.0, potassium=0.0,
                          raw_registers={k: 1 for k in JXBS_REGISTERS})
    sample = HardwareSampleAdapter().build_sample(parse_nmea_sentence(GOOD_GGA), impossible)
    assert sample.validation_state == ValidationState.VALID       # adapter stays neutral
    assert ValidationEngine().validate(sample).pipeline_eligible is False  # engine rejects


def test_acquisition_report_exposes_diagnostics():
    adapter = JXBSSoilAdapter(FakeProbe(), settle_seconds=0)
    adapter.initialize()
    report = HardwareSampleAdapter().acquisition_report(parse_nmea_sentence(GOOD_GGA), adapter.read())
    assert report["gps_fix_valid"] is True
    assert report["soil_parameters_read"] == 7
    assert report["ec_raw_us_cm"] == 210.0
    assert report["ec_converted_ds_m"] == pytest.approx(0.21)


def test_hardware_samples_flow_through_the_frozen_pipeline():
    """End-to-end: adapter output drives the full Phase 1 engine unchanged."""
    from fieldsense.intelligence import FieldIntelligenceEngine
    from fieldsense.spatial import SpatialConfig, SpatialEngine
    from fieldsense.zones import ZoneDetectionEngine
    from fieldsense.recommendations import RecommendationEngine

    builder = HardwareSampleAdapter()
    samples = []
    for index in range(9):
        lat = 12.9716 + (index // 3) * 0.0002
        lon = 77.5946 + (index % 3) * 0.0002
        gga = nmea("GNGGA,1235{:02d}.00,{},N,{},E,1,09,0.8,545.4,M,46.9,M,,".format(
            index,
            "{:02d}{:07.4f}".format(int(lat), (lat - int(lat)) * 60),
            "{:03d}{:07.4f}".format(int(lon), (lon - int(lon)) * 60)))
        probe = FakeProbe({0x0006: 650 + index, 0x0012: 300 + index * 5, 0x0013: 240,
                           0x0015: 200 + index, 0x001E: 40 + index,
                           0x001F: 18, 0x0020: 95})
        soil = JXBSSoilAdapter(probe, settle_seconds=0)
        soil.initialize()
        samples.append(builder.build_sample(parse_nmea_sentence(gga), soil.read()))

    eligible = ValidationEngine().get_eligible_samples(samples)
    assert len(eligible) == 9, "hardware samples were rejected by the frozen validator"

    intel = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine(config=SpatialConfig(grid_spacing_meters=10.0)).process(intel, eligible)
    assert spatial.layers, "spatial engine produced no layers"
    assert spatial.coverage.coverage_ratio > 0.0
    zones = ZoneDetectionEngine().process(spatial)
    recommendations = RecommendationEngine().process(zones)
    assert len(zones.zones) >= 1
    assert isinstance(recommendations.recommendations, list)
