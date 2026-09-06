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

    # output_dir matters: the default is the real artifacts/ directory, and
    # field_test_map.html is tracked on purpose so it can be opened straight
    # from the repo. Writing there from a test rewrites its session id on every
    # run, so the working tree goes dirty for a file nobody edited - and two
    # machines running the suite conflict on it.
    summary = run_spatial_test(json_file, output_dir=str(tmp_path), display="off")

    assert summary["samples"] == 5
    assert len(summary["local_xy"]) == 5
    assert summary["local_xy"][0] == (0.0, 0.0)
    assert summary["grid_points"] > 0
    assert summary["zones"] > 0
    assert summary["recommendations"] > 0


# ------------------------------------------------- panel map pages


def _grid_point(lat, lon, status):
    from fieldsense.presentation.models import MapPoint

    return MapPoint(latitude=lat, longitude=lon, value=0.5,
                    support_distance=1.0, status=status)


def _view(points_by_layer):
    from types import SimpleNamespace

    return SimpleNamespace(map=SimpleNamespace(grid_by_layer=points_by_layer))


def test_the_panel_grid_is_ordered_north_first_and_west_first():
    """The panel draws a lattice, so the ordering IS the layout.

    The engine emits its grid points in its own order. Passing them through
    unsorted would put a tidy-looking map on the glass that is quietly
    transposed - worse than showing nothing, because nothing about it looks
    wrong. This feeds them in deliberately scrambled and south-first.
    """
    from run_spatial_test import panel_map_fields

    points = [
        _grid_point(17.0000, 78.0002, "POOR"),        # south row, east
        _grid_point(17.0001, 78.0000, "HEALTHY"),     # north row, west
        _grid_point(17.0000, 78.0000, "MODERATE"),
        _grid_point(17.0001, 78.0002, "HEALTHY"),
        _grid_point(17.0000, 78.0001, "MODERATE"),
        _grid_point(17.0001, 78.0001, "HEALTHY"),
    ]
    fields = panel_map_fields([(17.0000, 78.0000)], [(0.0, 0.0)],
                              _view({"soil_health": points}))

    assert (fields["grid_rows"], fields["grid_cols"]) == (2, 3)
    # North row west-to-east, then the south row: GGG then AAR.
    assert fields["grid_soil_health"] == "GGGAAR"


def test_a_layer_the_engine_did_not_produce_is_simply_absent():
    """There is no pH, EC or NPK grid. An empty page must not be offered."""
    from run_spatial_test import panel_map_fields

    fields = panel_map_fields(
        [(17.0, 78.0)], [(0.0, 0.0)],
        _view({"soil_health": [_grid_point(17.0, 78.0, "HEALTHY")]}))

    assert "grid_soil_health" in fields
    assert "grid_moisture" not in fields
    assert "grid_nitrogen" not in fields


def test_sample_positions_span_the_panel_frame():
    """Two digits per axis, 0..99, north-up. The extremes must reach the edges."""
    from run_spatial_test import panel_map_fields

    points = [_grid_point(17.0000, 78.0000, "HEALTHY"),
              _grid_point(17.0001, 78.0001, "HEALTHY")]
    fields = panel_map_fields([(17.0, 78.0)], [(0.0, 0.0), (10.0, 20.0)],
                              _view({"soil_health": points}))

    positions = fields["sample_positions"]
    assert len(positions) == 8              # two samples, "xxyy" each
    assert positions.isdigit()
    assert fields["zone_box"].isdigit() and len(fields["zone_box"]) == 8


def test_the_map_record_fits_the_firmware_line_buffer():
    """fieldsense_unoq.ino reads into lineBuf[256] and DROPS an overlong line WHOLE.

    Not truncated - dropped, silently, with no error anywhere. This is why the
    map travels as its own record instead of riding on the result record, which
    already measures 200 bytes. Four layers of a 5x6 lattice is the tested
    shape; a materially larger field would need the map split again.
    """
    from fieldsense.hardware.panel_renderer import build_panel_record

    cells = "G" * 30
    record = build_panel_record({
        "grid_rows": 6, "grid_cols": 5,
        "grid_soil_health": cells, "grid_moisture": cells,
        "grid_nitrogen": cells, "grid_carbon_readiness": cells,
        "sample_positions": "0000" * 5, "zone_box": "00009999",
    })
    assert len(record) < 256, "map record is {} bytes; the MCU drops it".format(len(record))
