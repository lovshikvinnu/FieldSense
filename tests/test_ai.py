"""Tests for the AI explanation layer (fieldsense/ai).

Covers the safety boundary (NarrativeGuard), the deterministic template
backend (MockAIAdapter), context reduction, and optional narrative rendering
in the offline dashboard.
"""

import os
import subprocess
import sys
from dataclasses import replace

import pytest

from fieldsense.ai import (
    AIAdapterFactory,
    AIConfig,
    AINarrative,
    ExplanationContext,
    GuardConfig,
    LlamaCppAdapter,
    MockAIAdapter,
    NarrativeGuard,
    NarrativeStatus,
    ZoneContext,
    build_context_from_view,
    build_explanation_context,
)
from fieldsense.demo import run_demo
from fieldsense.intelligence import FieldIntelligenceEngine, ValidationEngine
from fieldsense.presentation import LocalUIRenderer, UIFieldView, UIViewAdapter
from fieldsense.recommendations import RecommendationEngine
from fieldsense.spatial import SpatialConfig, SpatialEngine
from fieldsense.testing import GoldenDatasetRegistry
from fieldsense.zones import ZoneDetectionEngine


def _run_pipeline(scenario_name="competition_demo_v1"):
    """Execute the deterministic pipeline and return its stage outputs."""
    scenario = GoldenDatasetRegistry.get_scenario(scenario_name)
    session = GoldenDatasetRegistry.load_session(scenario)
    eligible = ValidationEngine().get_session_eligible_samples(session)
    intel = FieldIntelligenceEngine().process_many(eligible)
    spatial = SpatialEngine(config=SpatialConfig(grid_spacing_meters=10.0)).process(intel, eligible)
    zones = ZoneDetectionEngine().process(spatial)
    recs = RecommendationEngine().process(zones)
    return session, spatial, zones, recs


def _simple_context():
    """Minimal hand-built context for guard unit tests."""
    return ExplanationContext(
        field_name="North Field",
        session_id="SES-001",
        overall_soil_health=0.67,
        soil_health_status="MODERATE",
        nitrogen_score=0.42,
        moisture_score=0.55,
        carbon_readiness_score=0.61,
        total_samples=25,
        valid_samples=24,
        rejected_samples=1,
        coverage_ratio=1.0,
        zones=[
            ZoneContext(
                zone_id="Z03",
                status="POOR",
                severity="HIGH",
                primary_issue="nitrogen",
                affected_parameters=["nitrogen"],
                confidence="HIGH",
                area_estimate=800.0,
            )
        ],
    )


# ---------------------------------------------------------------- NarrativeGuard


@pytest.mark.parametrize(
    "text,expected_code",
    [
        ("Apply approximately 40 kg/ha of urea to Zone Z03.", "FORBIDDEN_UNIT"),
        ("Irrigate Zone Z03 with 15 liters per square metre.", "FORBIDDEN_UNIT"),
        ("Add gypsum to correct the pH in Zone Z03.", "FORBIDDEN_SUBSTANCE"),
        ("This field can generate carbon credits.", "FORBIDDEN_CLAIM"),
        ("Nitrogen measured 137 units below the regional mean.", "UNSUPPORTED_NUMBER"),
    ],
)
def test_guard_blocks_unsafe_narratives(text, expected_code):
    """Every class of unsafe statement must be caught."""
    violations = NarrativeGuard().inspect_text(text, _simple_context(), location="Z03")
    assert violations, f"guard failed to block: {text}"
    assert any(v.startswith(expected_code) for v in violations)


def test_guard_blocks_dosage_with_redundant_coverage():
    """A hallucinated dosage trips both the unit list and the number check."""
    violations = NarrativeGuard().inspect_text(
        "Apply approximately 40 kg/ha of urea before the next irrigation.",
        _simple_context(),
    )
    codes = {v.split("[")[0] for v in violations}
    assert "FORBIDDEN_UNIT" in codes
    assert "FORBIDDEN_SUBSTANCE" in codes
    assert "UNSUPPORTED_NUMBER" in codes


def test_guard_allows_supported_narrative():
    """Text restating only context values passes cleanly."""
    text = (
        "Zone Z03 is among the weaker parts of this field, showing lower "
        "nitrogen-related soil scores. It covers roughly 800 m². "
        "Overall field health is 67%."
    )
    assert NarrativeGuard().inspect_text(text, _simple_context()) == []


