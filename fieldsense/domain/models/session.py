"""FieldSession domain model representing one complete field-assessment operation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Any, Dict, Union

from .enums import SessionStatus
from .sample import FieldSample


@dataclass
class FieldSession:
    """FieldSession model representing one complete field-assessment operation.

    Contains session metadata, raw samples, and placeholders for downstream derived results.
    Raw samples remain strictly independent from derived intelligence.
    """
    session_id: str
    created_at: Union[datetime, str]
    status: SessionStatus = SessionStatus.CREATED
    field_name: Optional[str] = None
    samples: List[FieldSample] = field(default_factory=list)

    # Derived results placeholders (must be kept independent from raw samples)
    field_result: Optional[Any] = None
    spatial_result: Optional[Any] = None
    zones: List[Any] = field(default_factory=list)
    recommendations: List[Any] = field(default_factory=list)

    @property
    def sample_count(self) -> int:
        """Authoritative sample count derived from the raw samples list."""
        return len(self.samples)

    def add_sample(self, sample: FieldSample) -> None:
        """Add a raw FieldSample to the session."""
        if not isinstance(sample, FieldSample):
            raise TypeError(f"Expected FieldSample instance, got {type(sample).__name__}")
        self.samples.append(sample)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session metadata and raw samples to a dictionary."""
        created_at_str = self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at)
        status_str = self.status.value if isinstance(self.status, SessionStatus) else str(self.status)

        return {
            "session_id": self.session_id,
            "created_at": created_at_str,
            "status": status_str,
            "field_name": self.field_name,
            "sample_count": self.sample_count,
            "samples": [sample.to_dict() for sample in self.samples],
            "derived_results": {
                "field_result": self.field_result,
                "spatial_result": self.spatial_result,
                "zones": self.zones,
                "recommendations": self.recommendations,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldSession":
        """Deserialize dictionary representation into a FieldSession."""
        created_at_val = data.get("created_at")
        if isinstance(created_at_val, str):
            try:
                created_at_val = datetime.fromisoformat(created_at_val)
            except ValueError:
                pass

        status_val = data.get("status", SessionStatus.CREATED)
        if isinstance(status_val, str):
            status_val = SessionStatus(status_val)

        raw_samples = data.get("samples", [])
        parsed_samples = [
            s if isinstance(s, FieldSample) else FieldSample.from_dict(s)
            for s in raw_samples
        ]

        session = cls(
            session_id=data["session_id"],
            created_at=created_at_val,
            status=status_val,
            field_name=data.get("field_name"),
            samples=parsed_samples,
        )

        derived = data.get("derived_results", {})
        session.field_result = derived.get("field_result")
        session.spatial_result = derived.get("spatial_result")
        session.zones = derived.get("zones", [])
        session.recommendations = derived.get("recommendations", [])

        return session
