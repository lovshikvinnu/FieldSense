"""MockAIAdapter - deterministic template-based narrative generation.

This is the DEFAULT explanation backend, not a placeholder. It requires no
model weights, no inference binary, and no network, so the repository stays
clonable and runnable on any machine. Four properties matter:

    1. Always available   is_available() is unconditionally True
    2. Bit-exact          same context always yields the same text, so golden
                          scenario and determinism tests remain valid
    3. Instant            adds no measurable time to the sub-second pipeline
    4. Fallback target    substituted whenever a real model times out, is
                          absent, or trips NarrativeGuard

The task here is slot-filling over an already-structured decision, not
reasoning. The deterministic engines have already chosen the action, the
reason, and the evidence; only the phrasing remains.
"""

from typing import Dict, List, Optional

from .base import LocalLLMAdapter
from .config import GuardConfig
from .guard import NarrativeGuard
from .models import AINarrative, ExplanationContext, NarrativeStatus, ZoneContext

TEMPLATE_VERSION = "MOCK_TEMPLATE_v1"

# Plain-language rendering of a deterministic primary_issue parameter key.
_ISSUE_PHRASES: Dict[str, str] = {
    "nitrogen": "nitrogen-related soil scores",
    "phosphorus": "phosphorus availability indicators",
    "potassium": "potassium availability indicators",
    "ph": "soil pH balance",
    "ec": "soil salinity indicators",
    "salinity": "soil salinity indicators",
    "moisture": "soil moisture levels",
    "carbon_readiness": "carbon readiness indicators",
    "temperature": "soil temperature readings",
}

_STATUS_OPENERS: Dict[str, str] = {
    "POOR": "is among the weaker parts of this field",
    "MODERATE": "is in workable condition but is not the strongest part of this field",
    "HEALTHY": "is performing well relative to the rest of the field",
}

_CONFIDENCE_CLAUSES: Dict[str, str] = {
    "HIGH": "Spatial sample support here is high, so this pattern is well evidenced.",
    "MEDIUM": "Spatial sample support here is moderate.",
    "LOW": "Spatial sample support here is low, so treat this as indicative only.",
}


def _issue_phrase(primary_issue: Optional[str]) -> str:
    """Render a parameter key as a readable noun phrase."""
    if not primary_issue:
        return "overall soil condition"
    key = primary_issue.strip().lower()
    if key in _ISSUE_PHRASES:
        return _ISSUE_PHRASES[key]
    return f"{key.replace('_', ' ')} indicators"


def _format_measure(value: float) -> str:
    """Format a numeric measure without trailing noise."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.1f}"


def _percent(value: float) -> str:
    """Render a [0,1] score as a whole percentage."""
    return str(int(round(value * 100)))


class MockAIAdapter(LocalLLMAdapter):
    """Deterministic template explanation backend requiring no model weights."""

    def __init__(self, guard: Optional[NarrativeGuard] = None, self_check: bool = True) -> None:
        """Initialize the template backend.

        Args:
            guard: Optional NarrativeGuard. Templates are guard-clean by
                construction; the self-check exists so a future template edit
                that breaks the boundary fails loudly instead of shipping.
            self_check: When True, run generated text through the guard and
                record any violations on the returned narrative.
        """
        self.guard = guard or NarrativeGuard(GuardConfig())
        self.self_check = self_check
        self._initialized = False

    def is_available(self) -> bool:
        """Always True. This backend has no external dependency."""
        return True

    def initialize(self) -> None:
        """No resources to acquire."""
        self._initialized = True

    def explain(self, context: ExplanationContext) -> AINarrative:
        """Compose a deterministic narrative from the explanation context.

        Args:
            context: Deterministic pipeline results to describe.

        Returns:
            AINarrative with is_ai_generated False, so the dashboard can label
            the text honestly as template-generated rather than model-generated.
        """
        field_summary = self.compose_field_summary(context)
        zone_narratives = {
            zone.zone_id: self.compose_zone_narrative(zone) for zone in context.zones
        }

        narrative = AINarrative(
            field_summary=field_summary,
            zone_narratives=zone_narratives,
            generated_by=TEMPLATE_VERSION,
            generation_status=NarrativeStatus.FALLBACK_TEMPLATE,
            guard_violations=[],
            is_ai_generated=False,
            decision_support_only=True,
            evidence_level=context.evidence_level,
            # Held at 0.0 rather than measured, to keep this backend bit-exact
            # for golden scenario and determinism tests.
            generation_time_ms=0.0,
            methodology_version=context.methodology_version,
        )

        if self.self_check:
            violations = self.guard.inspect(narrative, context)
            if violations:
                from dataclasses import replace

                return replace(narrative, guard_violations=violations)

        return narrative

    def shutdown(self) -> None:
        """No resources to release."""
        self._initialized = False

    def compose_field_summary(self, context: ExplanationContext) -> str:
        """Build the whole-field paragraph.

        Public because LlamaCppAdapter uses it for per-section fallback when a
        model-generated section is rejected by NarrativeGuard.
        """
        sentences: List[str] = [
            f"Field {context.field_name} recorded an overall soil health score of "
            f"{_percent(context.overall_soil_health)}%, which the system classifies as "
            f"{context.soil_health_status}.",
            f"{context.valid_samples} of {context.total_samples} samples passed validation "
            f"and were used to build the field map.",
        ]

        if context.rejected_samples == 1:
            sentences.append(
                "1 sample was rejected as physically implausible and excluded from the map, "
                "but kept in the session record for audit."
            )
        elif context.rejected_samples > 1:
            sentences.append(
                f"{context.rejected_samples} samples were rejected as physically implausible "
                f"and excluded from the map, but kept in the session record for audit."
            )

        sentences.append(
            f"Interpolated coverage reached {_percent(context.coverage_ratio)}% of the mapped area."
        )

        if context.zone_count == 0:
            sentences.append("No spatially connected management zones were detected.")
        else:
            attention = sum(1 for z in context.zones if z.status == "POOR")
            zone_word = "zone" if context.zone_count == 1 else "zones"
            base = (
                f"The system identified {context.zone_count} spatially connected "
                f"management {zone_word}"
            )
            if attention == 1:
                sentences.append(f"{base}, 1 of which needs attention.")
            elif attention > 1:
                sentences.append(f"{base}, {attention} of which need attention.")
            else:
                sentences.append(f"{base}, none of which is currently flagged as poor.")

        return " ".join(sentences)

    def compose_zone_narrative(self, zone: ZoneContext) -> str:
        """Build the paragraph for a single management zone.

        Public because LlamaCppAdapter uses it for per-section fallback.
        """
        opener = _STATUS_OPENERS.get(zone.status, "was assessed by the system")
        sentences: List[str] = []

        if zone.status == "HEALTHY" or not zone.primary_issue:
            sentences.append(f"Zone {zone.zone_id} {opener}.")
        else:
            sentences.append(
                f"Zone {zone.zone_id} {opener}, showing lower "
                f"{_issue_phrase(zone.primary_issue)} than the surrounding area."
            )

        if zone.area_estimate > 0:
            sentences.append(f"It covers roughly {_format_measure(zone.area_estimate)} m².")

        sentences.append(
            _CONFIDENCE_CLAUSES.get(zone.confidence, "Spatial sample support here is moderate.")
        )

        if zone.actions:
            sentences.append(f"Recommended action: {zone.actions[0]}")
            if len(zone.actions) > 1:
                sentences.append(
                    f"{len(zone.actions)} recommended actions apply to this zone in total."
                )

        return " ".join(sentences)
