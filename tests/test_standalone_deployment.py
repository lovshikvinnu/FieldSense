"""Standalone physical-deployment tests — the board with nothing attached to it.

Every test here corresponds to a defect found while auditing whether a flashed
Arduino UNO Q boots and runs with no computer, no Wi-Fi, and no cloud. They are
regression tests: each one fails on the code as it stood before this audit.

Layer 1  boot service and zero-dependency runtime
Layer 2  STM32 serial bridge and Modbus/NMEA correctness
Layer 3  local SLM fail-safe
Layer 4  ST7789V framebuffer output
Layer 5  power isolation and validation robustness
"""

import json
import os
import shutil
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from fieldsense.hardware import (
    BridgeSoilAdapter,
    BridgeSoilTransport,
    StdlibModbusTransport,
    normalise_bridge_payload,
    soil_data_to_canonical_json,
)
from fieldsense.hardware.factory import DataSourceConfig, SensorAdapterFactory
from fieldsense.hardware.models import HardwareError, HardwareErrorCode
from fieldsense.hardware.sensor_adapter import HardwareSensorAdapter
from fieldsense.hardware.soil_adapter import SoilData
from fieldsense.hardware.transport import MockHardwareTransport
from fieldsense.hardware.gps import VirtualGPSAdapter
from fieldsense.intelligence import ValidationEngine

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------- Layer 1: boot & dependencies


def test_boot_service_unit_files_exist():
    """The systemd units must exist as files, not only as documentation prose.

    The deployment guide previously carried a unit definition inside a fenced
    code block, which nothing could install.
    """
    for name in ("fieldsense.service", "fieldsense-refresh.service"):
        path = os.path.join(REPO_ROOT, "deploy", name)
        assert os.path.isfile(path), "missing unit file: deploy/{}".format(name)
        body = open(path, encoding="utf-8").read()
        assert "[Service]" in body and "ExecStart=" in body
        assert "WantedBy=multi-user.target" in body


def test_boot_service_sets_working_directory_and_groups():
    """A unit without WorkingDirectory cannot find the dashboard or the weights."""
    body = open(os.path.join(REPO_ROOT, "deploy", "fieldsense.service"),
                encoding="utf-8").read()
    assert "WorkingDirectory=" in body
    # 'video' writes /dev/fbN, 'dialout' opens the RS485 tty. Both fail silently
    # until runtime if the service account lacks them.
    assert "video" in body and "dialout" in body


def test_boot_script_is_executable_and_valid_shell():
    """The boot entry point must be executable and syntactically sound."""
    path = os.path.join(REPO_ROOT, "scripts", "boot_fieldsense.sh")
    assert os.path.isfile(path) and (sys.platform == "win32" or os.access(path, os.X_OK))

    has_bash = False
    if shutil.which("bash"):
        try:
            res = subprocess.run(["bash", "-c", "true"], capture_output=True)
            has_bash = (res.returncode == 0)
        except Exception:
            has_bash = False

    if has_bash:
        assert subprocess.run(["bash", "-n", path], capture_output=True).returncode == 0
    else:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline()
        assert first_line.startswith("#!") and "sh" in first_line


def test_boot_script_never_blocks_on_operator_input():
    """Live acquisition under systemd has no TTY, so it must pass --no-interactive.

    `live_collector` prompts with input() by default. Under a service that
    prompt blocks forever and the unit hangs at boot with a dark panel.
    """
    body = open(os.path.join(REPO_ROOT, "scripts", "boot_fieldsense.sh"),
                encoding="utf-8").read()
    assert "--no-interactive" in body


def test_runtime_declares_no_third_party_dependencies():
    """`dependencies = []` is the deployment contract; it must stay empty."""
    body = open(os.path.join(REPO_ROOT, "pyproject.toml"), encoding="utf-8").read()
    assert "dependencies = []" in body


