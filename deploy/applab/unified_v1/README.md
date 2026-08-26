# App Lab app `user:unified_v1` — deployment config

The board's copy of this lives at `~/ArduinoApps/unified_v1/sketch/`, which is
outside this repository. This directory is the version-controlled original.

## What the sketch carries now

Three things, because only one sketch can be on the MCU at a time:

1. the **320x240 landscape** field panel,
2. the NEO-M8N receiver and its `get_gps_data` Bridge endpoint,
3. the **operator's START control** — the XPT2046 touch target in the panel's
   bottom bar, plus an optional momentary switch to ground on D5.

Presses leave the MCU as a monotonic counter appended to the GPS telemetry
line (`,UI:n,TP:0|1,TZ:z,Z1:..,Z2:..`) rather than through a second Bridge
endpoint. A second endpoint would mean a second RPC poll on a link where one
round trip already costs about 595 ms, and the telemetry contract is explicitly
open-ended — `parse_gps_telemetry()` reads four fields and ignores the rest,
which the receiver diagnostics already rely on.

## Why the App Lab app carries the display firmware

Starting an App Lab app **flashes the MCU** — its log carries openocd bank writes
and `Progress[sketch updated]`. The app used to ship a GPS-only sketch with no
`ST7789`, so every start, and therefore every power-on, overwrote the display
firmware and the panel went dark. The app cannot simply be removed: its container
owns the GPS gateway that `run_standalone_node.sh` reads.

The resolution is to let the app carry the *unified* sketch, because
`firmware/unoq/fieldsense_unoq.ino` is a strict superset — it
provides the same `Bridge.provide("get_gps_data", ...)` endpoint the container's
only RPC calls, and it drives the panel. App Lab's flash-on-start then becomes
the deployment mechanism instead of the thing that breaks the panel.

## Deploying

The sketch is **not duplicated here** — a second copy would drift from the one
that is actually built and verified. Copy it, and App Lab requires the
`sketch.ino` basename:

    cp firmware/unoq/fieldsense_unoq.ino \
       ~/ArduinoApps/unified_v1/sketch/sketch.ino
    cp deploy/applab/unified_v1/sketch.yaml \
       ~/ArduinoApps/unified_v1/sketch/sketch.yaml
    arduino-app-cli app restart user:unified_v1

Then confirm the flashed sketch is the one you meant, without opening the
enclosure — only the current firmware emits the operator-control fields:

    python3 - <<'PY'
    import socket
    from fieldsense.hardware.gps.bridge_gps import parse_ui_event
    host = "<docker exec unified_v1-main-1 hostname -i>"
    with socket.create_connection((host, 9876), timeout=4) as s:
        line = s.recv(400).decode()
    print(line, parse_ui_event(line), sep="\n")
    PY

`TP:1` means the touch controller answered its boot probe. `TP:0` means it did
not, the panel says `BUTTON ONLY` in its bottom bar, and the START control is
whatever switch is fitted on D5. `Z1`/`Z2` are the raw pressure channels, which
separate "no controller" from "untouched controller" from "MISO stuck at a
rail" — all three read `TZ:0`.

## Why the versions are pinned

`arduino-cli compile --dump-profile` is the authoritative dependency list: the
unified sketch needs **nine** libraries, not the three obvious Adafruit ones. The
six RouterBridge-chain libraries (`Arduino_RouterBridge`, `Arduino_RPClite`,
`MsgPack`, `DebugLog`, `ArxTypeTraits`, `ArxContainer`) are added automatically by
App Lab from the sketch's includes, so only the display three are declared here.

ST7789 is pinned to **1.10.4** deliberately. App Lab's library cache shipped
**1.11.0**, so without the pin the panel would be built against a driver version
that was never verified on the glass — a silent difference, since either compiles.
The pin makes App Lab fetch and cache 1.10.4, which needs the network **once**;
after that the build is offline-clean. Verified: all nine resolved with every
download blackholed, producing the same 111,168-byte image.
