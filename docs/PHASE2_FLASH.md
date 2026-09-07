# Flashing the Phase 2 panel firmware

The map pages are firmware. Nothing on the glass changes until the MCU is
reflashed, and reflashing is the riskiest routine operation this project has:
it blanks the panel for about ninety seconds and puts openocd on the same SWD
lines App Lab uses.

Do this with the unit in front of you. Not over SSH from another room, and not
while anybody is mid-survey.

**RUN THIS ON MAINS POWER. NEVER ON BATTERY.**

The unit browned out twice while this was being written, both times during a
compile: SSH timed out, ICMP kept answering, and it came back a few minutes
later with `uptime` reset. It was a flat battery, not a board fault - and a
compile is exactly the sustained current draw that finds a flat battery.

A flash is the same kind of load with none of the forgiveness. Losing power
part-way through writing the MCU is the one failure this procedure cannot talk
you out of, and it is a plausible one on battery, not a theoretical one.

Before starting: confirm the supply is external, and check `uptime -s` so you
know the unit has not just restarted underneath you.

## 0. Gates

Do not start until all three are true.

- [x] **The sketch compiles.** Verified 2026-09-06 on the board itself with
      `arduino-cli 1.5.1`, `arduino:zephyr:unoq`: 125,092 bytes of program
      storage (15%), globals 50,394 bytes (19%), no errors. `dashboard.ino`
      builds too (110,580 / 43,852); its one warning, `workflowArmed defined
      but not used`, predates this work. Rebuild anyway if the sketch has been
      touched since.
- [ ] **`PANEL_ROTATION` is 3.** 1 is the same landscape surface upside down.
      `tests/test_landscape_panel.py` pins it; run the suite. It briefly said 1,
      from reading this repo instead of the sketch that was actually flashed.
- [ ] **You have read step 4.** The repo sketch is not what flashes.
- [ ] **No session is in progress.** `journalctl -u fieldsense-field -n 5`

## 1. Backup

Sessions are gitignored and `hardware_test/` is untracked, so git will not
bring either back.

```bash
ssh uno-q 'cd ~/FieldSense/FieldSense && tar czf ~/pre-flash-$(date +%s).tar.gz artifacts hardware_test field_test_live_hardware.json'
```

**Never run `git clean -x` on the board.** It would take ~850 field sessions
with it.

## 2. Compile first, flash second

Build in a scratch directory so a failed build cannot leave the repo in a
half-state:

```bash
ssh uno-q 'set -e; rm -rf /tmp/fsbuild && mkdir -p /tmp/fsbuild/fieldsense_unoq && cp ~/FieldSense/FieldSense/firmware/fieldsense_unoq/fieldsense_unoq.ino /tmp/fsbuild/fieldsense_unoq/ && arduino-cli compile --fqbn arduino:zephyr:unoq /tmp/fsbuild/fieldsense_unoq'
```

Confirm the FQBN with `arduino-cli board listall` if that one is rejected.
**A compile error here is a bug in the sketch, not a flashing problem.** Fix it
and commit before going further.

## 3. Stop the node

The field node pushes panel records about once a state change. Flashing while
it writes is how you get a half-parsed record on a panel that is also being
rewritten.

```bash
ssh uno-q 'sudo systemctl stop fieldsense-field'
```

## 4. COPY THE SKETCH ACROSS. THIS IS THE STEP THAT GETS MISSED.

`arduino-app-cli app restart` flashes **App Lab's own copy** of the sketch, at
`~/ArduinoApps/unified_v1/sketch/sketch.ino`. That path is outside this
repository and nothing syncs it. Editing, committing and pulling
`firmware/fieldsense_unoq/fieldsense_unoq.ino` changes NOTHING on the MCU until
it is copied.

This was missed four times in a row. Each flash printed
`Progress[sketch updated]`, the MCU rebooted, its counters reset - and it came
back running the same August sketch. Every symptom of a successful flash was
present except the new firmware. App Lab requires the `sketch.ino` basename:

```bash
ssh uno-q 'cd ~/FieldSense/FieldSense && cp firmware/fieldsense_unoq/fieldsense_unoq.ino ~/ArduinoApps/unified_v1/sketch/sketch.ino && cp deploy/applab/unified_v1/sketch.yaml ~/ArduinoApps/unified_v1/sketch/sketch.yaml && md5sum firmware/fieldsense_unoq/fieldsense_unoq.ino ~/ArduinoApps/unified_v1/sketch/sketch.ino'
```

The two md5s must match before you go on. See
`deploy/applab/unified_v1/README.md`, which has said all this from the start.

## 5. Flash

Starting the App Lab app is what performs the flash.

```bash
ssh uno-q 'arduino-app-cli app restart user:unified_v1'
```

Watch the panel. It blanks, then comes back.

If it fails with `Error requesting gpio line swdio`, two openocd sessions are
fighting over SWD:

```bash
ssh uno-q 'sudo killall -9 openocd'
```

`killall` matches on process name, so this works even though openocd is not on
PATH - it lives at `/opt/openocd/bin/openocd` (0.12.0), with its gpiod config
beside it at `/opt/openocd/openocd_gpiod.cfg`. `command -v openocd` returning
nothing is NOT a broken toolchain; do not go installing one.

Wait for it to settle, then retry step 4. Do not retry in a loop.

## 6. PROVE THE FLASH LANDED, BEFORE TRUSTING ANYTHING ELSE

`Progress[sketch updated]` is not evidence. A reboot is not evidence. The only
evidence is the new firmware saying something the old one could not:

```bash
ssh uno-q 'timeout 8 python3 -c "
import socket
s=socket.create_connection((\"172.22.0.2\",9876),4)
print(s.recv(400).decode(\"utf-8\",\"ignore\").strip())"' | grep -o "HD:[0-9]*,PG:[0-9]*"
```

No `HD:`/`PG:` means the copy in step 4 did not happen, or did not take. Stop
and fix that; do not debug the panel.

## 7. Verify, in this order

1. **Orientation.** Hold the unit naturally. The text must be upright. If it is
   upside down, `PANEL_ROTATION` went out as 1 - stop, fix, reflash.
2. **The old screens still work.** `sudo systemctl start fieldsense-field`,
   wait for `PLACE PROBE IN SOIL`.
3. **A run reaches RESULT** and shows the score, the badge, and a zone tile
   rather than `NO ZONES`.
4. **Short press turns the page.** Result -> SOIL HEALTH -> MOISTURE ->
   NITROGEN -> CARBON -> GPS MAP -> back.
5. **Long hold still starts a new run** and does not also flip a page.

## 8. If the panel comes back wrong

The previous sketch is the one the board ran for weeks:

```bash
ssh uno-q 'cd ~/FieldSense/FieldSense && git show 9235002:firmware/fieldsense_unoq/fieldsense_unoq.ino > firmware/fieldsense_unoq/fieldsense_unoq.ino'
```

Then repeat steps 2-5, copy included. That blob is `6673ff14f2628f64b7e83a0b3bd0a74d83800f09`;
check it with `git hash-object` before flashing so you know what you are putting
back.

## What is NOT covered

The map pages have never been seen on hardware. The record format, the ordering
and the byte budget are tested off-target; the drawing is not, and cannot be
until this is flashed. Expect to iterate on tile sizes and label placement, and
budget a second flash for it.
