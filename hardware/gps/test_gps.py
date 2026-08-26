"""NEO-M8N GPS bench harness.

Thin console wrapper over the shared adapter layer. NMEA checksum validation,
sentence parsing, and DDMM.MMMM -> decimal degrees conversion live in
`fieldsense.hardware.gps_adapter` and are NOT reimplemented here.

    python3 hardware/gps/test_gps.py --port /dev/ttyUSB0 --samples 30

Note: the original version of this script reported raw NMEA coordinate fields
(e.g. '1258.2960N') without converting them. It now prints decimal degrees,
which is what the rest of the system consumes.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fieldsense.hardware.gps_adapter import parse_nmea_sentence  # noqa: E402
from fieldsense.hardware.transport.serial_port import SerialTransport  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample NMEA fixes from a NEO-M8N.")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="serial device (default: /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args()

    print("NEO-M8N  port={}  baud={}".format(args.port, args.baud))
    print("Waiting for {} valid fixes. Antenna needs sky view; cold start takes minutes.\n".format(args.samples))

    transport = SerialTransport(args.port, args.baud, timeout=2.0)
    try:
        transport.open()
    except Exception as exc:
        print("Could not open {}: {}".format(args.port, exc))
        return 1

    stamps = []
    try:
        while len(stamps) < args.samples:
            line = transport.read_line().decode("ascii", errors="ignore")
            data = parse_nmea_sentence(line)
            if data is None or not data.fix_valid or data.sentence_type != "GGA":
                continue
            stamps.append(time.time())
            print("fix {}/{}  lat={:.6f}  lon={:.6f}  sats={}  hdop={}  alt={}m".format(
                len(stamps), args.samples, data.latitude, data.longitude,
                data.satellites, data.hdop, data.altitude_m))

        gaps = [stamps[i] - stamps[i - 1] for i in range(1, len(stamps))]
        if gaps:
            average = sum(gaps) / len(gaps)
            print("\nAverage update interval: {:.2f}s (~{:.2f} Hz)".format(average, 1 / average if average else 0))
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        transport.close()
        print("Port closed cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