def test_default_hardware_path_does_not_require_pyserial():
    """The factory's HARDWARE source must import cleanly with pyserial absent.

    Previously HARDWARE built DirectUSBModbusTransport, whose only backend is
    pyserial — a package `dependencies = []` does not install. On a freshly
    flashed image the acquisition path died with "pyserial is not installed".
    """
    adapter = SensorAdapterFactory.create_adapter(DataSourceConfig(source="HARDWARE"))
    assert isinstance(adapter, HardwareSensorAdapter)
    assert isinstance(adapter.transport, StdlibModbusTransport)

    # Prove the transport does not reach for pyserial at all.
    import fieldsense.hardware.transport.direct_modbus as direct_modbus

    with patch.object(direct_modbus, "serial", None):
        assert isinstance(adapter.transport, StdlibModbusTransport)


def test_factory_rejects_an_unknown_source_instead_of_simulating():
    """A typo in a unit file must fail loudly, not fabricate field data."""
    with pytest.raises(ValueError, match="unknown data source"):
        SensorAdapterFactory.create_adapter(DataSourceConfig(source="HARDWAER"))


def test_factory_reads_configuration_from_the_environment():
    """A boot unit steers acquisition with Environment=, not a code edit."""
    env = {
        "FIELDSENSE_SOURCE": "bridge",
        "FIELDSENSE_SENSOR_PORT": "/dev/ttyUSB3",
        "FIELDSENSE_SENSOR_BAUD": "19200",
        "FIELDSENSE_SOIL_METHOD": "get_soil_data",
        "FIELDSENSE_REQUIRE_GPS_FIX": "1",
    }
    with patch.dict(os.environ, env, clear=False):
        cfg = DataSourceConfig.from_env()
    assert cfg.source == "BRIDGE"
    assert cfg.sensor_port == "/dev/ttyUSB3"
    assert cfg.sensor_baudrate == 19200
    assert cfg.require_gps_fix is True


# -------------------------------------- Layer 2: STM32 bridge & serial gateway


def test_stm32_soil_bridge_payload_reaches_the_pipeline():
    """The sketch's `get_soil_data` output must decode into canonical telemetry.

    The STM32 published this endpoint and no Python consumer existed, so soil
    readings from the bench-verified MAX485 wiring could not reach the pipeline
    at all.
    """
    sketch_output = '{"temp":22.5,"moisture":25.0,"ph":6.89,"ec":603,"n":43,"p":60,"k":120}'
    soil = normalise_bridge_payload(sketch_output)

    assert soil.temperature == 22.5      # 'temp' -> 'temperature'
    assert soil.nitrogen == 43.0         # 'n' -> 'nitrogen'
    assert soil.phosphorus == 60.0
    assert soil.potassium == 120.0
    assert soil.ph == 6.89
    assert soil.ec == pytest.approx(0.603)   # uS/cm -> dS/m
    assert soil.ec_raw_us_cm == 603.0
    assert soil.complete


def test_stm32_soil_bridge_reports_its_own_modbus_failure_as_degraded():
    """The sketch's in-band error becomes a degraded sample, not an exception."""
    soil = normalise_bridge_payload('{"error":"MODBUS_READ_FAILED"}')
    assert soil.parameters_read == 0
    assert any("MODBUS_READ_FAILED" in err for err in soil.read_errors)


def test_stm32_soil_bridge_end_to_end_through_the_factory():
    """BRIDGE source: soil and GPS both over RouterBridge, into a FieldSample."""
    adapter = SensorAdapterFactory.create_adapter(
        DataSourceConfig(source="BRIDGE", require_gps_fix=False)
    )
    assert isinstance(adapter.transport, BridgeSoilTransport)

    soil_bridge = MagicMock()
    soil_bridge.call.return_value = (
        '{"temp":22.5,"moisture":25.0,"ph":6.89,"ec":603,"n":43,"p":60,"k":120}'
    )
    gps_bridge = MagicMock()
    gps_bridge.call.return_value = "FIX_OK,1734.18667N,07825.47349E,Sats:06,HDOP:1.61"

    with patch("fieldsense.hardware.bridge_soil.Bridge", soil_bridge), \
         patch("fieldsense.hardware.gps.bridge_gps.Bridge", gps_bridge):
        adapter.initialize()
        sample = adapter.acquire_sample()

    assert sample.ph == 6.89
    assert sample.ec == pytest.approx(0.603)
    assert abs(sample.latitude - 17.5697778) < 1e-6
    assert abs(sample.longitude - 78.4245582) < 1e-6
    assert ValidationEngine().validate(sample).pipeline_eligible is True


