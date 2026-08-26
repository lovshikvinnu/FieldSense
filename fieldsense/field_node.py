"""FieldSense field node — the whole device, from power-on to field result.

This is what runs on the UNO Q when nobody is holding a laptop. It binds the
hardware-free workflow in `fieldsense.field` to the three physical things this
unit has: a JXBS probe on USB-RS485, a NEO-M8N behind the STM32's Bridge
endpoint, and a 320x240 landscape panel on the other end of the router's
monitor proxy.

    power on
      -> App Lab starts, flashes the unified sketch, opens the GPS gateway
      -> this node waits for the gateway, never restarts an app mid-flash
      -> READY, sample 1 of N
      -> operator presses START on the panel (or a switch on D5)
      -> MEASURING -> plausibility -> stored -> SAMPLE 1 SAVED
      -> READY, sample 2 of N ... repeat
      -> PROCESSING -> the frozen spatial pipeline -> RESULT on the panel

NO NETWORK IS INVOLVED ANYWHERE ABOVE. The gateway is a loopback-reachable
container on this same board, the panel link is 127.0.0.1:7500, the probe is a
tty, and the SLM weights are a file. Nothing here opens an outbound socket, and
the unit is expected to run with the radios off.

WHAT THIS DOES NOT DO
---------------------
It does not decide when a sample begins. That comes from a person pressing a
control, and from nothing else — not from a timer, and above all not from GPS
movement. A stationary receiver wanders several metres, and a previous bench
run turned that wander into five "locations" spanning 8 m at HDOP 3.58.
"""

import argparse
import json
import os
import select
import struct
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fieldsense.field import panel as field_panel
from fieldsense.field.session import FieldSession, MIN_PROCESSABLE_SAMPLES
from fieldsense.field.states import FieldState
from fieldsense.field.store import FieldSessionStore
from fieldsense.hardware.factory import DataSourceConfig, SensorAdapterFactory
from fieldsense.hardware.gps.bridge_gps import UIEvent, parse_ui_event
from fieldsense.hardware.panel_renderer import DEFAULT_PANEL_ENDPOINT
from fieldsense.intelligence import FieldIntelligenceEngine, ValidationEngine

PROVENANCE_LIVE = "LIVE_HARDWARE"
PROVENANCE_SIMULATED = "SIMULATED"

#: How long to let the probe settle in soil before reading it. Carried over
#: from live_collector's default, which is the value the V1 field runs used.
DEFAULT_SETTLE_SECONDS = 2.0

#: How long a result screen stays up before the workflow moves on. Long enough
#: that an operator who glanced away still sees SAMPLE N SAVED, short enough not
#: to feel like the device has hung. Configurable mainly so tests do not spend
#: it: a three-sample test would otherwise be twelve seconds of pure sleep.
DEFAULT_DWELL_SECONDS = 2.0

#: Poll interval while waiting for the operator. Well under the firmware's
#: press lockout, so no press can fall between two polls.
TRIGGER_POLL_SECONDS = 0.5

#: How long the finished result stays on the panel waiting for the operator to
#: ask for another run. Long enough to read the result, walk back, and decide;
#: bounded so a unit left switched on in a shed still recycles by itself.
RESULT_HOLD_SECONDS = 900.0

#: The board's own push-button, exposed by the kernel's gpio-keys driver. It is
#: already on the UNO Q - nothing to wire, nothing to fit - and readable straight
#: from Linux with no MCU round trip. The by-path name is stable across boots;
#: /dev/input/eventN is not.
GPIO_KEYS_DEVICE = "/dev/input/by-path/platform-gpio-keys-event"

#: KEY_VOLUMEDOWN and KEY_VOLUMEUP, read off the device's own capability bitmap
#: rather than assumed.
#:
#: DO NOT CALL THESE "THE VOLUME KEYS" TO AN OPERATOR. The UNO Q has no volume
#: keys - it has one user push-button and a power button. These labels are
#: inherited from the Qualcomm SoM's reference device tree, where the same GPIO
#: lines really were a phone's volume rocker. On this board the physical control
#: that reports them is the USER button, and telling someone to press a key that
#: is not printed on the hardware sends them hunting for it in a field.
#:
#: Both codes are watched because which one the user button maps to is a
#: property of the board's wiring, not something worth asserting from a label.
GPIO_KEY_CODES = (114, 115)

