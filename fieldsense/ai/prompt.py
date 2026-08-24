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

# WHY THIS DOES NOT LIST FORBIDDEN TERMS
#
# It used to carry the line "Never mention carbon credits, carbon offsets, or
# carbon sequestration". Qwen2.5-0.5B then produced all three phrases verbatim,
# in both sections, on every attempt including the retry. Naming a term to
# forbid it puts that term in a small model's context, where it reads as topic
# rather than prohibition.
#
# The replacement is a positive scope rule: describe the DATA and nothing else.
# That covers carbon claims without ever writing the words, and covers whatever
# the next model free-associates toward as well.
#
# The guard is unchanged and remains the enforcement. These instructions only
# reduce how often it has to fire.
SYSTEM_RULES = (
    "You are a plain-language explainer for a soil measurement instrument.\n"
    "You restate results that have already been calculated. You never add new information.\n"
    "\n"
    "Absolute rules:\n"
    "- Write only about the values listed in DATA. Introduce no other subject.\n"
    "- Never state a quantity, dose, or product name of any kind.\n"
    "- Never state a number that does not appear in the DATA block.\n"
    "- Never promise a yield, an outcome, or a guarantee.\n"
    "- Write plain sentences for a farmer. No lists, no headings, no markdown.\n"
)

# Word budgets, sized under the guard's character limits with margin: roughly six
# characters per word puts 120 words near 720 characters against a 900 limit, and
# 60 words near 360 against 500. The model was previously told a sentence count
# and no length at all, so "three or four sentences" became 1367 characters.
FIELD_SUMMARY_WORD_BUDGET = 120
ZONE_WORD_BUDGET = 60


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
        f"farmer, using at most {FIELD_SUMMARY_WORD_BUDGET} words in total. "
        "Use only the values in DATA. Stop when you have described them.\n\nSUMMARY:"
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
        + "\n\nTASK: Write two or three plain sentences about this zone for the farmer, "
        f"using at most {ZONE_WORD_BUDGET} words in total. "
        "Use only the values in DATA. Stop when you have described them.\n\nDESCRIPTION:"
    )


def build_retry_suffix(violations: List[str]) -> str:
    """Build the corrective instruction appended after a guard rejection.

    Args:
        violations: Guard violation codes from the rejected attempt.

    Returns:
        Suffix appended to the original prompt for one retry attempt.
    """
    codes = {v.split("[")[0] for v in violations}

    # Address the actual failure. The suffix used to name only quantities and
    # numbers, so a rejection for length was answered with advice about units -
    # which is why the retry came back 1493 characters after the first attempt
    # came back 1523. Violation codes are deliberately not echoed: naming what
    # went wrong reintroduces the vocabulary that caused it.
    corrections = ["Rewrite it using ONLY the values in DATA."]
    if "LENGTH_EXCEEDED" in codes:
        corrections.append("Your answer was far too long. Write much less.")
    if "FORBIDDEN_CLAIM" in codes or "FORBIDDEN_UNIT" in codes:
        corrections.append(
            "Describe only the values in DATA. Do not introduce any other subject, "
            "product, or scheme.")
    if "UNSUPPORTED_NUMBER" in codes:
        corrections.append("Use no number that is not written in DATA.")

    return (
        "\n\nYour previous answer was rejected. "
        + " ".join(corrections)
        + "\n\nREWRITE:"
    )
