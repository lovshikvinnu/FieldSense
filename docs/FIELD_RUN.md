# Field Run — probe to dashboard

Everything needed to turn the rig into a real, GPS-tagged soil dataset: flash,
verify, collect, publish. Two gates in the middle decide whether it is worth
walking outside.

| | |
| :--- | :--- |
| Board | `arduino@uno` over SSH |
| Repo | `~/FieldSense/FieldSense` |
| Time | ~30 min, most of it waiting for satellites |

## What counts as done

Three artifacts, all produced by step 6:

- `field_test_live_hardware.json` — stamped `LIVE_HARDWARE`, with valid,
  non-zero GPS coordinates. For a spatial mapping demonstration the samples
  should come from distinct field locations; repeated readings at one spot are
  perfectly valid sensor data, they just interpolate to a single region.
- `artifacts/field_test_map.html` — the interpolated field map, openable in any browser.
- The 2.8" TFT showing live values pushed from the pipeline.

The dataset is the real deliverable. If every point reads `0.000000, 0.000000`,
the run failed even though nothing printed an error — see gate B.

---

## 0. The one-command path

Steps 2, 5 and 6 below are the manual version. Once the firmware is flashed,
this does all of them — restart the App Lab app if needed, discover the
gateway container address, wait for a real fix, collect, interpolate, render,
and push the panel:

```bash
./scripts/run_standalone_node.sh
```

Add `--loop` to keep cycling (default every 15 min). To make the board do this
on power-on with no SSH at all:

```bash
sudo ./scripts/install_boot_service.sh --standalone
```

```bash
journalctl -u fieldsense-standalone -f
```

It **skips a cycle rather than recording without a satellite fix** — the
failure described in gate B below. Set `REQUIRE_GPS_FIX=0` for a bench run
where position does not matter.

The manual steps remain the reference, and are what to fall back to when a
gate fails.

---

## 1. Pull and flash the firmware

The sketch changed since the last flash: the GPS receiver is now told to send
only GGA sentences, and the UART is drained far more often. Without this the
receiver's output is corrupted and no position ever arrives.

```bash
cd ~/FieldSense/FieldSense && git pull --ff-only origin main
arduino-cli compile --fqbn arduino:zephyr:unoq hardware_test/fieldsense_unoq
arduino-cli upload -p 172.17.0.1 --fqbn arduino:zephyr:unoq hardware_test/fieldsense_unoq
```

The upload asks for the board password. Expect roughly `110000 bytes (14%)` of
program storage — anything wildly different means the wrong sketch directory.

> **If it says `Error requesting gpio line swdio`** — a previous upload was
> interrupted and left `openocd` holding the debug pins. Run
> `sudo killall -9 openocd`, then retry the upload.

## 2. Restart the GPS gateway

Flashing resets the microcontroller, so the App Lab app on the Linux side needs
restarting to reconnect to it.

```bash
arduino-app-cli app restart user:unified_v1
```

---

## 3. Gate A — is the firmware reading the GPS?

Do this **indoors**. It takes seconds and needs no satellites. It answers one
question: are NMEA sentences arriving and passing their checksums? Wait about
fifteen seconds after the restart, then:

```bash
arduino-app-cli app logs user:unified_v1 | tail -3
```

You are looking for a line like this:

```
NO_FIX,0.0,0.0,Sats:07,HDOP:2.31,rx=1842,lines=61,csum=61,gga=61,ovf=0
```

- **PASS** — `csum` and `gga` are both above zero, and climbing between checks.
- **PASS** — `Sats:` and `HDOP:` show real numbers. Those can only come from a
  decoded sentence; that alone proves the parser works.
- **FAIL** — `Sats:0,HDOP:99.9`, the untouched startup value. Nothing has been
  decoded. Go to the troubleshooting table at the bottom.

`NO_FIX` here is **expected and fine**. It means the receiver has no satellite
lock yet, which is normal indoors and unrelated to whether the parser works.

## 4. Gate B — take it outside and wait for a lock

Sky visibility, not a window. A cold receiver can take several minutes to fix.
Watch the same log until the line changes shape:

```bash
arduino-app-cli app logs user:unified_v1 | tail -3
```

```
FIX_OK,1734.18667N,07825.47349E,Sats:09,HDOP:0.89
```

- **PASS** — line starts `FIX_OK` and carries real coordinates. The diagnostic
  counters drop away entirely once there is a fix.
- **WAIT** — still `NO_FIX` with counters climbing. The parser is fine, the
  receiver just has not locked. Give it more time and more sky.

