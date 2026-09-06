# Flashing the Phase 2 panel firmware

The map pages are firmware. Nothing on the glass changes until the MCU is
reflashed, and reflashing is the riskiest routine operation this project has:
it blanks the panel for about ninety seconds and puts openocd on the same SWD
lines App Lab uses.

Do this with the unit in front of you. Not over SSH from another room, and not
while anybody is mid-survey.

**Confirm the board is actually up before you start, and keep it powered.**
The unit went unreachable twice while this was being written - SSH timing out
while ICMP still answered. Both were the operator switching it off, not a
fault: there is NO evidence the board is unstable under load, and an earlier
draft of this file wrongly said there was. Check `uptime -s` rather than
assuming.

What remains true regardless of cause: a board that loses power mid-flash is
the one failure this procedure cannot talk you out of. Do not flash a unit
somebody might switch off, and do not flash over a link you have just watched
drop.

## 0. Gates

Do not start until all three are true.

- [x] **The sketch compiles.** Verified 2026-09-06 on the board itself with
      `arduino-cli 1.5.1`, `arduino:zephyr:unoq`: 125,092 bytes of program
      storage (15%), globals 50,394 bytes (19%), no errors. `dashboard.ino`
      builds too (110,580 / 43,852); its one warning, `workflowArmed defined
      but not used`, predates this work. Rebuild anyway if the sketch has been
      touched since.
- [ ] **`PANEL_ROTATION` is 1.** 3 is the same landscape surface upside down.
      `tests/test_landscape_panel.py` pins it; run the suite.
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

## 4. Flash

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

Wait for it to settle, then retry step 4. Do not retry in a loop.

## 5. Verify, in this order

1. **Orientation.** Hold the unit naturally. The text must be upright. If it is
   upside down, `PANEL_ROTATION` went out as 3 - stop, fix, reflash.
2. **The old screens still work.** `sudo systemctl start fieldsense-field`,
   wait for `PLACE PROBE IN SOIL`.
3. **A run reaches RESULT** and shows the score, the badge, and a zone tile
   rather than `NO ZONES`.
4. **Short press turns the page.** Result -> SOIL HEALTH -> MOISTURE ->
   NITROGEN -> CARBON -> GPS MAP -> back.
5. **Long hold still starts a new run** and does not also flip a page.

## 6. If the panel comes back wrong

The previous sketch is the one the board ran for weeks:

```bash
ssh uno-q 'cd ~/FieldSense/FieldSense && git show 9235002:firmware/fieldsense_unoq/fieldsense_unoq.ino > firmware/fieldsense_unoq/fieldsense_unoq.ino'
```

Then repeat steps 2-4. That blob is `6673ff14f2628f64b7e83a0b3bd0a74d83800f09`;
check it with `git hash-object` before flashing so you know what you are putting
back.

## What is NOT covered

The map pages have never been seen on hardware. The record format, the ordering
and the byte budget are tested off-target; the drawing is not, and cannot be
until this is flashed. Expect to iterate on tile sizes and label placement, and
budget a second flash for it.