#: What to call the control when speaking to a person.
GPIO_KEY_DESCRIPTION = "the board's USER button"

#: The power button is a SEPARATE input device (pm8941_pwrkey, event1) and is
#: deliberately never watched: holding it five seconds reboots the Linux side,
#: which in the middle of a field session would cost the operator their walk.
POWER_KEY_DEVICE = "/dev/input/by-path/platform-1c40000.spmi-platform-1c40000.spmi:pmic@0:pon@800:pwrkey-event"

#: struct input_event: struct timeval, then type, code, value. 24 bytes on a
#: 64-bit kernel; calcsize keeps this correct on a 32-bit one.
INPUT_EVENT_FORMAT = "llHHi"
INPUT_EVENT_SIZE = struct.calcsize(INPUT_EVENT_FORMAT)
EV_KEY = 0x01
KEY_PRESSED = 1          # 0 is release, 2 is autorepeat - neither is a new press


def log(message: str) -> None:
    """Timestamped line to stdout, which is where journalctl reads it."""
    print("[{}] {}".format(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), message), flush=True)


# --------------------------------------------------------------- triggers


class TriggerSource:
    """Something that tells the node an operator wants to take a sample."""

    name = "none"
    poll_seconds = TRIGGER_POLL_SECONDS

    def poll(self) -> bool:
        """Return True if a press has arrived since the last call. Never blocks."""
        raise NotImplementedError

    def wait_for_press(self, timeout: Optional[float] = None) -> bool:
        """Block until a press arrives or `timeout` elapses. True on a press."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while deadline is None or time.monotonic() < deadline:
            if self.poll():
                return True
            time.sleep(self.poll_seconds)
        return False

    def sync(self) -> None:
        """Discard anything pending, so a stale press cannot fire sample 1."""

    def close(self) -> None:
        """Release any handle this trigger holds."""

    def available(self) -> bool:
        """True when this trigger can actually be used on this unit."""
        return True

    def describe(self) -> str:
        """One line about this trigger, for the boot log."""
        return self.name


class ButtonTrigger(TriggerSource):
    """The board's own USER button, read from the kernel's evdev node.

    This is the operator control with the fewest things that can be wrong with
    it: the button is soldered to the board, the driver is in the kernel, and
    the path from a finger to this process is one file read. Nothing has to be
    wired, nothing crosses the RPC link, and it works whether or not the panel's
    touch controller is connected.

    Every code the node reports starts a sample, rather than one chosen code.
    There is exactly one action in this workflow, so there is nothing to
    distinguish between - and which code the user button actually emits is a
    property of this board's wiring rather than of its labels. See
    GPIO_KEY_CODES for why those labels say "volume".
    """

    name = "button"
    poll_seconds = 0.05          # a local file read; no reason to be lazy

    def __init__(self, device_path: str = GPIO_KEYS_DEVICE,
                 key_codes: Tuple[int, ...] = GPIO_KEY_CODES) -> None:
        self.device_path = device_path
        self.key_codes = tuple(key_codes)
        self.handle = None
        self.error: Optional[str] = None
        self._open()

    def _open(self) -> None:
        try:
            self.handle = open(self.device_path, "rb", buffering=0)
            os.set_blocking(self.handle.fileno(), False)
        except OSError as exc:
            self.handle = None
            self.error = "{}: {}".format(type(exc).__name__, exc)

    def available(self) -> bool:
        return self.handle is not None

    def sync(self) -> None:
        """Drain events queued before the session armed."""
        while self._read_batch():
            pass

    def _read_batch(self) -> List[Tuple[int, int, int]]:
        """Return whatever events are already buffered. Never blocks."""
        if self.handle is None:
            return []
        try:
            ready, _, _ = select.select([self.handle], [], [], 0)
            if not ready:
                return []
            data = self.handle.read(INPUT_EVENT_SIZE * 64)
        except (OSError, ValueError):
            return []
        if not data:
            return []

        events = []
        for offset in range(0, len(data) - INPUT_EVENT_SIZE + 1, INPUT_EVENT_SIZE):
            _sec, _usec, kind, code, value = struct.unpack_from(
                INPUT_EVENT_FORMAT, data, offset)
            events.append((kind, code, value))
        return events

    def poll(self) -> bool:
        """True when one of the watched keys was pressed since the last call."""
        for kind, code, value in self._read_batch():
            if kind == EV_KEY and code in self.key_codes and value == KEY_PRESSED:
                return True
        return False

    def close(self) -> None:
        if self.handle is not None:
            try:
                self.handle.close()
            finally:
                self.handle = None

    def describe(self) -> str:
        if self.handle is None:
            return "button (UNAVAILABLE: {})".format(self.error)
        return "button ({} via {})".format(GPIO_KEY_DESCRIPTION, self.device_path)


class CompositeTrigger(TriggerSource):
    """Several controls at once; whichever the operator reaches fires.

    The unit should not care which input a person happens to have. The board
    keys work today with nothing fitted; the panel's touch target works if the
    XPT2046 is wired; a switch on D5 works if one is soldered. Watching all of
    them costs one extra file read per poll and removes an entire class of
    "the device did not respond" in a field.
    """

    name = "any"
    poll_seconds = 0.05

    def __init__(self, sources: List[TriggerSource]) -> None:
        self.sources = [s for s in sources if s.available()]

    def available(self) -> bool:
        return bool(self.sources)

    def sync(self) -> None:
        for source in self.sources:
            source.sync()

    def poll(self) -> bool:
        # Poll every source rather than returning on the first hit, so a press
        # on one control does not leave a stale event queued on another that
        # would fire the next sample the instant the device re-arms.
        fired = False
        for source in self.sources:
            if source.poll():
                fired = True
        return fired

    def close(self) -> None:
        for source in self.sources:
            source.close()

    def describe(self) -> str:
        if not self.sources:
            return "any (NO OPERATOR CONTROL AVAILABLE)"
        return "any -> " + " + ".join(s.describe() for s in self.sources)


class MCUTrigger(TriggerSource):
    """The panel's own touch target, and a switch on D5 if one is fitted.

    Reads the press counter the firmware appends to its GPS telemetry line.
    A counter rather than a level: the firmware's press window is a few hundred
    milliseconds and this polls twice a second, so a level would be missed
    about as often as it was caught, while a counter that moved from 3 to 4 is
    unambiguous whenever it is read.
    """

    name = "mcu"

    def __init__(self, read_raw, poll_seconds: float = TRIGGER_POLL_SECONDS) -> None:
        """Args:
            read_raw: Callable returning one raw telemetry line.
            poll_seconds: Seconds between polls.
        """
        self._read_raw = read_raw
        self.poll_seconds = poll_seconds
        self.last_count: Optional[int] = None
        self.last_event: UIEvent = UIEvent()
        self._last_poll_at = 0.0

    def sync(self) -> None:
        """Adopt the current counter without treating it as a press.

        Called when the node arms. Without this, a session started after the
        operator had already pressed something during boot would fire
        immediately on a press that was never meant for it.
        """
        event = self._poll()
        self.last_count = event.press_count

    def _poll(self) -> UIEvent:
        try:
            event = parse_ui_event(self._read_raw())
        except Exception:
            return UIEvent()
        if event.reported:
            self.last_event = event
        return event

    def poll(self) -> bool:
        """True when the MCU's press counter moved since the last read."""
        now = time.monotonic()
        if now - self._last_poll_at < self.poll_seconds:
            # Rate-limit: unlike the board keys this crosses a socket to the
            # App Lab gateway, and the composite trigger polls every 50 ms.
            return False
        self._last_poll_at = now

        event = self._poll()
        if not event.reported:
            return False
        if self.last_count is None:
            self.last_count = event.press_count
            return False
        moved = event.presses_since(self.last_count) > 0
        # Adopt the new value either way. A counter that went backwards means
        # the MCU reset, and re-baselining is what stops a reflash from reading
        # as a burst of presses.
        self.last_count = event.press_count
        return moved

    def available(self) -> bool:
        """True unless the firmware has never reported an operator control."""
        return True

    def describe(self) -> str:
        event = self.last_event
        if not event.reported:
            return ("mcu (firmware has not reported an operator control yet; "
                    "an older sketch would never report one)")
        # Two independent facts, and conflating them is what made the earlier
        # log line wrong: a panel can detect touch through PENIRQ - which needs
        # only power and the glass - while its SPI wires carry nothing.
        if not event.touch_present:
            touch = "no touch detected yet"
        elif event.spi_answering:
            touch = "touch active with coordinates"
        else:
            touch = ("touch active, PEN-DETECT ONLY - the controller does not "
                     "answer over SPI, so presses work and hit zones do not")
        return "mcu ({}, press count {})".format(touch, event.press_count)


