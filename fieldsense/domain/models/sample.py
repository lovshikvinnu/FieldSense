"""FieldSample domain model representing one soil measurement event."""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, Union

from .enums import SampleSource, ValidationState


@dataclass(frozen=True)
class FieldSample:
    """Canonical FieldSample model representing one soil measurement event.

    This is a pure data contract. It contains no processing, calculation, or validation logic.
    """
    sample_id: str
    timestamp: Union[datetime, str]
    latitude: float
    longitude: float
    nitrogen: float
    phosphorus: float
    potassium: float
    ph: float
    ec: float
    moisture: float
    temperature: float
    measurement_quality: float
    source: SampleSource
    validation_state: ValidationState = ValidationState.VALID

    def to_dict(self) -> Dict[str, Any]:
        """Serialize sample to a dictionary representation."""
        data = asdict(self)
        if isinstance(self.timestamp, datetime):
            data["timestamp"] = self.timestamp.isoformat()
        else:
            data["timestamp"] = str(self.timestamp)
        data["source"] = self.source.value if isinstance(self.source, SampleSource) else str(self.source)
        data["validation_state"] = self.validation_state.value if isinstance(self.validation_state, ValidationState) else str(self.validation_state)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldSample":
        """Deserialize dictionary representation into a FieldSample."""
        data_copy = dict(data)
        if isinstance(data_copy.get("timestamp"), str):
            try:
                data_copy["timestamp"] = datetime.fromisoformat(data_copy["timestamp"])
            except ValueError:
                pass
        if isinstance(data_copy.get("source"), str):
            data_copy["source"] = SampleSource(data_copy["source"])
        if isinstance(data_copy.get("validation_state"), str):
            data_copy["validation_state"] = ValidationState(data_copy["validation_state"])
        return cls(**data_copy)
