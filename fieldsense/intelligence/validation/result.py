"""ValidationResult model representing validation engine output."""

from dataclasses import dataclass, field
from typing import List, Dict, Any

from fieldsense.domain.models import ValidationState
from .reasons import ValidationReason


@dataclass(frozen=True)
class ValidationResult:
    """Evaluation output for a single FieldSample.

    Explicitly communicates pipeline eligibility and validation reasons.
    """
    sample_id: str
    state: ValidationState
    pipeline_eligible: bool
    reasons: List[ValidationReason] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ValidationResult to dictionary format."""
        return {
            "sample_id": self.sample_id,
            "state": self.state.value,
            "pipeline_eligible": self.pipeline_eligible,
            "reasons": [r.value for r in self.reasons],
        }
