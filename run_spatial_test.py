"""FieldSense AI — Hardware JSON to Phase 1 Engines Integration Bridge.

Usage:
    python run_spatial_test.py [json_file_path]
"""

import json
import math
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Any

from fieldsense.domain.models import FieldSample, SampleSource, ValidationState
from fieldsense.intelligence.engine import FieldIntelligenceEngine, FieldIntelligenceResult
from fieldsense.intelligence.validation.engine import ValidationEngine
from fieldsense.spatial.engine import SpatialEngine, SpatialConfig
from fieldsense.zones.engine import ZoneDetectionEngine
from fieldsense.recommendations.engine import RecommendationEngine
from fieldsense.intelligence.scoring import interpret_score


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
        })

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(json_entries, f, indent=2)

    print(f"[OK] Created hardware JSON test file: {file_path}")


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


def run_spatial_test(json_path: str = "field_test_20260823_171931.json") -> Dict[str, Any]:
    """Bridge hardware JSON output to Phase 1 Spatial, Zone, and Recommendation engines."""
    print("\n================================================================================")
    print("      FIELDSENSE SPATIAL INTEGRATION TEST & HARDWARE BRIDGE (PHASE 1)   ")
    print("================================================================================")

    # Auto-generate JSON file if missing to ensure script is fully runnable out-of-the-box
    if not os.path.exists(json_path):
        generate_sample_hardware_json(json_path)

    # 1. Parse JSON File
    print(f"\n[1/5] Parsing Hardware JSON Output: '{json_path}'...")
    samples, intel_results = parse_hardware_json(json_path)
    print(f"     -> Extracted {len(samples)} valid physical soil samples and intelligence results.")

    # 2. Coordinate Projection (Lat/Lon -> Local 2D Cartesian Grid in meters)
    print("\n[2/5] Coordinate Projection (Lat/Lon -> Local 2D Cartesian Grid, Point 1 as Origin):")
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
    print("\n[3/5] Instantiating Phase 1 Spatial, Zone, and Recommendation Engines...")
    spatial_engine = SpatialEngine(config=SpatialConfig(grid_spacing_meters=5.0))
    zone_engine = ZoneDetectionEngine()
    rec_engine = RecommendationEngine()

    # 4. Processing Phase 1 Engines
    print("[4/5] Executing Spatial IDW Interpolation, Zone Detection & Recommendations...")
    spatial_result = spatial_engine.process(intel_results, samples)
    zone_result = zone_engine.process(spatial_result)
    rec_result = rec_engine.process(zone_result)

    # 5. Terminal Output Summary
    print("\n[5/5] End-to-End Pipeline Summary:")
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

    print("================================================================================")
    print(" SUCCESS: End-to-End Pipeline Hardware JSON -> Cartesian -> IDW -> Zones -> Recs")
    print("================================================================================\n")

    return {
        "samples": len(samples),
        "local_xy": local_xy,
        "grid_points": len(spatial_result.grid_points),
        "zones": len(zone_result.zones),
        "recommendations": len(rec_result.recommendations),
    }


if __name__ == "__main__":
    target_json = sys.argv[1] if len(sys.argv) > 1 else "field_test_20260823_171931.json"
    run_spatial_test(target_json)
