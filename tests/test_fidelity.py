"""Tests for the semantic fidelity layer.

The four contradictions pinned here are verbatim from a physical run on the
UNO Q with Qwen2.5-0.5B. The pipeline reported OK and zero guard blocks for
that narrative: it was safe, in-length, and used no number absent from the
context. It was also wrong about four things, one of them dangerously.
"""

import pytest

from fieldsense.ai.config import FidelityConfig
from fieldsense.ai.fidelity import FidelityChecker
from fieldsense.ai.mock import MockAIAdapter
from fieldsense.ai.models import ExplanationContext, ZoneContext


def _context():
    """The context behind the physical run: POOR, 5 valid, 0 rejected, dry."""
    return ExplanationContext(
        field_name="Hardware Field Test",
        session_id="FIDELITY-001",
        overall_soil_health=0.36,
        soil_health_status="POOR",
        nitrogen_score=0.07,
        moisture_score=0.0,
        carbon_readiness_score=0.30,
        total_samples=5,
        valid_samples=5,
        rejected_samples=0,
        coverage_ratio=1.0,
        zones=[ZoneContext(
            zone_id="ZONE-01",
            status="POOR",
            severity="HIGH",
            primary_issue="moisture",
            affected_parameters=["moisture", "nitrogen"],
            confidence="LOW",
            area_estimate=225.0,
            action_ids=["REC-ZONE-01-WATER"],
            actions=["Review irrigation timing and soil moisture conditions."],
            categories=["WATER"],
            priorities=["HIGH"],
        )],
        evidence_level="LIMITED",
        methodology_version="0.1",
    )


def _codes(violations):
    """Reduce violation strings to the field each one is about."""
    return {v.split(":")[1].split("=")[0] for v in violations}


# ------------------------------------------------- the four real contradictions


def test_rejects_good_health_claim_for_a_poor_field():
    """From hardware: "indicating good overall soil health" with status POOR."""
    text = ("The Hardware Field Test was conducted on a field with a soil health "
            "score of 36%, indicating good overall soil health.")

    violations = FidelityChecker().inspect(text, _context(), "field_summary")

    assert "soil_health_status" in _codes(violations)


def test_rejects_a_rejected_count_the_context_does_not_support():
    """From hardware: "five were rejected as implausible" against zero rejected.

    The safety guard cannot catch this. Its rule is that a number must appear
    in the context, and five does - as valid_samples. Binding the number to the
    field it is attached to is the whole point of this layer.
    """
    text = ("Five samples passed validation, while five were rejected as "
            "implausible.")

    violations = FidelityChecker().inspect(text, _context(), "field_summary")

    assert "rejected_samples" in _codes(violations)
    assert any("claimed 5" in v for v in violations)


def test_rejects_an_excess_reading_of_a_moisture_deficiency():
    """From hardware: "high moisture levels" for a moisture score of 0.0.

    The most consequential of the four. It appeared directly above a
    recommendation to review irrigation, and a farmer acting on the sentence
    rather than the recommendation would withhold water.
    """
    ctx = _context()
    text = "The main limiting factor is high moisture levels."

    violations = FidelityChecker().inspect(text, ctx, "ZONE-01", zone=ctx.zones[0])

    assert "moisture_score" in _codes(violations)


def test_rejects_overstated_spatial_support():
    """From hardware: "spatial data support is high" with confidence LOW."""
    ctx = _context()
    text = ("The area is 225 square meters, and spatial data support is high.")

    violations = FidelityChecker().inspect(text, ctx, "ZONE-01", zone=ctx.zones[0])

    assert "confidence" in _codes(violations)


def test_the_whole_hardware_zone_narrative_is_rejected():
    """End to end on the exact text the pipeline accepted before this layer."""
    ctx = _context()
    text = ("This zone is in Zone 01, characterized by poor conditions. The main "
            "limiting factor is high moisture levels. The area is 225 square "
            "meters, and spatial data support is high. The recommended action is "
            "to review irrigation timing and soil moisture conditions in this zone.")

    violations = FidelityChecker().inspect(text, ctx, "ZONE-01", zone=ctx.zones[0])

    assert {"moisture_score", "confidence"} <= _codes(violations)


# ------------------------------------------- the fallback must survive the check


def test_the_template_fallback_passes_fidelity():
    """The deterministic narrative must never be rejected by this layer.

    If it were, a rejected model section would fall back to text that fails the
    same validator. Nothing in the pipeline would recover, and the failure would
    be silent and circular. This test is what makes the fallback path safe to
    enable at all.
    """
    ctx = _context()
    adapter = MockAIAdapter()
    adapter.initialize()
    narrative = adapter.explain(ctx)
    checker = FidelityChecker()

    assert checker.inspect(narrative.field_summary, ctx, "field_summary") == []
    for zone in ctx.zones:
        text = narrative.zone_narratives.get(zone.zone_id, "")
        assert checker.inspect(text, ctx, zone.zone_id, zone=zone) == []