def test_guard_does_not_false_positive_on_ordinary_words():
    """Blocklist tokens embedded in longer words must not trigger."""
    text = "The background monitoring plan is limited, but that is acceptable here."
    assert NarrativeGuard().inspect_text(text, _simple_context()) == []


def test_guard_ignores_digits_inside_identifiers():
    """Zone and recommendation IDs must not read as unsupported numbers."""
    text = "Zone Z03 is covered by recommendation REC-Z03-NUTRIENT-N."
    assert NarrativeGuard().inspect_text(text, _simple_context()) == []


def test_guard_rejects_empty_and_overlong_text():
    """Empty and oversized strings are violations."""
    guard = NarrativeGuard()
    ctx = _simple_context()
    assert any(v.startswith("EMPTY_NARRATIVE") for v in guard.inspect_text("   ", ctx))

    long_text = "Zone Z03 is stable. " * 60
    violations = guard.inspect_text(long_text, ctx, max_chars=100)
    assert any(v.startswith("LENGTH_EXCEEDED") for v in violations)


def test_guard_enforce_blanks_rejected_narrative():
    """enforce() strips unsafe text and records why, keeping the outcome auditable."""
    unsafe = AINarrative(
        field_summary="Apply 40 kg of urea to this field.",
        zone_narratives={"Z03": "Spread lime across the zone."},
    )
    result = NarrativeGuard().enforce(unsafe, _simple_context())

    assert result.generation_status == NarrativeStatus.GUARD_REJECTED
    assert result.field_summary == ""
    assert result.zone_narratives == {}
    assert result.guard_violations


def test_guard_unsupported_number_check_can_be_disabled():
    """The number check is configurable but on by default."""
    ctx = _simple_context()
    permissive = NarrativeGuard(GuardConfig(reject_unsupported_numbers=False))
    text = "Nitrogen measured 137 units below the mean."
    assert permissive.inspect_text(text, ctx) == []
    assert NarrativeGuard().inspect_text(text, ctx)


# ---------------------------------------------------------------- MockAIAdapter


def test_mock_adapter_is_always_available():
    """The template backend never depends on on-disk assets."""
    assert MockAIAdapter().is_available() is True


def test_mock_adapter_supports_context_manager():
    """Matches the SensorAdapter lifecycle idiom."""
    ctx = _simple_context()
    with MockAIAdapter() as adapter:
        narrative = adapter.explain(ctx)
    assert narrative.field_summary


def test_mock_narrative_passes_its_own_guard():
    """Templates must be guard-clean by construction, on real pipeline data."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)
    narrative = MockAIAdapter().explain(ctx)

    assert narrative.guard_violations == []
    assert NarrativeGuard().is_safe(narrative, ctx)


def test_mock_narrative_content_and_labelling():
    """Narrative restates deterministic facts and is labelled honestly."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)
    narrative = MockAIAdapter().explain(ctx)

    assert "24 of 25 samples" in narrative.field_summary
    assert "MODERATE" in narrative.field_summary
    assert len(narrative.zone_narratives) == len(zones.zones)
    assert narrative.is_ai_generated is False
    assert narrative.decision_support_only is True
    assert narrative.evidence_level == "LIMITED"
    assert narrative.generation_status == NarrativeStatus.FALLBACK_TEMPLATE


def test_mock_narrative_is_bit_exact_deterministic():
    """Two independent runs must produce identical narrative payloads."""
    ctx_a = build_explanation_context(*_run_pipeline())
    ctx_b = build_explanation_context(*_run_pipeline())

    assert ctx_a.to_dict() == ctx_b.to_dict()
    assert MockAIAdapter().explain(ctx_a).to_dict() == MockAIAdapter().explain(ctx_b).to_dict()


def test_mock_narrative_never_states_a_dosage():
    """The end-to-end safety promise, asserted on generated prose."""
    session, spatial, zones, recs = _run_pipeline()
    narrative = MockAIAdapter().explain(build_explanation_context(session, spatial, zones, recs))

    blob = (narrative.field_summary + " " + " ".join(narrative.zone_narratives.values())).lower()
    for banned in ["kg", "acre", "urea", "litre", "liter", "ppm", "hectare"]:
        assert banned not in blob


# ---------------------------------------------------------------- context


