"""The field workflow: an explicit, durable, multi-sample sampling session.

V1 proved acquisition. This package is what turns that into a field
instrument — a state machine the operator drives one sample at a time, a
plausibility layer that refuses to present sensor artifacts as soil data, and
storage that survives the power cut halfway through a session.

Nothing here imports hardware. `fieldsense.field_node` is the module that binds
this to a probe, a receiver, and a panel.
"""

from .geo import assess_movement, haversine_meters, position_uncertainty_m, spatial_spread_m
from .plausibility import PlausibilityConfig, PlausibilityVerdict, assess_reading
from .session import (
    DEFAULT_PLANNED_SAMPLES,
    MIN_PROCESSABLE_SAMPLES,
    FieldSession,
    MeasurementOutcome,
)
from .states import (
    ARMED_STATES,
    TRANSITIONS,
    FieldState,
    IllegalTransition,
    SampleQuality,
    assert_transition,
    can_transition,
)
from .store import FieldSessionStore, latest_session, list_sessions, new_session_id

__all__ = [
    "ARMED_STATES", "DEFAULT_PLANNED_SAMPLES", "MIN_PROCESSABLE_SAMPLES",
    "TRANSITIONS", "FieldSession", "FieldSessionStore", "FieldState",
    "IllegalTransition", "MeasurementOutcome", "PlausibilityConfig",
    "PlausibilityVerdict", "SampleQuality", "assert_transition",
    "assess_movement", "assess_reading", "can_transition", "haversine_meters",
    "latest_session", "list_sessions", "new_session_id",
    "position_uncertainty_m", "spatial_spread_m",
]