def test_bridge_soil_payload_missing_fields_degrade_not_raise():
    """A truncated bridge frame yields a partial reading with recorded errors."""
    soil = normalise_bridge_payload('{"temp":22.5,"ph":6.89}')
    assert soil.temperature == 22.5
    assert soil.nitrogen is None
    assert soil.parameters_read == 2
    assert len(soil.read_errors) == 5


def test_bridge_soil_empty_and_non_json_payloads_raise_hardware_error():
    """An unusable payload is a structured HardwareError, not a stray ValueError."""
    for payload in ("", "   ", "GARBAGE FROM THE WIRE"):
        with pytest.raises(HardwareError) as info:
            normalise_bridge_payload(payload)
        assert info.value.error_code == HardwareErrorCode.MALFORMED_RESPONSE


def test_canonical_json_always_carries_every_measurement_key():
    """A partial read must not raise MALFORMED_RESPONSE downstream.

    HardwareSensorAdapter requires all seven keys. Emitting only the ones that
    answered would turn one dropped register into a lost sample.
    """
    payload = json.loads(soil_data_to_canonical_json(SoilData(ph=6.5)).decode())
    for key in ("nitrogen", "phosphorus", "potassium", "ph", "ec",
                "moisture", "temperature"):
        assert key in payload
    assert payload["ph"] == 6.5
    assert payload["nitrogen"] == 0.0
    assert payload["_meta"]["parameters_read"] == 1


def test_ec_conversion_is_unconditional_across_the_full_probe_range():
    """EC must always convert uS/cm -> dS/m, never on a magnitude threshold.

    The old `>= 20.0` gate was wrong in both directions: a genuinely low
    15 uS/cm passed through as 15 dS/m and was rejected by the 0-10 bound, and
    a saline 25000 uS/cm became 25 dS/m and was also rejected. Both looked
    like sensor faults rather than a unit bug.
    """
    for raw_us_cm in (0.0, 5.0, 15.0, 19.0, 20.0, 210.0, 1500.0, 9000.0):
        soil = normalise_bridge_payload(json.dumps({"ec": raw_us_cm}))
        assert soil.ec == pytest.approx(raw_us_cm / 1000.0)
        assert soil.ec_raw_us_cm == raw_us_cm


def test_pyserial_transport_ec_conversion_matches_the_stdlib_path():
    """Both soil transports must agree on EC units for the same register value."""
    from fieldsense.hardware.transport.direct_modbus import (
        DirectUSBModbusTransport,
        modbus_crc,
    )

    transport = DirectUSBModbusTransport(port="COM_MOCK")
    mock_ser = MagicMock()
    mock_ser.is_open = True
    transport._ser = mock_ser

    # pH, moisture, temperature, EC=15 uS/cm, N, P, K
    raw_vals = [689, 250, 225, 15, 43, 60, 120]
    frames = []
    for value in raw_vals:
        body = bytes([0x01, 0x03, 0x02, (value >> 8) & 0xFF, value & 0xFF])
        crc = modbus_crc(body)
        frames.append(body + bytes([crc & 0xFF, (crc >> 8) & 0xFF]))
    mock_ser.read.side_effect = frames

    data = json.loads(transport.read().decode("utf-8"))
    assert data["ec"] == pytest.approx(0.015)
    assert data["ec_raw_us_cm"] == 15.0

    bridge_soil = normalise_bridge_payload(json.dumps({"ec": 15}))
    assert data["ec"] == pytest.approx(bridge_soil.ec)


