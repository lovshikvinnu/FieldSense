"""Tests for the FieldSense V1 Unified Runner (v1_runner.py)."""

import os
import pytest
from fieldsense.live_collector import CollectionError, PROVENANCE_SIMULATED
from fieldsense.v1_runner import run_v1_pipeline, main
from run_spatial_test import dataset_provenance


def test_v1_runner_simulated_pipeline(tmp_path):
    """End-to-end simulated run via v1_runner orchestration."""
    out_json = str(tmp_path / "v1_test_sim.json")
    out_dir = str(tmp_path / "artifacts")

    result = run_v1_pipeline(
        samples=4,
        out_json=out_json,
        simulate=True,
        interactive=False,
        output_dir=out_dir,
        display="off",
    )

    assert result["samples_captured"] == 4
    assert result["dataset_path"] == out_json
    assert os.path.exists(out_json)
    assert dataset_provenance(out_json) == PROVENANCE_SIMULATED

    assert result["html_path"] is not None
    assert os.path.exists(result["html_path"])
    assert result["zones"] >= 1
    assert result["recommendations"] >= 1


def test_v1_runner_aborts_on_fewer_than_3_samples(tmp_path):
    """v1_runner must refuse to run spatial processing with fewer than 3 samples."""
    out_json = str(tmp_path / "too_few.json")
    out_dir = str(tmp_path / "artifacts")

    with pytest.raises(CollectionError) as exc_info:
        run_v1_pipeline(
            samples=2,
            out_json=out_json,
            simulate=True,
            interactive=False,
            output_dir=out_dir,
            display="off",
        )

    assert "requires at least 3 valid samples" in str(exc_info.value)


def test_v1_runner_cli_main_success(tmp_path):
    """CLI entry point main() returns 0 on successful execution."""
    out_json = str(tmp_path / "cli_sim.json")
    out_dir = str(tmp_path / "cli_artifacts")

    exit_code = main([
        "--samples", "3",
        "--simulate",
        "--no-interactive",
        "--out", out_json,
        "--output-dir", out_dir,
        "--display", "off",
    ])

    assert exit_code == 0
    assert os.path.exists(out_json)
    assert os.path.exists(os.path.join(out_dir, "field_test_map.html"))


def test_v1_runner_cli_main_failure(tmp_path, capsys):
    """CLI entry point main() returns 1 and outputs error message on failure."""
    out_json = str(tmp_path / "cli_fail.json")

    exit_code = main([
        "--samples", "1",
        "--simulate",
        "--no-interactive",
        "--out", out_json,
        "--display", "off",
    ])

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "[V1 RUNNER ERROR]" in stderr
