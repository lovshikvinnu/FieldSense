"""The multi-sample field workflow: states, plausibility, jitter, and storage.

Everything here runs with no board attached. That is the point of the split
between `fieldsense.field` and `fieldsense.field_node`: the sequence an
operator drives is the part most likely to be wrong and the part hardest to
debug standing in a field, so it is the part that must be testable at a desk.
"""

import json
import os

import pytest

from fieldsense.field import geo
from fieldsense.field.panel import action_line, workflow_summary
from fieldsense.field.plausibility import (
    PlausibilityConfig,
    assess_reading,
    channels_all_zero,
    nutrients_all_zero,
    readings_identical,
)
from fieldsense.field.session import FieldSession
from fieldsense.field.states import (
    ARMED_STATES,
    TRANSITIONS,
    FieldState,
    IllegalTransition,
    SampleQuality,
    assert_transition,
    can_transition,
)
from fieldsense.field.store import FieldSessionStore, atomic_write_json
from fieldsense.hardware.panel_renderer import build_panel_record

SOIL = {
    "moisture": 31.2, "ph": 6.6, "ec": 0.42, "temperature": 26.4,
    "nitrogen": 48.0, "phosphorus": 22.0, "potassium": 133.0,
}
AIR = {
    "moisture": 0.0, "ph": 7.0, "ec": 0.0, "temperature": 28.1,
    "nitrogen": 0.0, "phosphorus": 0.0, "potassium": 0.0,
}


def fix(lat=17.5697, lon=78.4247, hdop=0.96, sats=10, valid=True):
    """One GPS block, defaulting to the quality of the proven V1 field run."""
    return {"latitude": lat, "longitude": lon, "fix_valid": valid,
            "satellites": sats, "hdop": hdop}


def make_session(tmp_path, planned=5):
    store = FieldSessionStore(root=str(tmp_path / "sessions"), planned_samples=planned)
    return FieldSession(store=store, planned_samples=planned)


# --------------------------------------------------------------- states


def test_every_state_has_a_transition_entry():
    """A state with no entry silently accepts nothing and strands the workflow."""
    assert set(TRANSITIONS) == set(FieldState)


def test_the_happy_path_is_legal_end_to_end():
    path = [
        FieldState.BOOT, FieldState.READY, FieldState.MEASURING,
        FieldState.SAMPLE_SAVED, FieldState.READY_NEXT_SAMPLE,
        FieldState.MEASURING, FieldState.SAMPLE_SAVED, FieldState.PROCESSING,
        FieldState.RESULT,
    ]
    for current, target in zip(path, path[1:]):
        assert can_transition(current, target), "{} -> {}".format(current, target)


def test_measuring_can_fall_back_to_armed_without_saving():
    """The retry edge. Without it a rejected reading would burn a sample index."""
    assert can_transition(FieldState.MEASURING, FieldState.READY)
    assert can_transition(FieldState.MEASURING, FieldState.READY_NEXT_SAMPLE)


def test_illegal_transitions_raise_rather_than_being_absorbed():
    with pytest.raises(IllegalTransition):
        assert_transition(FieldState.READY, FieldState.RESULT)
    with pytest.raises(IllegalTransition):
        assert_transition(FieldState.PROCESSING, FieldState.MEASURING)


def test_error_is_recoverable():
    """A unit that latches on one bad read has to be power-cycled in a field."""
    assert can_transition(FieldState.ERROR, FieldState.READY)
    assert can_transition(FieldState.ERROR, FieldState.READY_NEXT_SAMPLE)


def test_only_the_two_waiting_states_accept_a_start_press():
    assert ARMED_STATES == {FieldState.READY, FieldState.READY_NEXT_SAMPLE}
    for state in (FieldState.MEASURING, FieldState.PROCESSING, FieldState.RESULT):
        assert state not in ARMED_STATES


# --------------------------------------------------------- plausibility