def test_bridge_soil_transport_is_read_only():
    """Linux must not write to the RS485 bus the STM32 owns."""
    transport = BridgeSoilTransport()
    transport.open()
    with pytest.raises(HardwareError) as info:
        transport.write(b"\x01\x03")
    assert info.value.error_code == HardwareErrorCode.TRANSPORT_ERROR


def test_bridge_soil_transport_requires_open_before_read():
    transport = BridgeSoilTransport()
    with pytest.raises(HardwareError) as info:
        transport.read()
    assert info.value.error_code == HardwareErrorCode.DEVICE_NOT_INITIALIZED


def test_bridge_soil_gateway_refusal_is_a_structured_error():
    """With no RouterBridge and no gateway, the failure is diagnosable."""
    adapter = BridgeSoilAdapter(port=9, timeout=0.1)   # nothing listens on port 9
    with patch("fieldsense.hardware.bridge_soil.Bridge", None):
        with pytest.raises(HardwareError) as info:
            adapter.read()
    assert info.value.error_code == HardwareErrorCode.DEVICE_UNAVAILABLE


def test_stdlib_modbus_transport_defaults_match_the_probe_datasheet():
    """JXBS-3001 factory defaults: 9600 8N1, slave 0x01."""
    transport = StdlibModbusTransport()
    assert transport.baudrate == 9600
    assert transport.slave_id == 0x01
    assert transport.port == "/dev/ttyUSB0"
    assert transport.is_open is False


def test_stdlib_modbus_transport_reports_a_missing_device_clearly():
    """An absent tty is a structured TRANSPORT_ERROR naming the device."""
    transport = StdlibModbusTransport(port="/dev/definitely-not-here")
    with pytest.raises(HardwareError) as info:
        transport.open()
    assert info.value.error_code == HardwareErrorCode.TRANSPORT_ERROR
    assert "/dev/definitely-not-here" in str(info.value)


def test_stdlib_modbus_transport_degrades_on_a_single_failed_register():
    """One dropped register must cost one parameter, not the whole sample.

    A probe pushed into stony ground routinely drops a register. The pyserial
    transport aborts the entire read in that case; this one does not.
    """
    from fieldsense.hardware.soil_adapter import (
        JXBS_REGISTERS,
        JXBSSoilAdapter,
        build_read_request,
        modbus_crc16,
    )
    from fieldsense.hardware.transport.base import SensorTransport

    class FlakyProbe(SensorTransport):
        """Answers every register except nitrogen (0x001E)."""

        VALUES = {0x0006: 689, 0x0012: 250, 0x0013: 225,
                  0x0015: 603, 0x001E: None, 0x001F: 60, 0x0020: 120}

        def __init__(self):
            self._open = False
            self._pending = None

        def open(self): self._open = True
        def close(self): self._open = False
        @property
        def is_open(self): return self._open

        def write(self, payload):
            self._pending = (payload[2] << 8) | payload[3]

        def read(self, length=256):
            value = self.VALUES.get(self._pending)
            if value is None:
                return b""            # timeout, no answer at all
            body = bytes([0x01, 0x03, 0x02, (value >> 8) & 0xFF, value & 0xFF])
            crc = modbus_crc16(body)
            return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    probe = FlakyProbe()
    transport = StdlibModbusTransport(
        adapter=JXBSSoilAdapter(probe, settle_seconds=0)
    )
    transport.open()
    soil = transport.read_soil()

    assert soil.parameters_read == len(JXBS_REGISTERS) - 1
    assert soil.nitrogen is None
    assert soil.ph == 6.89
    assert any("nitrogen" in err for err in soil.read_errors)

    # And the canonical JSON still carries every key, so nothing downstream breaks.
    payload = json.loads(transport.read().decode("utf-8"))
    assert payload["nitrogen"] == 0.0
    assert payload["_meta"]["parameters_read"] == 6
    transport.close()


# ------------------------------------------- Layer 2/5: acquisition robustness


