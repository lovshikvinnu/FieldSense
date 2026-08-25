"""The field node: triggers, one whole session, and the export it hands the pipeline.

The node is the only place hardware appears, so these tests substitute fakes for
the probe and the receiver and exercise everything else for real — the state
machine, the plausibility layer, the durable store, and the dataset written for
`run_spatial_test`. No board, no probe, no network.
"""

import json
import os
from datetime import datetime, timezone

import pytest

from fieldsense.domain.models import FieldSample
from fieldsense.domain.models.enums import SampleSource
from fieldsense.field.states import FieldState
from fieldsense.field_node import AutoTrigger, EnterTrigger, FieldNode, MCUTrigger
from fieldsense.hardware.gps.bridge_gps import UIEvent, parse_ui_event


# ------------------------------------------------------------- fakes


class FakeGPS:
    """Serves canned telemetry lines, the way the App Lab gateway would."""

    def __init__(self, lines):
        self.lines = list(lines)
        self.reads = 0

    def read_raw(self):
        self.reads += 1
        index = min(self.reads - 1, len(self.lines) - 1)
        return self.lines[index]


class FakeAdapter:
    """A probe and receiver that produce exactly the readings a test asks for."""

    def __init__(self, readings, gps_lines=None):
        self.readings = list(readings)
        self.index = 0
        self.initialized = False
        self.shutdown_called = False
        self.gps_adapter = FakeGPS(gps_lines or ["NO_FIX,0.0,0.0,Sats:0,HDOP:99.9,UI:0,TP:1,TZ:0"])
        self.last_acquisition_meta = {}

    def initialize(self):
        self.initialized = True

    def shutdown(self):
        self.shutdown_called = True

    def acquire_sample(self):
        reading = self.readings[min(self.index, len(self.readings) - 1)]
        self.index += 1
        self.last_acquisition_meta = {
            "gps_fix_valid": reading.get("fix_valid", True),
            "gps_quality": {"satellites": reading.get("satellites", 10),
                            "hdop": reading.get("hdop", 0.96)},
            "sensor_meta": {},
            "measurement_quality": reading.get("quality", 0.95),
        }
        return FieldSample(
            sample_id="HW-SMP-{:03d}".format(self.index),
            timestamp=datetime.now(timezone.utc),
            latitude=reading.get("lat", 17.5697),
            longitude=reading.get("lon", 78.4247),
            nitrogen=reading.get("nitrogen", 48.0),
            phosphorus=reading.get("phosphorus", 22.0),
            potassium=reading.get("potassium", 133.0),
            ph=reading.get("ph", 6.6),
            ec=reading.get("ec", 0.42),
            moisture=reading.get("moisture", 31.2),
            temperature=reading.get("temperature", 26.4),
            measurement_quality=reading.get("quality", 0.95),
            source=SampleSource.HARDWARE,
        )


def build_node(tmp_path, adapter, samples=3, **kwargs):
    """A node wired to `adapter`, writing everything under tmp_path."""
    node = FieldNode(
        planned_samples=samples,
        trigger="auto",
        panel_endpoint=None,
        session_root=str(tmp_path / "sessions"),
        output_dir=str(tmp_path / "artifacts"),
        dataset_path=str(tmp_path / "dataset.json"),
        settle_seconds=0.0,
        dwell_seconds=0.0,
        auto_delay=0.0,
        **kwargs,
    )
    node.adapter = adapter
    node.open_hardware = lambda: adapter.initialize()
    node.show = lambda extra=None: None          # no panel in a unit test
    return node


# ----------------------------------------------------------- triggers


def test_the_mcu_trigger_fires_on_a_counter_that_moved():
    gps = FakeGPS([
        "FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96,UI:4,TP:1,TZ:0",
        "FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96,UI:5,TP:1,TZ:1900",
    ])
    trigger = MCUTrigger(gps.read_raw, poll_seconds=0.0)
    trigger.sync()
    assert trigger.wait_for_press(timeout=2.0)


def test_the_mcu_trigger_ignores_a_counter_that_has_not_moved():
    gps = FakeGPS(["FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96,UI:4,TP:1,TZ:0"])
    trigger = MCUTrigger(gps.read_raw, poll_seconds=0.0)
    trigger.sync()
    assert not trigger.wait_for_press(timeout=0.2)


