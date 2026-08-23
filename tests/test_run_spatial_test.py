"""Unit test for run_spatial_test integration script and coordinate projection bridge."""

import os
import pytest
from run_spatial_test import (
    latlon_to_local_cartesian,
    parse_hardware_json,
    run_spatial_test,
    generate_sample_hardware_json,
)


def test_latlon_to_local_cartesian_origin():
    """Verify point 1 is anchored to local Cartesian origin (0.0, 0.0)."""
    coords = [
        (12.971598, 77.594562),
        (12.971778, 77.594562),
        (12.971598, 77.594746),
    ]
    local_xy = latlon_to_local_cartesian(coords)

    assert len(local_xy) == 3
    # Origin check (Point 1)
    assert local_xy[0] == (0.0, 0.0)
    # Point 2 (~20m North)
    assert local_xy[1][0] == 0.0
    assert 19.0 <= local_xy[1][1] <= 21.0
    # Point 3 (~20m East)
    assert 19.0 <= local_xy[2][0] <= 21.0
    assert local_xy[2][1] == 0.0


def test_run_spatial_test_e2e(tmp_path):
    """Verify end-to-end processing of JSON hardware data through spatial, zone, and rec engines."""
    json_file = str(tmp_path / "test_field_data.json")
    generate_sample_hardware_json(json_file)

    assert os.path.exists(json_file)

    samples, intel_results = parse_hardware_json(json_file)
    assert len(samples) == 5
    assert len(intel_results) == 5

    summary = run_spatial_test(json_file)

    assert summary["samples"] == 5
    assert len(summary["local_xy"]) == 5
    assert summary["local_xy"][0] == (0.0, 0.0)
    assert summary["grid_points"] > 0
    assert summary["zones"] > 0
    assert summary["recommendations"] > 0
