"""Tests for the value-based panel link.

The pixel path (display_bridge --target mcu) cannot work on the UNO Q: Serial
there is Arduino_RouterBridge's Monitor, every available() is a mon/read RPC
round trip measured at ~595 ms, and link_probe.ino clocked 1.68 calls/second
over 247 seconds - about 860 B/s. A 153,600-byte frame would take three
minutes. So the host sends values and the MCU draws the dashboard.

These tests pin the record format against the parser in
hardware_test/TFT_UNOQ/dashboard/dashboard.ino. If you change the keys on one
side, these fail until you change the other.

Hardware-free: nothing opens a socket.
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

from push_panel import build_record

SUMMARY = {
    "field_name": "Hardware Field Test",
    "soil_health_status": "HEALTHY",
    "soil_health_score": 0.79,
    "total_samples": 5,
    "valid_samples": 5,
    "rejected_samples": 0,
    "zone_count": 2,
    "recommendation_count": 4,
    "evidence_level": "LIMITED",
    "offline_mode": True,
}


def test_record_is_newline_terminated_ascii():
    record = build_record(SUMMARY)
    assert record.endswith(b"\n")
    assert record.decode("ascii")


def test_record_starts_with_the_sketch_sentinel():
    """dashboard.ino rejects anything not starting FS|, so line noise is safe."""
    assert build_record(SUMMARY).startswith(b"FS|")


def test_record_carries_every_mapped_field():
    text = build_record(SUMMARY).decode().strip()
    for key in ("f=", "s=", "h=", "n=", "v=", "r=", "z=", "c=", "e=", "o="):
        assert key in text, "missing {}".format(key)


def test_record_stays_small_enough_for_the_measured_link():
    """~860 B/s measured. Keep a full update well under one second."""
    assert len(build_record(SUMMARY)) < 200


def test_score_is_rounded_not_dumped_at_full_float_precision():
    record = build_record({"soil_health_score": 0.7912345678}).decode()
    assert "h=0.79" in record
    assert "0.7912" not in record


def test_delimiters_inside_values_cannot_break_the_parser():
    """A field name with | or = must not create spurious key/value pairs."""
    record = build_record({"field_name": "North|Field=A"}).decode().strip()
    assert record == "FS|f=North/Field-A"
    assert record.count("|") == 1
    assert record.count("=") == 1


def test_missing_fields_are_omitted_not_sent_empty():
    """The sketch keeps its last good value for absent keys."""
    record = build_record({"soil_health_status": "DEGRADED"}).decode().strip()
    assert record == "FS|s=DEGRADED"


def test_offline_mode_is_encoded_as_one_or_zero():
    assert b"o=1" in build_record({"offline_mode": True})
    assert b"o=0" in build_record({"offline_mode": False})


def test_empty_summary_still_produces_a_valid_record():
    """A degenerate summary must not emit something the sketch will reject."""
    assert build_record({}) == b"FS\n"


def test_newlines_in_values_cannot_split_one_record_into_two():
    record = build_record({"field_name": "line\nbreak"})
    assert record.count(b"\n") == 1


# ------------------------------------------------- the pipeline's bridge mode

def test_run_spatial_test_shares_one_record_builder():
    """Two copies of the key map would drift the moment one side gained a field."""
    from fieldsense.hardware.panel_renderer import build_panel_record

    assert build_record is build_panel_record


def test_bridge_mode_sends_the_record_over_the_link(tmp_path):
    """--display bridge must put the FS| record on the wire, not an RGB565 frame."""
    import json
    import socket
    import threading

    from run_spatial_test import push_record_to_mcu

    summary_path = tmp_path / "panel_summary.json"
    summary_path.write_text(json.dumps(SUMMARY), encoding="utf-8")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    received = []

    def accept_once():
        conn, _ = server.accept()
        received.append(conn.recv(4096))
        conn.close()

    thread = threading.Thread(target=accept_once, daemon=True)
    thread.start()

    result = push_record_to_mcu(
        str(summary_path), endpoint="127.0.0.1:{}".format(server.getsockname()[1]))
    thread.join(timeout=5)
    server.close()

    assert result["status"] == "PUSHED"
    assert received and received[0] == build_record(SUMMARY)
    # 76-ish bytes, not 153,600. The frame path is what made this mode useless.
    assert len(received[0]) < 200


def test_bridge_mode_rejects_a_serial_device_path(tmp_path):
    """A tty can never reach the panel: arduino-router owns the device itself."""
    from run_spatial_test import push_record_to_mcu

    result = push_record_to_mcu(str(tmp_path / "absent.json"), endpoint="/dev/ttyGS0")
    assert result["status"] == "FAILED"
    assert "host:port" in result["detail"]


def test_bridge_mode_never_raises_when_the_link_is_down(tmp_path):
    """A dead panel link must degrade to a reported status, not kill the run."""
    import json

    from run_spatial_test import push_record_to_mcu

    summary_path = tmp_path / "panel_summary.json"
    summary_path.write_text(json.dumps(SUMMARY), encoding="utf-8")

    result = push_record_to_mcu(str(summary_path), endpoint="127.0.0.1:1")
    assert result["status"] == "FAILED"
    assert "panel link" in result["detail"]


def test_bridge_mode_reports_a_missing_summary(tmp_path):
    from run_spatial_test import push_record_to_mcu

    result = push_record_to_mcu(str(tmp_path / "nope.json"), endpoint="127.0.0.1:7500")
    assert result["status"] == "FAILED"
    assert "panel summary" in result["detail"]

# ------------------------------------------------- one-shot socket lifetime


def _serve_once(listener, seen):
    """Accept one connection, record the record and how long the peer stayed."""
    conn, _ = listener.accept()
    opened = time.monotonic()
    conn.settimeout(10.0)
    payload = b""
    try:
        while True:
            chunk = conn.recv(256)
            if not chunk:
                break            # peer closed
            payload += chunk
    except OSError:
        pass
    seen.append((payload, time.monotonic() - opened))
    conn.close()


def _write_summary(tmp_path):
    """A minimal summary on disk - these tests must not need a pipeline run."""
    path = tmp_path / "panel_summary.json"
    path.write_text(json.dumps(SUMMARY), encoding="utf-8")
    return str(path)


def _run_push(summary_path, endpoint, extra=None):
    import push_panel
    argv = ["--summary", summary_path, "--port", endpoint]
    return push_panel.main(argv + (extra or []))


def test_one_shot_push_holds_the_socket_for_the_mcu_poll_cycle(tmp_path):
    """The default push must outlive the MCU's ~1 s poll, with no flags.

    The MCU pulls: monitor.h's _read() returns immediately unless a client is
    connected, and fieldsense_unoq.ino polls only about once a second (400 ms
    GPS drain plus ~595 ms for one Serial.available()). A connect-write-close
    finishes in milliseconds, so the record was almost never collected - the
    command reported success and the panel kept showing dashes.
    """
    import socket as _socket
    import threading

    listener = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    listener.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()

    seen = []
    thread = threading.Thread(target=_serve_once, args=(listener, seen))
    thread.start()
    try:
        # Short hold keeps the test fast; the mechanism is what is under test.
        rc = _run_push(_write_summary(tmp_path),
                       "{}:{}".format(host, port), ["--hold", "1.0"])
    finally:
        thread.join(timeout=15)
        listener.close()

    assert rc == 0
    assert len(seen) == 1
    payload, lifetime = seen[0]
    assert payload.startswith(b"FS|"), "record never arrived"
    assert payload.endswith(b"\n")
    assert lifetime >= 1.0, \
        "socket closed after {:.3f}s - too fast for the MCU poll".format(lifetime)


def test_hold_zero_restores_the_old_close_immediately_behaviour(tmp_path):
    """An explicit --hold 0 must still be available for scripted use."""
    import socket as _socket
    import threading

    listener = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    listener.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()

    seen = []
    thread = threading.Thread(target=_serve_once, args=(listener, seen))
    thread.start()
    try:
        rc = _run_push(_write_summary(tmp_path),
                       "{}:{}".format(host, port), ["--hold", "0"])
    finally:
        thread.join(timeout=15)
        listener.close()

    assert rc == 0
    assert seen[0][0].startswith(b"FS|")
    assert seen[0][1] < 1.0


def test_default_hold_is_long_enough_for_the_firmware_poll_interval():
    """Pin the default against the firmware timing it exists to cover.

    fieldsense_unoq.ino: GPS_DRAIN_MS (400 ms) + ~595 ms per Serial.available()
    is about one second per pass. The default must span several passes.
    """
    import push_panel
    assert push_panel.HOLD_SECONDS >= 2.0