def test_a_probe_in_air_is_not_a_valid_soil_sample():
    """The bench failure this layer exists for: five VALID samples taken in air."""
    assert channels_all_zero(AIR)
    assert assess_reading(AIR).quality is SampleQuality.RETRY


def test_a_persistently_zero_probe_is_stored_and_marked_not_retried_forever():
    verdict = assess_reading(AIR, retry_count=2)
    assert verdict.quality is SampleQuality.SUSPICIOUS
    assert verdict.storable and not verdict.map_eligible


def test_soil_contact_alone_does_not_make_a_reading_suspicious():
    assert assess_reading(SOIL).quality is SampleQuality.VALID


def test_dead_nutrient_channels_are_flagged_without_discarding_moisture():
    reading = dict(SOIL, nitrogen=0.0, phosphorus=0.0, potassium=0.0)
    assert nutrients_all_zero(reading)
    verdict = assess_reading(reading)
    assert verdict.quality is SampleQuality.SUSPICIOUS
    assert "NUTRIENT_CHANNELS_ZERO" in verdict.reasons


def test_an_identical_repeat_reading_is_flagged():
    """A stale frame, or a probe that never moved. Soil does not repeat exactly."""
    assert readings_identical(SOIL, SOIL)
    assert "IDENTICAL_TO_PREVIOUS" in assess_reading(SOIL, previous_reading=SOIL).reasons


def test_a_sample_with_no_fix_is_retried_then_rejected():
    assert assess_reading(SOIL, gps_fix_valid=False).quality is SampleQuality.RETRY
    exhausted = assess_reading(SOIL, gps_fix_valid=False, retry_count=2)
    assert exhausted.quality is SampleQuality.REJECTED


def test_the_frozen_validator_is_never_overridden():
    """This layer may narrow VALID. It may not widen REJECTED."""
    verdict = assess_reading(SOIL, validation_state="REJECTED")
    assert verdict.quality is SampleQuality.REJECTED
    assert not verdict.map_eligible


def test_no_agronomic_threshold_is_applied_to_a_low_but_real_reading():
    """Low numbers from a probe that is in contact are data, not defects."""
    lean = dict(SOIL, moisture=4.1, nitrogen=2.0, phosphorus=1.0, potassium=3.0)
    assert assess_reading(lean).quality is SampleQuality.VALID


def test_retry_budget_is_configurable():
    config = PlausibilityConfig(max_retries=0)
    assert assess_reading(AIR, config=config).quality is SampleQuality.SUSPICIOUS


# ----------------------------------------------------------------- geo


def test_the_bench_run_that_looked_spatial_is_not_treated_as_movement():
    """8 m of spread at HDOP 3.58 sits inside the receiver's own noise floor."""
    verdict = geo.assess_movement((17.5697, 78.4247), 3.58,
                                  (17.56977, 78.42474), 3.58)
    assert not verdict.distinct
    assert verdict.distance_m < verdict.threshold_m


def test_a_real_walk_at_a_good_fix_is_recognised():
    verdict = geo.assess_movement((17.5697, 78.4247), 0.96,
                                  (17.5701, 78.4251), 0.96)
    assert verdict.distinct


def test_a_fix_with_no_hdop_cannot_establish_movement():
    verdict = geo.assess_movement((17.5697, 78.4247), None,
                                  (17.5900, 78.4500), None)
    assert not verdict.distinct
    assert "cannot be established" in verdict.detail


def test_uncertainty_never_drops_below_the_floor():
    """An optimistic HDOP must not license centimetre claims."""
    assert geo.position_uncertainty_m(0.5) >= geo.MIN_UNCERTAINTY_M


def test_spread_of_a_single_point_is_zero_not_an_error():
    assert geo.spatial_spread_m([(1.0, 2.0)]) == 0.0


# --------------------------------------------------------------- store


