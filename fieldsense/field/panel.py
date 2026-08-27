"""What the operator reads off the panel at each point in the workflow.

One function per concern:

    workflow_summary()   session state -> the mapping build_panel_record() sends
    action_line()        session state -> the one large instruction on the glass

Both live here rather than in the session so the state machine stays free of
presentation, and rather than in the firmware so the wording can change without
a flash cycle — on this board a flash-and-check round trip is about ninety
seconds, and the wording is the part most likely to need a second opinion from
somebody actually holding the unit.

The instruction text is deliberately short and imperative. It is rendered at
the largest size the landscape layout allows, because it is the only thing on
the panel a person reads while walking.
"""

import time
from typing import Any, Dict, Optional

from ..hardware.panel_renderer import (
    DEFAULT_PANEL_ENDPOINT,
    PANEL_HOLD_SECONDS,
    build_panel_record,
)
from .states import ARMED_STATES, FieldState

#: The large instruction, per state. `{i}` is the current sample index and
#: `{m}` the planned total; both are substituted before the record is built.
ACTION_LINES: Dict[FieldState, str] = {
    FieldState.BOOT: "STARTING",
    FieldState.READY: "PLACE PROBE - PRESS START",
    FieldState.MEASURING: "MEASURING - PLEASE WAIT",
    FieldState.SAMPLE_SAVED: "SAMPLE {i} SAVED",
    FieldState.READY_NEXT_SAMPLE: "MOVE TO NEXT LOCATION",
    FieldState.PROCESSING: "PROCESSING - PLEASE WAIT",
    FieldState.RESULT: "FIELD RESULT READY",
    FieldState.ERROR: "CHECK DEVICE",
}

#: The label on the full-width action button, per state. Empty means the device
#: is busy and there is nothing to press - the button is not drawn at all, which
#: is the clearest way to say "wait" on a panel read at arm's length outdoors.
BUTTON_LABELS: Dict[FieldState, str] = {
    FieldState.BOOT: "",
    FieldState.READY: "START SAMPLE",
    FieldState.MEASURING: "",
    FieldState.SAMPLE_SAVED: "",
    FieldState.READY_NEXT_SAMPLE: "NEXT SITE",
    FieldState.PROCESSING: "",
    # "HOLD" is not decoration - the firmware genuinely requires a longer press
    # here than anywhere else, because with no touch coordinates a stray brush
    # would otherwise dismiss a result the operator may not have read. A control
    # that behaves differently must say so, or it reads as an unresponsive one.
    FieldState.RESULT: "HOLD FOR NEW RUN",
    FieldState.ERROR: "HOLD FOR NEW RUN",
}

#: Button label when the previous attempt has to be taken again. Overrides the
#: armed-state label so the control names the actual next act, not the generic one.
RETRY_BUTTON_LABEL = "RETRY"

#: One short, actionable line per state - the "teaser banner". Kept to a single
#: line on purpose: this replaces sentences that were being read outdoors, in
#: sunlight, by someone holding a probe.
TEASER_LINES: Dict[FieldState, str] = {
    FieldState.BOOT: "STARTING UP",
    FieldState.READY: "PLACE PROBE IN SOIL",
    FieldState.MEASURING: "MEASURING - HOLD STILL",
    FieldState.SAMPLE_SAVED: "SAMPLE {i} SAVED",
    FieldState.READY_NEXT_SAMPLE: "MOVE TO THE NEXT SITE",
    FieldState.PROCESSING: "PROCESSING {m} SAMPLES",
    FieldState.RESULT: "FIELD RESULT READY",
    FieldState.ERROR: "CHECK DEVICE",
}

#: Teaser for a reading that has to be retaken. Names the physical cause,
#: because "RETRY" alone does not tell an operator what to change.
#: 21 characters, not 29. "PROBE LOOSE - RE-SEAT IN SOIL" said it better but
#: only fitted at text size 1, which is unreadable at arm's length in sunlight -
#: and this is the line an operator most needs to read without stopping to
#: squint. tests/test_landscape_panel.py holds every teaser to size 2 or above.
RETRY_TEASER = "RE-SEAT PROBE IN SOIL"

#: Progress-segment letters, one per planned sample. The panel draws one tile
#: per character: V solid green, S amber, R amber (in progress / retaking),
#: '-' unlit. Compressing the whole strip to N characters keeps it affordable
#: on a link measured at about 860 B/s.
SEGMENT_VALID = "V"
SEGMENT_FLAGGED = "S"
SEGMENT_CURRENT = "R"
SEGMENT_PENDING = "-"

