"""FieldSense AI — UNO Q Linux-side companion for the unified sketch.

Runs inside Arduino App Lab next to `sketch.ino`. Two jobs:

    1. Poll the STM32 for GPS at 1 Hz over RouterBridge (`get_gps_data`).
    2. Re-expose the newest telemetry on a TCP socket, so a FieldSense
       process that is NOT inside this container can still read a position.

WHY THE TCP GATEWAY EXISTS
--------------------------
`BridgeGPSAdapter` prefers RouterBridge and falls back to this socket
(`fieldsense/hardware/gps/bridge_gps.py`). `arduino.app_utils` only imports
inside the App Lab container, so a pipeline started from a plain SSH shell has
no Bridge at all — the socket is the only way it can reach the receiver.

BIND ADDRESS
------------
Defaults to 0.0.0.0, which is what the working bench configuration used and
what lets a process outside this container connect. That also means anything
that can route to the board can read your position. On a shared or untrusted
network set:

    FIELDSENSE_GPS_GATEWAY_BIND=127.0.0.1

and run the pipeline inside this container. The host side picks its target
with FIELDSENSE_GPS_GATEWAY_HOST / _PORT, which default to 127.0.0.1:9876.

SOIL PROBE IS NOT HERE
----------------------
The JXBS probe is read on the Linux side over USB-RS485 (/dev/ttyUSB0) with
FIELDSENSE_SOURCE=HARDWARE, not through this bridge. Serial1 on the MCU
belongs to the GPS; see the UART ownership note in sketch.ino.
"""

import os
import socket
import threading
import time

from arduino.app_utils import *  # noqa: F401,F403  (App Lab injects Bridge/App)

GATEWAY_BIND = os.environ.get("FIELDSENSE_GPS_GATEWAY_BIND", "0.0.0.0")
GATEWAY_PORT = int(os.environ.get("FIELDSENSE_GPS_GATEWAY_PORT", "9876"))
POLL_SECONDS = 1.0

# Matches the sketch's cold-start value and the shape parse_gps_telemetry()
# expects. Never leave this as an empty string: the host raises
# MALFORMED_RESPONSE on an empty payload, which reads like a dead link rather
# than a receiver that simply has no fix yet.
latest_telemetry = "NO_FIX,0.0,0.0,Sats:0,HDOP:99.9"
telemetry_lock = threading.Lock()


def report_container_ip() -> None:
    """Print the container's outward-facing IP, for pointing a remote client at it.

    The UDP connect sends no packets and needs no internet; it only asks the
    routing table which local address would be used. Purely diagnostic.
    """
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        print("[GPS GATEWAY] container IP: {}".format(probe.getsockname()[0]))
        probe.close()
    except Exception:
        pass  # no route is fine; the gateway still serves locally


def tcp_server_daemon() -> None:
    """Serve the newest telemetry line to each client, one line per connection."""
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((GATEWAY_BIND, GATEWAY_PORT))
        server.listen(5)
        print("[GPS GATEWAY] listening on {}:{}".format(GATEWAY_BIND, GATEWAY_PORT))
        if GATEWAY_BIND == "0.0.0.0":
            print("[GPS GATEWAY] reachable from the network - see the bind note "
                  "in this file's docstring")

        while True:
            client, _addr = server.accept()
            with telemetry_lock:
                payload = latest_telemetry + "\n"
            try:
                client.sendall(payload.encode("utf-8"))
            except Exception:
                pass  # a client that hung up must not take the gateway down
            finally:
                client.close()
    except Exception as exc:
        print("[GPS GATEWAY] server error: {}".format(exc))


def loop() -> None:
    """Poll the STM32 once per second and publish the result."""
    global latest_telemetry
    try:
        reading = Bridge.call("get_gps_data")  # noqa: F405
        if reading:
            with telemetry_lock:
                latest_telemetry = str(reading).strip()
            print("[GPS TELEMETRY] {}".format(latest_telemetry))
        else:
            # Keep the last good value rather than publishing an empty line.
            print("[GPS TELEMETRY] empty bridge reply, holding previous fix")
    except Exception as exc:
        print("[BRIDGE ERROR] {}: {}".format(type(exc).__name__, exc))

    time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    report_container_ip()
    threading.Thread(target=tcp_server_daemon, daemon=True).start()
    App.run(user_loop=loop)  # noqa: F405