def test_syncing_adopts_a_press_that_happened_before_the_session_started():
    """Otherwise a press during boot fires sample 1 the instant the node arms."""
    gps = FakeGPS(["FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96,UI:7,TP:1,TZ:0"])
    trigger = MCUTrigger(gps.read_raw, poll_seconds=0.0)
    trigger.sync()
    assert trigger.last_count == 7
    assert not trigger.wait_for_press(timeout=0.2)


def test_an_mcu_reset_does_not_fire_a_burst_of_triggers():
    """A reflash restarts the counter at zero. That is not thirty presses."""
    gps = FakeGPS([
        "FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96,UI:30,TP:1,TZ:0",
        "FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96,UI:0,TP:1,TZ:0",
    ])
    trigger = MCUTrigger(gps.read_raw, poll_seconds=0.0)
    trigger.sync()
    assert not trigger.wait_for_press(timeout=0.2)
    assert trigger.last_count == 0


def test_firmware_without_the_control_is_distinguishable_from_no_press():
    old = parse_ui_event("FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96")
    assert not old.reported
    assert UIEvent(press_count=0).reported


def test_the_trigger_describes_a_panel_whose_touch_did_not_answer():
    gps = FakeGPS(["FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96,UI:0,TP:0,TZ:0"])
    trigger = MCUTrigger(gps.read_raw, poll_seconds=0.0)
    trigger.sync()
    assert "ABSENT" in trigger.describe()


def test_the_auto_trigger_says_it_is_not_an_operator():
    assert "REHEARSAL" in AutoTrigger(0.0).describe()


# -------------------------------------------------------- whole session


def test_a_three_sample_walk_stores_three_separate_samples(tmp_path):
    adapter = FakeAdapter([
        {"lat": 17.5697, "moisture": 31.2},
        {"lat": 17.5701, "moisture": 28.4},
        {"lat": 17.5705, "moisture": 25.9},
    ])
    node = build_node(tmp_path, adapter, samples=3)
    assert node.run() == 0

    records = node.session.store.records()
    assert [r["sample_index"] for r in records] == [1, 2, 3]
    assert [r["quality"] for r in records] == ["VALID"] * 3
    assert len({r["gps"]["latitude"] for r in records}) == 3
    assert node.session.distinct_location_count() == 3
    assert node.session.state is FieldState.RESULT
    assert adapter.shutdown_called


def test_the_exported_dataset_is_the_schema_the_frozen_pipeline_reads(tmp_path):
    adapter = FakeAdapter([
        {"lat": 17.5697 + i * 0.0004, "moisture": 31.2 - i} for i in range(3)])
    node = build_node(tmp_path, adapter, samples=3)
    node.run()

    entries = json.load(open(str(tmp_path / "dataset.json")))
    assert len(entries) == 3
    for entry in entries:
        assert set(entry) == {"field_sample", "field_intelligence_result",
                              "provenance", "acquired_at"}
        assert json.loads(entry["field_sample"])["sample_id"].startswith("HW-SMP-")
        assert entry["provenance"] == "LIVE_HARDWARE"


def test_samples_taken_in_air_never_reach_the_map(tmp_path):
    """They are stored, they are marked, and they are not interpolated."""
    air = {"moisture": 0.0, "ec": 0.0, "nitrogen": 0.0,
           "phosphorus": 0.0, "potassium": 0.0}
    adapter = FakeAdapter([dict(air, lat=17.5697 + i * 0.0004) for i in range(3)])
    node = build_node(tmp_path, adapter, samples=3)
    node.run()

    records = node.session.store.records()
    assert records, "the evidence must still be stored"
    assert all(r["quality"] == "SUSPICIOUS" for r in records)
    assert node.session.map_eligible_records() == []
    assert not os.path.exists(str(tmp_path / "dataset.json"))


