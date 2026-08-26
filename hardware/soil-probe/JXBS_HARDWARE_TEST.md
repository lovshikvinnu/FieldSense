"""JXBS-3001-TR bench harness.

Thin console wrapper over the shared adapter layer. All Modbus framing, CRC,
register addressing, scaling, and the uS/cm -> dS/m conversion live in
`fieldsense.hardware.soil_adapter` and are NOT reimplemented here. This script
only opens a port, calls the adapter, and prints what it got.

    python3 "hardware/soil-probe/jxbs_test.py"

Windows:  defaults to COM8 (or specify via --port COM8)
Linux:    defaults to /dev/ttyUSB0 (ls /dev/ttyUSB*)
macOS:    defaults to /dev/ttyUSB0 (or --port /dev/cu.usbserial-XXXX)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fieldsense.hardware.soil_adapter import JXBS_REGISTERS, JXBSSoilAdapter  # noqa: E402


def main() -> int:
    # Auto-detect default serial port based on operating system
    default_port = "COM8" if sys.platform.startswith("win") else "/dev/ttyUSB0"

    parser = argparse.ArgumentParser(description="Read the JXBS 7-in-1 soil probe.")
    parser.add_argument("--port", default=default_port, help=f"serial device (default: {default_port})")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--slave", type=lambda v: int(v, 0), default=0x01)
    parser.add_argument("--samples", type=int, default=1, help="number of read cycles")
    args = parser.parse_args()

    print("JXBS-3001-TR  port={}  baud={}  slave=0x{:02X}".format(args.port, args.baud, args.slave))
    print("Modbus RTU, function 0x03, one holding register per parameter.\n")

    adapter = JXBSSoilAdapter.from_serial(args.port, args.baud, slave_id=args.slave)
    try:
        adapter.initialize()
    except Exception as exc:
        print("Could not open {}: {}".format(args.port, exc))
        return 1

    try:
        for cycle in range(1, args.samples + 1):
            data = adapter.read()
            print("--- read {}/{} ---".format(cycle, args.samples))
            for parameter in JXBS_REGISTERS:
                address, _divisor, unit, _signed = JXBS_REGISTERS[parameter]
                value = getattr(data, parameter)
                raw = data.raw_registers.get(parameter)
                if value is None:
                    print("  {:<12s} 0x{:04X}  FAILED".format(parameter, address))
                else:
                    print("  {:<12s} 0x{:04X}  raw={:<6} {:>8.2f} {}".format(
                        parameter, address, raw, value, unit))
            if data.ec is not None:
                print("  {:<12s} {:>8.4f} dS/m   (converted from {} uS/cm for the software contract)".format(
                    "ec [conv]", data.ec, data.ec_raw_us_cm))
            print("  parameters read: {}/{}".format(data.parameters_read, len(JXBS_REGISTERS)))
            for error in data.read_errors:
                print("  error: {}".format(error))
            print()
    finally:
        adapter.shutdown()
        print("Port closed cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())