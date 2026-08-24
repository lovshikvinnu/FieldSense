"""FieldSense AI V1 — Unified End-to-End Runner.

Connects live hardware sample collection to Phase 1 spatial intelligence,
dashboard generation, and display output in a single orchestration command:

    REAL HARDWARE
    -> live_collector
    -> validated JSON session
    -> run_spatial_test
    -> field_test_map.html
    -> optional TFT rendering

Usage:
    # Live hardware run on UNO Q:
    python3 -m fieldsense.v1_runner --samples 5

    # Simulated rehearsal run:
    python3 -m fieldsense.v1_runner --samples 5 --simulate
"""

import argparse
import sys
from typing import Any, Dict, List, Optional

from fieldsense.live_collector import (
    CollectionError,
    collect_samples,
    write_dataset,
)
from run_spatial_test import run_spatial_test


def run_v1_pipeline(
    samples: int = 5,
    out_json: str = "field_test_live_hardware.json",
    sensor_port: str = "/dev/ttyUSB0",
    simulate: bool = False,
    interactive: bool = True,
    output_dir: str = "artifacts",
    display: str = "auto",
    mcu_port: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute complete FieldSense V1 pipeline: Live hardware collection -> Spatial intelligence.

    Args:
        samples: Number of soil samples to capture (default 5, minimum 3).
        out_json: Output path for validated hardware JSON session.
        sensor_port: Serial device path for JXBS probe (e.g. /dev/ttyUSB0).
        simulate: If True, use virtual sensor (stamped SIMULATED).
        interactive: If True, wait for Enter between probe insertions.
        output_dir: Output directory for generated artifacts.
        display: Display mode for the 2.8" TFT panel
            (auto | png | force | bridge | serial | off). `bridge` is the only
            mode that reaches the panel on an Arduino UNO Q: the QRB2210 routes
            no SPI to the external headers, so no framebuffer device for this
            panel can exist and `auto` finds nothing to write to.
        mcu_port: `host:port` of the router monitor proxy for `bridge` mode.
            Defaults to 127.0.0.1:7500. Not a tty - arduino-router owns the
            serial device itself.

    Returns:
        Summary dictionary containing collection and spatial metrics.

    Raises:
        CollectionError: If sample collection fails or fewer than 3 valid samples are captured.
    """
    # Stage 1: Hardware Sample Collection
    entries = collect_samples(
        points=samples,
        simulate=simulate,
        sensor_port=sensor_port,
        interactive=interactive,
    )

    if len(entries) < 3:
        raise CollectionError(
            f"Spatial intelligence pipeline requires at least 3 valid samples; "
            f"captured {len(entries)} usable sample(s). Aborting."
        )

    saved_path = write_dataset(entries, out_json)

    # Stage 2: Spatial Intelligence Processing & Dashboard/Panel Rendering
    spatial_summary = run_spatial_test(
        json_path=saved_path,
        output_dir=output_dir,
        display=display,
        allow_generate=False,
        mcu_port=mcu_port,
    )

    result = {
        "samples_captured": len(entries),
        "dataset_path": saved_path,
        "html_path": spatial_summary.get("html_path"),
        "zones": spatial_summary.get("zones", 0),
        "recommendations": spatial_summary.get("recommendations", 0),
        "provenance": spatial_summary.get("provenance"),
        "spatial_summary": spatial_summary,
    }

    print("\n==================================================")
    print("      FIELDSENSE V1 END-TO-END PIPELINE")
    print("==================================================")
    print("\n[1/2] LIVE HARDWARE COLLECTION")
    print(f"Samples captured: {result['samples_captured']}")
    print(f"Dataset:          {result['dataset_path']}")
    print("\n[2/2] SPATIAL INTELLIGENCE")
    print(f"Map:              {result['html_path']}")
    print(f"Zones:            {result['zones']}")
    print(f"Recommendations:  {result['recommendations']}")
    print("\n==================================================")
    print("          V1 PIPELINE COMPLETE")
    print("==================================================\n")

    return result


def main(argv: Optional[List[str]] = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(
        description="FieldSense V1 — Unified Live Hardware & Spatial Pipeline Runner"
    )
    parser.add_argument(
        "--samples",
        "--points",
        dest="samples",
        type=int,
        default=5,
        help="number of field samples to collect (default 5, minimum 3)",
    )
    parser.add_argument(
        "--out",
        default="field_test_live_hardware.json",
        help="output JSON path for captured session",
    )
    parser.add_argument(
        "--port",
        default="/dev/ttyUSB0",
        help="JXBS probe serial device (default /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="use virtual sensor; output is stamped SIMULATED",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="do not wait for Enter between points",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts",
        help="directory for generated artifacts (default artifacts)",
    )
    parser.add_argument(
        "--display",
        default="auto",
        choices=("auto", "png", "force", "bridge", "serial", "off"),
        help="TFT display push mode (default auto). Use 'bridge' on an Arduino "
             "UNO Q - it is the only mode that reaches the panel there, and "
             "'auto' silently finds no framebuffer to write to",
    )
    parser.add_argument(
        "--mcu-port",
        default=None,
        help="host:port of the router monitor proxy for --display bridge "
             "(default 127.0.0.1:7500)",
    )
    args = parser.parse_args(argv)

    try:
        run_v1_pipeline(
            samples=args.samples,
            out_json=args.out,
            sensor_port=args.port,
            simulate=args.simulate,
            interactive=not args.no_interactive,
            output_dir=args.output_dir,
            display=args.display,
            mcu_port=args.mcu_port,
        )
        return 0
    except (CollectionError, Exception) as exc:
        print(f"\n[V1 RUNNER ERROR] {exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
