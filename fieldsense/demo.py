"""FieldSense AI — Competition Demonstration Runner.

Executable via:
    python -m fieldsense.demo
"""

import os
from typing import Dict, Any

from fieldsense.testing.golden import GoldenDatasetRegistry
from fieldsense.intelligence import ValidationEngine, FieldIntelligenceEngine
from fieldsense.spatial import SpatialEngine, SpatialConfig
from fieldsense.zones import ZoneDetectionEngine
from fieldsense.recommendations import RecommendationEngine
from fieldsense.presentation import UIViewAdapter, LocalUIRenderer


def run_demo(
    output_path: str = "artifacts/fieldsense_competition_demo.html",
    scenario_name: str = "competition_demo_v1",
) -> Dict[str, Any]:
    """Execute complete 8-stage FieldSense pipeline demonstration and generate offline HTML dashboard.

    Args:
        output_path: Target path for HTML dashboard artifact output.
        scenario_name: Name of golden dataset scenario to load.

    Returns:
        Dictionary containing demonstration summary metrics.
    """
    # 1. Load Competition Demonstration Golden Dataset
    scenario = GoldenDatasetRegistry.get_scenario(scenario_name)
    session = GoldenDatasetRegistry.load_session(scenario)
    total_samples = session.sample_count

    # 2. Validation Engine
    val_engine = ValidationEngine()
    eligible_samples = val_engine.get_session_eligible_samples(session)
    valid_samples = len(eligible_samples)
    rejected_samples = max(0, total_samples - valid_samples)

    # 3. Deterministic Intelligence Engine
    intel_engine = FieldIntelligenceEngine()
    intel_results = intel_engine.process_many(eligible_samples)

    # 4. Spatial Engine
    spatial_engine = SpatialEngine(config=SpatialConfig(grid_spacing_meters=10.0))
    spatial_result = spatial_engine.process(intel_results, eligible_samples)

    # 5. Zone Detection Engine
    zone_engine = ZoneDetectionEngine()
    zone_result = zone_engine.process(spatial_result)

    # 6. Recommendation Engine
    rec_engine = RecommendationEngine()
    rec_result = rec_engine.process(zone_result)

    # 7. UI View Adapter
    ui_adapter = UIViewAdapter()
    ui_view = ui_adapter.adapt(session, spatial_result, zone_result, rec_result)

    # 8. Local HTML Renderer
    renderer = LocalUIRenderer()
    html_content = renderer.render_html(ui_view)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    summary = {
        "dataset": scenario.name,
        "session_id": session.session_id,
        "total_samples": total_samples,
        "valid_samples": valid_samples,
        "rejected_samples": rejected_samples,
        "soil_health_score": ui_view.health_summary.score,
        "soil_health_status": ui_view.health_summary.status,
        "coverage_ratio": round(spatial_result.coverage.coverage_ratio * 100, 1),
        "zone_count": len(zone_result.zones),
        "recommendation_count": len(rec_result.recommendations),
        "output_path": output_path,
        "offline_mode": ui_view.system_status.offline_mode,
        "data_source": ui_view.system_status.data_source,
    }

    # Print clean terminal report
    print("\n==================================================")
    print("           FIELDSENSE AI — DEMO                   ")
    print("==================================================")
    print(f"Dataset:            {summary['dataset']}")
    print(f"Data Source:        {summary['data_source']} (Offline Mode: {summary['offline_mode']})")
    print(f"Samples:            {summary['total_samples']} Total | {summary['valid_samples']} Valid | {summary['rejected_samples']} Rejected")
    print(f"Overall Health:     {int(summary['soil_health_score'] * 100)}% [{summary['soil_health_status']}]")
    print(f"Coverage Ratio:     {summary['coverage_ratio']}%")
    print(f"Zones Detected:     {summary['zone_count']} Spatially Connected Management Zones")
    print(f"Recommendations:    {summary['recommendation_count']} Rule-Based Actions")
    print(f"Dashboard Artifact: {summary['output_path']}")
    print("==================================================\n")

    return summary


if __name__ == "__main__":
    run_demo()
