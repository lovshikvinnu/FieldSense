"""FieldSense AI — Hardware JSON to Phase 1 Engines Integration Bridge.

Usage:
    python run_spatial_test.py [json_file_path]
"""

import argparse
import json
import math
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fieldsense.domain.models import FieldSample, FieldSession, SampleSource, ValidationState
from fieldsense.intelligence.engine import FieldIntelligenceEngine, FieldIntelligenceResult
from fieldsense.intelligence.validation.engine import ValidationEngine
from fieldsense.spatial.engine import SpatialEngine, SpatialConfig
from fieldsense.zones.engine import ZoneDetectionEngine
from fieldsense.recommendations.engine import RecommendationEngine
from fieldsense.intelligence.scoring import interpret_score
from fieldsense.presentation import LocalUIRenderer, UIViewAdapter
from fieldsense.ai import AIAdapterFactory, build_explanation_context


def generate_sample_hardware_json(file_path: str) -> None:
    """Generate sample field_test_20260823_171931.json with 5 physical soil samples if missing."""
    print(f"Generating realistic 5-point hardware test dataset at '{file_path}'...")
    
    # 5 Physical sample locations in Bangalore field area (Lat/Lon spherical degrees)
    # Point 1: Anchor Origin (0,0)
    # Point 2: ~20m North
    # Point 3: ~20m East
    # Point 4: ~20m North, ~20m East
    # Point 5: ~40m North, ~40m East
    sample_definitions = [
        # (lat, lon, N, P, K, pH, EC, moisture, temp)
        (12.971598, 77.594562, 48.0, 28.0, 185.0, 6.7, 1.15, 24.5, 24.0),
        (12.971778, 77.594562, 45.0, 26.0, 175.0, 6.5, 1.10, 22.0, 24.5),
        (12.971598, 77.594746, 22.0, 14.0, 105.0, 5.8, 0.85, 14.0, 26.0),
        (12.971778, 77.594746, 14.0, 10.0, 85.0,  5.4, 0.60, 11.5, 27.0),
        (12.971958, 77.594930, 32.0, 20.0, 145.0, 6.2, 0.98, 18.0, 25.0),
    ]

    intel_engine = FieldIntelligenceEngine()
    val_engine = ValidationEngine()
    json_entries = []

    for idx, (lat, lon, n, p, k, ph, ec, moist, temp) in enumerate(sample_definitions, start=1):
        sample = FieldSample(
            sample_id=f"FS-HW-20260823-{idx:03d}",
            timestamp=datetime.now().isoformat(),
            latitude=lat,
            longitude=lon,
            nitrogen=n,
            phosphorus=p,
            potassium=k,
            ph=ph,
            ec=ec,
            moisture=moist,
            temperature=temp,
            measurement_quality=0.95,
            source=SampleSource.HARDWARE,
            validation_state=ValidationState.VALID,
        )

        val_res = val_engine.validate(sample)
        intel_res = intel_engine.process(sample, val_res)

        json_entries.append({
            "field_sample": json.dumps(sample.to_dict()),
            "field_intelligence_result": json.dumps(intel_res.to_dict()),
            "provenance": "SYNTHETIC_FIXTURE",
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        })

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(json_entries, f, indent=2)

    print(f"[OK] Created hardware JSON test file: {file_path}")