class EnterTrigger(TriggerSource):
    """Enter on a terminal. For a bench run with a keyboard attached."""

    name = "enter"

    def poll(self) -> bool:
        """Never used: this trigger blocks on stdin instead of polling."""
        return False

    def wait_for_press(self, timeout: Optional[float] = None) -> bool:
        try:
            input("      press Enter to start this sample...")
            return True
        except (EOFError, KeyboardInterrupt):
            return False


class AutoTrigger(TriggerSource):
    """Fires on a timer. A rehearsal aid, never a field trigger.

    Every dataset produced under this trigger is stamped SIMULATED_TRIGGER in
    the session manifest, because samples advanced by a clock are not samples
    an operator placed. It exists so the full state machine can be exercised on
    a bench with nobody standing over it, and for no other reason.
    """

    name = "auto"

    def __init__(self, delay_seconds: float = 2.0) -> None:
        self.delay_seconds = delay_seconds

    def poll(self) -> bool:
        """A timer always says yes. That is exactly why it is not a field trigger."""
        return True

    def wait_for_press(self, timeout: Optional[float] = None) -> bool:
        time.sleep(self.delay_seconds if timeout is None
                   else min(self.delay_seconds, timeout))
        return True

    def describe(self) -> str:
        return "auto ({}s, BENCH REHEARSAL - not an operator)".format(self.delay_seconds)


