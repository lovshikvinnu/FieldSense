"""The field sampling session — the state machine an operator actually drives.

This is the piece V1 did not have. V1's collector ran a `for` loop over N
points: the loop counter existed only inside one Python frame, so nothing on
the device could say which sample was in progress, nothing could tell the
operator that sample 3 was stored, and a power cut lost the lot.

`FieldSession` makes that sequence explicit, durable, and observable:

    session.boot_complete()          BOOT  -> READY (sample 1 of N)
    session.start_measurement()      READY -> MEASURING     (operator pressed START)
    session.record_measurement(...)  MEASURING -> SAMPLE_SAVED  (accepted)
                                               -> READY*      (retry, same index)
    session.begin_processing()       -> PROCESSING
    session.complete(summary)        -> RESULT

No hardware is touched here and no I/O happens beyond the session store, which
means the entire operator workflow — every transition, every retry, every
index — is testable with no board attached.

WHAT IS NOT INFERRED
--------------------
Sample boundaries come from `start_measurement()` and nothing else. GPS
movement never advances the index: a receiver drifting 8 m while the unit sits
on a bench is indistinguishable from a short walk, and the previous bench run
proved it produces a map of noise. The operator says when a sample begins.
"""

from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, List, Optional

from . import geo
from .plausibility import PlausibilityConfig, PlausibilityVerdict, assess_reading
from .states import (
    ADVANCES_INDEX,
    ARMED_STATES,
    FieldState,
    SampleQuality,
    assert_transition,
)
from .store import FieldSessionStore, utc_now_iso

#: Default point count. Matches V1's `--points 5` so an existing field
#: procedure keeps working unchanged.
DEFAULT_PLANNED_SAMPLES = 5

#: The spatial engine cannot interpolate below three points; V1 enforced this
#: in `run_v1_pipeline` and the same floor applies here.
MIN_PROCESSABLE_SAMPLES = 3