def test_a_session_short_of_usable_samples_is_reported_not_processed(tmp_path):
    adapter = FakeAdapter([
        {"lat": 17.5697, "moisture": 31.2},
        {"moisture": 0.0, "ec": 0.0, "nitrogen": 0.0, "phosphorus": 0.0,
         "potassium": 0.0, "lat": 17.5701},
        {"moisture": 0.0, "ec": 0.0, "nitrogen": 0.0, "phosphorus": 0.0,
         "potassium": 0.0, "lat": 17.5705},
    ])
    node = build_node(tmp_path, adapter, samples=3)
    node.run()
    outcome = node.process()
    assert outcome["processed"] is False
    assert "usable for a map" in outcome["reason"]


def test_a_session_survives_being_resumed_after_a_power_cut(tmp_path):
    """Sample 1 and 2 are on disk; the resumed run must start at sample 3."""
    first = FakeAdapter([{"lat": 17.5697, "moisture": 31.2},
                         {"lat": 17.5701, "moisture": 28.4}])
    node = build_node(tmp_path, first, samples=2)
    node.run()
    session_id = node.session.store.session_id

    second = FakeAdapter([{"lat": 17.5705, "moisture": 25.9}])
    resumed = build_node(tmp_path, second, samples=3, resume=session_id)
    resumed.run()

    assert resumed.session.store.session_id == session_id
    indices = [r["sample_index"] for r in resumed.session.store.records()]
    assert indices == [1, 2, 3]


def test_every_sample_records_the_position_it_was_actually_taken_at(tmp_path):
    adapter = FakeAdapter([
        {"lat": 17.5697, "lon": 78.4247, "hdop": 0.9, "satellites": 11},
        {"lat": 17.5701, "lon": 78.4251, "hdop": 1.4, "satellites": 9},
    ])
    node = build_node(tmp_path, adapter, samples=2)
    node.run()
    gps = [r["gps"] for r in node.session.store.records()]
    assert gps[0]["latitude"] == 17.5697 and gps[0]["hdop"] == 0.9
    assert gps[1]["latitude"] == 17.5701 and gps[1]["satellites"] == 9


def test_a_probe_that_raises_is_retried_rather_than_ending_the_session(tmp_path):
    class Flaky(FakeAdapter):
        def acquire_sample(self):
            if self.index == 1:
                self.index += 1
                raise OSError("RS485 read timed out")
            return super().acquire_sample()

    adapter = Flaky([
        {"lat": 17.5697 + i * 0.0004, "moisture": 31.2 - i} for i in range(4)])
    node = build_node(tmp_path, adapter, samples=2)
    assert node.run() == 0
    assert node.session.stored_count == 2


def test_nothing_in_the_node_opens_an_outbound_network_connection(tmp_path):
    """The unit must run with the radios off. The panel and gateway are local."""
    import socket

    opened = []
    original = socket.socket.connect

    def watched(self, address):
        opened.append(address)
        return original(self, address)

    socket.socket.connect = watched
    try:
        adapter = FakeAdapter([
            {"lat": 17.5697 + i * 0.0004, "moisture": 31.2 - i} for i in range(3)])
        node = build_node(tmp_path, adapter, samples=3)
        node.run()
    finally:
        socket.socket.connect = original

    remote = [a for a in opened
              if isinstance(a, tuple) and a[0] not in ("127.0.0.1", "localhost", "::1")]
    assert not remote, "the node reached off-board: {}".format(remote)


# ------------------------------------------------- the board's own buttons


def _input_event(code, value, kind=1):
    """One struct input_event, as the kernel would write it."""
    import struct

    from fieldsense.field_node import INPUT_EVENT_FORMAT

    return struct.pack(INPUT_EVENT_FORMAT, 0, 0, kind, code, value)


def _fake_evdev(tmp_path, payload):
    """A file standing in for /dev/input/by-path/platform-gpio-keys-event."""
    path = str(tmp_path / "gpio-keys-event")
    with open(path, "wb") as handle:
        handle.write(payload)
    return path


def test_a_volume_key_press_is_a_start_press(tmp_path):
    from fieldsense.field_node import GPIO_KEY_CODES, ButtonTrigger

    path = _fake_evdev(tmp_path, _input_event(GPIO_KEY_CODES[0], 1))
    trigger = ButtonTrigger(device_path=path)
    assert trigger.available()
    assert trigger.poll()
    trigger.close()