def test_sample_two_does_not_overwrite_sample_one(tmp_path):
    store = FieldSessionStore(root=str(tmp_path), planned_samples=3)
    store.append_sample({"sample_index": 1, "quality": "VALID", "soil": {"moisture": 30.0}})
    store.append_sample({"sample_index": 2, "quality": "VALID", "soil": {"moisture": 25.0}})
    records = store.records()
    assert [r["sample_index"] for r in records] == [1, 2]
    assert records[0]["soil"]["moisture"] == 30.0


def test_a_torn_final_line_costs_one_sample_and_no_more(tmp_path):
    """The shape of a crash mid-write. Everything before it must survive."""
    store = FieldSessionStore(root=str(tmp_path), planned_samples=3)
    store.append_sample({"sample_index": 1, "quality": "VALID"})
    store.append_sample({"sample_index": 2, "quality": "VALID"})
    with open(store.samples_path, "a", encoding="utf-8") as handle:
        handle.write('{"sample_index": 3, "qual')

    reopened = FieldSessionStore(session_id=store.session_id, root=str(tmp_path))
    assert reopened.stored_count() == 2
    assert reopened.next_index() == 3


def test_every_record_carries_its_session_id(tmp_path):
    """A power cut must not be able to merge two sessions into one dataset."""
    store = FieldSessionStore(root=str(tmp_path), planned_samples=2)
    stored = store.append_sample({"sample_index": 1})
    assert stored["session_id"] == store.session_id


def test_resuming_continues_the_index_rather_than_restarting(tmp_path):
    store = FieldSessionStore(root=str(tmp_path), planned_samples=5)
    store.append_sample({"sample_index": 1, "quality": "VALID"})
    store.append_sample({"sample_index": 2, "quality": "VALID"})
    session = FieldSession(
        store=FieldSessionStore(session_id=store.session_id, root=str(tmp_path)),
        planned_samples=5)
    assert session.sample_index == 3
    assert session.stored_count == 2


def test_the_manifest_is_replaced_atomically(tmp_path):
    """A reader sees the old manifest or the new one, never a half-written one."""
    path = os.path.join(str(tmp_path), "m.json")
    atomic_write_json(path, {"a": 1})
    atomic_write_json(path, {"a": 2})
    assert json.load(open(path)) == {"a": 2}
    leftovers = [n for n in os.listdir(str(tmp_path)) if n.startswith(".tmp-")]
    assert not leftovers, "temp files were left behind: {}".format(leftovers)


# ------------------------------------------------------------- session


def test_a_full_session_stores_every_sample_separately(tmp_path):
    session = make_session(tmp_path, planned=3)
    session.boot_complete()
    for step in range(3):
        session.start_measurement()
        outcome = session.record_measurement(
            soil=dict(SOIL, moisture=30.0 + step),
            gps=fix(lat=17.5697 + step * 0.001),
            validation_state="VALID", measurement_quality=0.95)
        assert outcome.accepted
        session.advance()

    assert session.complete
    records = session.store.records()
    assert [r["sample_index"] for r in records] == [1, 2, 3]
    assert len({r["soil"]["moisture"] for r in records}) == 3
    assert session.state is FieldState.PROCESSING


def test_a_retry_does_not_consume_a_sample_index(tmp_path):
    """A probe in air must not silently spend one of the operator's points."""
    session = make_session(tmp_path, planned=3)
    session.boot_complete()
    session.start_measurement()
    outcome = session.record_measurement(soil=AIR, gps=fix(), validation_state="VALID")

    assert not outcome.accepted
    assert outcome.quality is SampleQuality.RETRY
    assert session.sample_index == 1
    assert session.stored_count == 0
    assert session.state is FieldState.READY


def test_the_retry_budget_eventually_stores_the_evidence(tmp_path):
    session = make_session(tmp_path, planned=3)
    session.boot_complete()
    for _ in range(3):
        session.start_measurement()
        outcome = session.record_measurement(soil=AIR, gps=fix(), validation_state="VALID")
    assert outcome.accepted
    assert outcome.quality is SampleQuality.SUSPICIOUS
    assert session.stored_count == 1
    assert session.map_eligible_records() == []


