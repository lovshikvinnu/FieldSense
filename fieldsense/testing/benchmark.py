"""Host performance benchmark for FieldSense pipeline execution."""

import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

from fieldsense.input import VirtualSensorAdapter
from fieldsense.intelligence import ValidationEngine, FieldIntelligenceEngine
from fieldsense.spatial import SpatialEngine, SpatialConfig
from fieldsense.zones import ZoneDetectionEngine
from fieldsense.recommendations import RecommendationEngine
from fieldsense.presentation import UIViewAdapter, LocalUIRenderer


@dataclass
class BenchmarkStageTime:
    """Execution timing measurements for a single dataset benchmark run."""
    sample_count: int
    acquisition_time_ms: float
    validation_time_ms: float
    intelligence_time_ms: float
    spatial_time_ms: float
    zones_time_ms: float
    recommendation_time_ms: float
    presentation_time_ms: float
    total_pipeline_time_ms: float
    label: str = "HOST BENCHMARK"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HostPerformanceBenchmark:
    """Host performance benchmarking utility.

    Measures stage-by-stage pipeline execution times across sample sizes (25, 50, 100, 250, 500).
    Explicitly labeled as HOST BENCHMARK (Windows development machine).
    """

    @staticmethod
    def run_benchmark_for_samples(sample_count: int) -> BenchmarkStageTime:
        """Run full pipeline benchmark for a given sample count.

        Args:
            sample_count: Target number of samples.

        Returns:
            BenchmarkStageTime populated with timing data.
        """
        # 1. Acquisition
        t0 = time.perf_counter()
        adapter = VirtualSensorAdapter(seed=42, num_samples=sample_count)
        session = adapter.collect_session(session_id=f"SES-BENCH-{sample_count}")
        t1 = time.perf_counter()

        # 2. Validation
        val_engine = ValidationEngine()
        eligible = val_engine.get_session_eligible_samples(session)
        t2 = time.perf_counter()

        # 3. Deterministic Intelligence
        intel_engine = FieldIntelligenceEngine()
        intels = intel_engine.process_many(eligible)
        t3 = time.perf_counter()

        # 4. Spatial Engine
        spatial_engine = SpatialEngine(config=SpatialConfig(grid_spacing_meters=10.0))
        spatial = spatial_engine.process(intels, eligible)
        t4 = time.perf_counter()

        # 5. Zone Detection Engine
        zone_engine = ZoneDetectionEngine()
        zones = zone_engine.process(spatial)
        t5 = time.perf_counter()

        # 6. Recommendation Engine
        rec_engine = RecommendationEngine()
        recs = rec_engine.process(zones)
        t6 = time.perf_counter()

        # 7. Presentation Layer & HTML Rendering
        ui_adapter = UIViewAdapter()
        ui_view = ui_adapter.adapt(session, spatial, zones, recs)
        html = LocalUIRenderer().render_html(ui_view)
        t7 = time.perf_counter()

        return BenchmarkStageTime(
            sample_count=sample_count,
            acquisition_time_ms=round((t1 - t0) * 1000.0, 2),
            validation_time_ms=round((t2 - t1) * 1000.0, 2),
            intelligence_time_ms=round((t3 - t2) * 1000.0, 2),
            spatial_time_ms=round((t4 - t3) * 1000.0, 2),
            zones_time_ms=round((t5 - t4) * 1000.0, 2),
            recommendation_time_ms=round((t6 - t5) * 1000.0, 2),
            presentation_time_ms=round((t7 - t6) * 1000.0, 2),
            total_pipeline_time_ms=round((t7 - t0) * 1000.0, 2),
            label="HOST BENCHMARK",
        )

    @staticmethod
    def run_suite(sample_sizes: List[int] = None) -> List[BenchmarkStageTime]:
        """Run benchmark suite across multiple sample sizes."""
        if sample_sizes is None:
            sample_sizes = [25, 50, 100, 250, 500]

        results = []
        for count in sample_sizes:
            res = HostPerformanceBenchmark.run_benchmark_for_samples(count)
            results.append(res)
        return results

    @staticmethod
    def format_table(results: List[BenchmarkStageTime]) -> str:
        """Format benchmark results into a clean text summary table."""
        header = "Samples | Total Time (ms) | Spatial Time (ms) | Validation Time (ms) | Label\n"
        header += "-" * 75 + "\n"
        lines = []
        for r in results:
            lines.append(
                f"{r.sample_count:<7} | {r.total_pipeline_time_ms:<15} | {r.spatial_time_ms:<17} | {r.validation_time_ms:<20} | {r.label}"
            )
        return header + "\n".join(lines)
