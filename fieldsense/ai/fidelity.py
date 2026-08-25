"""FidelityChecker — does the narrative agree with the numbers it describes?

Third and last filter on generated language, and the newest:

    ValidationEngine   guards DATA entering the pipeline
    NarrativeGuard     guards LANGUAGE leaving it - safe to say?
    FidelityChecker    guards MEANING - true to what was measured?

The guard cannot do this job and should not try. Its strongest rule is that
every number must appear in the ExplanationContext, which is exactly why a real
run on the UNO Q passed with the sentence "Five samples passed validation, while
five were rejected as implausible" against a context of five valid and zero
rejected. Five is in the context. The guard was right; it was answering a
different question.

Measured on hardware, Qwen2.5-0.5B produced four contradictions in one run:

    "indicating good overall soil health"   status was POOR
    "five were rejected as implausible"     rejected_samples was 0
    "high moisture levels"                  moisture score 0.0, a deficiency
    "spatial data support is high"          zone confidence was LOW

The third is the dangerous one. It inverts a deficiency into an excess directly
above a recommendation to review irrigation, and a farmer acting on it would
withhold water.

WHAT THIS IS NOT
----------------
Not comprehension. Every rule reads one deterministic field and looks for an
explicit assertion of its opposite. A model that invents something plausible and
non-contradictory still passes here. This raises the floor; it does not make a
small model trustworthy.

Deliberately conservative, because the failure modes are asymmetric. A missed
contradiction is one bad sentence. A false positive rejects every narrative into
the template and silently disables the model, with nothing to say it happened.
"""

import re
from typing import Any, List, Optional

from .config import FidelityConfig
from .models import ExplanationContext, ZoneContext

# Small models write counts as words. "Five samples were rejected" has to be
# comparable with rejected_samples == 0.
_WORD_NUMBERS = {
    "zero": 0, "no": 0, "none": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}

_COUNT_WORD = r"(\d+|" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")"

# Two shapes carry a count, and they put it on opposite sides of the keyword.
#
# Prose puts the count first - "five were rejected" - which is what a model
# writing sentences produces. A list-formatted answer puts it after a label:
# "Rejected as Implausible: 0". TinyLlama produced exactly that and the prose
# pattern matched the 5 from the PRECEDING "Sampled: 5", reporting a
# contradiction against text that was correct.
#
# The labelled form is checked first and wins, because a colon binds a value to
# its label unambiguously in a way that adjacency does not.
_REJECTED_LABELLED = re.compile(
    r"rejected[^:\n]{0,40}?:\s*" + _COUNT_WORD, re.IGNORECASE)
_PASSED_LABELLED = re.compile(
    r"(?:passed|validated)[^:\n]{0,40}?:\s*" + _COUNT_WORD, re.IGNORECASE)

# "five were rejected", "5 samples rejected", "five of five rejected".
_REJECTED_PATTERN = re.compile(
    _COUNT_WORD + r"(?:\s+of\s+\S+)?\s+(?:samples?\s+)?(?:were\s+|was\s+|are\s+|have\s+been\s+)?rejected",
    re.IGNORECASE,
)
_PASSED_PATTERN = re.compile(
    _COUNT_WORD + r"(?:\s+of\s+\S+)?\s+(?:samples?\s+)?(?:were\s+|was\s+|are\s+|have\s+)?(?:passed|validated)",
    re.IGNORECASE,
)

# Claims are scoped to the sentence that carries their subject.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_HEALTH_SUBJECTS = ("soil health", "overall condition", "overall soil", "field condition")
_CONFIDENCE_SUBJECTS = ("data support", "spatial data", "spatial support", "confidence", "support is")


def _to_count(token: str) -> Optional[int]:
    """Read a count written as digits or as an English word."""
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