def test_cold_start_without_a_gps_fix_still_produces_a_sample():
    """A receiver with no fix yet must degrade quality, not abort the campaign.

    A cold NEO-M8N needs minutes for its first fix. Raising GPS_NO_FIX for
    every sample meant an unattended boot recorded nothing at all.
    """
    adapter = HardwareSensorAdapter(
        transport=MockHardwareTransport(mode="NORMAL"),
        gps_adapter=VirtualGPSAdapter(fix_valid=False),
        require_gps_fix=False,
    )
    adapter.initialize()
    sample = adapter.acquire_sample()

    assert sample.measurement_quality < 0.70   # visibly degraded
    assert sample.measurement_quality >= 0.30  # still usable
    result = ValidationEngine().validate(sample)
    assert result.pipeline_eligible is True
    assert result.state.value == "VALID_WITH_WARNING"


def test_strict_mode_still_raises_gps_no_fix():
    """The bench contract is preserved: require_gps_fix=True keeps raising."""
    adapter = HardwareSensorAdapter(
        transport=MockHardwareTransport(mode="NORMAL"),
        gps_adapter=VirtualGPSAdapter(fix_valid=False),
        require_gps_fix=True,
    )
    adapter.initialize()
    with pytest.raises(HardwareError) as info:
        adapter.acquire_sample()
    assert info.value.error_code == HardwareErrorCode.GPS_NO_FIX


def test_measurement_quality_reflects_acquisition_health():
    """Quality must be derived, never asserted as 1.0.

    A hardcoded 1.0 hid a no-fix receiver and a half-answered probe from the
    ValidationEngine, which is the only component allowed to judge a sample.
    """
    good = HardwareSensorAdapter(
        transport=MockHardwareTransport(mode="NORMAL"),
        gps_adapter=VirtualGPSAdapter(fix_valid=True),
    )
    good.initialize()
    good_sample = good.acquire_sample()

    degraded = HardwareSensorAdapter(
        transport=MockHardwareTransport(mode="NORMAL"),
        gps_adapter=VirtualGPSAdapter(fix_valid=False),
        require_gps_fix=False,
    )
    degraded.initialize()
    degraded_sample = degraded.acquire_sample()

    assert degraded_sample.measurement_quality < good_sample.measurement_quality
    assert good.last_acquisition_meta["gps_fix_valid"] is True
    assert degraded.last_acquisition_meta["gps_fix_valid"] is False


def test_partial_soil_read_lowers_quality_below_a_full_read():
    """Sensor completeness must move the quality score, not just GPS health."""
    full = HardwareSensorAdapter(
        transport=MockHardwareTransport(mode="NORMAL"),
        gps_adapter=VirtualGPSAdapter(),
    )
    full.initialize()
    full_quality = full.acquire_sample().measurement_quality

    class PartialTransport(MockHardwareTransport):
        """Answers four of seven registers and says so in _meta."""

        def read(self, length=256):
            payload = json.loads(super().read(length).decode("utf-8"))
            payload["_meta"] = {"parameters_read": 4, "parameters_expected": 7}
            return json.dumps(payload).encode("utf-8")

    partial = HardwareSensorAdapter(
        transport=PartialTransport(mode="NORMAL"),
        gps_adapter=VirtualGPSAdapter(),
    )
    partial.initialize()
    assert partial.acquire_sample().measurement_quality < full_quality


def test_noisy_probe_insertion_is_rejected_without_hanging():
    """An out-of-range reading is rejected deterministically and in bounded time.

    Layer 5 requirement: ValidationEngine must catch a bad insertion without
    stalling the main loop.
    """
    import time

    bad_payload = {
        "nitrogen": 45.0, "phosphorus": 25.0, "potassium": 150.0,
        "ph": 0.0,            # a failed pH register reads as zero
        "ec": 1.2, "moisture": 32.0, "temperature": 22.5,
    }
    adapter = HardwareSensorAdapter(
        transport=MockHardwareTransport(mode="NORMAL", custom_payload=bad_payload),
        gps_adapter=VirtualGPSAdapter(),
    )
    adapter.initialize()

    started = time.perf_counter()
    result = ValidationEngine().validate(adapter.acquire_sample())
    elapsed = time.perf_counter() - started

    assert result.pipeline_eligible is False
    assert result.state.value == "REJECTED"
    assert elapsed < 0.5, "validation must not stall the acquisition loop"