#: Shown instead of the state's usual line when the previous attempt was not
#: accepted and the operator has to take that same sample again.
#:
#: Without this the panel is actively misleading. A RETRY verdict returns the
#: workflow to READY or READY_NEXT_SAMPLE - the same states it passes through
#: normally - so the glass said "PLACE PROBE - PRESS START" exactly as if
#: nothing had gone wrong, while the reason sat in a small quality field the
#: operator has no cause to read. Someone standing in a field would press again,
#: get the same rejection, and have nothing on screen to explain the loop.
RETRY_ACTION_LINE = "RESEAT PROBE - RETRY SAMPLE {i}"

#: Shown on the result screen. The session is finished and the only thing left
#: to do is start another one, so the instruction says so rather than merely
#: announcing that a result exists.
RESULT_ACTION_LINE = "COMPLETE - TAP FOR NEW RUN"

#: Channels lifted onto the panel from the most recent reading.
SOIL_KEYS = ("moisture", "ph", "ec", "nitrogen", "phosphorus", "potassium")


def button_label(state: FieldState, retrying: bool = False) -> str:
    """Return the text on the full-width action button.

    Empty when the device is busy. An absent button says "wait" more clearly
    than a greyed-out one, and removes any target to press by mistake.
    """
    if retrying and state in ARMED_STATES:
        return RETRY_BUTTON_LABEL
    return BUTTON_LABELS.get(state, "")


def teaser_line(
    state: FieldState,
    sample_index: int,
    planned: int,
    retrying: bool = False,
) -> str:
    """Return the single guidance line shown above the button."""
    template = RETRY_TEASER if (retrying and state in ARMED_STATES) \
        else TEASER_LINES.get(state, state.value)
    return template.format(i=sample_index, m=planned)


def progress_segments(session: Any, retrying: bool = False) -> str:
    """One character per planned sample, for the step bar across the top.

    Reads the stored records rather than a counter, so the strip cannot drift
    from what is actually on disk - a segment is lit because a sample exists,
    not because the workflow believes it should.

    V a stored VALID sample        S a stored but flagged one
    R the sample being taken now   -  not yet reached
    """
    planned = int(getattr(session, "planned_samples", 0) or 0)
    stored = []
    for record in session.store.iter_records():
        stored.append(SEGMENT_VALID if record.get("map_eligible") else SEGMENT_FLAGGED)

    segments = stored[:planned]
    current = len(segments)
    if current < planned:
        state = getattr(session, "state", None)
        if state in ARMED_STATES or state is FieldState.MEASURING or retrying:
            segments.append(SEGMENT_CURRENT)
    return "".join(segments).ljust(planned, SEGMENT_PENDING)[:planned]


def _is_retrying(outcome: Any) -> bool:
    """True when the last measurement was rejected and must be taken again.

    Keyed on the outcome not being accepted rather than on the quality word, so
    a storage failure reads as a retry to the operator too - from where they are
    standing the required action is identical.
    """
    return outcome is not None and not getattr(outcome, "accepted", True)


def _short_label(session_id: str) -> str:
    """Trim a session id to something that fits the panel's 23-char field."""
    return str(session_id).replace("session_", "", 1)[:23] or "FIELD SESSION"


def action_line(
    state: FieldState,
    sample_index: int,
    planned: int,
    retrying: bool = False,
    session_complete: bool = False,
) -> str:
    """Return the large operator instruction for one state.

    Args:
        state: The workflow state being displayed.
        sample_index: Sample number the instruction should refer to.
        planned: Planned sample count for the session.
        retrying: True when the previous attempt at this same sample was not
            accepted, so the line has to say that rather than repeating the
            ordinary prompt.
        session_complete: True on the result screen, where the useful
            instruction is how to begin another run.
    """
    if retrying and state in ARMED_STATES:
        template = RETRY_ACTION_LINE
    elif session_complete and state is FieldState.RESULT:
        template = RESULT_ACTION_LINE
    else:
        template = ACTION_LINES.get(state, state.value)
    return template.format(i=sample_index, m=planned)


