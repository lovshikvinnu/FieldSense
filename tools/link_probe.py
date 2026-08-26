#!/usr/bin/env python3
"""Feed a known byte pattern to the UNO Q monitor proxy and report progress.

Pairs with hardware/tft-unoq/link_probe/link_probe.ino, which displays
what actually arrives. This side controls the ONE variable that has never been
isolated: how fast the host pushes.

Every failure so far is consistent with rate rather than volume. Protocol v1
trickled 3842 bytes and waited for an ACK, and the 12-byte header always
arrived. Protocol v2 dumps 153,600 bytes as fast as TCP accepts them, and the
header stopped arriving at all. So this sends a fixed total at a chosen rate
and lets the panel say where the bytes went.

    python3 tools/link_probe.py                    # 25 KB, 512 B every 100 ms
    python3 tools/link_probe.py --burst            # same total, no pacing
    python3 tools/link_probe.py --total 153600 --write-size 3842 --delay 0.05

Reads nothing back. The sketch never writes, so there is nothing to read, and
that is deliberate - it keeps the MCU's write path out of the experiment.
"""

import argparse
import socket
import sys
import time


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7500)
    parser.add_argument("--total", type=int, default=25600,
                        help="bytes to send in total")
    parser.add_argument("--write-size", type=int, default=512,
                        help="bytes per send() call")
    parser.add_argument("--delay", type=float, default=0.1,
                        help="seconds to pause between sends")
    parser.add_argument("--burst", action="store_true",
                        help="ignore --delay and send as fast as TCP allows")
    parser.add_argument("--hold", type=float, default=10.0,
                        help="seconds to keep the socket open after the last "
                             "send, so the panel can be read before the "
                             "connection drops")
    args = parser.parse_args(argv)

    delay = 0.0 if args.burst else args.delay

    # A repeating counter, so a torn or reordered stream is visible as a
    # pattern break rather than looking like plausible data.
    pattern = bytes(range(256))
    payload = (pattern * ((args.total // 256) + 1))[:args.total]

    print("connecting to {}:{}".format(args.host, args.port))
    try:
        sock = socket.create_connection((args.host, args.port), timeout=10)
    except OSError as exc:
        print("cannot connect: {}".format(exc), file=sys.stderr)
        return 1

    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print("sending {} bytes in {}-byte writes, {} pacing".format(
        args.total, args.write_size,
        "no" if delay == 0 else "{}s".format(delay)))

    started = time.monotonic()
    sent = 0
    try:
        while sent < len(payload):
            piece = payload[sent:sent + args.write_size]
            sock.sendall(piece)
            sent += len(piece)
            if sent % (args.write_size * 10) == 0 or sent == len(payload):
                elapsed = time.monotonic() - started
                print("  sent {}/{} bytes in {:.1f}s".format(sent, len(payload), elapsed))
            if delay:
                time.sleep(delay)
    except OSError as exc:
        print("send failed after {} bytes: {}".format(sent, exc), file=sys.stderr)
        sock.close()
        return 1

    elapsed = time.monotonic() - started
    print("done: {} bytes in {:.1f}s ({:.0f} B/s)".format(
        sent, elapsed, sent / elapsed if elapsed else 0))
    print("holding the socket open {}s - read the panel now".format(args.hold))
    time.sleep(args.hold)
    sock.close()
    print("closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