def test_gps_movement_never_advances_a_sample_by_itself(tmp_path):
    """The index moves on an operator press and on nothing else."""
    session = make_session(tmp_path, planned=3)
    session.boot_complete()
    assert session.sample_index == 1
    session.store.append_sample({"sample_index": 0, "gps": fix(lat=17.9)})
    assert session.sample_index == 1


def test_jitter_between_samples_is_not_counted_as_a_second_location(tmp_path):
    session = make_session(tmp_path, planned=2)
    session.boot_complete()
    for lat in (17.5697, 17.56977):
        session.start_measurement()
        session.record_measurement(soil=dict(SOIL, moisture=30.0 + lat % 1),
                                   gps=fix(lat=lat, hdop=3.58),
                                   validation_state="VALID")
        session.advance()
    assert session.stored_count == 2
    assert session.distinct_location_count() == 1


def test_a_real_walk_between_samples_counts_as_two_locations(tmp_path):
    session = make_session(tmp_path, planned=2)
    session.boot_complete()
    for lat in (17.5697, 17.5701):
        session.start_measurement()
        session.record_measurement(soil=dict(SOIL, moisture=30.0 + lat % 1),
                                   gps=fix(lat=lat), validation_state="VALID")
        session.advance()
    assert session.distinct_location_count() == 2


def test_a_suspicious_sample_is_stored_but_kept_out_of_the_map(tmp_path):
    session = make_session(tmp_path, planned=2)
    session.boot_complete()
    session.start_measurement()
    session.record_measurement(
        soil=dict(SOIL, nitrogen=0.0, phosphorus=0.0, potassium=0.0),
        gps=fix(), validation_state="VALID")
    assert session.stored_count == 1
    assert session.map_eligible_records() == []
    assert session.summary()["processable"] is False


def test_a_press_outside_an_armed_state_is_refused(tmp_path):
    session = make_session(tmp_path, planned=2)
    session.boot_complete()
    session.start_measurement()
    with pytest.raises(IllegalTransition):
        session.start_measurement()


def test_every_stored_record_keeps_the_raw_evidence(tmp_path):
    """An audit has to be able to see what the probe and receiver actually said."""
    session = make_session(tmp_path, planned=1)
    session.boot_complete()
    session.start_measurement()
    session.record_measurement(
        soil=SOIL, gps=fix(), validation_state="VALID_WITH_WARNING",
        validation_reasons=["LOW_MEASUREMENT_QUALITY"], measurement_quality=0.55,
        diagnostics={"raw_frame": "01 03 0E ..."})
    record = session.store.records()[0]
    for key in ("session_id", "sample_index", "timestamp", "gps", "soil",
                "validation", "quality", "reasons", "diagnostics"):
        assert key in record
    assert record["validation"]["reasons"] == ["LOW_MEASUREMENT_QUALITY"]
    assert record["diagnostics"]["raw_frame"] == "01 03 0E ..."
    assert record["gps"]["hdop"] == 0.96


# --------------------------------------------------------------- panel


def test_the_saved_screen_names_the_sample_that_was_just_saved(tmp_path):
    """Showing the next index here would tell the operator they have one more."""
    session = make_session(tmp_path, planned=5)
    session.boot_complete()
    session.start_measurement()
    session.record_measurement(soil=SOIL, gps=fix(), validation_state="VALID")

    summary = workflow_summary(session, soil=SOIL)
    assert summary["sample_index"] == 1
    assert summary["action_line"] == "SAMPLE 1 SAVED"

    session.advance()
    assert workflow_summary(session, soil=SOIL)["sample_index"] == 2