def test_either_volume_key_starts_a_sample(tmp_path):
    """One action, two identical-feeling buttons. Remembering which is a trap."""
    from fieldsense.field_node import GPIO_KEY_CODES, ButtonTrigger

    for code in GPIO_KEY_CODES:
        trigger = ButtonTrigger(device_path=_fake_evdev(tmp_path, _input_event(code, 1)))
        assert trigger.poll(), "key {} did not trigger".format(code)
        trigger.close()


def test_a_key_release_is_not_a_press(tmp_path):
    from fieldsense.field_node import GPIO_KEY_CODES, ButtonTrigger

    trigger = ButtonTrigger(
        device_path=_fake_evdev(tmp_path, _input_event(GPIO_KEY_CODES[0], 0)))
    assert not trigger.poll()
    trigger.close()


def test_autorepeat_is_not_a_second_press(tmp_path):
    """A held button must take one sample, not one per repeat interval."""
    from fieldsense.field_node import GPIO_KEY_CODES, ButtonTrigger

    trigger = ButtonTrigger(
        device_path=_fake_evdev(tmp_path, _input_event(GPIO_KEY_CODES[0], 2)))
    assert not trigger.poll()
    trigger.close()


def test_a_non_key_event_is_ignored(tmp_path):
    """EV_SYN separators share the stream and must not read as presses."""
    from fieldsense.field_node import GPIO_KEY_CODES, ButtonTrigger

    trigger = ButtonTrigger(
        device_path=_fake_evdev(tmp_path, _input_event(GPIO_KEY_CODES[0], 1, kind=0)))
    assert not trigger.poll()
    trigger.close()


def test_syncing_discards_presses_queued_before_the_session_armed(tmp_path):
    from fieldsense.field_node import GPIO_KEY_CODES, ButtonTrigger

    payload = _input_event(GPIO_KEY_CODES[0], 1) * 3
    trigger = ButtonTrigger(device_path=_fake_evdev(tmp_path, payload))
    trigger.sync()
    assert not trigger.poll()
    trigger.close()


def test_a_missing_input_device_is_reported_not_crashed():
    """A unit with no readable evdev node must say so, not raise at boot."""
    from fieldsense.field_node import ButtonTrigger

    trigger = ButtonTrigger(device_path="/nonexistent/gpio-keys")
    assert not trigger.available()
    assert "UNAVAILABLE" in trigger.describe()
    assert not trigger.poll()


def test_the_composite_trigger_fires_on_whichever_control_was_used(tmp_path):
    from fieldsense.field_node import GPIO_KEY_CODES, ButtonTrigger, CompositeTrigger

    gps = FakeGPS(["FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96,UI:0,TP:0,TZ:0"])
    button = ButtonTrigger(device_path=_fake_evdev(tmp_path, _input_event(GPIO_KEY_CODES[1], 1)))
    mcu = MCUTrigger(gps.read_raw, poll_seconds=0.0)
    mcu.sync()

    composite = CompositeTrigger([button, mcu])
    assert composite.poll()
    composite.close()


def test_the_composite_trigger_drops_unavailable_controls(tmp_path):
    """A unit with no buttons wired must still run on whatever it does have."""
    from fieldsense.field_node import ButtonTrigger, CompositeTrigger

    gps = FakeGPS(["FIX_OK,1734.18N,07825.47E,Sats:10,HDOP:0.96,UI:0,TP:0,TZ:0"])
    composite = CompositeTrigger([
        ButtonTrigger(device_path="/nonexistent/gpio-keys"),
        MCUTrigger(gps.read_raw, poll_seconds=0.0),
    ])
    assert composite.available()
    assert [s.name for s in composite.sources] == ["mcu"]


def test_a_unit_with_no_control_at_all_says_so(tmp_path):
    from fieldsense.field_node import ButtonTrigger, CompositeTrigger

    composite = CompositeTrigger([ButtonTrigger(device_path="/nonexistent/gpio-keys")])
    assert not composite.available()
    assert "NO OPERATOR CONTROL" in composite.describe()
