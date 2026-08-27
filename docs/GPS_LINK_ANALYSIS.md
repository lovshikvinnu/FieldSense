# GPS link — why sentences are lost, and what can be done about it

> ## ⚠️ SUPERSEDED — root cause established by A/B on 2026-08-27
>
> **`quietenGPS()` is the immediate cause of the parsing failure.** The function
> written to protect the link is what breaks it. Measured, both directions, same
> module and same firmware — see §0.
>
> Two earlier conclusions in this document are wrong and are kept only as the
> record of how the investigation went:
>
> - **§2's "root cause".** The 64-byte RX ring is a *contributing constraint*
>   exposed by an isolated GGA burst, not the regression. It was 64 bytes while
>   the GPS worked.
> - **§4's "lowering the GGA rate reduces successes per minute without improving
>   the success rate".** Wrong in the worst way: it does not reduce successes, it
>   **eliminates** them. Fewer bytes made parsing strictly worse.
>
> The RPC-polling theory in §7 is also **not causal** — the failure reproduces
> with `field_node` not running at all.
>
> §1–§6 are retained as the measurements and reasoning that led here. Read §0
> first; it is the only section with a confirmed answer.

**Status:** root cause confirmed (§0). §1–§7 superseded but retained.
**Measured:** 2026-08-26 and 2026-08-27, assembled unit, USB-powered.

---

## 0. The A/B that settled it (2026-08-27)

One variable: whether `quietenGPS()`'s configuration reaches the receiver.
Same NEO-M8N, same UNO Q, same flashed firmware, same wiring otherwise. Each arm
measured over 60 s from the live gateway.

| Counter | Quietened — GGA only | Un-quietened — factory default | |
| :--- | ---: | ---: | :--- |
| `rx` | 60.2 B/s | **217.6 B/s** | |
| `lines` | **0.00/s** | **3.54/s** | complete sentences |
| `csum` | **0.00/s** | **3.02/s** | valid checksums |
| `gga` | **0.00/s** | **0.25/s** | positions parsed |
| `ovf` | 0.30/s | **0.05/s** | 6× fewer overflows |
| `hi` | 0 | 0 | clean 7-bit ASCII in both |

Un-quietened arm: **`FIX_OK` on 60/60 samples, `age=0`, 12 satellites,
fix quality 2 (DGPS)**. Sentence types `GPGSV, GLGSV, GNRMC, GNGGA, GNGSA,
GNGLL`. **No `$GNTXT`** in either arm — the receiver is not resetting.

Quietened arm reproduced twice independently: 60.2 and 60.24 B/s, `lines`
exactly 0 both times.

**Method.** The receiver's `PUBX,40` settings live in RAM, so disconnecting the
module's RX alone does not undo them. The un-quietened arm required
disconnecting module RX **and then power-cycling the module**, so it boots to
factory defaults with no way for `quietenGPS()` to re-quieten it.

### Why less data is worse

- **Un-quietened**: ~217 B/s across seven sentence types is a near-continuous
  stream. The 400 ms drain polls every 2 ms and consumes it incrementally, so
  sentences complete.
- **Quietened**: GGA-only is one ~78-byte burst in 81 ms, then 919 ms of
  silence. The 64-byte ring cannot hold that burst. Land it in the ~595 ms blind
  window — roughly 60% of the time — and the tail is lost, taking the checksum
  and the CRLF.

An isolated burst is all-or-nothing. A continuous stream is drained a byte at a
time. That asymmetry is the whole finding.

There is also a **latch**: on overflow the code discards until a newline, and
that newline exits discard with `gpsLineLen == 0`, producing no line. Once
intermittent CRLF loss starts, `lines` can sit at zero indefinitely even while
newlines keep arriving. That is why `lines` was pinned at exactly 0, not merely
low.

### What this says about the original regression

`quietenGPS()` landed in `86a879d` on 2026-08-24 19:01, **before** the
known-good 21:22 run — and the GPS worked. That is only consistent if MCU
TX → module RX was **not connected** then, leaving the receiver un-quietened.
Somewhere in the later rewiring that wire was connected, `quietenGPS()` began
taking effect, and parsing collapsed.

### Current stable operating configuration

**Leave the GPS module's RX wire disconnected.** That is a wiring-level
workaround for a firmware logic error, and it is stable and reproducible:
`FIX_OK`, `age=0`, DGPS quality. The proper fix — drop `quietenGPS()`, or keep
the receiver talkative enough that the stream stays continuous — is a firmware
decision and has **not** been made.

---

The receiver is healthy and the wiring is sound. The MCU still parses roughly
one GGA sentence in fifty. This is why, with the numbers behind each claim.

---

## 1. What the hardware is doing

Measured from the live gateway with the diagnostic counters:

| Quantity | Measured | Expected if healthy |
| :--- | :--- | :--- |
| Byte rate on `Serial1` | **59 B/s** | ~76 B/s (GGA at 1 Hz) |
| Bytes lost | **~22%** | 0% |
| Complete lines | **2 in ~105 sentences (~2%)** | ~100% |
| High-bit bytes (`hi`) | **3 of 2067 (0.1%)** | 0% |
| Software overflows (`ovf`) | **0.30/s** | 0 |

