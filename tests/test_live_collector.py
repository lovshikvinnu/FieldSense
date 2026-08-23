"""Tests for the live hardware sample collector and dataset provenance."""

import json
import os

import pytest

from fieldsense.live_collector import (
    PROVENANCE_LIVE,
    PROVENANCE_SIMULATED,
    CollectionError,
    collect_samples,
    write_dataset,
)
from run_spatial_test import dataset_provenance, parse_hardware_json, run_spatial_test


def _collect(points=4):
    return collect_samples(points=points, simulate=True, interactive=False, settle_seconds=0)


def test_collector_produces_entries_in_the_reader_schema():
    """Output must be exactly what run_spatial_test.parse_hardware_json expects."""
    entries = _collect(4)
    assert len(entries) == 4
    for entry in entries:
        assert set(entry) >= {"field_sample", "field_intelligence_result", "provenance", "acquired_at"}
        json.loads(entry["field_sample"])
        json.loads(entry["field_intelligence_result"])


def test_collected_dataset_round_trips_through_the_reader(tmp_path):
    path = write_dataset(_collect(4), str(tmp_path / "d.json"))
    samples, intel = parse_hardware_json(path)
    assert len(samples) == len(intel) == 4
    assert all(s.sample_id == i.sample_id for s, i in zip(samples, intel))


def test_simulated_output_is_stamped_and_never_claims_hardware(tmp_path):
    """A synthetic dataset must declare itself. This is the guard against
    presenting generated values as field measurements."""
    path = write_dataset(_collect(3), str(tmp_path / "sim.json"))
    assert dataset_provenance(path) == PROVENANCE_SIMULATED
    assert dataset_provenance(path) != PROVENANCE_LIVE


def test_provenance_detects_unstamped_and_mixed(tmp_path):
    unstamped = tmp_path / "old.json"
    unstamped.write_text(json.dumps([{"field_sample": "{}", "field_intelligence_result": "{}"}]))
    assert dataset_provenance(str(unstamped)) == "UNSTAMPED"

    mixed = tmp_path / "mixed.json"
    mixed.write_text(json.dumps([
        {"field_sample": "{}", "field_intelligence_result": "{}", "provenance": "LIVE_HARDWARE"},
        {"field_sample": "{}", "field_intelligence_result": "{}", "provenance": "SIMULATED"},
    ]))
    assert dataset_provenance(str(mixed)) == "MIXED"


def test_collector_refuses_to_write_nothing():
    """Zero usable samples must fail loudly rather than emit an empty dataset."""
    with pytest.raises(CollectionError):
        collect_samples(points=0, simulate=True, interactive=False, settle_seconds=0)


def test_run_spatial_test_refuses_to_fabricate_a_missing_dataset(tmp_path):
    """The regression that let a generated fixture be mistaken for field data."""
    missing = str(tmp_path / "field_test_live_hardware.json")
    with pytest.raises(FileNotFoundError) as exc:
        run_spatial_test(missing)
    assert "will NOT invent data" in str(exc.value)
    assert not os.path.exists(missing), "a missing dataset must not be silently created"


def test_generated_fixture_is_stamped_when_explicitly_requested(tmp_path):
    path = str(tmp_path / "fixture.json")
    summary = run_spatial_test(path, output_dir=str(tmp_path), display="off", allow_generate=True)
    assert os.path.exists(path)
    assert dataset_provenance(path) == "SYNTHETIC_FIXTURE"
    assert summary["provenance"] == "SYNTHETIC_FIXTURE"


def test_collected_samples_drive_the_full_pipeline_and_dashboard(tmp_path):
    """End-to-end: collector output → engines → HTML dashboard."""
    path = write_dataset(_collect(6), str(tmp_path / "run.json"))
    summary = run_spatial_test(path, output_dir=str(tmp_path), display="off")

    assert summary["samples"] == 6
    assert summary["grid_points"] > 0
    assert summary["zones"] >= 1
    assert summary["provenance"] == PROVENANCE_SIMULATED
    assert summary["display_status"] == "SKIPPED"

    html = summary["html_path"]
    assert os.path.exists(html)
    content = open(html, encoding="utf-8").read()
    assert "FIELDSENSE AI" in content
    assert 'src="http' not in content and 'href="http' not in content
