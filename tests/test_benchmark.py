"""Performance benchmark test for FieldSense pipeline (Sprint 10)."""

from fieldsense.testing import HostPerformanceBenchmark, BenchmarkStageTime


def test_host_performance_benchmark():
    results = HostPerformanceBenchmark.run_suite(sample_sizes=[25, 50])
    assert len(results) == 2
    assert isinstance(results[0], BenchmarkStageTime)
    assert results[0].sample_count == 25
    assert results[0].total_pipeline_time_ms > 0.0
    assert results[0].label == "HOST BENCHMARK"

    table_text = HostPerformanceBenchmark.format_table(results)
    assert "HOST BENCHMARK" in table_text
    assert "Samples" in table_text
