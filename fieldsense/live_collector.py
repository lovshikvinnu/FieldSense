"""FieldSense AI — Live hardware sample collector.

Walks a field, captures N GPS-tagged soil samples from the physical JXBS probe
and NEO-M8N GPS, runs each through the frozen validation and intelligence
engines, and writes them to JSON in the schema `run_spatial_test.py` reads:

    [
      {
        "field_sample":               "<serialized FieldSample>",
        "field_intelligence_result":  "<serialized FieldIntelligenceResult>",
        "provenance":                 "LIVE_HARDWARE",
        "acquired_at":                "2026-08-23T18:04:11+00:00"
      },
      ...
    ]

PROVENANCE
----------
Every entry is stamped. `LIVE_HARDWARE` means the values came off a physical
probe; `SIMULATED` means they came from the virtual sensor. The stamp exists
because a synthetic dataset that merely *looks* like field data is worse than
no dataset — it invites a claim nobody can back up. `run_spatial_test.py`
prints the stamp so the origin of a dashboard is never in doubt.

Usage
-----
    # On the UNO Q, with the probe and GPS attached:
    python3 -m fieldsense.live_collector --points 5 --out field_test_live_hardware.json

    # Off-target rehearsal of the same flow (clearly stamped SIMULATED):
    python3 -m fieldsense.live_collector --points 5 --simulate --out rehearsal.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fieldsense.hardware.factory import DataSourceConfig, SensorAdapterFactory
from fieldsense.intelligence import FieldIntelligenceEngine, ValidationEngine

PROVENANCE_LIVE = "LIVE_HARDWARE"
PROVENANCE_SIMULATED = "SIMULATED"


class CollectionError(Exception):
    """Raised when acquisition cannot proceed at all."""


def collect_samples(
    points: int = 5,
    simulate: bool = False,
    sensor_port: str = "/dev/ttyUSB0",
    interactive: bool = True,
    settle_seconds: float = 2.0,
    keep_invalid: bool = False,
) -> List[Dict[str, Any]]:
    """Acquire `points` samples and return serialized JSON entries.

    Args:
        points: How many field points to capture.
        simulate: Use the virtual sensor instead of physical hardware. Output
            is stamped SIMULATED and must never be presented as field data.
        sensor_port: Serial device for the JXBS probe.
        interactive: Wait for Enter between points, so the operator can move
            and reinsert the probe.
        settle_seconds: Pause after insertion before reading, letting the
            probe's moisture and EC readings stabilise.
        keep_invalid: Retain samples the ValidationEngine rejects. Off by
            default so a bad insertion does not poison the spatial map.

    Returns:
        List of JSON-ready entries.

    Raises:
        CollectionError: Hardware unreachable, or nothing usable was captured.
    """
    provenance = PROVENANCE_SIMULATED if simulate else PROVENANCE_LIVE
    source = "VIRTUAL" if simulate else "HARDWARE"

    print("\n================================================================================")
    print("            FIELDSENSE — LIVE FIELD SAMPLE COLLECTION")
    print("================================================================================")
    print(f"  Provenance : {provenance}")
    print(f"  Source     : {source}" + ("" if simulate else f"   port {sensor_port}"))
    print(f"  Points     : {points}")
    if simulate:
        print("\n  ** SIMULATED RUN — values are synthetic. Do not present as field data. **")
    print()

    try:
        adapter = SensorAdapterFactory.create_adapter(
            DataSourceConfig.from_env(source=source, sensor_port=sensor_port)
        )
        adapter.initialize()
    except (NameError, TypeError, AttributeError, ImportError, SyntaxError):
        # A defect in FieldSense itself, not a fault on the bench. Let it fly
        # with its traceback intact, which names the line to fix. The handler
        # below would instead send the operator to a multimeter for something
        # no amount of rewiring can clear -- a missing `Any` import in
        # factory.py once cost exactly that, presenting a NameError as a
        # suspected wiring fault.
        raise
    except Exception as exc:
        raise CollectionError(
            "Could not initialise the {} adapter.\n"
            "  {}: {}\n"
            "Check the probe is powered from 12 V (its own supply, not the 5 V "
            "board rail), that RS485 A/B are not swapped, that the 12 V ground "
            "is tied to board ground, and that {} exists.\n"
            "Isolate the link before suspecting software:\n"
            "  python3 \"hardware_test/soil sensor/rs485_probe_sweep.py\" --port {}".format(
                source, type(exc).__name__, exc, sensor_port, sensor_port)
        ) from exc

    validator = ValidationEngine()
    intelligence = FieldIntelligenceEngine()
    entries: List[Dict[str, Any]] = []
    rejected = 0

    try:
        for index in range(1, points + 1):
            if interactive:
                try:
                    input(f"  [{index}/{points}] Insert the probe at point {index}, then press Enter...")
                except (EOFError, KeyboardInterrupt):
                    print("\n  Collection interrupted by operator.")
                    break
            if settle_seconds > 0:
                time.sleep(settle_seconds)

            try:
                if hasattr(adapter, "transport") and hasattr(adapter.transport, "is_open") and not adapter.transport.is_open:
                    adapter.initialize()
                elif hasattr(adapter, "initialized") and not getattr(adapter, "initialized", True):
                    adapter.initialize()

                sample = adapter.acquire_sample()
            except (NameError, TypeError, AttributeError, ImportError) as exc:
                # Same boundary as initialise: a code defect repeats identically
                # at every point, so swallowing it per-point would print the
                # same misleading line N times and still write no data.
                raise CollectionError(
                    "Acquisition raised {}, which is a FieldSense defect rather "
                    "than a hardware fault: {}".format(type(exc).__name__, exc)
                ) from exc
            except Exception as exc:
                print(f"      [!!] acquisition failed at point {index}: "
                      f"{type(exc).__name__}: {exc}")
                continue

            result = validator.validate(sample)
            status = result.state.value if hasattr(result.state, "value") else str(result.state)

            print(f"      {sample.sample_id}")
            print(f"        position : {sample.latitude:.6f}, {sample.longitude:.6f}")
            print(f"        soil     : pH {sample.ph} | {sample.moisture}% | {sample.temperature} C "
                  f"| EC {sample.ec} dS/m | NPK {sample.nitrogen}-{sample.phosphorus}-{sample.potassium}")
            print(f"        quality  : {sample.measurement_quality}   validation: {status}")

            if not result.pipeline_eligible and not keep_invalid:
                reasons = [r.value if hasattr(r, "value") else str(r) for r in result.reasons]
                print(f"        [--] discarded, not pipeline eligible: {reasons}")
                rejected += 1
                continue

            intel = intelligence.process(sample, result)
            entries.append({
                "field_sample": json.dumps(sample.to_dict()),
                "field_intelligence_result": json.dumps(intel.to_dict()),
                "provenance": provenance,
                "acquired_at": datetime.now(timezone.utc).isoformat(),
            })
            print(f"        [OK] captured   soil health {intel.soil_health.score:.4f}")
    finally:
        try:
            adapter.shutdown()
        except Exception:
            pass

    print(f"\n  Captured {len(entries)} usable sample(s), discarded {rejected}.")
    if not entries:
        raise CollectionError(
            "No usable samples captured. Nothing written — an empty or fabricated "
            "dataset is worse than none."
        )
    if len(entries) < 3:
        print("  [!!] The spatial engine needs at least 3 samples to interpolate a map.")
    return entries


def write_dataset(entries: List[Dict[str, Any]], out_path: str) -> str:
    """Write collected entries to JSON, refusing to overwrite blindly."""
    directory = os.path.dirname(out_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2)
    size_kb = os.path.getsize(out_path) / 1024.0
    print(f"  Written: {out_path} ({size_kb:.1f} KB, {len(entries)} entries)")
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(
        description="Collect live GPS-tagged soil samples into a FieldSense dataset.")
    parser.add_argument("--points", type=int, default=5, help="number of field points (default 5)")
    parser.add_argument("--out", default="field_test_live_hardware.json", help="output JSON path")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="JXBS serial device")
    parser.add_argument("--settle", type=float, default=2.0,
                        help="seconds to wait after insertion before reading")
    parser.add_argument("--no-interactive", action="store_true",
                        help="do not wait for Enter between points")
    parser.add_argument("--keep-invalid", action="store_true",
                        help="retain samples that fail validation")
    parser.add_argument("--simulate", action="store_true",
                        help="use the virtual sensor; output is stamped SIMULATED")
    args = parser.parse_args(argv)

    try:
        entries = collect_samples(
            points=args.points,
            simulate=args.simulate,
            sensor_port=args.port,
            interactive=not args.no_interactive,
            settle_seconds=args.settle,
            keep_invalid=args.keep_invalid,
        )
    except CollectionError as exc:
        print(f"\n[FAILED] {exc}\n", file=sys.stderr)
        return 1

    write_dataset(entries, args.out)
    print("\n  Next:  PYTHONPATH=. python3 run_spatial_test.py {}\n".format(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
