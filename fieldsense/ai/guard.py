"""NarrativeGuard - deterministic safety filter for generated language.

Counterpart to the input-side ValidationEngine:

    ValidationEngine   guards DATA entering the pipeline
                       rejects physically implausible measurements

    NarrativeGuard     guards LANGUAGE leaving the pipeline
                       rejects agronomically unsupported statements

A language model will readily invent a fertilizer dosage, because it has read
a great deal of agronomy and does not know this instrument forbids one. Prompt
instructions reduce that; they do not eliminate it. Every generated string
therefore passes this deterministic filter before it can reach a screen.

Three independent checks, in increasing order of strength:

    1. Forbidden dose units       'kg', 'ha', 'litres', 'ppm', ...
    2. Forbidden substances/claims 'urea', 'gypsum', 'carbon credit', ...
    3. Unsupported numbers        any number absent from ExplanationContext

Check 3 is the strongest and the cheapest: a narrative may only restate
quantities the deterministic engines actually produced.
"""

import re
from typing import List, Optional, Set

from .config import GuardConfig
from .models import AINarrative, ExplanationContext, NarrativeStatus

# Matches a standalone number. The boundary guards stop it from matching digits
# embedded in identifiers such as 'Z03' or 'REC-Z03-001'.
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])(\d[\d,]*(?:\.\d+)?)(?![A-Za-z0-9])")


class NarrativeGuard:
    """Deterministic post-filter enforcing the FieldSense language boundary."""

    def __init__(self, config: Optional[GuardConfig] = None) -> None:
        """Initialize guard with configuration."""
        self.config = config or GuardConfig()

    def inspect_text(
        self,
        text: str,
        context: ExplanationContext,
        location: str = "text",
        max_chars: Optional[int] = None,
    ) -> List[str]:
        """Inspect a single string and return a list of violation codes.

        Args:
            text: Candidate narrative string.
            context: Deterministic context the text is permitted to describe.
            location: Label recorded in violation codes for auditability.
            max_chars: Optional length ceiling for this string.

        Returns:
            List of violation codes. Empty list means the text is acceptable.
        """
        violations: List[str] = []

        if text is None or not text.strip():
            return [f"EMPTY_NARRATIVE[{location}]:"]

        if max_chars is not None and len(text) > max_chars:
            violations.append(f"LENGTH_EXCEEDED[{location}]:{len(text)}>{max_chars}")

        lowered = text.lower()

        for token in self.config.forbidden_unit_tokens:
            if self._contains_token(lowered, token):
                violations.append(f"FORBIDDEN_UNIT[{location}]:{token}")

        for token in self.config.forbidden_substance_tokens:
            if self._contains_token(lowered, token):
                violations.append(f"FORBIDDEN_SUBSTANCE[{location}]:{token}")

        for phrase in self.config.forbidden_claim_phrases:
            if self._contains_token(lowered, phrase):
                violations.append(f"FORBIDDEN_CLAIM[{location}]:{phrase}")

        if self.config.reject_unsupported_numbers:
            allowed = context.allowed_numbers()
            for raw in _NUMBER_PATTERN.findall(text):
                value = self._parse_number(raw)
                if value is None:
                    continue
                if not self._is_allowed(value, allowed):
                    violations.append(f"UNSUPPORTED_NUMBER[{location}]:{raw}")

        return violations

    def inspect(self, narrative: AINarrative, context: ExplanationContext) -> List[str]:
        """Inspect a complete AINarrative, field summary and every zone entry.

        Args:
            narrative: Candidate narrative.
            context: Deterministic context it describes.

        Returns:
            Aggregated list of violation codes across all strings.
        """
        violations = self.inspect_text(
            narrative.field_summary,
            context,
            location="field_summary",
            max_chars=self.config.max_field_summary_chars,
        )

        for zone_id, text in narrative.zone_narratives.items():
            violations.extend(
                self.inspect_text(
                    text,
                    context,
                    location=zone_id,
                    max_chars=self.config.max_zone_narrative_chars,
                )
            )

        return violations

    def is_safe(self, narrative: AINarrative, context: ExplanationContext) -> bool:
        """Return True when the narrative carries no violations."""
        return not self.inspect(narrative, context)

    def enforce(self, narrative: AINarrative, context: ExplanationContext) -> AINarrative:
        """Return the narrative if safe, otherwise a rejected marker narrative.

        The rejected narrative carries the violation list so the outcome stays
        auditable. Callers are expected to substitute a deterministic template
        rather than display a rejected narrative.

        Args:
            narrative: Candidate narrative.
            context: Deterministic context it describes.

        Returns:
            The original narrative, or an empty GUARD_REJECTED narrative.
        """
        violations = self.inspect(narrative, context)
        if not violations:
            return narrative

        from dataclasses import replace

        return replace(
            narrative,
            field_summary="",
            zone_narratives={},
            generation_status=NarrativeStatus.GUARD_REJECTED,
            guard_violations=violations,
        )

    @staticmethod
    def _contains_token(lowered_text: str, token: str) -> bool:
        """Word-boundary containment test that ignores matches inside longer words."""
        pattern = r"(?<![a-z])" + re.escape(token.lower()) + r"(?![a-z])"
        return re.search(pattern, lowered_text) is not None

    @staticmethod
    def _parse_number(raw: str) -> Optional[float]:
        """Parse a matched numeric literal, tolerating thousands separators."""
        try:
            return float(raw.replace(",", ""))
        except ValueError:
            return None

    def _is_allowed(self, value: float, allowed: Set[float]) -> bool:
        """Check a number against the permitted set within configured tolerance."""
        tolerance = self.config.number_match_tolerance
        return any(abs(value - permitted) <= tolerance for permitted in allowed)
