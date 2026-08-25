# Field Session — the operator's procedure

The device as a field instrument: power it on, walk a field, take N samples,
read the result off the glass. No laptop, no SSH, no Wi-Fi, no typed commands.

| | |
| :--- | :--- |
| Unit | Arduino UNO Q, 2.8" ST7789 panel in **landscape**, NEO-M8N, JXBS probe |
| Service | `fieldsense-field.service` (`scripts/run_field_session.sh`) |
| Storage | `artifacts/sessions/<session_id>/` |
| Time | ~2 min per sample, plus the walk |

## How this differs from a V1 run

V1 collected five points in a `for` loop. The loop counter lived in one Python
frame, so nothing on the device could say which sample was in progress, nothing
told the operator that sample 3 was stored, and a power cut lost everything.

A field session makes the sequence explicit and durable:

- the operator says when each sample begins, by pressing START;
- each sample is written to disk the moment it is taken, under its own index;
- a power cut costs at most the sample that was in flight;
- every sample keeps the position it was actually taken at, and a verdict on
  whether the device had moved far enough for that to be a *different* position.

`scripts/run_standalone_node.sh` and `fieldsense-standalone.service` still run
the unattended V1 cycle, which is the right thing for a fixed installation.
Enable one or the other, never both — they contend for the probe and the panel.

---

## The workflow

```
BOOT ──► READY ──► MEASURING ──► SAMPLE_SAVED ──► READY_NEXT_SAMPLE ──┐
                       │                │                             │
                       │                └──► PROCESSING ──► RESULT    │
                       └──► READY (retry, same index)  ◄──────────────┘
```

The transition table is in `fieldsense/field/states.py` and an illegal edge
raises rather than being absorbed — a device that quietly ends up in the wrong
state stores samples under the wrong index, and nobody finds out until the
session is inspected.

### What the operator sees

| State | Panel |
| :--- | :--- |
| `BOOT` | `FIELDSENSE` / `STARTING` |
| `READY` | `SAMPLE 1 / 5` / **`PLACE PROBE - PRESS START`** / green START bar |
| `MEASURING` | `SAMPLE 1 / 5` / **`MEASURING - PLEASE WAIT`** |
| `SAMPLE_SAVED` | `SAMPLE 1 / 5` / **`SAMPLE 1 SAVED`** / live moisture, pH, EC, N-P-K |
| `READY_NEXT_SAMPLE` | `SAMPLE 2 / 5` / **`MOVE TO NEXT LOCATION`** / green START bar |
| `PROCESSING` | **`PROCESSING - PLEASE WAIT`** |
| `RESULT` | `FIELD STATUS` + score bar + zones + recommendations |
| `ERROR` | **`CHECK DEVICE`** and the reason |

The instruction line is drawn at the largest text size that fits the 320 px
width, so `SAMPLE 1 SAVED` renders at 24 px tall and every instruction reaches
at least 16 px. `tests/test_landscape_panel.py` holds the firmware to that.

### The START control

`TRIGGER=any`, the default, watches every control the unit physically has.
Whichever the operator reaches for starts the sample.

**1. The board's own VOL+ / VOL- keys - the primary control.**

These are soldered to the UNO Q, exposed by the kernel's `gpio-keys` driver at
`/dev/input/by-path/platform-gpio-keys-event` as `KEY_VOLUMEDOWN` (114) and
`KEY_VOLUMEUP` (115). Nothing to wire, nothing to fit. The path from a finger
to the workflow is one file read: no RPC round trip, no MCU involvement, and it
works whether or not the panel's touch controller is connected.

*Either* key starts a sample. There is one action in this workflow, and making
an operator remember which of two identical-feeling buttons means "go" is a way
to lose a sample, not a feature. Key *releases* and autorepeat are ignored, so
a held button takes one sample rather than one per repeat interval.

The device node is `root:input`, so the service needs the `input` group -
`fieldsense-field.service` declares it. Without it the node starts, finds no
usable trigger, and waits forever with nothing in the log to say why.

**2. The panel's touch target, and an optional switch on D5.**

The XPT2046 laminated to this glass, if it is wired. The target is the
**bottom bar only** - the integration record for this panel documents a
lamination pinch that produces phantom touches near the *centre*, so the centre
is not a safe place for a control. A press must be held ~180 ms, which phantom
contacts do not survive. A momentary switch to ground on **D5** is read the
same way, with the internal pull-up; if none is fitted the line stays high.

> **Status on the assembled unit as of 2026-08-25: the touch controller does
> not answer.** Its telemetry reads `TP:0,Z1:0,Z2:0` - both raw pressure
> channels at zero, which is a MISO that returns nothing rather than an
> untouched controller. The touch wiring (TOUCH_CS D4, TOUCH_IRQ D2, and MISO)
> is not present on this build. The board keys are the working control, and the
> firmware re-arms touch automatically the moment those channels start
> answering, so wiring it later needs no reflash.

