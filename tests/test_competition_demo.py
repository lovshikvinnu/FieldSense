"""Automated tests for competition demonstration scenario and guide (Sprint 11)."""

import os
import pytest

from fieldsense.demo import run_demo
from fieldsense.testing import GoldenDatasetRegistry
from fieldsense.intelligence import ValidationEngine, FieldIntelligenceEngine
from fieldsense.spatial import SpatialEngine
from fieldsense.zones import ZoneDetectionEngine
from fieldsense.recommendations import RecommendationEngine
from fieldsense.presentation import UIViewAdapter, LocalUIRenderer


def test_competition_demo_v1_scenario_content():
    scenario = GoldenDatasetRegistry.get_scenario("competition_demo_v1")
    assert scenario.num_samples == 25
    assert scenario.expected_valid_count == 24
    assert scenario.expected_rejected_count == 1

    session = GoldenDatasetRegistry.load_session(scenario)
    assert session.sample_count == 25


def test_competition_demo_pipeline_execution(tmp_path):
    out_path = str(tmp_path / "competition_demo.html")
    summary = run_demo(output_path=out_path, scenario_name="competition_demo_v1")

    assert summary["dataset"] == "competition_demo_v1"
    assert summary["total_samples"] == 25
    assert summary["valid_samples"] == 24
    assert summary["rejected_samples"] == 1
    assert summary["zone_count"] > 0
    assert summary["recommendation_count"] > 0
    assert summary["offline_mode"] is True
    assert os.path.exists(out_path)


def test_competition_demo_determinism():
    scenario = GoldenDatasetRegistry.get_scenario("competition_demo_v1")

    # Run 1
    session1 = GoldenDatasetRegistry.load_session(scenario)
    eligible1 = ValidationEngine().get_session_eligible_samples(session1)
    intels1 = FieldIntelligenceEngine().process_many(eligible1)
    spatial1 = SpatialEngine().process(intels1, eligible1)
    zones1 = ZoneDetectionEngine().process(spatial1)
    recs1 = RecommendationEngine().process(zones1)

    # Run 2
    session2 = GoldenDatasetRegistry.load_session(scenario)
    eligible2 = ValidationEngine().get_session_eligible_samples(session2)
    intels2 = FieldIntelligenceEngine().process_many(eligible2)
    spatial2 = SpatialEngine().process(intels2, eligible2)
    zones2 = ZoneDetectionEngine().process(spatial2)
    recs2 = RecommendationEngine().process(zones2)

    assert spatial1.to_dict() == spatial2.to_dict()
    assert zones1.to_dict() == zones2.to_dict()
    assert recs1.to_dict() == recs2.to_dict()


def test_competition_demo_ui_and_safety_checks(tmp_path):
    out_path = str(tmp_path / "competition_demo_safety.html")
    summary = run_demo(output_path=out_path, scenario_name="competition_demo_v1")

    with open(out_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert "<!DOCTYPE html>" in html
    assert "FIELDSENSE AI" in html
    assert "OFFLINE MODE" in html
    assert 'src="http' not in html
    assert 'href="http' not in html
    assert "kg/acre" not in html.lower()
    assert "liters" not in html.lower()