@dataclass
class MeasurementOutcome:
    """What happened to one attempted measurement."""

    accepted: bool
    quality: SampleQuality
    sample_index: int
    verdict: PlausibilityVerdict
    record: Optional[Dict[str, Any]] = None
    movement: Optional[geo.MovementVerdict] = None
    retry_count: int = 0
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for logs and the panel."""
        return {
            "accepted": self.accepted,
            "quality": self.quality.value,
            "sample_index": self.sample_index,
            "retry_count": self.retry_count,
            "message": self.message,
            "verdict": self.verdict.to_dict(),
            "movement": self.movement.to_dict() if self.movement else None,
        }


@dataclass
class FieldSession:
    """One multi-sample field session, from power-on to field result."""

    store: FieldSessionStore
    planned_samples: int = DEFAULT_PLANNED_SAMPLES
    plausibility: PlausibilityConfig = dataclass_field(default_factory=PlausibilityConfig)
    state: FieldState = FieldState.BOOT
    detail: str = "starting"
    last_outcome: Optional[MeasurementOutcome] = None
    _retry_count: int = 0

    def __post_init__(self) -> None:
        """Recover the sample index from disk, so a resumed session continues."""
        self.planned_samples = max(1, int(self.planned_samples))
        self.store.planned_samples = self.planned_samples
        self.sample_index = self.store.next_index()

    # ------------------------------------------------------------- queries

    @property
    def stored_count(self) -> int:
        """Samples already written for this session."""
        return self.store.stored_count()

    @property
    def complete(self) -> bool:
        """True once the planned number of samples has been stored."""
        return self.stored_count >= self.planned_samples

    @property
    def armed(self) -> bool:
        """True when a START press would begin a measurement."""
        return self.state in ARMED_STATES

    def _set_state(self, target: FieldState, detail: str) -> None:
        """Move to `target`, refusing an edge the workflow does not define.

        Raises:
            IllegalTransition: `target` is not reachable from the current state.
        """
        assert_transition(self.state, target)
        self.state = target
        self.detail = detail

    # --------------------------------------------------------- transitions

    def boot_complete(self, detail: str = "ready") -> FieldState:
        """Subsystems are up; arm the device for sample 1."""
        self._set_state(FieldState.READY, detail)
        return self.state

    def fail(self, detail: str) -> FieldState:
        """Enter ERROR with a reason the operator can read off the panel.

        Idempotent. A second failure while already in ERROR updates the reason
        rather than raising: the caller reporting it is handling a fault, and
        making fault handling itself throw is how a recoverable state turns
        into a crash the operator has to power-cycle out of.
        """
        if self.state is not FieldState.ERROR:
            assert_transition(self.state, FieldState.ERROR)
            self.state = FieldState.ERROR
        self.detail = detail
        self.store.write_manifest(last_error=detail)
        return self.state

    def recover(self, detail: str = "recovered") -> FieldState:
        """Leave ERROR and re-arm at whichever sample is still outstanding."""
        target = FieldState.READY if self.stored_count == 0 else FieldState.READY_NEXT_SAMPLE
        assert_transition(self.state, target)
        self.state = target
        self.detail = detail
        self.sample_index = self.store.next_index()
        return self.state

    def start_measurement(self) -> FieldState:
        """Operator pressed START. Begin reading the probe.

        Raises:
            IllegalTransition: Called when the device was not armed. A press
                during MEASURING or PROCESSING is noise and must not be turned
                into a second concurrent sample.
        """
        self._set_state(FieldState.MEASURING,
                        "measuring sample {}".format(self.sample_index))
        return self.state

    def record_measurement(
        self,
        soil: Dict[str, Any],
        gps: Dict[str, Any],
        validation_state: Optional[str] = None,
        validation_reasons: Optional[List[str]] = None,
        measurement_quality: Optional[float] = None,
        sample_id: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> MeasurementOutcome:
        """Judge, store, and account for one measurement.

        Args:
            soil: Probe channels — moisture, ph, ec, nitrogen, phosphorus,
                potassium, temperature.
            gps: Position block with at least `fix_valid`; `latitude`,
                `longitude`, `satellites` and `hdop` when there is a fix.
            validation_state: The frozen ValidationEngine's verdict.
            validation_reasons: That engine's reason codes, kept verbatim.
            measurement_quality: The adapter's own 0..1 confidence.
            sample_id: The adapter's id for this reading, if it issues one.
            diagnostics: Anything else worth keeping for a later audit — raw
                telemetry, register frames, retry history.

        Returns:
            A MeasurementOutcome. A RETRY outcome stores nothing and leaves the
            sample index where it was, so the operator re-takes the same
            numbered sample rather than burning one.
        """
        verdict = assess_reading(
            reading=soil,
            previous_reading=self.store.last_reading(),
            gps_fix_valid=bool(gps.get("fix_valid")),
            validation_state=validation_state,
            measurement_quality=measurement_quality,
            retry_count=self._retry_count,
            config=self.plausibility,
        )

        movement = self._assess_movement(gps)

        if not verdict.storable:
            self._retry_count += 1
            outcome = MeasurementOutcome(
                accepted=False, quality=verdict.quality,
                sample_index=self.sample_index, verdict=verdict,
                movement=movement, retry_count=self._retry_count,
                message=verdict.detail,
            )
            self.last_outcome = outcome
            # Back to armed at the SAME index. READY for sample 1,
            # READY_NEXT_SAMPLE once anything has been stored, so the panel
            # shows the right instruction.
            target = FieldState.READY if self.stored_count == 0 else FieldState.READY_NEXT_SAMPLE
            self._set_state(target, verdict.detail)
            return outcome

        record = self._build_record(
            soil=soil, gps=gps, verdict=verdict, movement=movement,
            validation_state=validation_state,
            validation_reasons=validation_reasons,
            measurement_quality=measurement_quality,
            sample_id=sample_id, diagnostics=diagnostics,
        )

        try:
            stored = self.store.append_sample(record)
        except OSError as exc:
            self.fail("could not write sample {}: {}".format(self.sample_index, exc))
            outcome = MeasurementOutcome(
                accepted=False, quality=verdict.quality,
                sample_index=self.sample_index, verdict=verdict,
                movement=movement, retry_count=self._retry_count,
                message="storage failure: {}".format(exc),
            )
            self.last_outcome = outcome
            return outcome

        outcome = MeasurementOutcome(
            accepted=True, quality=verdict.quality,
            sample_index=self.sample_index, verdict=verdict,
            record=stored, movement=movement, retry_count=self._retry_count,
            message="sample {} saved ({})".format(self.sample_index, verdict.quality.value),
        )
        self.last_outcome = outcome
        self._set_state(FieldState.SAMPLE_SAVED, outcome.message)
        if verdict.quality in ADVANCES_INDEX:
            self.sample_index = self.store.next_index()
            self._retry_count = 0
        return outcome

    def advance(self) -> FieldState:
        """Leave SAMPLE_SAVED for whatever comes next.

        Returns:
            READY_NEXT_SAMPLE while samples are outstanding, PROCESSING once
            the planned count has been reached.
        """
        if self.complete:
            self._set_state(FieldState.PROCESSING,
                            "processing {} samples".format(self.stored_count))
        else:
            self._set_state(
                FieldState.READY_NEXT_SAMPLE,
                "ready for sample {} of {}".format(self.sample_index, self.planned_samples))
        return self.state

    def begin_processing(self) -> FieldState:
        """Force the move to PROCESSING, e.g. an operator ending early."""
        if self.state is FieldState.SAMPLE_SAVED:
            self._set_state(FieldState.PROCESSING,
                            "processing {} samples".format(self.stored_count))
        else:
            assert_transition(self.state, FieldState.PROCESSING)
            self.state = FieldState.PROCESSING
            self.detail = "processing {} samples".format(self.stored_count)
        return self.state

    def complete_processing(self, summary: Optional[Dict[str, Any]] = None) -> FieldState:
        """Processing finished; the field result is ready to show."""
        self._set_state(FieldState.RESULT, "field result ready")
        self.result_summary = dict(summary or {})
        self.store.close("COMPLETED", result=self.result_summary,
                         spatial_spread_m=round(self.spatial_spread(), 2))
        return self.state

    # ------------------------------------------------------------ internals

    def _assess_movement(self, gps: Dict[str, Any]) -> Optional[geo.MovementVerdict]:
        """Compare this fix with the last stored one, when both are usable."""
        if not gps.get("fix_valid"):
            return None
        previous = self.store.last_position()
        if not previous:
            return None
        try:
            return geo.assess_movement(
                previous=(float(previous["latitude"]), float(previous["longitude"])),
                previous_hdop=previous.get("hdop"),
                current=(float(gps["latitude"]), float(gps["longitude"])),
                current_hdop=gps.get("hdop"),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _build_record(
        self,
        soil: Dict[str, Any],
        gps: Dict[str, Any],
        verdict: PlausibilityVerdict,
        movement: Optional[geo.MovementVerdict],
        validation_state: Optional[str],
        validation_reasons: Optional[List[str]],
        measurement_quality: Optional[float],
        sample_id: Optional[str],
        diagnostics: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Assemble the durable record for one accepted measurement."""
        return {
            "sample_index": self.sample_index,
            "sample_id": sample_id or "{}_p{:02d}".format(self.store.session_id, self.sample_index),
            "timestamp": utc_now_iso(),
            "quality": verdict.quality.value,
            "reasons": list(verdict.reasons),
            "detail": verdict.detail,
            "map_eligible": verdict.map_eligible,
            "retry_count": self._retry_count,
            "gps": dict(gps),
            "movement": movement.to_dict() if movement else None,
            "soil": dict(soil),
            "measurement_quality": measurement_quality,
            "validation": {
                "state": validation_state,
                "reasons": list(validation_reasons or []),
            },
            "diagnostics": dict(diagnostics or {}),
        }

    # -------------------------------------------------------------- reports

    def map_eligible_records(self) -> List[Dict[str, Any]]:
        """Stored samples whose values may feed the interpolated map."""
        return [r for r in self.store.iter_records() if r.get("map_eligible")]

    def spatial_spread(self) -> float:
        """Greatest separation between any two stored fixes, in metres."""
        points = []
        for record in self.store.iter_records():
            gps = record.get("gps") or {}
            if gps.get("fix_valid"):
                try:
                    points.append((float(gps["latitude"]), float(gps["longitude"])))
                except (KeyError, TypeError, ValueError):
                    continue
        return geo.spatial_spread_m(points)

    def distinct_location_count(self) -> int:
        """How many stored samples sit clear of the previous one's GPS noise.

        The honest denominator for any spatial claim. A session of five samples
        with a distinct-location count of one measured one place five times,
        whatever its five coordinates say.
        """
        count = 0
        previous = None
        for record in self.store.iter_records():
            gps = record.get("gps") or {}
            if not gps.get("fix_valid"):
                continue
            if previous is None:
                count = 1
            else:
                movement = record.get("movement") or {}
                if movement.get("distinct"):
                    count += 1
            previous = gps
        return count

    def summary(self) -> Dict[str, Any]:
        """A whole-session report, for the manifest, the panel, and the log."""
        records = self.store.records()
        return {
            "session_id": self.store.session_id,
            "state": self.state.value,
            "detail": self.detail,
            "planned_samples": self.planned_samples,
            "stored_samples": len(records),
            "sample_index": self.sample_index,
            "quality_counts": self.store.quality_counts(records),
            "map_eligible": sum(1 for r in records if r.get("map_eligible")),
            "distinct_locations": self.distinct_location_count(),
            "spatial_spread_m": round(self.spatial_spread(), 2),
            "processable": len([r for r in records if r.get("map_eligible")]) >= MIN_PROCESSABLE_SAMPLES,
        }