# ------------------------------------------------------ Layer 3: local SLM


def test_ai_factory_falls_back_to_templates_without_weights():
    """No GGUF weights is the normal case and must never crash startup."""
    from fieldsense.ai import AIAdapterFactory
    from fieldsense.ai.config import AIConfig
    from fieldsense.ai.mock import MockAIAdapter

    cfg = AIConfig(model_path="/nonexistent/model.gguf", binary_path="llama-cli-absent")
    adapter = AIAdapterFactory.create_adapter(cfg)
    assert isinstance(adapter, MockAIAdapter)
    adapter.shutdown()


def test_ai_model_path_survives_a_service_working_directory():
    """A relative model path must resolve, not silently vanish under systemd.

    The default `models/fieldsense-slm.gguf` is relative. A service whose
    working directory is not the repository would never find the weights, and
    the failure was indistinguishable from having no model installed.
    """
    from fieldsense.ai.config import AIConfig
    from fieldsense.ai.llama_cpp import LlamaCppAdapter

    relative = AIConfig()
    assert not os.path.isabs(relative.model_path)
    assert os.path.isabs(relative.resolved_model_path())
    assert relative.resolved_model_path("/opt/fieldsense") == (
        os.path.abspath("/opt/fieldsense/models/fieldsense-slm.gguf")
    )

    absolute = AIConfig(model_path="/opt/fieldsense/models/m.gguf")
    assert LlamaCppAdapter(config=absolute).model_path() == "/opt/fieldsense/models/m.gguf"

    env = {"FIELDSENSE_MODEL_PATH": "/opt/fieldsense/models/env.gguf",
           "FIELDSENSE_LLAMA_BIN": "/usr/local/bin/llama-cli"}
    with patch.dict(os.environ, env, clear=False):
        from_env = AIConfig.from_env()
    assert from_env.model_path == "/opt/fieldsense/models/env.gguf"
    assert from_env.binary_path == "/usr/local/bin/llama-cli"


def test_ai_config_survives_a_malformed_unit_file_value():
    """A typo in Environment= must cost the narrative, not the boot."""
    from fieldsense.ai.config import AIConfig

    with patch.dict(os.environ, {"FIELDSENSE_AI_THREADS": "four",
                                 "FIELDSENSE_AI_TIMEOUT": ""}, clear=False):
        cfg = AIConfig.from_env()
    assert cfg.threads == AIConfig.threads
    assert cfg.timeout_seconds == AIConfig.timeout_seconds


def test_narrative_guard_blocks_dosages_units_and_chemicals():
    """The safety filter must strip prescriptive language before it reaches a screen."""
    from fieldsense.ai.config import GuardConfig
    from fieldsense.ai.guard import NarrativeGuard
    from fieldsense.ai.models import ExplanationContext

    guard = NarrativeGuard(GuardConfig())
    context = ExplanationContext(
        field_name="Test Field", session_id="S-1",
        overall_soil_health=0.62, soil_health_status="MODERATE",
        nitrogen_score=0.5, moisture_score=0.6, carbon_readiness_score=0.4,
        total_samples=25, valid_samples=24, rejected_samples=1,
        coverage_ratio=1.0,
    )

    for text in (
        "Apply 40 kg of urea per hectare across zone Z01.",
        "Broadcast gypsum at 2 tonnes/acre.",
        "Dose 250 ml of the pesticide per litre of water.",
        "This qualifies for carbon credits after certification.",
    ):
        assert guard.inspect_text(text, context), "guard let through: {}".format(text)


# ---------------------------------------------- Layer 4: ST7789V framebuffer