# ------------------------------------------------------------- the node


class FieldNode:
    """One field unit: hardware, session, panel, and the loop that joins them."""

    def __init__(
        self,
        planned_samples: int = 5,
        sensor_port: str = "/dev/ttyUSB0",
        simulate: bool = False,
        trigger: str = "any",
        panel_endpoint: Optional[str] = None,
        session_root: str = os.path.join("artifacts", "sessions"),
        output_dir: str = "artifacts",
        dataset_path: str = "field_test_live_hardware.json",
        settle_seconds: float = DEFAULT_SETTLE_SECONDS,
        dwell_seconds: float = DEFAULT_DWELL_SECONDS,
        auto_delay: float = 2.0,
        field_name: Optional[str] = None,
        resume: Optional[str] = None,
    ) -> None:
        """Configure a node. Nothing is opened until `run()`."""
        self.planned_samples = max(1, int(planned_samples))
        self.sensor_port = sensor_port
        self.simulate = simulate
        self.trigger_name = trigger
        self.panel_endpoint = panel_endpoint or DEFAULT_PANEL_ENDPOINT
        self.session_root = session_root
        self.output_dir = output_dir
        self.dataset_path = dataset_path
        self.settle_seconds = settle_seconds
        self.dwell_seconds = dwell_seconds
        self.auto_delay = auto_delay
        self.field_name = field_name
        self.resume = resume

        self.provenance = PROVENANCE_SIMULATED if simulate else PROVENANCE_LIVE
        self.adapter: Any = None
        self.session: Optional[FieldSession] = None
        self.trigger: TriggerSource = EnterTrigger()
        self.validator = ValidationEngine()
        self.intelligence = FieldIntelligenceEngine()
        self.last_soil: Optional[Dict[str, Any]] = None
        self._panel_fault: Optional[str] = None
        self._panel_fault_count = 0

    # ------------------------------------------------------------- panel

    def show(self, extra: Optional[Dict[str, Any]] = None) -> None:
        """Push the current workflow state to the panel.

        Failures are logged and swallowed. A panel that cannot be reached must
        never stop a sample being measured and stored — the storage is the
        record of truth and the glass is a view of it.
        """
        if self.session is None:
            return
        summary = field_panel.workflow_summary(
            self.session, soil=self.last_soil,
            field_name=self.field_name, offline=True, extra=extra)
        result = field_panel.push_summary(summary, endpoint=self.panel_endpoint)
        if result["status"] == "PUSHED":
            self._panel_fault = None
            return
        # Report a given panel fault once and then count it. The push happens
        # on every state change, so an unreachable link would otherwise repeat
        # the same six-line diagnostic dozens of times per session and bury the
        # sample results underneath it - in the one log a field operator has.
        fault = result["detail"]
        if fault != self._panel_fault:
            self._panel_fault = fault
            self._panel_fault_count = 1
            log("panel: {} ({})".format(result["status"], fault))
        else:
            self._panel_fault_count += 1
            if self._panel_fault_count % 10 == 0:
                log("panel: still unreachable ({} pushes dropped)".format(
                    self._panel_fault_count))

    # -------------------------------------------------------- acquisition

    def open_hardware(self) -> None:
        """Bring up the probe and the GPS adapter.

        Raises:
            Exception: Whatever the adapter raised. The caller turns it into an
                ERROR state with the reason on the glass.
        """
        source = "VIRTUAL" if self.simulate else "HARDWARE"
        config = DataSourceConfig.from_env(source=source, sensor_port=self.sensor_port)
        log("acquisition source: {}".format(SensorAdapterFactory.describe_source(config)))
        self.adapter = SensorAdapterFactory.create_adapter(config)
        self.adapter.initialize()

    def _read_raw_telemetry(self) -> str:
        """One raw GPS telemetry line, trailing operator fields included."""
        gps = getattr(self.adapter, "gps_adapter", None)
        if gps is None or not hasattr(gps, "read_raw"):
            return ""
        return gps.read_raw()

    def build_trigger(self) -> TriggerSource:
        """Choose the operator control this run will listen to.

        The default watches everything the unit has. A field device should not
        care which control the person holding it reaches for, and the set that
        physically exists varies between units - the board keys are always
        there, the panel's touch controller is wired on some units and not
        others, and a switch on D5 is optional.
        """
        if self.trigger_name == "enter":
            return EnterTrigger()
        if self.trigger_name == "auto":
            return AutoTrigger(self.auto_delay)

        if self.trigger_name == "button":
            trigger: TriggerSource = ButtonTrigger()
        elif self.trigger_name == "mcu":
            trigger = MCUTrigger(self._read_raw_telemetry)
        else:
            trigger = CompositeTrigger([
                ButtonTrigger(),
                MCUTrigger(self._read_raw_telemetry),
            ])

        if not trigger.available():
            log("WARNING: {} is not usable on this unit: {}".format(
                trigger.name, trigger.describe()))
        trigger.sync()
        return trigger

    def acquire(self) -> Tuple[Dict[str, Any], Dict[str, Any], Any, Any]:
        """Take one reading. Returns (soil, gps, sample, validation result).

        Raises:
            Exception: Propagated from the adapter, so the caller can decide
                between a retry and an ERROR state.
        """
        if self.settle_seconds > 0:
            time.sleep(self.settle_seconds)
        sample = self.adapter.acquire_sample()
        result = self.validator.validate(sample)

        soil = {
            "moisture": sample.moisture,
            "ph": sample.ph,
            "ec": sample.ec,
            "temperature": sample.temperature,
            "nitrogen": sample.nitrogen,
            "phosphorus": sample.phosphorus,
            "potassium": sample.potassium,
        }
        meta = dict(getattr(self.adapter, "last_acquisition_meta", {}) or {})
        quality = dict(meta.get("gps_quality") or {})

        # Where "did the receiver have a fix" comes from.
        #
        # The hardware adapter always publishes acquisition metadata, and its
        # gps_fix_valid is the only trustworthy answer - a NEO-M8N with no lock
        # still hands back a sample, at 0.000000, 0.000000. The virtual sensor
        # publishes no metadata at all, so reading a missing key as False would
        # make every rehearsal sample fail the no-fix check and the state
        # machine could never be exercised off-target. Absent metadata
        # therefore falls back to "are the coordinates real", which is only
        # ever reached by an adapter that does not measure a receiver.
        if "gps_fix_valid" in meta:
            fix_valid = bool(meta["gps_fix_valid"])
        else:
            fix_valid = bool(sample.latitude) or bool(sample.longitude)

        gps = {
            "latitude": sample.latitude,
            "longitude": sample.longitude,
            "fix_valid": fix_valid,
            "satellites": quality.get("satellites"),
            "hdop": quality.get("hdop"),
        }
        return soil, gps, sample, result

    # ---------------------------------------------------------- one sample

    def take_sample(self) -> bool:
        """Measure, judge, and store one sample. True when one was stored."""
        assert self.session is not None
        self.session.start_measurement()
        self.show()
        log("measuring sample {} of {}".format(
            self.session.sample_index, self.planned_samples))

        try:
            soil, gps, sample, validation = self.acquire()
        except Exception as exc:
            log("acquisition failed: {}: {}".format(type(exc).__name__, exc))
            self.session.fail("probe read failed: {}".format(type(exc).__name__))
            self.show()
            time.sleep(self.dwell_seconds)
            self.session.recover("retrying")
            self.show()
            return False

        self.last_soil = soil
        reasons = [r.value if hasattr(r, "value") else str(r) for r in validation.reasons]
        state = validation.state.value if hasattr(validation.state, "value") else str(validation.state)

        # The intelligence result is computed for every storable sample and
        # kept in the record, so the session can be re-processed later without
        # the probe. It is NOT what decides the map — that is the field
        # quality verdict, below.
        try:
            intel = self.intelligence.process(sample, validation)
            intel_dict = intel.to_dict()
        except Exception as exc:
            intel_dict = {"error": "{}: {}".format(type(exc).__name__, exc)}

        outcome = self.session.record_measurement(
            soil=soil, gps=gps,
            validation_state=state, validation_reasons=reasons,
            measurement_quality=sample.measurement_quality,
            sample_id=sample.sample_id,
            diagnostics={
                "provenance": self.provenance,
                "trigger": self.trigger.name,
                "acquisition_meta": dict(
                    getattr(self.adapter, "last_acquisition_meta", {}) or {}),
                "field_sample": sample.to_dict(),
                "field_intelligence_result": intel_dict,
            },
        )

        log("sample {}: {} - {}".format(
            outcome.sample_index, outcome.quality.value, outcome.message))
        if outcome.movement is not None:
            log("  position: {}".format(outcome.movement.detail))

        self.show()
        if not outcome.accepted:
            time.sleep(self.dwell_seconds)
            self.show()
            return False

        time.sleep(self.dwell_seconds)   # let SAMPLE N SAVED sit on the glass
        self.session.advance()
        self.show()
        return True

    # ------------------------------------------------------------ export

    def export_dataset(self) -> Optional[str]:
        """Write the map-eligible samples in the schema the pipeline reads.

        Only VALID samples are exported. A SUSPICIOUS reading stays in the
        session record, where an audit can find it, and stays out of the
        interpolation, because a probe that was standing in air has no soil
        value to contribute to a map of a field.

        Returns:
            The dataset path, or None when there was nothing eligible to write.
        """
        assert self.session is not None
        entries: List[Dict[str, Any]] = []
        for record in self.session.store.iter_records():
            if not record.get("map_eligible"):
                continue
            diagnostics = record.get("diagnostics") or {}
            sample = diagnostics.get("field_sample")
            intel = diagnostics.get("field_intelligence_result")
            if not sample or not intel:
                continue
            entries.append({
                "field_sample": json.dumps(sample),
                "field_intelligence_result": json.dumps(intel),
                "provenance": diagnostics.get("provenance", self.provenance),
                "acquired_at": record.get("timestamp"),
            })

        if not entries:
            return None
        directory = os.path.dirname(self.dataset_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.dataset_path, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2)
        log("dataset: {} ({} map-eligible entries)".format(self.dataset_path, len(entries)))
        return self.dataset_path

    def process(self) -> Dict[str, Any]:
        """Run the frozen spatial pipeline over this session and show the result.

        The pipeline, the AI layer, the fidelity guard and the deterministic
        fallback are all reached exactly as they were in V1 — this method
        changes nothing about them, it only decides when they run and what they
        are handed.
        """
        assert self.session is not None
        report = self.session.summary()
        eligible = report["map_eligible"]

        if eligible < MIN_PROCESSABLE_SAMPLES:
            detail = ("{} of {} samples are usable for a map; the spatial "
                      "engine needs {}".format(
                          eligible, report["stored_samples"], MIN_PROCESSABLE_SAMPLES))
            log("NOT PROCESSING: " + detail)
            log("  the session is stored in full at {} - nothing is lost, and "
                "nothing is claimed".format(self.session.store.directory))
            self.session.fail(detail)
            self.show(extra={"action_line": "NOT ENOUGH VALID SAMPLES",
                             "soil_health_status": "UNKNOWN"})
            self.session.store.close("INCOMPLETE", reason=detail)
            return {"processed": False, "reason": detail}

        dataset = self.export_dataset()
        if dataset is None:
            self.session.fail("nothing to process")
            self.show()
            return {"processed": False, "reason": "no exportable entries"}

        self.show()
        from run_spatial_test import run_spatial_test

        try:
            summary = run_spatial_test(
                json_path=dataset,
                output_dir=self.output_dir,
                display="off",          # the panel is driven from here, below
                allow_generate=False,
            )
        except Exception as exc:
            detail = "{}: {}".format(type(exc).__name__, exc)
            log("processing failed: " + detail)
            self.session.fail("processing failed")
            self.show()
            return {"processed": False, "reason": detail}

        self.session.complete_processing(summary)
        self.show(extra=self._result_overlay(summary, report))
        log("field result: {} samples, {} distinct locations, spread {} m".format(
            report["stored_samples"], report["distinct_locations"],
            report["spatial_spread_m"]))
        return {"processed": True, "summary": summary}

    def await_new_run(self) -> bool:
        """Hold the result on screen until the operator asks for another run.

        The launcher's --loop starts a fresh session as soon as this process
        exits, so without this the result would be replaced by READY seconds
        after appearing - and an operator who looked away would never see what
        their walk produced. Waiting here makes starting the next run an
        explicit act on the panel, which is the point of a screen-only device.

        Bounded, because an unattended unit must still recycle: after
        RESULT_HOLD_SECONDS it returns anyway and the launcher starts the next
        session. Returns True when a press ended the wait.
        """
        # RESULT *or* ERROR. A session that could not be processed - too few
        # usable samples - is just as finished as one that produced a map, and
        # its screen carries something the operator needs more: the reason. The
        # first version held only on RESULT, so a run that ended "0 of 5 samples
        # are usable" flashed that conclusion and was replaced by READY within
        # seconds, which is how an operator learns nothing from a failed walk.
        if self.session is None or self.session.state not in (
                FieldState.RESULT, FieldState.ERROR):
            return False
        self.trigger.sync()          # a tap during PROCESSING is not a request
        log("{} on screen; tap to start a new run (auto-continues in {:.0f}s)".format(
            "result" if self.session.state is FieldState.RESULT else "outcome",
            RESULT_HOLD_SECONDS))
        pressed = self.trigger.wait_for_press(timeout=RESULT_HOLD_SECONDS)
        log("operator started a new run" if pressed
            else "no input; recycling for the next session")
        return pressed

    def _result_overlay(self, summary: Dict[str, Any],
                        report: Dict[str, Any]) -> Dict[str, Any]:
        """Fold the finished pipeline's own numbers onto the result screen."""
        panel_summary: Dict[str, Any] = {}
        try:
            from fieldsense.hardware.panel_renderer import load_panel_summary
            panel_summary = load_panel_summary(
                os.path.join(self.output_dir, "panel_summary.json")) or {}
        except Exception:
            panel_summary = {}

        overlay = {
            "soil_health_status": panel_summary.get("soil_health_status"),
            "soil_health_score": panel_summary.get("soil_health_score"),
            "zone_count": summary.get("zones"),
            "recommendation_count": summary.get("recommendations"),
            "evidence_level": panel_summary.get("evidence_level"),
            "distinct_locations": report["distinct_locations"],
        }
        return {k: v for k, v in overlay.items() if v is not None}

    # --------------------------------------------------------------- run

    def run(self) -> int:
        """Drive one whole field session. Returns a process exit code."""
        store = FieldSessionStore(
            session_id=self.resume,
            root=self.session_root,
            planned_samples=self.planned_samples,
            metadata={
                "provenance": self.provenance,
                "trigger": self.trigger_name,
                "sensor_port": self.sensor_port,
                "panel_endpoint": self.panel_endpoint,
                "simulated": self.simulate,
            },
        )
        self.session = FieldSession(store=store, planned_samples=self.planned_samples)
        log("session {} at {}".format(store.session_id, store.directory))
        if store.stored_count():
            log("resuming: {} sample(s) already stored, next is {}".format(
                store.stored_count(), self.session.sample_index))
        self.show()

        try:
            self.open_hardware()
        except Exception as exc:
            detail = "{}: {}".format(type(exc).__name__, exc)
            log("hardware unavailable: " + detail)
            self.session.fail("probe or GPS unavailable")
            self.show()
            store.close("FAILED", reason=detail)
            return 1

        try:
            self.trigger = self.build_trigger()
            log("operator control: {}".format(self.trigger.describe()))
            if self.trigger_name == "auto":
                store.write_manifest(trigger_note="SIMULATED_TRIGGER - samples "
                                     "were advanced by a timer, not by an operator")

            self.session.boot_complete("ready for sample {}".format(self.session.sample_index))
            self.show()

            while not self.session.complete:
                if self.session.state is FieldState.ERROR:
                    self.session.recover()
                    self.show()
                # Discard anything that arrived while the device was busy.
                #
                # The press counter is monotonic and the host only diffs it
                # inside wait_for_press. Without this, taps during MEASURING -
                # an impatient second tap, a palm on the glass while the probe
                # is being seated - sit in the counter and fire the NEXT wait
                # instantly, taking a sample before the operator has moved or
                # even seen the READY screen. Presses made while the device was
                # working are not instructions about the sample after it.
                self.trigger.sync()
                log("waiting for START (sample {} of {})".format(
                    self.session.sample_index, self.planned_samples))
                if not self.trigger.wait_for_press():
                    log("no operator input; ending the session early")
                    break
                self.take_sample()

            if self.session.state is FieldState.SAMPLE_SAVED:
                self.session.advance()
            if self.session.state is not FieldState.PROCESSING:
                self.session.begin_processing()
            self.show()
            self.process()
            self.await_new_run()
            return 0
        except KeyboardInterrupt:
            log("interrupted; the session is stored at {}".format(store.directory))
            store.close("INTERRUPTED")
            return 130
        finally:
            try:
                if self.adapter is not None:
                    self.adapter.shutdown()
            except Exception:
                pass
            try:
                self.trigger.close()
            except Exception:
                pass


