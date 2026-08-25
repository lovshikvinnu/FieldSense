"""The field workflow state machine — what the operator is being asked to do.

V1 ran one pipeline cycle: collect N points in a loop, interpolate, render. The
loop was implicit, so nothing on the device could say *which* sample was being
taken, and nothing could tell an operator that sample 3 had been stored and it
was time to walk. This module makes that sequence explicit.

    BOOT -> READY -> MEASURING -> SAMPLE_SAVED -> READY_NEXT_SAMPLE -> ...
                                                        -> PROCESSING -> RESULT

The transition table below is the whole contract. It is deliberately data, not
control flow: an illegal transition raises rather than being quietly absorbed,
because a field device that silently ends up in the wrong state stores samples
under the wrong index and nobody finds out until the session is inspected.

Nothing here touches hardware or the filesystem. That is what makes the whole
workflow testable off-target, which matters when the only board is in a field.
"""

from enum import Enum
from typing import Dict, FrozenSet


class FieldState(str, Enum):
    """Every state the field device can be in during a sampling session."""

    BOOT = "BOOT"                              # subsystems coming up
    READY = "READY"                            # waiting for START, sample 1
    MEASURING = "MEASURING"                    # probe in soil, reading
    SAMPLE_SAVED = "SAMPLE_SAVED"              # sample committed to storage
    READY_NEXT_SAMPLE = "READY_NEXT_SAMPLE"    # waiting for START, sample n>1
    PROCESSING = "PROCESSING"                  # interpolating the full set
    RESULT = "RESULT"                          # field result on the panel
    ERROR = "ERROR"                            # something the operator must see


#: Legal transitions. Read as "from -> the set of states it may enter next".
TRANSITIONS: Dict[FieldState, FrozenSet[FieldState]] = {
    FieldState.BOOT: frozenset({FieldState.READY, FieldState.ERROR}),
    # MEASURING -> READY is the retry edge: a reading the plausibility layer
    # would not accept must NOT advance the sample index, or a rejected probe
    # position silently consumes one of the operator's five points.
    FieldState.READY: frozenset({FieldState.MEASURING, FieldState.ERROR}),
    FieldState.MEASURING: frozenset({
        FieldState.SAMPLE_SAVED, FieldState.READY,
        FieldState.READY_NEXT_SAMPLE, FieldState.ERROR,
    }),
    FieldState.SAMPLE_SAVED: frozenset({
        FieldState.READY_NEXT_SAMPLE, FieldState.PROCESSING, FieldState.ERROR,
    }),
    FieldState.READY_NEXT_SAMPLE: frozenset({FieldState.MEASURING, FieldState.ERROR}),
    FieldState.PROCESSING: frozenset({FieldState.RESULT, FieldState.ERROR}),
    # RESULT -> READY starts a fresh session. It never re-enters the session it
    # just finished: that session's samples are already written and closed.
    FieldState.RESULT: frozenset({FieldState.READY, FieldState.ERROR}),
    # ERROR is recoverable on purpose. A field unit that latches into a dead
    # state on one bad probe read is a unit the operator has to power-cycle
    # standing in a field, and a power cycle is what loses the session.
    FieldState.ERROR: frozenset({FieldState.READY, FieldState.READY_NEXT_SAMPLE,
                                 FieldState.PROCESSING}),
}

#: States in which a START press means "begin measuring". Nothing else accepts
#: one — a press during MEASURING or PROCESSING is noise, not an instruction.
ARMED_STATES: FrozenSet[FieldState] = frozenset({
    FieldState.READY, FieldState.READY_NEXT_SAMPLE,
})


class IllegalTransition(RuntimeError):
    """Raised when code asks for a transition the workflow does not allow."""


def can_transition(current: FieldState, target: FieldState) -> bool:
    """Return True when `current -> target` is a legal workflow edge."""
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: FieldState, target: FieldState) -> None:
    """Raise IllegalTransition unless `current -> target` is legal.

    Raises:
        IllegalTransition: The edge is not in TRANSITIONS.
    """
    if not can_transition(current, target):
        raise IllegalTransition(
            "{} -> {} is not a legal field workflow transition; legal targets "
            "are {}".format(
                current.value, target.value,
                sorted(s.value for s in TRANSITIONS.get(current, frozenset())) or ["<none>"],
            )
        )


class SampleQuality(str, Enum):
    """What the field plausibility layer concluded about one reading.

    Deliberately four-valued rather than a boolean. A probe standing in air
    produces numbers the frozen ValidationEngine accepts — every channel is
    inside its engineering sanity range — so a two-valued answer has to call
    that reading either 'good' or 'broken', and neither is true. SUSPICIOUS is
    the honest third answer: the sample is stored, is marked, and is not
    presented as an agronomic observation.
    """

    VALID = "VALID"            # store it, use it
    SUSPICIOUS = "SUSPICIOUS"  # store it, mark it, keep it out of the map
    RETRY = "RETRY"            # do not store; ask the operator to re-seat
    REJECTED = "REJECTED"      # store the evidence, never use the values


#: Qualities that may contribute values to the interpolated field map.
MAP_ELIGIBLE: FrozenSet[SampleQuality] = frozenset({SampleQuality.VALID})

#: Qualities that consume a sample index. RETRY does not: the operator is being
#: asked to take that same numbered sample again.
ADVANCES_INDEX: FrozenSet[SampleQuality] = frozenset({
    SampleQuality.VALID, SampleQuality.SUSPICIOUS, SampleQuality.REJECTED,
})