def test_every_state_has_an_operator_instruction():
    for state in FieldState:
        text = action_line(state, 2, 5)
        assert text and "{" not in text


def test_the_workflow_record_reaches_the_wire_intact(tmp_path):
    session = make_session(tmp_path, planned=5)
    session.boot_complete()
    record = build_panel_record(workflow_summary(session, soil=SOIL)).decode("ascii")
    assert record.startswith("FS|")
    assert "t=READY" in record and "m=5" in record and "i=1" in record
    assert "a=PLACE PROBE - PRESS START" in record
    assert "w=31.20" in record


def test_the_record_stays_inside_the_firmware_line_buffer(tmp_path):
    """lineBuf in the sketch is 256 bytes; an overlong line is dropped whole."""
    session = make_session(tmp_path, planned=5)
    session.boot_complete()
    session.start_measurement()
    session.record_measurement(soil=SOIL, gps=fix(), validation_state="VALID")
    summary = workflow_summary(session, soil=SOIL,
                               field_name="A" * 40, extra={"evidence_level": "LIMITED"})
    assert len(build_panel_record(summary)) < 256


def test_an_empty_session_is_never_recorded_as_completed(tmp_path):
    """A manifest that reads as a finished survey and holds nothing is a lie.

    Seen on hardware when a concurrent process removed the session directory
    mid-run: the samples were written, then deleted, and close() recomputed the
    count from disk and would otherwise have stamped COMPLETED over zero.
    """
    store = FieldSessionStore(root=str(tmp_path), planned_samples=3)
    store.close("COMPLETED")
    manifest = json.load(open(store.manifest_path))
    assert manifest["status"] == "INCOMPLETE"
    assert manifest["stored_samples"] == 0
    assert "no samples are on disk" in manifest["reason"]


def test_a_session_that_holds_samples_still_completes_normally(tmp_path):
    store = FieldSessionStore(root=str(tmp_path), planned_samples=1)
    store.append_sample({"sample_index": 1, "quality": "VALID"})
    store.close("COMPLETED")
    manifest = json.load(open(store.manifest_path))
    assert manifest["status"] == "COMPLETED"
    assert manifest["stored_samples"] == 1


def test_other_terminal_statuses_are_not_rewritten_on_an_empty_session(tmp_path):
    """FAILED and INTERRUPTED are honest answers for a session with no samples."""
    for status in ("FAILED", "INTERRUPTED", "INCOMPLETE"):
        store = FieldSessionStore(root=str(tmp_path / status), planned_samples=3)
        store.close(status)
        assert json.load(open(store.manifest_path))["status"] == status


# ------------------------------------------- contact lost, not merely absent

#: The readings from the 2026-08-25 field session, where the probe lost soil
#: contact after sample 2 and every sample was still stored VALID.
LOST_CONTACT_SESSION = [
    {"moisture": 14.2, "ph": 5.67, "ec": 0.014, "temperature": 26.0,
     "nitrogen": 1, "phosphorus": 1, "potassium": 3},
    {"moisture": 14.1, "ph": 5.67, "ec": 0.014, "temperature": 26.0,
     "nitrogen": 1, "phosphorus": 1, "potassium": 2},
    {"moisture": 0.2, "ph": 5.86, "ec": 0.021, "temperature": 26.0,
     "nitrogen": 1, "phosphorus": 2, "potassium": 4},
]


def test_the_readings_that_slipped_through_as_valid_are_now_caught():
    """0.2 % moisture is not 0.0 %, so the exact-zero check could not see it."""
    from fieldsense.field.plausibility import channels_near_floor

    assert not channels_near_floor(LOST_CONTACT_SESSION[0])
    assert not channels_near_floor(LOST_CONTACT_SESSION[1])
    assert channels_near_floor(LOST_CONTACT_SESSION[2])