def main(argv: Optional[List[str]] = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(
        description="FieldSense autonomous field node — multi-sample soil session")
    parser.add_argument("--samples", "--points", dest="samples", type=int, default=5,
                        help="samples in this session (default 5)")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="JXBS probe serial device")
    parser.add_argument("--simulate", action="store_true",
                        help="virtual sensor; output is stamped SIMULATED")
    parser.add_argument("--trigger", default="any",
                        choices=("any", "button", "mcu", "enter", "auto"),
                        help="operator control: any (every control this unit has, "
                             "the default), button (the board's own VOL+/VOL- keys), "
                             "mcu (the panel's touch target or a switch on D5), "
                             "enter (keyboard, bench), auto (timer, bench rehearsal "
                             "only - stamps the session SIMULATED_TRIGGER)")
    parser.add_argument("--auto-delay", type=float, default=2.0,
                        help="seconds between samples with --trigger auto")
    parser.add_argument("--panel", default=None,
                        help="host:port of the router monitor proxy "
                             "(default {})".format(DEFAULT_PANEL_ENDPOINT))
    parser.add_argument("--session-root", default=os.path.join("artifacts", "sessions"),
                        help="directory holding field sessions")
    parser.add_argument("--resume", default=None,
                        help="session id to continue instead of starting a new one")
    parser.add_argument("--output-dir", default="artifacts", help="artifact directory")
    parser.add_argument("--dataset", default="field_test_live_hardware.json",
                        help="dataset path handed to the spatial pipeline")
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE_SECONDS,
                        help="seconds to let the probe settle before reading")
    parser.add_argument("--dwell", type=float, default=DEFAULT_DWELL_SECONDS,
                        help="seconds a result screen stays up before moving on")
    parser.add_argument("--field-name", default=None, help="label shown on the panel")
    args = parser.parse_args(argv)

    node = FieldNode(
        planned_samples=args.samples,
        sensor_port=args.port,
        simulate=args.simulate,
        trigger=args.trigger,
        panel_endpoint=args.panel,
        session_root=args.session_root,
        output_dir=args.output_dir,
        dataset_path=args.dataset,
        settle_seconds=args.settle,
        dwell_seconds=args.dwell,
        auto_delay=args.auto_delay,
        field_name=args.field_name,
        resume=args.resume,
    )
    return node.run()


if __name__ == "__main__":
    raise SystemExit(main())