> **Do not skip this.** The collector runs happily without a fix and records
> every sample at `0.000000, 0.000000`. Nothing errors, five samples get
> captured, and the map that comes out is meaningless — five points stacked on
> one coordinate. This already happened once.

---

## 5. Collect five points, walking between them

First get the gateway's address. It changes whenever App Lab rebuilds the
container:

```bash
docker exec unified_v1-main-1 hostname -i
```

Put that address into the command below in place of `172.22.0.2` if it differs,
then start collecting:

```bash
FIELDSENSE_SOURCE=HARDWARE FIELDSENSE_SENSOR_PORT=/dev/ttyUSB0 FIELDSENSE_GPS_GATEWAY_HOST=172.22.0.2 PYTHONPATH=. python3 -m fieldsense.live_collector --points 5 --out field_test_live_hardware.json
```

**At each of the five points:** push the probe fully into moist soil, wait a
couple of seconds for it to settle, then press Enter. Move **three to five
metres** before the next one — samples from one spot give the interpolation
nothing to work with.

Each capture prints a line. Read two fields on every one:

- `position` is non-zero. For a spatial run it should also differ from the
  previous point — that is what gives the interpolation something to work with.
- `moisture` is above zero. `0.0%` means the probe is reading air, not soil.

Samples rejected as `not pipeline eligible` are usually a bad insertion — push
deeper and repeat that point. To see the raw values anyway, re-run with
`--keep-invalid`.

## 6. Build the map and light the panel

One command now. It interpolates the field, writes the dashboard, and pushes
values to the TFT.

```bash
PYTHONPATH=. python3 run_spatial_test.py field_test_live_hardware.json --display bridge
```

Step 1 of its output must read `PROVENANCE: LIVE_HARDWARE`. If it says
`UNSTAMPED`, it read the wrong file — check the filename.

Step 7 should end `PUSHED (MCU value link)` with about 76 bytes sent. If it
reports a connection failure, the App Lab app is not running — go back to step 2.

Then send it back:

```bash
git add field_test_live_hardware.json artifacts/field_test_map.html
git commit -m "Live field dataset from the UNO Q"
git push origin main
```

Stage those two files by name. `git add .` sweeps in regenerated artifacts and
causes conflicts between the two machines.

---

## If gate A fails

The counters in that `NO_FIX` line say exactly where the GPS path breaks.

| Counter reading | Meaning | Do this |
| :--- | :--- | :--- |
| `rx=0` | Nothing arriving on the wire at all. | Check the NEO-M8N is powered and connected: GPS TX to **D0**, GPS RX to **D1** — they cross over. |
| `rx>0, lines=0` | Bytes arriving, no complete lines. Wrong baud rate. | Send the reading over — the module may be a 38400 variant, which is a one-line change. |
| `lines>0, csum=0` | Sentences arriving corrupted. Bytes are still being dropped. | Send the whole line over, including the `last=` part. The drain window needs widening. |
| `ovf` climbing | Sentences merging into each other. | Same as above — send the line over. |
| `csum>0, gga>0` | Working. This is the pass condition. | Go to gate B. |

## Other things that go wrong

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Connection refused during collection | Container address changed. | Re-run `docker exec unified_v1-main-1 hostname -i` and use the new address. |
| Serial device not found | USB-RS485 adapter not enumerated. | `ls -l /dev/ttyUSB*`. If empty, replug it and check `sudo dmesg \| tail -20`. |
| Panel shows old numbers | Values persist until replaced, by design. | Re-run step 6. The panel never blanks itself on a dropped update. |
| Every sample identical **and** `moisture 0.0%` | Probe reading air, not soil. | Push deeper into moist ground. Identical readings on their own are fine if you did not move between points. |

---

## Worth knowing before you start

The soil probe is verified working — all seven registers read cleanly, checksums
valid, stable across repeated reads. The original fault was a software bug, now
fixed, not the sensor. If a soil reading looks wrong, suspect the insertion
before the hardware.

The GPS path is proven too. On 2026-08-24 this procedure ran clean end to end:
gate A passed, then gate B reported `FIX_OK` at ten satellites with an HDOP of
0.96, and the collector captured 5/5 samples with none rejected. Probe, GPS,
collector, spatial engine, dashboard and TFT panel all work together.

That run was a single-location proof, so the map collapsed to one region as it
should. A multi-point run — five locations 3–5 m apart — is what produces a
field map worth showing.