Whether touch answered is probed at boot and reported to Linux on the telemetry
line, so it can be checked without opening the enclosure:

```bash
python3 - <<'PY'
import socket
from fieldsense.hardware.gps.bridge_gps import parse_ui_event
with socket.create_connection(("<gateway-ip>", 9876), timeout=3) as s:
    line = s.recv(256).decode()
print(line)
print(parse_ui_event(line))
PY
```

`TP:1` means a touch controller answered. `TP:0` means it did not, and the
panel says `BUTTON ONLY` in its bottom bar - use the board keys, fit a switch on
D5, or use `TRIGGER=enter` on a bench. `Z1`/`Z2` are the raw pressure channels,
which separate "no controller" from "untouched controller" from "MISO stuck at
a rail" - all three read `TZ:0`.

`RC` is the number of `FS|` records the MCU has **parsed**. It is the only
delivery evidence on the wire: the panel link is a TCP socket into
`arduino-router`, so a write succeeds whether or not the MCU ever collected the
bytes, and this project has already had senders report success while the panel
kept showing dashes. If `RC` does not move after a push, the record did not
land.

To confirm the board keys are reaching the workflow, run this on the board and
press either volume key:

```python
# PYTHONPATH=. python3 button_check.py
import time
from fieldsense.field_node import ButtonTrigger

trigger = ButtonTrigger()
print(trigger.describe())
print("press VOL+ or VOL- within 20 seconds...")
print("PRESS SEEN" if trigger.wait_for_press(timeout=20) else "nothing seen")
trigger.close()
```

The press count is **monotonic and never reset**. The host polls at about 1 Hz
and a press lasts a few hundred milliseconds, so a boolean "is pressed" would
be missed roughly as often as it was seen; a counter that moved from 3 to 4 is
unambiguous whenever it is read. A counter that goes *backwards* means the MCU
restarted, and is treated as zero presses rather than as a burst.

---

## Running one

```bash
./scripts/run_field_session.sh
```

Or from boot, with nothing attached:

```bash
sudo ./scripts/install_boot_service.sh --field
sudo systemctl start fieldsense-field.service
journalctl -u fieldsense-field -f
```

Useful environment variables (all optional):

| | |
| :--- | :--- |
| `SAMPLES=5` | samples in a session |
| `TRIGGER=any` | `any` (every control), `button` (board keys), `mcu` (panel/D5), `enter` (keyboard), `auto` (bench only) |
| `FIELD_NAME=` | label shown on the panel |
| `RESUME=<session_id>` | continue a session after a power cut |
| `REQUIRE_GPS_FIX=1` | wait for a lock before the panel says READY |

`TRIGGER=auto` advances samples on a timer. It exists so the state machine can
be exercised on a bench with nobody present, and every session it produces is
stamped `SIMULATED_TRIGGER` in its manifest — samples advanced by a clock are
not samples an operator placed.

---

## What is stored

```
artifacts/sessions/session_20260825T164229Z/
    session.json     manifest, rewritten atomically on every change
    samples.jsonl    append-only, one JSON object per line, fsynced
```

Append-only for the samples: sample 2 is a new line, so no crash during sample 2
can damage sample 1. A process killed mid-write leaves a torn final line, which
fails to parse and is skipped — the sample in flight is lost and every earlier
one is intact. Rewriting a whole array on each capture, the obvious
alternative, would put the entire session at risk on every write.

Atomic replace for the manifest, which genuinely must be rewritten: temp file,
fsync, rename. A reader sees the old manifest or the new one, never half of one.

Every record keeps the evidence an audit needs:

```json
{
  "record_version": 1,
  "session_id": "session_20260825T164229Z",
  "sample_index": 2,
  "timestamp": "2026-08-25T16:44:02+00:00",
  "quality": "VALID",
  "reasons": [],
  "map_eligible": true,
  "gps": {"latitude": 17.5701, "longitude": 78.4251,
          "fix_valid": true, "satellites": 10, "hdop": 0.96},
  "movement": {"distance_m": 61.5, "threshold_m": 8.1, "distinct": true,
               "detail": "moved 61.5 m, clear of the 8.1 m jitter threshold"},
  "soil": {"moisture": 28.4, "ph": 6.6, "ec": 0.42, "temperature": 26.4,
           "nitrogen": 48.0, "phosphorus": 22.0, "potassium": 133.0},
  "validation": {"state": "VALID", "reasons": []},
  "diagnostics": {"field_sample": {...}, "field_intelligence_result": {...}}
}
```

`session_id` is stamped into every record, so a power cut cannot silently merge
two field sessions into one dataset. Resuming re-opens the session that was in
progress; starting fresh makes a new directory.

