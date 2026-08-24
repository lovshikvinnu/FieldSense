#!/usr/bin/env python3
"""Push dashboard VALUES to the UNO Q panel instead of pixels.

Pairs with hardware_test/TFT_UNOQ/dashboard/dashboard.ino.

WHY VALUES AND NOT PIXELS

display_bridge.py --target mcu ships a full 240x320 RGB565 frame, 153,600
bytes. That cannot work on this board, and the measurement rather than a hunch
says so: Serial on the UNO Q is Arduino_RouterBridge's Monitor, every
available() is a mon/read RPC round trip costing ~595 ms, and link_probe.ino
measured 1.68 calls/second over 247 seconds. About 860 B/s. One frame would
take three minutes.

This record is ~70 bytes. Under a second even at that rate, and small enough
that a flaky link still gets it across.

    python3 tools/push_panel.py                       # from panel_summary.json
    python3 tools/push_panel.py --watch --interval 5  # keep it updating
    python3 tools/push_panel.py --dry-run             # print, send nothing

The plain one-shot form is the supported way to update the panel. It holds the
socket open for HOLD_SECONDS after writing, because the MCU pulls on its own
~1 s cycle and collects nothing once the client has gone - see the note on
HOLD_SECONDS. No flags are needed for a normal push.

Reads nothing back. The sketch never replies, deliberately: a write from the
MCU breaks its own read channel on this transport.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fieldsense.hardware.panel_renderer import (
    PANEL_HOLD_SECONDS,
    DEFAULT_PANEL_ENDPOINT,
    PANEL_RECORD_FIELDS,
    build_panel_record,
)
from fieldsense.hardware.transport.tcp_socket import TcpTransport, TcpTransportError

DEFAULT_SUMMARY = "artifacts/panel_summary.json"

# The record format lives in fieldsense/hardware/panel_renderer.py, not here.
# `run_spatial_test.py --display bridge` sends the same record at the end of a
# pipeline run, and two copies of the key map would drift the moment one side
# gained a field. Re-exported under the old names so existing callers and
# tests/test_panel_values.py keep working.
FIELD_MAP = PANEL_RECORD_FIELDS
build_record = build_panel_record

# Shared with run_spatial_test.py via panel_renderer so the two senders
# cannot drift. See the note there for why a one-shot push needs it at all:
# the MCU only fetches while a client is connected, and it polls ~1 s.
HOLD_SECONDS = PANEL_HOLD_SECONDS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", default=DEFAULT_SUMMARY,
                        help="panel summary JSON to read")
    parser.add_argument("--port", default=DEFAULT_PANEL_ENDPOINT,
                        help="monitor proxy endpoint, host:port")
    parser.add_argument("--watch", action="store_true",
                        help="keep pushing until interrupted")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="seconds between pushes with --watch")
    parser.add_argument("--hold", type=float, default=HOLD_SECONDS,
                        help="seconds to keep the socket open after the last "
                             "write so the MCU's ~1 s poll can consume the "
                             "record; 0 closes immediately")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the record and exit without connecting")
    args = parser.parse_args(argv)

    try:
        summary = json.load(open(args.summary, encoding="utf-8"))
    except FileNotFoundError:
        print("no summary at {}. Generate one with:\n"
              "  python3 -m fieldsense.hardware.display_bridge --target panel"
              .format(args.summary), file=sys.stderr)
        return 1
    except ValueError as exc:
        print("{} is not valid JSON: {}".format(args.summary, exc), file=sys.stderr)
        return 1

    record = build_record(summary)
    print("record ({} bytes): {}".format(len(record), record.decode().strip()))
    if args.dry_run:
        return 0

    host, _, port_text = args.port.rpartition(":")
    transport = TcpTransport(host=host, port=int(port_text), timeout=10.0)
    try:
        transport.open()
    except TcpTransportError as exc:
        print("cannot reach the panel link: {}".format(exc), file=sys.stderr)
        return 1

    try:
        pushes = 0
        while True:
            # Re-read each pass so --watch picks up a regenerated summary
            # without being restarted.
            if pushes:
                try:
                    summary = json.load(open(args.summary, encoding="utf-8"))
                    record = build_record(summary)
                except (OSError, ValueError):
                    pass   # keep the last good record rather than dropping out

            transport.write(record)
            pushes += 1
            print("pushed #{} ({} bytes)".format(pushes, len(record)))

            if not args.watch:
                # Hold before closing. The MCU only fetches while a client is
                # connected, so closing straight after the write loses the
                # record - see HOLD_SECONDS.
                if args.hold > 0:
                    print("holding {}s for the MCU poll cycle...".format(args.hold))
                    time.sleep(args.hold)
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped after {} pushes".format(pushes))
    except TcpTransportError as exc:
        print("send failed: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
