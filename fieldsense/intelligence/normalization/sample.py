"""Normalized sample data model."""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass(frozen=True)
class NormalizedSample:
    """Standardized representation of a FieldSample suitable for deterministic scoring.

    Pure data model. Does not mutate raw FieldSample.
    """
    sample_id: str
    nitrogen: float
    phosphorus: float
    potassium: float
    ph: float
    ec: float
    moisture: float
    temperature: float
    methodology_version: str = "0.1"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize NormalizedSample to dictionary representation."""
        return asdict(self)