The manifest's `stored_samples` is always recomputed from disk, never from what
the session believed it had written, and a session holding no samples is never
stamped `COMPLETED` — it is downgraded to `INCOMPLETE` with the reason. A
manifest that reads as a finished survey and contains nothing is the one thing
this store exists to prevent.

---

## Sample quality — four answers, not two

`fieldsense/field/plausibility.py` sits **alongside** the frozen
`ValidationEngine`, never instead of it. That engine checks engineering sanity:
numeric, finite, in range. A probe held in open air passes every one of those
checks — moisture 0.0 %, EC 0, N/P/K 0 are all inside their ranges — and a
bench run recorded five such samples, all VALID. Nothing was wrong with the
validator; it was answering a different question.

| Verdict | Stored | On the map | Meaning |
| :--- | :---: | :---: | :--- |
| `VALID` | yes | yes | a soil measurement |
| `SUSPICIOUS` | yes | **no** | stored and marked; not presented as soil data |
| `RETRY` | no | no | re-seat the probe and take this same sample again |
| `REJECTED` | yes | no | evidence kept, values never used |

A `RETRY` does **not** consume a sample index — the operator re-takes sample 3,
they do not lose it. The retry budget is bounded (2 by default), after which the
reading is stored as `SUSPICIOUS` rather than looping forever on a dead probe.

Every detector keys on an **instrument** signature, not an agronomic one:

- **all contact channels exactly zero** — what a JXBS probe reports out of soil,
  or when no Modbus frame decoded. Exactly zero, not "near zero": a threshold
  there would be a claim about how dry soil can get.
- **N, P and K all zero while moisture is not** — nutrient channels not
  responding, a different fault that still leaves moisture and pH worth keeping.
- **identical to the previous reading across every channel** — a stale frame or
  an unmoved probe. Soil does not repeat to three decimals somewhere else.
- **no satellite fix** — a sample without a position is not a point on a map.

There is deliberately **no** detector of the form "pH below X is unlikely".
Those are agronomic thresholds, this project has no evidence for them, and
inventing them is the failure mode the four-valued verdict exists to avoid.

If fewer than three samples are map-eligible, the session is **not processed**.
The panel says so, the session is stored in full, and nothing is claimed.

---

## GPS jitter is not movement

A previous bench run recorded five samples whose coordinates were all
different: 8.0 m of spread at HDOP 3.58, with points 3/4/5 differing in the
seventh decimal — about a centimetre. Five distinct coordinates, one physical
location. The pipeline interpolated it and produced a map of noise.

`fieldsense/field/geo.py` is the answer to that. Two fixes are called distinct
locations only when their separation clears **2× the combined uncertainty**,
where uncertainty is `HDOP × UERE` with a floor of 2.5 m.

`UERE = 3.0 m` is a conventional working figure for an uncorrected consumer L1
receiver. **It is not measured on this NEO-M8N.** It is a parameter for exactly
that reason — treat it as the stated assumption behind every "did it move"
answer. A fix reporting no usable HDOP produces `distinct=False` with
"movement cannot be established", rather than a threshold that was never
measured.

The panel's `SITES` field is the count of stored samples that cleared this test.
**It is the honest denominator for any spatial claim.** A session of five
samples showing one site measured one place five times, whatever the five
coordinates say. For a spatial demonstration, physically walk between points.

---

## Offline

Nothing in the normal path leaves the board:

| Need | Where it is |
| :--- | :--- |
| GPS | App Lab container on this board, over the docker bridge |
| Panel | `arduino-router` monitor proxy, `127.0.0.1:7500` |
| Probe | `/dev/ttyUSB0` |
| SLM | a GGUF file in `models/` |
| Storage | `artifacts/sessions/` |

`fieldsense-field.service` declares no network unit and no
`network-online.target`. `tests/test_field_node.py` asserts that a whole
session opens no off-board socket.

Note that `arduino-app-cli.service` itself wants `network-online.target`, so on
a board with the radios off the gateway can take that target's full timeout to
appear. `GATEWAY_WAIT_SECONDS=180` is sized to outlast it, and the launcher
**waits** rather than restarting the app — a restart costs an MCU flash, and a
restart issued mid-flash puts a second openocd on the same SWD lines.

---

## The AI layer is unchanged

Qwen2.5-0.5B-Instruct Q4_K_M under llama.cpp, AUTO backend, binary and model
auto-discovery, the fidelity checker, the guard, and the deterministic template
fallback all behave exactly as they did. This stage changed *when* the pipeline
runs and *what it is handed*, not what it does.

The field summary is still **not trusted** to the model: it has repeatedly
failed fidelity, so the deterministic template remains authoritative and
narrative output stays labelled `FALLBACK_TEMPLATE`. Model-generated is not the
same as accepted. If the AI layer is unavailable or its output is rejected, the
device still produces a correct field result.