class FidelityChecker:
    """Rejects generated text that contradicts the deterministic result."""

    def __init__(self, config: Optional[FidelityConfig] = None) -> None:
        """Initialize the checker with its term lists and thresholds."""
        self.config = config or FidelityConfig()

    # ------------------------------------------------------------- entry point

    def inspect(
        self,
        text: str,
        context: ExplanationContext,
        location: str = "text",
        zone: Optional[ZoneContext] = None,
    ) -> List[str]:
        """Return contradiction codes for one narrative section.

        Args:
            text: Candidate narrative string.
            context: The deterministic result it claims to describe.
            location: Label recorded in the codes, for auditability.
            zone: The zone this section is about, when it is a zone narrative.

        Returns:
            Violation codes. Empty means no contradiction was found, which is
            not the same as the text being correct.
        """
        if not self.config.enabled or not text or not text.strip():
            return []

        lowered = text.lower()
        violations: List[str] = []

        violations += self._check_health_status(lowered, context, location)
        violations += self._check_sample_counts(text, context, location)
        violations += self._check_moisture_polarity(lowered, context, zone, location)
        if zone is not None:
            violations += self._check_zone_severity(lowered, zone, location)
            violations += self._check_confidence(lowered, zone, location)
            violations += self._check_action_direction(lowered, zone, location)
        return violations

    # ----------------------------------------------------------------- helpers

    def _flag(self, location: str, field_name: str, expected: Any, claimed: Any) -> str:
        """Build one auditable violation code."""
        return "CONTRADICTS_CONTEXT[{}]:{}={} claimed {}".format(
            location, field_name, expected, claimed)

    def _opposing_near(self, lowered: str, subjects, opposing) -> Optional[str]:
        """Find an opposing term in the same sentence as a subject.

        Scoped by sentence rather than by character distance. A window of
        characters reaches backwards across a full stop, and "Map coverage is
        high. Spatial data support is low." then reads as an overstatement of
        confidence when it is an accurate description of two different things.
        A claim and its subject share a sentence; that is what makes them one
        claim.
        """
        for sentence in _SENTENCE_SPLIT.split(lowered):
            if not any(subject in sentence for subject in subjects):
                continue
            for term in opposing:
                if re.search(r"\b" + re.escape(term) + r"\b", sentence):
                    return term
        return None

    def _first_phrase(self, lowered: str, phrases) -> Optional[str]:
        """Return the first whole phrase present, or None."""
        for phrase in phrases:
            if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
                return phrase
        return None

    # ------------------------------------------------------------------- rules

    def _check_health_status(self, lowered, context, location) -> List[str]:
        """A POOR field must not be described as good, and the reverse."""
        status = (context.soil_health_status or "").upper()
        if status in ("POOR", "CRITICAL", "DEGRADED"):
            opposing = self.config.positive_terms
        elif status in ("HEALTHY", "GOOD"):
            opposing = self.config.negative_terms
        else:
            return []  # MODERATE and unknown states are not judged

        found = self._opposing_near(lowered, _HEALTH_SUBJECTS, opposing)
        return [self._flag(location, "soil_health_status", status, found)] if found else []

    def _check_sample_counts(self, text, context, location) -> List[str]:
        """Counts attached to 'rejected' or 'passed' must match the context.

        This is the rule the guard structurally cannot have. It checks that a
        number belongs to the field it is attached to, where the guard only
        checks that the number exists somewhere in the context at all.
        """
        violations = []
        for labelled, prose, field_name, expected in (
            (_REJECTED_LABELLED, _REJECTED_PATTERN,
             "rejected_samples", context.rejected_samples),
            (_PASSED_LABELLED, _PASSED_PATTERN,
             "valid_samples", context.valid_samples),
        ):
            claimed = None
            match = labelled.search(text)
            if match:
                claimed = _to_count(match.group(1))
            else:
                for match in prose.finditer(text):
                    claimed = _to_count(match.group(1))
                    if claimed is not None:
                        break

            if claimed is not None and claimed != expected:
                violations.append(self._flag(location, field_name, expected, claimed))
        return violations

    def _check_moisture_polarity(self, lowered, context, zone, location) -> List[str]:
        """A deficiency must not be described as an excess, or the reverse.

        The most consequential rule here. On the physical run the model wrote
        "high moisture levels" for a moisture score of 0.0, immediately above a
        recommendation to review irrigation.
        """
        score = context.moisture_score
        if score is None:
            return []

        if score <= self.config.low_score_ceiling:
            found = self._first_phrase(lowered, self.config.excess_moisture_terms)
            if found:
                return [self._flag(location, "moisture_score",
                                   "{:.2f} (deficient)".format(score), found)]
        elif score >= self.config.high_score_floor:
            found = self._first_phrase(lowered, self.config.deficient_moisture_terms)
            if found:
                return [self._flag(location, "moisture_score",
                                   "{:.2f} (excessive)".format(score), found)]
        return []

    def _check_zone_severity(self, lowered, zone, location) -> List[str]:
        """A zone needing attention must not be described as untroubled."""
        serious = (zone.status or "").upper() in ("POOR", "CRITICAL") or \
                  (zone.severity or "").upper() in ("HIGH", "CRITICAL")
        if not serious:
            return []

        found = self._first_phrase(lowered, self.config.minimising_terms)
        return [self._flag(location, "zone_severity",
                           "{}/{}".format(zone.status, zone.severity), found)] if found else []

    def _check_confidence(self, lowered, zone, location) -> List[str]:
        """Spatial support must not be overstated, nor understated."""
        confidence = (zone.confidence or "").upper()
        if confidence == "LOW":
            opposing = self.config.positive_terms
        elif confidence == "HIGH":
            opposing = self.config.negative_terms
        else:
            return []

        found = self._opposing_near(lowered, _CONFIDENCE_SUBJECTS, opposing)
        return [self._flag(location, "confidence", confidence, found)] if found else []

    def _check_action_direction(self, lowered, zone, location) -> List[str]:
        """A water recommendation must not be reversed into withholding water."""
        categories = {str(c).upper() for c in (zone.categories or [])}
        if "WATER" not in categories:
            return []

        found = self._first_phrase(lowered, self.config.water_reversal_terms)
        return [self._flag(location, "action_direction", "WATER", found)] if found else []