def test_build_explanation_context_reduces_pipeline_results():
    """Context mirrors deterministic values without recomputing them."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)

    assert ctx.total_samples == 25
    assert ctx.valid_samples == 24
    assert ctx.rejected_samples == 1
    assert ctx.zone_count == len(zones.zones)
    assert ctx.data_source == "VIRTUAL"
    assert ctx.evidence_level == "LIMITED"
    assert ExplanationContext.from_dict(ctx.to_dict()).to_dict() == ctx.to_dict()


def test_context_actions_are_capped_per_zone():
    """Prompt size stays bounded regardless of recommendation count."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs, max_actions_per_zone=2)
    assert all(len(z.actions) <= 2 for z in ctx.zones)


def test_build_context_from_view_matches_raw_builder():
    """The convenience path agrees with the canonical path on key values."""
    session, spatial, zones, recs = _run_pipeline()
    view = UIViewAdapter().adapt(session, spatial, zones, recs)

    raw_ctx = build_explanation_context(session, spatial, zones, recs)
    view_ctx = build_context_from_view(view)

    assert view_ctx.total_samples == raw_ctx.total_samples
    assert view_ctx.valid_samples == raw_ctx.valid_samples
    assert view_ctx.zone_count == raw_ctx.zone_count
    assert view_ctx.soil_health_status == raw_ctx.soil_health_status


def test_allowed_numbers_admits_scores_as_percentages():
    """A [0,1] score may be restated as a whole percentage."""
    allowed = _simple_context().allowed_numbers()
    assert 0.67 in allowed
    assert 67.0 in allowed
    assert 800.0 in allowed
    assert 137.0 not in allowed


# ---------------------------------------------------------------- presentation


def test_ui_field_view_narrative_defaults_to_none():
    """The added field is optional, so existing construction still works."""
    session, spatial, zones, recs = _run_pipeline()
    view = UIViewAdapter().adapt(session, spatial, zones, recs)

    assert view.narrative is None
    assert view.to_dict()["narrative"] is None


def test_ui_field_view_narrative_round_trip():
    """UIFieldView serialization survives an attached narrative."""
    session, spatial, zones, recs = _run_pipeline()
    view = UIViewAdapter().adapt(session, spatial, zones, recs)
    narrative = MockAIAdapter().explain(build_explanation_context(session, spatial, zones, recs))

    with_narrative = replace(view, narrative=narrative)
    restored = UIFieldView.from_dict(with_narrative.to_dict())

    assert restored.narrative is not None
    assert restored.narrative.field_summary == narrative.field_summary
    assert restored.to_dict() == with_narrative.to_dict()


def test_renderer_omits_narrative_card_when_absent():
    """A pipeline with no explanation layer still renders a complete dashboard."""
    session, spatial, zones, recs = _run_pipeline()
    view = UIViewAdapter().adapt(session, spatial, zones, recs)
    html = LocalUIRenderer().render_html(view)

    assert '"narrative": null' in html
    assert "FIELDSENSE AI" in html


def test_renderer_includes_narrative_when_present():
    """Narrative text reaches the offline dashboard payload."""
    session, spatial, zones, recs = _run_pipeline()
    view = UIViewAdapter().adapt(session, spatial, zones, recs)
    narrative = MockAIAdapter().explain(build_explanation_context(session, spatial, zones, recs))
    html = LocalUIRenderer().render_html(replace(view, narrative=narrative))

    assert "Plain Language Summary" in html
    assert "renderNarrative" in html
    assert "24 of 25 samples" in html
    assert 'src="http' not in html
    assert 'href="http' not in html


# ---------------------------------------------------------------- demo wiring


def test_demo_attaches_narrative_by_default(tmp_path):
    """The demo runner reports explanation-layer provenance."""
    out = str(tmp_path / "demo_ai.html")
    summary = run_demo(output_path=out, enable_narrative=True)

    assert summary["narrative_source"] == "MOCK_TEMPLATE_v1"
    assert summary["narrative_status"] == "FALLBACK_TEMPLATE"
    assert summary["narrative_violations_blocked"] == 0

    with open(out, "r", encoding="utf-8") as f:
        html = f.read()
    assert "Plain Language Summary" in html
    assert "kg/acre" not in html.lower()
    assert "liters" not in html.lower()


def test_demo_runs_with_narrative_disabled(tmp_path):
    """The explanation layer is genuinely optional."""
    out = str(tmp_path / "demo_no_ai.html")
    summary = run_demo(output_path=out, enable_narrative=False)

    assert summary["narrative_source"] == "DISABLED"
    assert summary["total_samples"] == 25
    assert os.path.exists(out)