def dataset_provenance(file_path: str) -> str:
    """Report where a dataset's values came from.

    Returns LIVE_HARDWARE, SIMULATED, SYNTHETIC_FIXTURE, MIXED, or UNSTAMPED.
    Datasets written before provenance stamping are UNSTAMPED and their origin
    cannot be established from the file alone.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return "UNSTAMPED"
    if not isinstance(data, list) or not data:
        return "UNSTAMPED"
    stamps = {entry.get("provenance", "UNSTAMPED") for entry in data if isinstance(entry, dict)}
    if len(stamps) == 1:
        return stamps.pop()
    return "MIXED"


def parse_hardware_json(file_path: str) -> Tuple[List[FieldSample], List[FieldIntelligenceResult]]:
    """Parse JSON file containing raw FieldSample strings/dicts and FieldIntelligenceResult strings/dicts."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"JSON data file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected top-level JSON array in '{file_path}', got {type(data)}")

    samples: List[FieldSample] = []
    intelligence_results: List[FieldIntelligenceResult] = []

    for idx, entry in enumerate(data, start=1):
        # Handle field_sample key variants (field_sample, sample, FieldSample)
        raw_sample = entry.get("field_sample") or entry.get("sample") or entry.get("FieldSample")
        raw_intel = entry.get("field_intelligence_result") or entry.get("intelligence_result") or entry.get("FieldIntelligenceResult")

        if raw_sample is None or raw_intel is None:
            raise KeyError(f"Entry {idx} missing required 'field_sample' or 'field_intelligence_result' fields.")

        # If stored as serialized JSON strings, parse them
        if isinstance(raw_sample, str):
            sample_dict = json.loads(raw_sample)
        else:
            sample_dict = raw_sample

        if isinstance(raw_intel, str):
            intel_dict = json.loads(raw_intel)
        else:
            intel_dict = raw_intel

        sample = FieldSample.from_dict(sample_dict)
        intel_res = FieldIntelligenceResult.from_dict(intel_dict)

        samples.append(sample)
        intelligence_results.append(intel_res)

    return samples, intelligence_results