def test_the_template_fallback_passes_across_varied_field_states():
    """Same guarantee for healthy, moderate and wet fields, not just this one."""
    checker = FidelityChecker()
    adapter = MockAIAdapter()
    adapter.initialize()

    for status, health, moisture, confidence in (
        ("HEALTHY", 0.91, 0.80, "HIGH"),
        ("MODERATE", 0.55, 0.50, "MEDIUM"),
        ("POOR", 0.20, 0.05, "LOW"),
    ):
        ctx = _context()
        zone = ctx.zones[0]
        ctx = ExplanationContext(
            field_name=ctx.field_name, session_id=ctx.session_id,
            overall_soil_health=health, soil_health_status=status,
            nitrogen_score=0.5, moisture_score=moisture,
            carbon_readiness_score=0.4, total_samples=5, valid_samples=4,
            rejected_samples=1, coverage_ratio=0.8,
            zones=[ZoneContext(
                zone_id=zone.zone_id, status=status, severity="MEDIUM",
                primary_issue="moisture", affected_parameters=["moisture"],
                confidence=confidence, area_estimate=225.0,
                action_ids=zone.action_ids, actions=zone.actions,
                categories=zone.categories, priorities=zone.priorities,
            )],
            evidence_level="LIMITED", methodology_version="0.1",
        )
        narrative = adapter.explain(ctx)

        assert checker.inspect(narrative.field_summary, ctx, "field_summary") == [], status
        text = narrative.zone_narratives.get(ctx.zones[0].zone_id, "")
        assert checker.inspect(text, ctx, ctx.zones[0].zone_id, zone=ctx.zones[0]) == [], status


# ----------------------------------------------------------- staying conservative


def test_an_accurate_narrative_passes():
    """Correct description of the same context draws nothing."""
    ctx = _context()
    text = ("This field scored 36% and is classified as POOR. All 5 samples "
            "passed validation and none were rejected. Moisture is the limiting "
            "factor and the evidence level is limited.")

    assert FidelityChecker().inspect(text, ctx, "field_summary") == []


def test_opposing_words_about_other_subjects_do_not_fire():
    """Proximity scoping: 'high' about coverage is not a claim about support."""
    ctx = _context()
    text = ("Map coverage is high across the surveyed area. Spatial data support "
            "is low, so treat the interpolation cautiously.")

    violations = FidelityChecker().inspect(text, ctx, "ZONE-01", zone=ctx.zones[0])

    assert "confidence" not in _codes(violations)


def test_moderate_status_is_not_judged():
    """Ambiguous bands are skipped rather than guessed at."""
    ctx = _context()
    moderate = ExplanationContext(
        field_name=ctx.field_name, session_id=ctx.session_id,
        overall_soil_health=0.55, soil_health_status="MODERATE",
        nitrogen_score=0.5, moisture_score=0.5, carbon_readiness_score=0.4,
        total_samples=5, valid_samples=5, rejected_samples=0, coverage_ratio=1.0,
        zones=[], evidence_level="LIMITED", methodology_version="0.1",
    )

    text = "Overall soil health looks good, and the overall condition is poor."

    assert FidelityChecker().inspect(text, moderate, "field_summary") == []


def test_word_numbers_are_understood():
    """Small models write counts as words."""
    ctx = _context()

    assert FidelityChecker().inspect(
        "Three samples were rejected.", ctx, "field_summary") != []
    assert FidelityChecker().inspect(
        "No samples were rejected.", ctx, "field_summary") == []


def test_reversed_water_advice_is_rejected():
    """A WATER recommendation must not be inverted into withholding water."""
    ctx = _context()
    text = "Conditions suggest you should reduce irrigation in this zone."

    violations = FidelityChecker().inspect(text, ctx, "ZONE-01", zone=ctx.zones[0])

    assert "action_direction" in _codes(violations)


def test_minimising_a_serious_zone_is_rejected():
    """A HIGH severity zone must not be described as untroubled."""
    ctx = _context()
    text = "This zone shows only minor variation and is no concern."

    violations = FidelityChecker().inspect(text, ctx, "ZONE-01", zone=ctx.zones[0])

    assert "zone_severity" in _codes(violations)


def test_disabled_config_is_a_complete_no_op():
    """The layer can be switched off without touching code."""
    ctx = _context()
    checker = FidelityChecker(FidelityConfig(enabled=False))
    text = "Excellent soil health, and five samples were rejected."

    assert checker.inspect(text, ctx, "field_summary") == []


def test_empty_text_is_not_a_contradiction():
    """Emptiness is the guard's business, not this layer's."""
    ctx = _context()

    assert FidelityChecker().inspect("", ctx, "field_summary") == []
    assert FidelityChecker().inspect("   ", ctx, "field_summary") == []