def test_the_two_seated_samples_are_still_accepted():
    """The check must not swallow the samples that were genuinely in soil."""
    assert assess_reading(LOST_CONTACT_SESSION[0]).quality is SampleQuality.VALID
    assert assess_reading(LOST_CONTACT_SESSION[1],
                          previous_reading=LOST_CONTACT_SESSION[0]
                          ).quality is SampleQuality.VALID


def test_the_sample_that_lost_contact_is_retried_then_stored_marked():
    verdict = assess_reading(LOST_CONTACT_SESSION[2],
                             previous_reading=LOST_CONTACT_SESSION[1])
    assert verdict.quality is SampleQuality.RETRY
    assert "CONTACT_CHANNELS_AT_FLOOR" in verdict.reasons

    exhausted = assess_reading(LOST_CONTACT_SESSION[2],
                               previous_reading=LOST_CONTACT_SESSION[1],
                               retry_count=2)
    assert exhausted.quality is SampleQuality.SUSPICIOUS
    assert exhausted.storable and not exhausted.map_eligible


def test_a_tenfold_moisture_drop_between_insertions_is_flagged():
    """Soil dries across a field, but not by an order of magnitude in minutes."""
    from fieldsense.field.plausibility import moisture_collapsed

    assert moisture_collapsed({"moisture": 1.2}, {"moisture": 30.0})
    assert not moisture_collapsed({"moisture": 24.0}, {"moisture": 30.0})
    # Regaining contact is good news, not a fault.
    assert not moisture_collapsed({"moisture": 30.0}, {"moisture": 1.2})


def test_moisture_collapse_marks_but_does_not_discard():
    """The reading is kept - it is evidence about the probe, not noise."""
    collapsed = dict(SOIL, moisture=1.0)
    verdict = assess_reading(collapsed, previous_reading=SOIL)
    assert verdict.quality is SampleQuality.SUSPICIOUS
    assert "MOISTURE_COLLAPSE" in verdict.reasons
    assert verdict.storable


def test_genuinely_dry_or_poor_soil_is_not_rejected():
    """The near-floor check fires on a conjunction, never on one low channel."""
    dry = {"moisture": 3.0, "ph": 7.2, "ec": 0.12, "temperature": 30.0,
           "nitrogen": 4, "phosphorus": 2, "potassium": 8}
    lean = {"moisture": 8.0, "ph": 6.1, "ec": 0.30, "temperature": 25.0,
            "nitrogen": 6, "phosphorus": 3, "potassium": 9}
    for reading in (dry, lean):
        assert assess_reading(reading).quality is SampleQuality.VALID


def test_low_moisture_alone_is_not_enough_to_flag():
    """Only the conjunction counts; a single channel at its floor is data."""
    from fieldsense.field.plausibility import channels_near_floor

    assert not channels_near_floor(dict(SOIL, moisture=0.4))


def test_the_near_floor_limits_are_configurable_not_baked_in():
    """A region whose real soil trips them must be able to raise them."""
    from fieldsense.field.plausibility import PlausibilityConfig, channels_near_floor

    reading = LOST_CONTACT_SESSION[2]
    assert channels_near_floor(reading)
    relaxed = PlausibilityConfig(near_floor_moisture_pct=0.05)
    assert not channels_near_floor(reading, relaxed)


def test_the_result_screen_shows_samples_stored_not_the_next_index(tmp_path):
    """A finished five-sample session rendered SAMPLE 6/5 on the glass."""
    session = make_session(tmp_path, planned=5)
    session.boot_complete()
    for step in range(5):
        session.start_measurement()
        session.record_measurement(
            soil=dict(SOIL, moisture=30.0 + step),
            gps=fix(lat=17.5697 + step * 0.0004), validation_state="VALID")
        session.advance()

    assert session.state is FieldState.PROCESSING
    assert workflow_summary(session)["sample_index"] == 5
    session.complete_processing({})
    summary = workflow_summary(session)
    assert summary["sample_index"] == 5
    assert summary["planned_samples"] == 5
