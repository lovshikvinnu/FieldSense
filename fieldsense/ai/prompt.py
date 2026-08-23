"""Prompt construction for model-backed narrative generation.

Prompts are built per section rather than as one large request. Two reasons:

    1. A small quantized model produces short, factual text far more reliably
       than a long structured document, and needs no JSON parsing.
    2. Each section can be guarded and, if rejected, replaced by a
       deterministic template independently. One bad paragraph degrades one
       paragraph instead of discarding the whole narrative.

Prompt instructions REDUCE unsafe output. They do not guarantee it. Every
generated string still passes NarrativeGuard before it can be displayed.
"""

from typing import List

from .models import ExplanationContext, ZoneContext

SYSTEM_RULES = (
    "You are a plain-language explainer for a soil measurement instrument.\n"
    "You restate results that have already been calculated. You never add new information.\n"
    "\n"
    "Absolute rules:\n"
    "- Never state a fertilizer, chemical, or irrigation quantity of any kind.\n"
    "- Never name a fertilizer, chemical, or soil amendment.\n"
    "- Never mention carbon credits, carbon offsets, or carbon sequestration.\n"
    "- Never state a number that does not appear in the DATA block.\n"
    "- Never promise a yield, an outcome, or a guarantee.\n"
    "- Write plain sentences for a farmer. No lists, no headings, no markdown.\n"
)


def _percent(value: float) -> str:
    """Render a [0,1] score as a whole percentage string."""
    return str(int(round(value * 100)))


def _format_measure(value: float) -> str:
    """Format a numeric measure without trailing noise."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.1f}"


def build_field_summary_prompt(context: ExplanationContext) -> str:
    """Build the whole-field summary prompt.

    Args:
        context: Deterministic results to describe.

    Returns:
        Complete prompt string.
    """
    attention = sum(1 for z in context.zones if z.status == "POOR")

    data: List[str] = [
        f"field name: {context.field_name}",
        f"overall soil health score: {_percent(context.overall_soil_health)}%",
        f"overall condition: {context.soil_health_status}",
        f"samples collected: {context.total_samples}",
        f"samples that passed validation: {context.valid_samples}",
        f"samples rejected as implausible: {context.rejected_samples}",
        f"map coverage: {_percent(context.coverage_ratio)}%",
        f"management zones detected: {context.zone_count}",
        f"zones needing attention: {attention}",
        f"evidence level: {context.evidence_level}",
    ]

    return (
        f"{SYSTEM_RULES}\n"
        "DATA:\n"
        + "\n".join(data)
        + "\n\nTASK: Write three or four plain sentences summarising this field for the "
        "farmer. Use only the values in DATA.\n\nSUMMARY:"
    )


def build_zone_prompt(zone: ZoneContext) -> str:
    """Build the prompt for a single management zone.

    Args:
        zone: Deterministic zone description.

    Returns:
        Complete prompt string.
    """
    data: List[str] = [
        f"zone: {zone.zone_id}",
        f"condition: {zone.status}",
        f"severity: {zone.severity}",
        f"main limiting factor: {zone.primary_issue or 'none identified'}",
        f"area: {_format_measure(zone.area_estimate)} square metres",
        f"spatial data support: {zone.confidence}",
    ]
    if zone.actions:
        data.append(f"recommended action: {zone.actions[0]}")

    return (
        f"{SYSTEM_RULES}\n"
        "DATA:\n"
        + "\n".join(data)
        + "\n\nTASK: Write two or three plain sentences about this zone for the farmer. "
        "Use only the values in DATA.\n\nDESCRIPTION:"
    )


def build_retry_suffix(violations: List[str]) -> str:
    """Build the corrective instruction appended after a guard rejection.

    Args:
        violations: Guard violation codes from the rejected attempt.

    Returns:
        Suffix appended to the original prompt for one retry attempt.
    """
    reasons = ", ".join(sorted({v.split("[")[0] for v in violations}))
    return (
        f"\n\nYour previous answer was rejected ({reasons}). "
        "Rewrite it using ONLY the values in DATA. "
        "Do not state any quantity, unit, product name, or number that is not in DATA.\n\nREWRITE:"
    )