def latlon_to_local_cartesian(coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Convert spherical Lat/Lon coordinates to a local 2D Cartesian grid (X, Y in meters).

    Anchors Point 1 (index 0) as origin (0.0, 0.0) using equirectangular projection:
    - X: East (+m) / West (-m)
    - Y: North (+m) / South (-m)

    Args:
        coords: List of (latitude, longitude) decimal degree tuples.

    Returns:
        List of (x_meters, y_meters) tuples anchored at coords[0].
    """
    if not coords:
        return []

    ref_lat, ref_lon = coords[0]
    ref_lat_rad = math.radians(ref_lat)

    # Standard degree-to-meter scale at ref_lat
    meters_per_lat_deg = 111000.0
    meters_per_lon_deg = 111000.0 * math.cos(ref_lat_rad)

    local_xy = []
    for lat, lon in coords:
        x = (lon - ref_lon) * meters_per_lon_deg
        y = (lat - ref_lat) * meters_per_lat_deg
        local_xy.append((round(x, 2), round(y, 2)))

    return local_xy



def build_dashboard(
    samples: List[FieldSample],
    spatial_result: Any,
    zone_result: Any,
    rec_result: Any,
    output_dir: str = "artifacts",
    html_name: str = "field_test_map.html",
) -> Tuple[str, Any]:
    """Render the Field Intelligence Map dashboard from spatial + zone results.

    Feeds the frozen presentation layer: UIViewAdapter reshapes the engine
    results into a passive UIFieldView, the optional AI layer attaches a
    guarded plain-language narrative, and LocalUIRenderer emits one
    self-contained HTML file with no external requests.

    Args:
        samples: Hardware FieldSamples used for this run.
        spatial_result: SpatialFieldResult from the spatial engine.
        zone_result: ZoneDetectionResult from the zone engine.
        rec_result: RecommendationResult from the recommendation engine.
        output_dir: Directory for generated artifacts.
        html_name: Output file name.

    Returns:
        Tuple of (html_path, ui_view).
    """
    session = FieldSession(
        session_id="FIELD-TEST-{}".format(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")),
        created_at=datetime.now(timezone.utc),
        field_name="Hardware Field Test",
    )
    for sample in samples:
        session.add_sample(sample)

    view = UIViewAdapter().adapt(
        session, spatial_result, zone_result, rec_result,
        expected_samples=max(1, len(samples)),
    )

    # Optional narrative. Absent model weights resolve to deterministic
    # templates; a failure here must never cost us the dashboard.
    try:
        ai_adapter = AIAdapterFactory.create_adapter()
        try:
            narrative = ai_adapter.explain(
                build_explanation_context(session, spatial_result, zone_result, rec_result)
            )
            view = replace(view, narrative=narrative)
        finally:
            ai_adapter.shutdown()
    except Exception as exc:  # narrative is presentation text, never load-bearing
        print("     -> AI narrative unavailable ({}); dashboard renders without it.".format(exc))

    os.makedirs(output_dir, exist_ok=True)
    html_path = os.path.join(output_dir, html_name)
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(LocalUIRenderer().render_html(view))

    return html_path, view


def push_to_display(
    html_path: str,
    output_dir: str = "artifacts",
    mode: str = "auto",
    fb_device: Optional[str] = None,
    rotate: int = 0,
    png_name: str = "field_test_panel.png",
) -> Dict[str, Any]:
    """Render the dashboard to a 240x320 RGB565 frame and flush it to the panel.

    Modes:
        auto   push only when a framebuffer device exists, otherwise skip fast
        png    capture the frame and save a PNG, no framebuffer write
        force  capture and attempt the write even if detection found nothing
        off    do nothing

    Never raises. A missing panel, browser, or driver degrades to a reported
    status so the pipeline still completes.
    """
    outcome: Dict[str, Any] = {"status": "SKIPPED", "device": None, "frame_png": None, "detail": ""}
    if mode == "off":
        outcome["detail"] = "display disabled"
        return outcome

    from fieldsense.hardware import display_bridge as bridge

    candidates = [fb_device] if fb_device else ["/dev/fb1", "/dev/fb0"]
    device = next((d for d in candidates if d and os.path.exists(d)), None)

    if device is None and mode == "auto":
        outcome["detail"] = (
            "no framebuffer found ({}). On the UNO Q load the fbtft driver, then re-run. "
            "Use --display png to save a frame instead.".format(", ".join(c for c in candidates if c))
        )
        return outcome

    if bridge.find_browser() is None:
        outcome["status"] = "FAILED"
        outcome["detail"] = "no Chromium-family browser found (sudo apt install chromium)"
        return outcome

    try:
        width, height, rgb = bridge.capture_rgb(html_path, 240, 320, settle_ms=1200)
    except Exception as exc:
        outcome["status"] = "FAILED"
        outcome["detail"] = "frame render failed: {}".format(exc)
        return outcome

    # Always keep visual proof of the exact frame, panel present or not.
    try:
        png_path = os.path.join(output_dir, png_name)
        with open(png_path, "wb") as handle:
            handle.write(bridge.encode_png(rgb, width, height))
        outcome["frame_png"] = png_path
    except Exception:
        pass

    if device is None:
        outcome["status"] = "NO_DEVICE"
        outcome["detail"] = "frame rendered but no framebuffer to write"
        return outcome

    try:
        width, height, rgb = bridge.rotate_rgb(rgb, width, height, rotate)
        written = bridge.write_framebuffer(bridge.rgb_to_rgb565(rgb, "little"), device)
        outcome.update(status="PUSHED", device=device,
                       detail="{} bytes written ({}x{} RGB565)".format(written, width, height))
    except Exception as exc:
        outcome["status"] = "FAILED"
        outcome["device"] = device
        outcome["detail"] = str(exc)

    return outcome


def run_spatial_test(
    json_path: str = "field_test_20260823_171931.json",
    output_dir: str = "artifacts",
    render_ui: bool = True,
    display: str = "auto",
    fb_device: Optional[str] = None,
    rotate: int = 0,
    allow_generate: bool = False,
) -> Dict[str, Any]:
    """Bridge hardware JSON to Phase 1 engines, the visual dashboard, and the panel.

    Args:
        json_path: Hardware telemetry JSON produced by the acquisition run.
        output_dir: Directory for the generated dashboard and frame.
        render_ui: Generate the self-contained HTML Field Intelligence Map.
        display: auto | png | force | off. `auto` pushes to the panel only when
            a framebuffer device exists, so this stays fast off-target.
        fb_device: Explicit framebuffer, e.g. /dev/fb1. Defaults to auto-detect.
        rotate: Clockwise frame rotation in degrees (0, 90, 180, 270).
        allow_generate: Permit building a synthetic fixture when the dataset is
            missing. Off by default so real runs never silently fabricate data.

    Returns:
        Summary dictionary of the run.
    """
    print("\n================================================================================")
    print("      FIELDSENSE SPATIAL INTEGRATION TEST & HARDWARE BRIDGE (PHASE 1)   ")
    print("================================================================================")

    if not os.path.exists(json_path):
        if not allow_generate:
            raise FileNotFoundError(
                "Dataset not found: '{}'.\n"
                "This script will NOT invent data. Capture real samples with:\n"
                "    python3 -m fieldsense.live_collector --points 5 --out {}\n"
                "or pass --generate-sample to build a clearly-stamped synthetic "
                "fixture for a dry run.".format(json_path, json_path)
            )
        generate_sample_hardware_json(json_path)

    # 1. Parse JSON File
    print(f"\n[1/7] Parsing Hardware JSON Output: '{json_path}'...")
    samples, intel_results = parse_hardware_json(json_path)
    provenance = dataset_provenance(json_path)
    print(f"     -> Extracted {len(samples)} soil samples and intelligence results.")
    banner = {
        "LIVE_HARDWARE":    "     -> PROVENANCE: LIVE_HARDWARE — values came off the physical probe.",
        "SIMULATED":        "     -> PROVENANCE: SIMULATED — virtual sensor. NOT field data.",
        "SYNTHETIC_FIXTURE":"     -> PROVENANCE: SYNTHETIC_FIXTURE — generated placeholders. NOT field data.",
        "MIXED":            "     -> PROVENANCE: MIXED — entries disagree on origin. Inspect before use.",
        "UNSTAMPED":        "     -> PROVENANCE: UNSTAMPED — origin cannot be established from this file.",
    }[provenance]
    print(banner)

    # 2. Coordinate Projection (Lat/Lon -> Local 2D Cartesian Grid in meters)
    print("\n[2/7] Coordinate Projection (Lat/Lon -> Local 2D Cartesian Grid, Point 1 as Origin):")
    print("--------------------------------------------------------------------------------")
    coords = [(s.latitude, s.longitude) for s in samples]
    local_xy = latlon_to_local_cartesian(coords)

    intel_map = {res.sample_id: res for res in intel_results}
    for idx, (sample, (x, y)) in enumerate(zip(samples, local_xy), start=1):
        intel = intel_map.get(sample.sample_id)
        sh_score = intel.soil_health.score if intel else 0.0
        sh_status = interpret_score(sh_score) if intel else "N/A"
        m_score = intel.moisture.score if intel else 0.0
        n_score = intel.nitrogen.score if intel else 0.0

        origin_label = " (ORIGIN)" if idx == 1 else "         "
        print(f"  Point {idx}{origin_label} : Lat {sample.latitude:10.6f} deg, Lon {sample.longitude:10.6f} deg -> Local X:{x:7.2f} m, Y:{y:7.2f} m | "
              f"Soil Health: {sh_score:.4f} [{sh_status:8s}] | Moisture: {m_score:.4f} | Nitrogen: {n_score:.4f}")

    # 3. Instantiate Phase 1 Spatial Mapping Classes
    print("\n[3/7] Instantiating Phase 1 Spatial, Zone, and Recommendation Engines...")
    spatial_engine = SpatialEngine(config=SpatialConfig(grid_spacing_meters=5.0))
    zone_engine = ZoneDetectionEngine()
    rec_engine = RecommendationEngine()

    # 4. Processing Phase 1 Engines
    print("[4/7] Executing Spatial IDW Interpolation, Zone Detection & Recommendations...")
    spatial_result = spatial_engine.process(intel_results, samples)
    zone_result = zone_engine.process(spatial_result)
    rec_result = rec_engine.process(zone_result)

    # 5. Terminal Output Summary
    print("\n[5/7] End-to-End Pipeline Summary:")
    print("--------------------------------------------------------------------------------")
    print(f"  [Spatial IDW Grid]")
    print(f"    - Field Bounds       : Lat [{spatial_result.bounds.min_latitude:.6f} deg - {spatial_result.bounds.max_latitude:.6f} deg], "
          f"Lon [{spatial_result.bounds.min_longitude:.6f} deg - {spatial_result.bounds.max_longitude:.6f} deg]")
    print(f"    - Grid Points        : {len(spatial_result.grid_points)} interpolated points (5.0m resolution)")
    print(f"    - Spatial Coverage   : {spatial_result.coverage.coverage_ratio * 100:.1f}% (~{spatial_result.coverage.covered_area_estimate:.1f} m^2)")
    print(f"    - Spatial Layers     : {', '.join(spatial_result.layers.keys())}")

    print(f"\n  [Identified Priority Zones ({len(zone_result.zones)} total)]")
    for z in zone_result.zones:
        issue_str = z.primary_issue if z.primary_issue else "NONE"
        print(f"    - Zone {z.zone_id} [{z.status:8s}] : Area = {z.area_estimate:6.1f} m^2 | Severity = {z.severity:8s} | Primary Issue = {issue_str}")

    print(f"\n  [Actionable Recommendations ({len(rec_result.recommendations)} total)]")
    for r in rec_result.recommendations:
        p_val = r.priority.value if hasattr(r.priority, 'value') else r.priority
        c_val = r.category.value if hasattr(r.category, 'value') else r.category
        print(f"    - [{r.recommendation_id}] Zone {r.zone_id} ({p_val}) [{c_val}] : {r.action}")
        print(f"      Reason: {r.reason}")

    # 6. Visual Field Intelligence Map
    html_path = None
    health = None
    if render_ui:
        print("\n[6/7] Rendering Field Intelligence Map dashboard...")
        html_path, ui_view = build_dashboard(
            samples, spatial_result, zone_result, rec_result, output_dir=output_dir
        )
        health = ui_view.health_summary
        size_kb = os.path.getsize(html_path) / 1024.0
        print(f"     -> Overall Health : {health.score * 100:.0f}% [{health.status}]")
        print(f"     -> Dashboard      : {html_path} ({size_kb:.1f} KB, self-contained)")
        if ui_view.narrative:
            print(f"     -> Narrative      : {ui_view.narrative.generated_by} "
                  f"[{ui_view.narrative.generation_status.value}] | "
                  f"guard blocks: {len(ui_view.narrative.guard_violations)}")
    else:
        print("\n[6/7] Dashboard rendering disabled (--no-ui).")

    # 7. Physical 2.8" TFT panel
    print("\n[7/7] Pushing RGB565 frame to the 2.8\" TFT panel...")
    if html_path is None:
        display_result = {"status": "SKIPPED", "device": None, "frame_png": None,
                          "detail": "no dashboard rendered"}
    else:
        display_result = push_to_display(
            html_path, output_dir=output_dir, mode=display, fb_device=fb_device, rotate=rotate
        )
    marker = {"PUSHED": "[OK]", "NO_DEVICE": "[--]", "SKIPPED": "[--]", "FAILED": "[!!]"}.get(
        display_result["status"], "[--]")
    print(f"     {marker} {display_result['status']}: {display_result['detail']}")
    if display_result.get("frame_png"):
        print(f"     -> Panel frame    : {display_result['frame_png']} (240x320, exact panel pixels)")

    print("\n================================================================================")
    print(" SUCCESS: Hardware JSON -> Cartesian -> IDW -> Zones -> Recs -> Dashboard -> Panel")
    print("================================================================================\n")

    return {
        "samples": len(samples),
        "local_xy": local_xy,
        "grid_points": len(spatial_result.grid_points),
        "zones": len(zone_result.zones),
        "recommendations": len(rec_result.recommendations),
        "html_path": html_path,
        "soil_health": round(health.score, 4) if health else None,
        "soil_health_status": health.status if health else None,
        "provenance": provenance,
        "display_status": display_result["status"],
        "display_device": display_result["device"],
        "panel_frame": display_result.get("frame_png"),
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(
        description="Bridge hardware telemetry JSON to the FieldSense pipeline, dashboard and panel.")
    parser.add_argument("json_path", nargs="?", default="field_test_20260823_171931.json",
                        help="hardware telemetry JSON (generated if missing)")
    parser.add_argument("--output-dir", default="artifacts", help="where to write the dashboard and frame")
    parser.add_argument("--no-ui", action="store_true", help="skip dashboard rendering")
    parser.add_argument("--display", default="auto", choices=("auto", "png", "force", "off"),
                        help="auto: push only if a framebuffer exists · png: save a frame instead")
    parser.add_argument("--fb", dest="fb_device", default=None, help="explicit framebuffer, e.g. /dev/fb1")
    parser.add_argument("--rotate", type=int, default=0, choices=(0, 90, 180, 270))
    parser.add_argument("--generate-sample", action="store_true",
                        help="build a stamped synthetic fixture if the dataset is missing")
    args = parser.parse_args(argv)

    run_spatial_test(
        args.json_path,
        output_dir=args.output_dir,
        render_ui=not args.no_ui,
        display=args.display,
        fb_device=args.fb_device,
        rotate=args.rotate,
        allow_generate=args.generate_sample,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
