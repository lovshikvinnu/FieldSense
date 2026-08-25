# App Lab app `user:unified_v1` — deployment config

The board's copy of this lives at `~/ArduinoApps/unified_v1/sketch/`, which is
outside this repository. This directory is the version-controlled original.

## Why the App Lab app carries the display firmware

Starting an App Lab app **flashes the MCU** — its log carries openocd bank writes
and `Progress[sketch updated]`. The app used to ship a GPS-only sketch with no
`ST7789`, so every start, and therefore every power-on, overwrote the display
firmware and the panel went dark. The app cannot simply be removed: its container
owns the GPS gateway that `run_standalone_node.sh` reads.

The resolution is to let the app carry the *unified* sketch, because
`hardware_test/fieldsense_unoq/fieldsense_unoq.ino` is a strict superset — it
provides the same `Bridge.provide("get_gps_data", ...)` endpoint the container's
only RPC calls, and it drives the panel. App Lab's flash-on-start then becomes
the deployment mechanism instead of the thing that breaks the panel.

## Deploying

The sketch is **not duplicated here** — a second copy would drift from the one
that is actually built and verified. Copy it, and App Lab requires the
`sketch.ino` basename:

    cp hardware_test/fieldsense_unoq/fieldsense_unoq.ino \
       ~/ArduinoApps/unified_v1/sketch/sketch.ino
    cp deploy/applab/unified_v1/sketch.yaml \
       ~/ArduinoApps/unified_v1/sketch/sketch.yaml
    arduino-app-cli app restart user:unified_v1

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