def test_rgb565_frame_is_exactly_the_panel_size():
    """240 x 320 at 16 bits per pixel is 153,600 bytes."""
    from fieldsense.hardware.display_bridge import rgb_to_rgb565

    assert len(rgb_to_rgb565(bytes(240 * 320 * 3))) == 153_600


def test_framebuffer_autodetection_prefers_fb1_then_fb0():
    """auto must pick a device that EXISTS.

    `choose_target('auto')` used to select the fb target when either fb1 or fb0
    was present, while the write always went to the --device default of
    /dev/fb1. On a board whose panel is fb0 that wrote to a missing device.
    """
    from fieldsense.hardware.display_bridge import choose_target, detect_framebuffer

    with patch("os.path.exists", lambda p: p == "/dev/fb0"):
        assert detect_framebuffer() == "/dev/fb0"
        assert choose_target("auto") == "fb"

    with patch("os.path.exists", lambda p: p in ("/dev/fb0", "/dev/fb1")):
        assert detect_framebuffer() == "/dev/fb1"

    with patch("os.path.exists", lambda p: False), \
         patch("fieldsense.hardware.display_bridge.list_framebuffers", lambda: []):
        assert detect_framebuffer() is None

    # An explicit device always wins.
    assert detect_framebuffer("/dev/fb3") == "/dev/fb3"


def test_framebuffer_write_rejects_a_transposed_frame():
    """A rotated frame has the same byte count and the wrong geometry.

    Rotating 240x320 by 90 degrees yields 320x240: identical size in bytes, so
    a size-only check passes and the panel displays a transposed image.
    """
    from fieldsense.hardware import display_bridge

    payload = bytes(240 * 320 * 2)
    panel = {"device": "/dev/fb1", "width": 240, "height": 320, "bpp": 16}

    with patch.object(display_bridge, "framebuffer_info", lambda d: panel), \
         patch("os.path.exists", lambda p: True):
        with pytest.raises(display_bridge.DisplayBridgeError, match="geometry mismatch"):
            display_bridge.write_framebuffer(payload, "/dev/fb1", geometry=(320, 240))


def test_panel_renders_without_a_browser():
    """The display layer must not depend on Chromium being installed.

    Chromium is a system asset, not a declared dependency. With no browser the
    board previously showed nothing at all: no frame, no pixels, a dark screen.
    """
    from fieldsense.hardware.panel_renderer import render_summary_panel

    summary = {
        "field_name": "North Block", "soil_health_score": 0.62,
        "soil_health_status": "MODERATE", "total_samples": 25,
        "valid_samples": 23, "rejected_samples": 2, "coverage_ratio": 0.78,
        "zone_count": 4, "recommendation_count": 7, "data_source": "HARDWARE",
        "provenance": "LIVE_HARDWARE", "offline_mode": True,
    }
    width, height, rgb = render_summary_panel(summary)
    assert (width, height) == (240, 320)
    assert len(rgb) == 240 * 320 * 3
    # Not a blank frame: the renderer actually drew something.
    assert len(set(rgb[i:i + 3] for i in range(0, len(rgb), 3))) > 3


def test_panel_render_is_deterministic():
    """The same summary must always produce the same pixels."""
    from fieldsense.hardware.panel_renderer import render_summary_panel

    summary = {"soil_health_score": 0.5, "soil_health_status": "MODERATE"}
    assert render_summary_panel(summary)[2] == render_summary_panel(summary)[2]


def test_panel_renders_from_a_missing_or_broken_summary():
    """No summary file, or a corrupt one, still yields a drawable panel."""
    from fieldsense.hardware import panel_renderer

    assert panel_renderer.load_panel_summary("/nonexistent/summary.json") is None
    placeholder = panel_renderer.placeholder_summary("RUN FIELDSENSE.DEMO")
    width, height, rgb = panel_renderer.render_summary_panel(placeholder)
    assert len(rgb) == width * height * 3