def test_ai_narrative_serialization_round_trip():
    """AINarrative satisfies the project-wide to_dict/from_dict contract."""
    narrative = AINarrative(
        field_summary="Field summary text.",
        zone_narratives={"Z01": "Zone text."},
        generated_by="MOCK_TEMPLATE_v1",
        generation_status=NarrativeStatus.OK,
        guard_violations=["FORBIDDEN_UNIT[Z01]:kg"],
    )
    restored = AINarrative.from_dict(narrative.to_dict())

    assert restored.to_dict() == narrative.to_dict()
    assert restored.generation_status == NarrativeStatus.OK


# ---------------------------------------------------------------- factory


def test_factory_auto_resolves_to_mock_without_weights():
    """Absent GGUF weights is a normal condition, not an error."""
    adapter = AIAdapterFactory.create_adapter(AIConfig(backend="AUTO"))
    assert isinstance(adapter, MockAIAdapter)
    assert adapter.is_available() is True


def test_factory_honours_explicit_backend_choice():
    """Explicit backend selection overrides availability probing."""
    assert isinstance(AIAdapterFactory.create_adapter(AIConfig(backend="MOCK")), MockAIAdapter)
    assert isinstance(
        AIAdapterFactory.create_adapter(AIConfig(backend="LLAMA_CPP")), LlamaCppAdapter
    )


def test_factory_describes_active_backend():
    """Diagnostics string names the resolved backend."""
    assert "MockAIAdapter" in AIAdapterFactory.describe_active_backend(AIConfig(backend="AUTO"))


# ---------------------------------------------------------------- LlamaCppAdapter


