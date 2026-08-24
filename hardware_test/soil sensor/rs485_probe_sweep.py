"""RS485 link isolation sweep for the JXBS-3001-TR probe.

Answers one question and nothing else: **do bytes come back off the wire?**
`jxbs_test.py` sits on top of the adapter and reports decoded soil values, so a
failure there could be wiring, baud, slave id, framing, or scaling. This script
strips everything above the transport away and shows the raw hex in both
directions, then names the failure mode.

It reuses the repository's framing (`modbus_crc16`, `build_read_request`) rather
than reimplementing it, so a CRC disagreement here is a real bus fault and not
a second, divergent implementation. Standard library only, per `dependencies = []`.

    # single shot at the documented defaults
    python3 "hardware_test/soil sensor/rs485_probe_sweep.py" --port /dev/ttyUSB0

    # sweep the plausible baud rates when nothing answers
    python3 "hardware_test/soil sensor/rs485_probe_sweep.py" --port /dev/ttyUSB0 --baud 9600,4800,19200,2400

    # find a probe whose slave id was changed away from 0x01
    python3 "hardware_test/soil sensor/rs485_probe_sweep.py" --port /dev/ttyUSB0 --scan-slaves

    # verify this script's own logic with no hardware attached
    python3 "hardware_test/soil sensor/rs485_probe_sweep.py" --selftest
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fieldsense.hardware.soil_adapter import (  # noqa: E402
    JXBS_REGISTERS,
    MODBUS_READ_HOLDING,
    build_read_request,
    modbus_crc16,
)

# Baud rates the JXBS family ships with. 9600 is the factory default; 4800 is
# the most common alternative and the usual cause of a CRC-shaped failure.
CANDIDATE_BAUDS = (9600, 4800, 19200, 2400, 38400)

# Modbus exception codes, for turning 0x83 0x02 into a sentence.
EXCEPTION_TEXT = {
    0x01: "ILLEGAL FUNCTION - slave does not support 0x03",
    0x02: "ILLEGAL DATA ADDRESS - register not present on this probe",
    0x03: "ILLEGAL DATA VALUE - register count rejected",
    0x04: "SLAVE DEVICE FAILURE - probe reached its own internal error",
}


def hexdump(data: bytes) -> str:
    """Render bytes as spaced uppercase hex, or a placeholder when empty."""
    if not data:
        return "(nothing)"
    return " ".join("{:02X}".format(b) for b in data)


def classify(request: bytes, response: bytes, slave_id: int) -> tuple:
    """Name the failure mode for one request/response pair.

    Returns:
        (verdict, detail) where verdict is one of OK, EXCEPTION, NO_RESPONSE,
        ECHO, WRONG_SLAVE, CRC, SHORT, GARBAGE. EXCEPTION counts as a working
        electrical link — the probe understood the frame well enough to refuse
        it, which rules out wiring, baud, and slave id in one shot.
    """
    if not response:
        return ("NO_RESPONSE", "zero bytes inside the timeout window")

    if response[:len(request)] == request:
        return ("ECHO", "our own request came back - DE/RE stuck HIGH, or A/B "
                        "shorted to the TTL side")

    if response[0] != slave_id:
        # A real frame from a different address is a slave id mismatch; noise is not.
        if len(response) >= 3 and response[1] in (MODBUS_READ_HOLDING, MODBUS_READ_HOLDING | 0x80):
            return ("WRONG_SLAVE",
                    "frame from slave 0x{:02X}, not 0x{:02X}".format(response[0], slave_id))
        return ("GARBAGE", "first byte 0x{:02X} is not slave 0x{:02X} and the frame "
                           "is not Modbus-shaped - baud mismatch or A/B swap"
                           .format(response[0], slave_id))

    if len(response) >= 3 and response[1] & 0x80:
        code = response[2]
        return ("EXCEPTION", "code 0x{:02X}: {}".format(
            code, EXCEPTION_TEXT.get(code, "unknown exception code")))

    if len(response) < 7:
        return ("SHORT", "{} bytes, expected 7 - turnaround too fast, or the "
                         "settle delay is shorter than the probe's reply".format(len(response)))

    frame = response[:7]
    received_crc = frame[5] | (frame[6] << 8)
    expected_crc = modbus_crc16(frame[:5])
    if received_crc != expected_crc:
        return ("CRC", "got 0x{:04X}, computed 0x{:04X} - baud or parity mismatch, "
                       "or an unterminated/noisy bus".format(received_crc, expected_crc))

    raw = (frame[3] << 8) | frame[4]
    return ("OK", "raw register value {} (0x{:04X})".format(raw, raw))


def exchange(transport, request: bytes, settle: float, read_bytes: int) -> bytes:
    """Send one frame and return whatever arrives, without framing assumptions.

    Reads more bytes than a valid answer needs, so echo and noise are visible
    instead of being silently truncated to a plausible-looking 7 bytes.
    """
    transport.write(request)
    if settle:
        time.sleep(settle)
    return transport.read(read_bytes)


def probe_once(port: str, baud: int, slave: int, register: int, timeout: float,
               settle: float, verbose: bool = True) -> tuple:
    """Open the port at one baud rate, read one register, classify the result."""
    from fieldsense.hardware.transport.serial_port import SerialTransport, SerialPortError

    transport = SerialTransport(port=port, baudrate=baud, timeout=timeout)
    try:
        transport.open()
    except SerialPortError as exc:
        return ("PORT_ERROR", str(exc))

    try:
        request = build_read_request(register, slave)
        response = exchange(transport, request, settle, read_bytes=32)
        verdict, detail = classify(request, response, slave)
        if verbose:
            print("  TX  {}".format(hexdump(request)))
            print("  RX  {}".format(hexdump(response)))
            print("  ->  {}  {}".format(verdict, detail))
        return (verdict, detail)
    finally:
        transport.close()


def sweep(port: str, bauds, slaves, register: int, timeout: float, settle: float) -> int:
    """Try every baud x slave combination and report the ones that answered."""
    print("Port {}  register 0x{:04X}  timeout {}s  settle {}s".format(
        port, register, timeout, settle))
    print("Sweeping {} baud rate(s) x {} slave id(s) = {} exchange(s)\n".format(
        len(bauds), len(slaves), len(bauds) * len(slaves)))

    working = []
    for baud in bauds:
        for slave in slaves:
            noisy = len(slaves) <= 4
            if noisy:
                print("baud {:<6} slave 0x{:02X}".format(baud, slave))
            verdict, detail = probe_once(port, baud, slave, register, timeout, settle,
                                         verbose=noisy)
            if verdict == "PORT_ERROR":
                print("\n[FAILED] {}".format(detail))
                return 2
            if verdict in ("OK", "EXCEPTION", "WRONG_SLAVE"):
                working.append((baud, slave, verdict, detail))
                if not noisy:
                    print("baud {:<6} slave 0x{:02X}  ->  {}  {}".format(
                        baud, slave, verdict, detail))
            if noisy:
                print()

    print("=" * 72)
    if not working:
        print("No combination produced a Modbus-shaped reply.")
        print("The fault is below the protocol layer. In order of likelihood:")
        print("  1. Probe not powered   - measure 12 V DC across the probe's own")
        print("                           red/black pair, not the 5 V board rail.")
        print("  2. A/B swapped         - swap the two differential wires and rerun.")
        print("  3. Ground not shared   - the 12 V pack ground must tie to board GND.")
        print("  4. DE/RE stuck         - on the MAX485 path, D7 must be LOW to receive.")
        print("  5. Wrong device node   - confirm with: ls -l /dev/ttyUSB* /dev/ttyACM*")
        return 1

    print("Link is alive. Combinations that answered:")
    for baud, slave, verdict, detail in working:
        print("  baud {:<6} slave 0x{:02X}   {}  {}".format(baud, slave, verdict, detail))
    best = working[0]
    print("\nRun the decoder against it:")
    print('  python3 "hardware_test/soil sensor/jxbs_test.py" --port {} --baud {} --slave {}'
          .format(port, best[0], best[1]))
    print("\nThen point the pipeline at it:")
    print("  export FIELDSENSE_SOURCE=HARDWARE")
    print("  export FIELDSENSE_SENSOR_PORT={}".format(port))
    print("  export FIELDSENSE_SENSOR_BAUD={}".format(best[0]))
    print("  export FIELDSENSE_SENSOR_SLAVE={}".format(best[1]))
    return 0


def selftest() -> int:
    """Verify the classifier against synthetic frames. No hardware required."""
    request = build_read_request(0x0012, 0x01)

    def good_frame(raw: int, slave: int = 0x01) -> bytes:
        body = bytes([slave, 0x03, 0x02, (raw >> 8) & 0xFF, raw & 0xFF])
        crc = modbus_crc16(body)
        return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    cases = [
        ("OK",           good_frame(250)),
        ("EXCEPTION",    bytes([0x01, 0x83, 0x02, 0xC0, 0xF1])),
        ("NO_RESPONSE",  b""),
        ("ECHO",         request),
        ("WRONG_SLAVE",  good_frame(250, slave=0x02)),
        ("CRC",          good_frame(250)[:5] + b"\x00\x00"),
        ("SHORT",        good_frame(250)[:4]),
        ("GARBAGE",      bytes([0xFF, 0xFE, 0xF0, 0x00])),
    ]

    failures = 0
    for expected, response in cases:
        verdict, detail = classify(request, response, 0x01)
        ok = verdict == expected
        failures += 0 if ok else 1
        print("  [{}] {:<12} {:<24} {}".format(
            "PASS" if ok else "FAIL", expected, hexdump(response)[:22], detail))
    print("\n{}/{} classifier cases passed.".format(len(cases) - failures, len(cases)))
    return 1 if failures else 0


def main() -> int:
    """Command line entry point."""
    default_port = "COM8" if sys.platform.startswith("win") else "/dev/ttyUSB0"
    parser = argparse.ArgumentParser(
        description="Raw RS485/Modbus link sweep for the JXBS soil probe.")
    parser.add_argument("--port", default=default_port, help="serial device")
    parser.add_argument("--baud", default="9600",
                        help="comma separated baud rates, or 'all' for {}".format(
                            ",".join(str(b) for b in CANDIDATE_BAUDS)))
    parser.add_argument("--slave", default="1",
                        help="comma separated slave ids (decimal or 0x hex)")
    parser.add_argument("--scan-slaves", action="store_true",
                        help="sweep slave ids 1-247 to find a relabelled probe")
    parser.add_argument("--register", type=lambda v: int(v, 0), default=0x0012,
                        help="holding register to read (default 0x0012, moisture)")
    parser.add_argument("--timeout", type=float, default=0.5,
                        help="seconds to wait for a reply (default 0.5)")
    parser.add_argument("--settle", type=float, default=0.05,
                        help="RS485 turnaround pause before reading (default 0.05)")
    parser.add_argument("--selftest", action="store_true",
                        help="check this script's own logic, no hardware needed")
    parser.add_argument("--list-registers", action="store_true",
                        help="print the verified JXBS register map and exit")
    args = parser.parse_args()

    if args.list_registers:
        print("Verified JXBS-3001-TR register map (docs/HARDWARE.md section 4):")
        for name, (address, divisor, unit, signed) in JXBS_REGISTERS.items():
            print("  {:<12} 0x{:04X}  divide by {:<6} -> {:<7} {}".format(
                name, address, divisor, unit, "signed" if signed else ""))
        return 0

    if args.selftest:
        print("Classifier self-test (no hardware):\n")
        return selftest()

    bauds = list(CANDIDATE_BAUDS) if args.baud.strip().lower() == "all" else [
        int(b) for b in args.baud.split(",") if b.strip()]
    slaves = list(range(1, 248)) if args.scan_slaves else [
        int(s, 0) for s in args.slave.split(",") if s.strip()]

    return sweep(args.port, bauds, slaves, args.register, args.timeout, args.settle)


if __name__ == "__main__":
    raise SystemExit(main())