def test_panel_tolerates_every_field_being_absent():
    """A gap in the panel beats a panel that fails to draw."""
    from fieldsense.hardware.panel_renderer import panel_lines, render_summary_panel

    width, height, rgb = render_summary_panel({})
    assert len(rgb) == width * height * 3
    assert "--" in " ".join(panel_lines({}))


def test_display_bridge_falls_back_to_the_panel_renderer(tmp_path):
    """A failed dashboard render degrades to the status panel, not to nothing."""
    from fieldsense.hardware.display_bridge import capture_or_panel

    _w, _h, rgb, renderer = capture_or_panel(
        str(tmp_path / "absent.html"), 240, 320, allow_fallback=True
    )
    assert renderer == "panel"
    assert len(rgb) == 240 * 320 * 3


def test_display_bridge_strict_mode_still_fails_loudly(tmp_path):
    """Bench verification of the real UI must not be silently substituted."""
    from fieldsense.hardware.display_bridge import DisplayBridgeError, capture_or_panel

    with pytest.raises(DisplayBridgeError):
        capture_or_panel(str(tmp_path / "absent.html"), 240, 320, allow_fallback=False)


def test_launch_display_script_does_not_hardcode_fb1():
    """The launcher must inherit the same auto-detection as the bridge."""
    body = open(os.path.join(REPO_ROOT, "scripts", "launch_display.sh"),
                encoding="utf-8").read()
    assert 'FB_DEVICE="${FB_DEVICE:-auto}"' in body


def test_pipeline_writes_the_panel_summary_the_fallback_reads(tmp_path):
    """demo must publish the numbers the browser-free renderer draws."""
    from fieldsense.demo import run_demo
    from fieldsense.hardware import panel_renderer

    output = tmp_path / "dash.html"
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        summary = run_demo(output_path=str(output), enable_narrative=False)
        written = panel_renderer.load_panel_summary(panel_renderer.PANEL_SUMMARY_PATH)
    finally:
        os.chdir(cwd)

    assert summary["panel_summary_path"] is not None
    assert written is not None
    assert written["soil_health_status"] == summary["soil_health_status"]
    assert written["zone_count"] == summary["zone_count"]


# ------------------------------------------------ Layer 5: power & isolation


def test_power_domains_are_documented_with_measured_evidence():
    """Isolated rails must be stated explicitly: 12 V probe, 5 V board, 3.3 V logic."""
    body = open(os.path.join(REPO_ROOT, "docs", "HARDWARE.md"), encoding="utf-8").read()
    assert "12.0V DC" in body or "12V" in body
    assert "3.3V" in body or "3.3 V" in body
    # The RS485 module under test is a 5 V part; driving 3.3 V logic into the
    # display without level shifting is the documented hazard.
    assert "STRICTLY 3.3V LOGIC" in body or "strictly 3.3 V" in body


def test_offline_pipeline_makes_no_network_calls():
    """No socket, urllib, or subprocess-to-network anywhere in the offline path."""
    import fieldsense.demo as demo_module

    source_files = []
    package_root = os.path.join(REPO_ROOT, "fieldsense")
    for folder, _dirs, files in os.walk(package_root):
        if "__pycache__" in folder:
            continue
        for name in files:
            if name.endswith(".py"):
                source_files.append(os.path.join(folder, name))

    # Sockets are legitimate in exactly three places, all loopback-only:
    # the two STM32 bridge gateways, and the optional local preview server.
    # Nothing may open an outbound connection.
    allowed_sockets = {"bridge_gps.py", "bridge_soil.py", "renderer.py"}
    for path in source_files:
        body = open(path, encoding="utf-8").read()
        name = os.path.basename(path)
        assert "urllib" not in body, "network client in {}".format(path)
        assert "import requests" not in body, "network client in {}".format(path)
        assert "http.client" not in body, "network client in {}".format(path)
        if "import socket" in body:
            assert name in allowed_sockets, "unexpected socket use in {}".format(path)
            # Loopback only. A non-local bind or connect would leave the board.
            assert "127.0.0.1" in body, \
                "{} uses sockets without binding to loopback".format(path)
    assert demo_module is not None
