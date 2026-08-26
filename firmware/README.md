# firmware/

MCU firmware for the assembled field unit.

| Path | What it is |
| :--- | :--- |
| [`fieldsense_unoq/fieldsense_unoq.ino`](fieldsense_unoq/fieldsense_unoq.ino) | **The sketch the field unit runs.** Draws the 320 × 240 landscape panel, receives the NEO-M8N GPS stream and exposes it over `Bridge.provide("get_gps_data", …)`, and reads the operator's START control. |
| [`fieldsense_unoq/main.py`](fieldsense_unoq/main.py) | The Linux-side half of the same App Lab app — the GPS gateway the Python pipeline connects to. |

Only one sketch can be on the STM32U585 at a time, which is why the panel, the
GPS receiver and the START control all live in a single file rather than three.
The reasoning, including the measured 595 ms cost of one `Serial.available()`
that rules out pixel streaming, is documented at the top of the sketch itself.

## Building and flashing

```bash
arduino-cli compile --fqbn arduino:zephyr:unoq firmware/fieldsense_unoq
arduino-cli upload -p 172.17.0.1 --fqbn arduino:zephyr:unoq firmware/fieldsense_unoq
```

In normal operation the flash happens a different way: starting the App Lab app
`user:unified_v1` reflashes the MCU, so that app is made to carry *this* sketch.
See [`deploy/applab/unified_v1/README.md`](../deploy/applab/unified_v1/README.md)
for why, and [`docs/FIELD_RUN.md`](../docs/FIELD_RUN.md) for the full bring-up.

## Known issue: Serial1 loses sentence tails

The RX ring is 64 bytes and a GGA sentence is 74-82, so a sentence that arrives
while the loop is blocked in `Serial.available()` (~595 ms) loses its tail --
which is where the checksum and the newline are. The unit currently parses about
one sentence in fifty.

Measurements, the confirmed mechanism, what will not fix it, and three options
that might: **[docs/GPS_LINK_ANALYSIS.md](../docs/GPS_LINK_ANALYSIS.md)**.

## Related, but not firmware

Bench sketches written while bringing each component up — including
`hardware/tft-unoq/dashboard/dashboard.ino`, the display-only variant that must
keep agreeing with this one — live under [`hardware/`](../hardware/). They are
kept as evidence of how each peripheral was verified, not as things to flash.
