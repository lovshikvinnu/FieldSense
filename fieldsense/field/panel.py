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
from .states import FieldState

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

#: Channels lifted onto the panel from the most recent reading.
SOIL_KEYS = ("moisture", "ph", "ec", "nitrogen", "phosphorus", "potassium")


def _short_label(session_id: str) -> str:
    """Trim a session id to something that fits the panel's 23-char field."""
    return str(session_id).replace("session_", "", 1)[:23] or "FIELD SESSION"


def action_line(state: FieldState, sample_index: int, planned: int) -> str:
    """Return the large operator instruction for one state."""
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

    summary: Dict[str, Any] = {
        "field_name": field_name or _short_label(session.store.session_id),
        "workflow_state": report["state"],
        "sample_index": shown_index,
        "planned_samples": report["planned_samples"],
        "action_line": action_line(
            session.state, shown_index, report["planned_samples"]),
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