def workflow_summary(
    session: Any,
    soil: Optional[Dict[str, Any]] = None,
    field_name: Optional[str] = None,
    offline: bool = True,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the panel mapping for a session mid-flight.

    Args:
        session: A `FieldSession`.
        soil: The most recent probe reading, when there is one to show.
        field_name: Session label for the panel header.
        offline: Whether the unit is running with the radios off.
        extra: Anything to overlay last — used by the result screen to fold in
            the finished pipeline's own summary.

    Returns:
        A mapping suitable for `build_panel_record`. Keys whose values are None
        are dropped, because the firmware keeps the last value it was given for
        anything a record does not mention: sending an empty field would blank
        a reading that is still the truth.
    """
    report = session.summary()
    outcome = getattr(session, "last_outcome", None)

    # Which sample number the panel is talking about.
    #
    # `session.sample_index` is the NEXT sample to take, which is the right
    # number in every state but one. In SAMPLE_SAVED it has already advanced,
    # so using it there would put "SAMPLE 2 SAVED" on the glass the instant
    # sample 1 was stored - the single most misleading thing this panel could
    # say, because the operator would walk away believing they had two.
    shown_index = report["sample_index"]
    if session.state is FieldState.SAMPLE_SAVED and outcome is not None:
        shown_index = outcome.sample_index
    elif session.state in (FieldState.PROCESSING, FieldState.RESULT):
        # Collection is over, so "the next sample" is not a thing any more and
        # showing it reads as a counting error: a finished five-sample session
        # rendered SAMPLE 6/5 on the glass, because sample_index had already
        # advanced past the last stored point. On these two screens the honest
        # number is how many were actually stored.
        shown_index = report["stored_samples"]

    summary: Dict[str, Any] = {
        "field_name": field_name or _short_label(session.store.session_id),
        "workflow_state": report["state"],
        "sample_index": shown_index,
        "planned_samples": report["planned_samples"],
        "action_line": teaser_line(
            session.state, shown_index, report["planned_samples"],
            retrying=_is_retrying(outcome)),
        "button_label": button_label(session.state, retrying=_is_retrying(outcome)),
        "progress_segments": progress_segments(session, retrying=_is_retrying(outcome)),
        "total_samples": report["stored_samples"],
        "valid_samples": report["quality_counts"].get("VALID", 0),
        "rejected_samples": (report["quality_counts"].get("REJECTED", 0)
                             + report["quality_counts"].get("SUSPICIOUS", 0)),
        "distinct_locations": report["distinct_locations"],
        "offline_mode": offline,
    }

    if outcome is not None:
        summary["sample_quality"] = outcome.quality.value

    if soil:
        for key in SOIL_KEYS:
            value = soil.get(key)
            if value is not None:
                summary[key] = value

    if extra:
        summary.update({k: v for k, v in extra.items() if v is not None})
    return summary


def push_summary(
    summary: Dict[str, Any],
    endpoint: Optional[str] = None,
    hold_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Send one panel record to the MCU over the router's monitor proxy.

    The socket is held open for `hold_seconds` after the write for the same
    reason `run_spatial_test.push_record_to_mcu` does it: the MCU pulls rather
    than being pushed to, its poll cycle is about a second, and a
    connect-write-close takes milliseconds — so a record written and
    immediately closed is almost never collected. A successful send is still
    not a successful delivery; only the glass proves that.

    Never raises. A panel that cannot be reached must not stop a field session:
    the sample still gets measured and stored.

    Returns:
        {"status": "PUSHED"|"FAILED"|"SKIPPED", "detail": str, "record": bytes}
    """
    from ..hardware.transport.tcp_socket import TcpTransport, TcpTransportError

    target = endpoint or DEFAULT_PANEL_ENDPOINT
    record = build_panel_record(summary)
    result: Dict[str, Any] = {"status": "SKIPPED", "detail": "", "record": record}

    if not target or ":" not in target:
        result["status"] = "FAILED"
        result["detail"] = (
            "panel endpoint must be host:port, got {!r}. The panel is reached "
            "through arduino-router's monitor proxy (default {}), not a tty."
            .format(target, DEFAULT_PANEL_ENDPOINT)
        )
        return result

    host, _, port_text = target.rpartition(":")
    try:
        transport = TcpTransport(host=host, port=int(port_text), timeout=10.0)
        transport.open()
    except (TcpTransportError, ValueError) as exc:
        result["status"] = "FAILED"
        result["detail"] = "cannot reach the panel link at {}: {}".format(target, exc)
        return result

    try:
        transport.write(record)
        time.sleep(PANEL_HOLD_SECONDS if hold_seconds is None else hold_seconds)
        result["status"] = "PUSHED"
        result["detail"] = "{} bytes -> {}".format(len(record), target)
    except TcpTransportError as exc:
        result["status"] = "FAILED"
        result["detail"] = "panel write failed: {}".format(exc)
    finally:
        transport.close()
    return result