def _fake_llama_binary(tmp_path, response, exit_code=0, sleep_seconds=0.0):
    """Create an executable stub standing in for llama-cli."""
    runner = tmp_path / "fake_llama_runner.py"
    runner_code = (
        "import sys, time\n"
        f"sleep_sec = {float(sleep_seconds)}\n"
        f"exit_c = {int(exit_code)}\n"
        f"resp = {repr(response)}\n"
        "if sleep_sec > 0:\n"
        "    time.sleep(sleep_sec)\n"
        "sys.stdout.write(resp)\n"
        "sys.exit(exit_c)\n"
    )
    runner.write_text(runner_code, encoding="utf-8")

    if sys.platform == "win32":
        script = tmp_path / "fake-llama-cli.cmd"
        script.write_text(
            f'@echo off\n"{sys.executable}" "{runner.resolve()}" %*\n',
            encoding="utf-8",
        )
    else:
        script = tmp_path / "fake-llama-cli"
        script.write_text(
            f'#!/bin/sh\n"{sys.executable}" "{runner.resolve()}" "$@"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)

    weights = tmp_path / "model.gguf"
    weights.write_bytes(b"GGUF-stub")
    return str(script), str(weights)


def _llama_config(tmp_path, response, exit_code=0, sleep_seconds=0.0, **overrides):
    binary, weights = _fake_llama_binary(tmp_path, response, exit_code, sleep_seconds)
    params = dict(
        backend="LLAMA_CPP",
        binary_path=binary,
        model_path=weights,
        timeout_seconds=10.0,
        max_zone_generations=1,
    )
    params.update(overrides)
    return AIConfig(**params)


def test_llama_adapter_unavailable_without_assets():
    """Missing weights and binary must not raise."""
    adapter = LlamaCppAdapter(AIConfig(model_path="/nonexistent/model.gguf"))
    assert adapter.is_available() is False


def test_llama_adapter_degrades_cleanly_when_model_absent():
    """An absent model still yields a complete, renderable narrative."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)

    narrative = LlamaCppAdapter(AIConfig(model_path="/nonexistent/model.gguf")).explain(ctx)

    assert narrative.generation_status == NarrativeStatus.MODEL_UNAVAILABLE
    assert narrative.is_ai_generated is False
    assert narrative.field_summary
    assert len(narrative.zone_narratives) == len(zones.zones)
    assert "MODEL_NOT_FOUND" in narrative.generated_by


def test_llama_adapter_accepts_safe_model_output(tmp_path):
    """Clean model output is used verbatim and marked AI generated."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)

    safe = "This field is in workable condition overall. Most samples passed validation checks."
    adapter = LlamaCppAdapter(_llama_config(tmp_path, safe))

    assert adapter.is_available() is True
    narrative = adapter.explain(ctx)

    assert narrative.is_ai_generated is True
    assert narrative.field_summary == safe
    assert narrative.generation_status in (NarrativeStatus.OK, NarrativeStatus.FALLBACK_TEMPLATE)


def test_llama_adapter_blocks_hallucinated_dosage_and_falls_back(tmp_path):
    """A model inventing a dosage must never reach the narrative."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)

    unsafe = "Apply 40 kg/ha of urea across this field before the next irrigation."
    narrative = LlamaCppAdapter(_llama_config(tmp_path, unsafe)).explain(ctx)

    blob = (narrative.field_summary + " " + " ".join(narrative.zone_narratives.values())).lower()
    assert "urea" not in blob
    assert "kg" not in blob
    assert narrative.guard_violations
    assert narrative.is_ai_generated is False
    assert narrative.generation_status in (
        NarrativeStatus.GUARD_REJECTED,
        NarrativeStatus.FALLBACK_TEMPLATE,
    )
    # The rejected section is replaced, not dropped.
    assert narrative.field_summary
    assert len(narrative.zone_narratives) == len(zones.zones)


def test_llama_adapter_retries_before_falling_back(tmp_path):
    """A rejection is retried once, so both attempts appear in the audit trail."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)

    config = _llama_config(
        tmp_path,
        "Spread gypsum over the field.",
        max_generation_attempts=2,
        generate_zone_narratives=False,
    )
    narrative = LlamaCppAdapter(config).explain(ctx)

    summary_violations = [v for v in narrative.guard_violations if "field_summary" in v]
    assert len(summary_violations) >= 2


def test_llama_adapter_handles_binary_failure(tmp_path):
    """A non-zero exit code degrades to templates and is recorded."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)

    narrative = LlamaCppAdapter(_llama_config(tmp_path, "", exit_code=1)).explain(ctx)

    assert narrative.is_ai_generated is False
    assert any("GENERATION_FAILED" in v for v in narrative.guard_violations)
    assert narrative.field_summary


def test_llama_adapter_handles_timeout(tmp_path):
    """A slow model is abandoned rather than blocking the dashboard."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)

    config = _llama_config(
        tmp_path,
        "too slow",
        sleep_seconds=2,
        timeout_seconds=0.3,
        generate_zone_narratives=False,
    )
    narrative = LlamaCppAdapter(config).explain(ctx)

    assert narrative.generation_status == NarrativeStatus.TIMEOUT
    assert any("TIMEOUT" in v for v in narrative.guard_violations)
    assert narrative.field_summary


def test_llama_adapter_covers_every_zone_despite_generation_cap(tmp_path):
    """Zones beyond the generation cap receive templates, never nothing."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)

    config = _llama_config(tmp_path, "This zone is stable.", max_zone_generations=1)
    narrative = LlamaCppAdapter(config).explain(ctx)

    assert len(narrative.zone_narratives) == len(zones.zones)
    assert all(text.strip() for text in narrative.zone_narratives.values())


def test_llama_adapter_cleans_end_of_text_markers(tmp_path):
    """Model end markers are stripped from displayed text."""
    session, spatial, zones, recs = _run_pipeline()
    ctx = build_explanation_context(session, spatial, zones, recs)

    config = _llama_config(tmp_path, "This field is in workable condition. [end of text]")
    narrative = LlamaCppAdapter(config).explain(ctx)

    assert "[end of text]" not in narrative.field_summary


def test_llama_command_includes_determinism_flags(tmp_path):
    """Temperature and seed are passed through for repeatability."""
    config = _llama_config(tmp_path, "ok", temperature=0.0, seed=42)
    command = LlamaCppAdapter(config)._build_command("PROMPT")

    assert "--temp" in command and "0.0" in command
    assert "--seed" in command and "42" in command
    assert "--no-display-prompt" in command


def test_llama_command_suppresses_conversation_mode(tmp_path):
    """The single-turn flag must be the one the target binary actually accepts.

    Pinned to a measurement, not a guess. llama.cpp on the UNO Q reports
    0.2.0-dev (build 10615, commit f280b2698, aarch64) and offers
    `-st, --single-turn`; it does NOT have the `-no-cnv` this default used to
    carry. An unrecognised flag here is expensive to diagnose, because
    llama-cli fails, the adapter records GENERATION_FAILED, and the run
    degrades to templates while still reporting a complete narrative.

    If a future llama.cpp renames this again, verify with
    `llama-cli --help | grep -i single-turn` and change AIConfig.extra_args,
    not this test's intent.
    """
    command = LlamaCppAdapter(_llama_config(tmp_path, "ok"))._build_command("PROMPT")

    assert "--single-turn" in command
    assert "-no-cnv" not in command, (
        "the target build does not accept -no-cnv; see AIConfig.extra_args")


# llama.cpp furniture observed on the UNO Q, build 10615, once setsid let its
# output reach a pipe. The spinner is literal backspaces; the stats line is what
# the terminal renders as "[ Prompt: 15.9 t/s | Generation: 8.3 t/s ]".
_LLAMA_SPINNER = "Loading model... " + "|\b-\b\\\b|\b/\b" * 40
_LLAMA_STATS = "\n\n[ Prompt: 15.9 t/s | Generation: 8.3 t/s ]\n\nExiting...\n"
_MODEL_TEXT = (
    "The field shows markedly low moisture across the single management zone, "
    "with nitrogen availability also constrained. Irrigation timing should be "
    "reviewed before any nutrient intervention is considered."
)


def test_clean_output_keeps_plain_model_text_untouched():
    """The baseline: without furniture, this text is already clean and allowed."""
    cleaned = LlamaCppAdapter._clean_output(_MODEL_TEXT)

    assert cleaned == _MODEL_TEXT


@pytest.mark.xfail(strict=True, reason="_clean_output does not yet strip llama.cpp furniture")
def test_clean_output_strips_the_llama_cpp_timing_line():
    """The timing line's token rates reach the guard as invented measurements.

    Observed on the UNO Q: UNSUPPORTED_NUMBER[field_summary]:15.9 and :8.3, which
    are llama.cpp's prompt and generation rates - not anything the model claimed
    about the field. The guard was right; it was reading llama.cpp's own output.
    """
    cleaned = LlamaCppAdapter._clean_output(_MODEL_TEXT + _LLAMA_STATS)

    assert "15.9" not in cleaned and "8.3" not in cleaned
    assert "t/s" not in cleaned
    assert "Exiting" not in cleaned


@pytest.mark.xfail(strict=True, reason="_clean_output does not yet strip llama.cpp furniture")
def test_clean_output_strips_the_loading_spinner():
    """The progress spinner is backspace control characters, not narrative.

    It arrived once setsid let generation reach a pipe, and it inflates every
    section toward LENGTH_EXCEEDED before the model has said anything.
    """
    cleaned = LlamaCppAdapter._clean_output(_LLAMA_SPINNER + "\n" + _MODEL_TEXT)

    assert "Loading model" not in cleaned
    assert "\b" not in cleaned
    assert not any(ord(c) < 32 and c not in "\n\t" for c in cleaned)


@pytest.mark.xfail(strict=True, reason="_clean_output does not yet strip llama.cpp furniture")
def test_clean_output_recovers_exactly_the_model_text_from_a_real_capture():
    """End to end on the shape the board actually produced.

    Spinner, then generation, then the timing line. What survives must be the
    model's sentences and nothing else - this is the contract that makes the
    guard's verdict about the model rather than about llama.cpp.
    """
    raw = _LLAMA_SPINNER + "\n" + _MODEL_TEXT + _LLAMA_STATS

    assert LlamaCppAdapter._clean_output(raw) == _MODEL_TEXT


def test_llama_detaches_the_controlling_terminal(tmp_path, monkeypatch):
    """llama-cli must run without a controlling terminal.

    It opens /dev/tty directly and renders a chat UI there. With a terminal
    present it exits 0 having written nothing to stdout or stderr, and the guard
    then reports EMPTY_NARRATIVE for text the model generated correctly.

    Measured on the UNO Q against llama.cpp 0.2.0-dev build 10615: inherited
    stdin gave 0 bytes on both pipes, stdin=DEVNULL gave 0 as well - stdin is
    not what it consults - and start_new_session gave 1055 bytes on stdout.

    Asserted on the call rather than through a pty, so it is deterministic and
    does not depend on whether the test runner happens to own a terminal.
    """
    seen = {}
    real_run = subprocess.run

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    LlamaCppAdapter(_llama_config(tmp_path, "ok"))._run_binary("PROMPT")

    assert seen.get("start_new_session") is True, (
        "without setsid llama-cli writes to /dev/tty and both pipes come back empty")


def test_llama_extra_args_are_appended_verbatim(tmp_path):
    """Whatever a deployment configures reaches the binary unchanged.

    The flag is configuration precisely so a board with a different llama.cpp
    can be corrected without a code change.
    """
    config = _llama_config(tmp_path, "ok", extra_args=("-st", "--flash-attn"))
    command = LlamaCppAdapter(config)._build_command("PROMPT")

    assert command[-2:] == ["-st", "--flash-attn"]
