"""Core domain enums for FieldSense AI."""

from enum import Enum


class SampleSource(str, Enum):
    """Source origin of a field sample."""
    VIRTUAL = "VIRTUAL"
    HARDWARE = "HARDWARE"


class ValidationState(str, Enum):
    """Downstream eligibility validation state of a field sample."""
    VALID = "VALID"
    VALID_WITH_WARNING = "VALID_WITH_WARNING"
    REJECTED = "REJECTED"


class SessionStatus(str, Enum):
    """Status lifecycle state of a field assessment session."""
    CREATED = "CREATED"
    COLLECTING = "COLLECTING"
    READY_FOR_PROCESSING = "READY_FOR_PROCESSING"
    PROCESSED = "PROCESSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