`hi` near zero proves the stream is 7-bit ASCII — real NMEA, not noise on a
floating pin. A window of the raw bytes confirms it directly:

```
$GNGGA;122117.00;1734.12909;N;07826.17301;E;1;10;0.93;607.8;M;-73.8;M;;*6A
```

(`;` is the comma-escape the firmware applies so the field cannot split the
host's CSV.) That is a clean sentence: 10 satellites, HDOP 0.93. The receiver
is not the problem.

---

## 2. The mechanism (a standing constraint, not the regression)

Three facts, each verifiable on the board:

**The RX ring buffer is 64 bytes.**

```
.../llext-edk/include/zephyr/include/generated/zephyr/autoconf.h:122
    #define CONFIG_ARDUINO_API_SERIAL_BUFFER_SIZE 64
```

and `cores/arduino/zephyrSerial.h:109` instantiates the receive side with it:

```cpp
ZephyrSerialBuffer<CONFIG_ARDUINO_API_SERIAL_BUFFER_SIZE> rx;
```

**A GGA sentence is 74–82 bytes.** The buffer is physically smaller than one
sentence. It cannot hold a whole one under any timing.

**The overflow policy drops the newest bytes**, not the oldest.
`cores/arduino/zephyrSerial.cpp`:

```cpp
while (uart_irq_rx_ready(uart) && ((length = uart_fifo_read(...)) > 0)) {
    ret = ring_buf_put(&rx.ringbuf, &buf[0], length);
    if (ret < 0) { break; }          // full: the rest of the burst is discarded
}
```

That last point is what makes the failure total rather than partial. The bytes
discarded are the **tail** of the sentence — which is where the `*hh` checksum
and the `\r\n` terminator live. Lose the tail and:

- no newline arrives, so the line never completes → `lines` does not advance;
- the fragment merges with the next sentence → the 120-byte software buffer
  fills → `ovf` increments;
- even if a line did complete, its checksum would fail.

Every symptom in §1 follows from that one mechanism.

---

## 3. The timing constraint

At 9600 8-N-1 a byte costs 10 bits, so the link carries 960 B/s and a 76-byte
sentence occupies **79 ms** of wire time. It arrives as a burst, once a second.

`serviceGPS()` drains the ring. It runs continuously for `GPS_DRAIN_MS = 400`
per loop pass, then the loop pays for **one `Serial.available()`, which costs
~595 ms** — that figure is measured, not assumed: `link_probe.ino` recorded 1.68
calls/second over a 247-second run, because `Serial` here is RouterBridge's
`Monitor` and every `available()` is an RPC round trip.

So each loop pass has a **drain window** and a **blind window**:

```
|<-- 400 ms draining, serviceGPS() every ~2 ms -->|<-- ~595 ms blind -->|  ...
```

A sentence survives only if the drain window overlaps its 79 ms burst. During
the blind window the ring accumulates untouched, and since one sentence exceeds
64 bytes, **any sentence arriving wholly inside the blind window loses its
tail.**

Two thresholds fall out:

- **To never overflow between drains:** at 76 B/s the ring fills in
  `64 / 76 ≈ 840 ms`. Gaps must stay under that.
- **To never truncate a single burst:** a drain must land *inside* the 79 ms
  burst, because the ring cannot hold the burst whole.

The first is nearly satisfied today. The second is not, and it is the binding
one.

---

## 4. What will not work

Worth stating, because these are the intuitive fixes:

**Lowering the GGA rate.** `PUBX,40,GGA,0,N,...` reduces how *often* sentences
arrive, not how *big* each burst is. A 76-byte burst still overflows a 64-byte
ring. It reduces successes per minute without improving the success rate.

**Lowering the GPS baud.** At 4800 the burst takes 158 ms instead of 79 ms, but
the same 76 bytes still land in the ring during a 595 ms blind window. No
change.

**Raising `CONFIG_ARDUINO_API_SERIAL_BUFFER_SIZE`.** This is the fix that would
actually address the root cause, and it does **not** appear to be available to a
sketch. `platform.txt` injects the config via

```
compiler.zephyr.macros="-imacros{build.variant.path}/.../autoconf.h"
```

from a **pre-generated** header, and the sketch is linked as an llext against a
precompiled Zephyr image (`llext-edk`, `build.link_mode`). The `Serial1` object
and its ring are instantiated inside that image, so redefining the macro in the
sketch would change only the sketch's view of the type — an ODR mismatch, not a
bigger buffer. Changing it for real means rebuilding the core/variant, which is
outside what App Lab deployment can do.

*This one deserves a second opinion.* If there is a supported Kconfig override
path in the Arduino Zephyr core, it is by far the cleanest fix and everything
below becomes unnecessary.

---

## 5. What can work

The only lever left in the sketch is **the proportion of wall-clock time spent
draining**, and specifically **eliminating gaps longer than one burst**.

**Option A — interleave `serviceGPS()` into the render path.**
`renderValues()` drives the panel over SPI once a second and does not drain
while it runs. That time adds directly to the blind window. `serviceGPS()` is
cheap — it touches a real UART with no RPC — and the loop already calls it
between panel bytes for exactly this reason. Extending that to the render path
is low-risk and costs nothing but a few calls.

**Option B — call `Serial.available()` on alternate passes.**
Halves the blind windows per unit time. Trades operator-input latency: a press
would be noticed in up to ~2 s rather than ~1 s. Given that presses are already
delivered via a monotonic counter that cannot be missed, this may be acceptable
— but it is a UX decision, not a purely technical one.

**Option C — raise `GPS_DRAIN_MS`.**
Increases the drain share directly. Same latency trade as B, in a smaller
increment, and easier to tune.

A and C are complementary and neither changes the workflow. B is the bigger
lever and the bigger trade.

---

## 6. How to tell whether it worked

The counters added for this investigation answer it directly. After any change,
read the gateway and compare:

| Signal | Broken (today) | Fixed |
| :--- | :--- | :--- |
| `lines` | flat, or ~2% of sentences | climbing ~1/s |
| `csum` | flat | climbing with `lines` |
| `gga` | flat | climbing with `csum` |
| `ovf` | climbing 0.30/s | flat |
| `rx` rate | 59 B/s | ~76 B/s |
| `age` | grows into the minutes | stays in single digits |

`age` is the one that matters for the product: it is seconds since the last
successful parse, and the host now refuses a fix older than
`FIELDSENSE_GPS_MAX_FIX_AGE` (default 120 s). **Until this is fixed, the unit
will often refuse to sample rather than attach a stale position** — that is the
guard working as designed, not a regression. Set the variable to `0` to bypass
it while debugging.

---

## 7. What actually changed — and the test that settles it

The measured success rate is ~2%. The model in §3 predicts roughly the drain
share, around 40%. That gap was the clue: something else is consuming the time
the drain needs, and §5's rendering theory turned out to be wrong — `render()`
was **28** draw calls in the known-good firmware and `renderValues()` is now
**17**. Rendering got cheaper.

What changed is the workload on the other side of the link.

| | Known-good, 2026-08-24 | Now |
| :--- | :--- | :--- |
| Service | `fieldsense-standalone` | `fieldsense-field` |
| Runner | `v1_runner` | `field_node` (added 08-25, `e55d163`) |
| `get_gps_data` calls | once per sample, ~5 per run | **every 0.5 s, forever** |

`TriggerSource.wait_for_press()` polls the MCU at 2 Hz for the whole time it is
waiting for START. The journal shows the board sat waiting from 08:54 to 09:52
— 58 minutes, roughly 7,000 RPCs. Every one is serviced by the same MCU loop
that has to drain `Serial1`, and the 400 ms drain in `7024f3e` was tuned when
that load was five calls per run.

The known-good `loop()` says so in its own comment: the symptom the drain was
written to fix was *"rx=1518 with lines=2"*. Today's board reads rx=49790,
lines=1. Same failure, and the drain is unchanged — so the thing that moved is
what it has to compete with.

**This is not yet confirmed.** The A/B that settles it needs no code change:

```bash
sudo systemctl stop fieldsense-field.service     # stop the 2 Hz polling
# wait ~60 s, then read the gateway
sudo systemctl start fieldsense-field.service    # resume it
```

Confirmed if `lines`, `csum` and `gga` climb ~1/s with the service stopped and
`ovf` goes flat, then stall again when it restarts. A single variable, both
directions.

If it confirms, the first thing to try is `TRIGGER_POLL_SECONDS` — a host-side
constant, currently 0.5. Backing it to 1–2 s costs a little START latency and
may restore the margin without touching firmware at all.

### Ruled out

- **The receiver.** `hi=0` across 49,790 bytes and valid `*68` checksums in the
  raw window. Independently confirmed off-board: the NEO-M8N behaves correctly
  on both an ESP and an Arduino UNO, with and without a fix.
- **Wiring and noise.** Same evidence — a floating pin cannot produce clean
  7-bit ASCII NMEA.
- **Rendering.** Fewer draw calls than the known-good build.
- **The touch driver.** `serviceOperatorInput()` is IRQ-gated: no finger, no SPI.
- **The diagnostics added on 08-26.** They grew the payload from ~135 to 271
  bytes, which plausibly makes matters worse at 2 Hz, but telemetry was already
  frozen at 09:17 — before the first of them was flashed.

---

## References

| What | Where |
| :--- | :--- |
| Counters and raw window | `firmware/fieldsense_unoq/fieldsense_unoq.ino`, `get_gps_data()` |
| Drain loop and blind window | same file, `loop()` and `serviceGPS()` |
| 595 ms measurement | `hardware/tft-unoq/link_probe/link_probe.ino` |
| Host-side staleness gate | `fieldsense/hardware/gps/bridge_gps.py`, `BridgeGPSAdapter.read()` |
| Ring buffer size | `.../zephyr/0.90.0/.../generated/zephyr/autoconf.h:122` |
| Overflow policy | `.../zephyr/0.90.0/cores/arduino/zephyrSerial.cpp` |
