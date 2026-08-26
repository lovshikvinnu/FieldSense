"""Pin the host's FS| record against the firmware that parses it.

tests/test_panel_values.py checks the record the host BUILDS. Nothing checked
it against the sketch that READS it - the contract existed only as a comment,
and the comment named dashboard.ino while the board actually runs
firmware/unoq/fieldsense_unoq.ino.

That gap is expensive. The far side of this format is firmware: a mismatch is
invisible until someone flashes a board and watches the panel not update, and
on the UNO Q a flash-and-check cycle is about ninety seconds. These tests read
the .ino directly so drift fails here instead.

Hardware-free: the sketches are parsed as text, never compiled or flashed.
"""

import os
import re

import pytest

from fieldsense.hardware.panel_renderer import PANEL_RECORD_FIELDS, build_panel_record

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The firmware actually flashed for field runs. dashboard.ino is the
# display-only variant and must agree with it.
DEPLOYED = os.path.join(REPO_ROOT, "firmware", "unoq", "fieldsense_unoq.ino")
DISPLAY_ONLY = os.path.join(REPO_ROOT, "hardware", "tft-unoq", "dashboard", "dashboard.ino")

# 'o' is appended separately by build_panel_record, so it is not in
# PANEL_RECORD_FIELDS but is still on the wire.
HOST_KEYS = {key for key, _ in PANEL_RECORD_FIELDS} | {"o"}


def _read(path):
    if not os.path.exists(path):
        pytest.skip("sketch not present: {}".format(path))
    return open(path, encoding="utf-8", errors="replace").read()


def _parser_keys(source):
    """Keys handled by applyPair(), read straight out of the sketch."""
    body = re.search(r"applyPair\s*\([^)]*\)\s*\{(.*?)\n\}", source, re.S)
    assert body, "applyPair() not found - did the sketch's parser move?"
    return set(re.findall(r'strcmp\s*\(\s*key\s*,\s*"([^"]+)"\s*\)', body.group(1)))


def _sentinel(source):
    match = re.search(r'strncmp\s*\(\s*text\s*,\s*"([^"]+)"', source)
    assert match, "record sentinel check not found in the sketch"
    return match.group(1)


def _buffer_size(source, name):
    match = re.search(r"char\s+{}\s*\[\s*(\d+)\s*\]".format(re.escape(name)), source)
    assert match, "buffer {} not found in the sketch".format(name)
    return int(match.group(1))


# ------------------------------------------------------- key parity


def test_deployed_firmware_handles_every_key_the_host_sends():
    """A key the sketch ignores is a value that silently never appears."""
    missing = HOST_KEYS - _parser_keys(_read(DEPLOYED))
    assert not missing, "firmware ignores host keys: {}".format(sorted(missing))


def test_host_sends_every_key_the_deployed_firmware_expects():
    """A key the sketch waits for but never receives shows as a stale field."""
    unused = _parser_keys(_read(DEPLOYED)) - HOST_KEYS
    assert not unused, "firmware expects keys the host never sends: {}".format(sorted(unused))


def test_both_sketches_parse_the_same_record():
    """dashboard.ino and the deployed firmware must not diverge."""
    assert _parser_keys(_read(DEPLOYED)) == _parser_keys(_read(DISPLAY_ONLY))


# ------------------------------------------------------- framing


def test_host_record_starts_with_the_sentinel_the_firmware_requires():
    sentinel = _sentinel(_read(DEPLOYED))
    record = build_panel_record({"soil_health_status": "HEALTHY"})
    assert record.startswith(sentinel.encode()), \
        "firmware wants {!r}, host sends {!r}".format(sentinel, record[:4])


def test_record_is_newline_terminated_because_the_firmware_splits_on_it():
    assert build_panel_record({"total_samples": 5}).endswith(b"\n")


# ------------------------------------------------------- buffer limits


def test_a_realistic_record_fits_the_firmware_line_buffer():
    """Over lineBuf the sketch drops the WHOLE line, so a long field name
    silently loses every value in that update, not just the name."""
    cap = _buffer_size(_read(DEPLOYED), "lineBuf")
    record = build_panel_record({
        "field_name": "North Paddock Extended Trial Site",
        "soil_health_status": "HEALTHY",
        "soil_health_score": 0.79,
        "total_samples": 999,
        "valid_samples": 999,
        "rejected_samples": 99,
        "zone_count": 99,
        "recommendation_count": 99,
        "evidence_level": "LIMITED",
        "offline_mode": True,
    })
    assert len(record) < cap, \
        "record is {} bytes but lineBuf is {}".format(len(record), cap)


def test_an_absurd_field_name_cannot_silently_drop_the_whole_update():
    """Documents a real failure mode rather than asserting it cannot happen.

    The firmware truncates individual values safely via copyField(), but an
    overlong LINE is discarded entirely. Nothing host-side caps field_name
    today, so a pathological summary would blank an update with no error on
    either end. If this ever starts failing, the host gained a cap - update
    the test rather than removing it.
    """
    cap = _buffer_size(_read(DEPLOYED), "lineBuf")
    record = build_panel_record({"field_name": "X" * 400})
    assert len(record) > cap, "host now caps field_name; tighten this test"
