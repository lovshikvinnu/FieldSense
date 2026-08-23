"""Demonstration runner tests for fieldsense.demo (Sprint 10)."""

import os
from fieldsense.demo import run_demo


def test_system_demo_execution(tmp_path):
    output_html = str(tmp_path / "test_demo_dashboard.html")
    summary = run_demo(output_path=output_html)

    assert isinstance(summary, dict)
    assert summary["total_samples"] == 25
    assert summary["valid_samples"] == 24
    assert summary["rejected_samples"] == 1
    assert summary["offline_mode"] is True
    assert summary["data_source"] == "VIRTUAL"
    assert os.path.exists(output_html)

    with open(output_html, "r", encoding="utf-8") as f:
        content = f.read()

    assert "<!DOCTYPE html>" in content
    assert "FIELDSENSE AI" in content
    assert "OFFLINE MODE" in content
    assert 'src="http' not in content
    assert 'href="http' not in content
