"""Spatial Intelligence Engine implementation."""

import math
from typing import List, Dict, Optional, Tuple

from fieldsense.domain.models import FieldSample
from fieldsense.intelligence.scoring.models import FieldIntelligenceResult
from fieldsense.intelligence.validation.engine import ValidationEngine

from .bounds import FieldBounds, LocalCoordinateConverter
from .config import SpatialConfig
from .grid import (
    GridPoint,
    GridValue,
    SpatialCoverage,
    SpatialFieldResult,
    SpatialLayer,
)
from .idw import IDWInterpolator


class SpatialEngine:
    """Deterministic Spatial Engine for field representation and interpolation.

    Consumes validated FieldSample GPS coordinates and FieldIntelligenceResult objects
    to produce a spatial field representation.
    """

    def __init__(self, config: Optional[SpatialConfig] = None) -> None:
        """Initialize spatial engine with configuration."""
        self.config = config or SpatialConfig()
        self._validator = ValidationEngine()

    def process(
        self,
        intelligence_results: List[FieldIntelligenceResult],
        samples: List[FieldSample],
    ) -> SpatialFieldResult:
        """Process intelligence results and samples to build a SpatialFieldResult.

        Args:
            intelligence_results: List of FieldIntelligenceResult objects.
            samples: List of corresponding FieldSample objects.

        Returns:
            SpatialFieldResult containing bounds, grid points, interpolated layers, and coverage.
        """
        # 1. Match and filter for pipeline-eligible samples only
        intel_map = {res.sample_id: res for res in intelligence_results}
        valid_pairs: List[Tuple[FieldSample, FieldIntelligenceResult]] = []

        for sample in samples:
            val_res = self._validator.validate(sample)
            if val_res.pipeline_eligible and sample.sample_id in intel_map:
                valid_pairs.append((sample, intel_map[sample.sample_id]))

        if not valid_pairs:
            raise ValueError("Cannot compute spatial representation: 0 eligible samples provided")

        valid_samples = [pair[0] for pair in valid_pairs]
        valid_intels = [pair[1] for pair in valid_pairs]
        source_ids = [s.sample_id for s in valid_samples]

        # 2. Derive Field Bounds
        lats = [s.latitude for s in valid_samples]
        lons = [s.longitude for s in valid_samples]
        bounds = FieldBounds(
            min_latitude=min(lats),
            max_latitude=max(lats),
            min_longitude=min(lons),
            max_longitude=max(lons),
        )

        # 3. Setup Local Coordinate System centered at centroid
        converter = LocalCoordinateConverter(bounds.center_latitude, bounds.center_longitude)
        local_samples: List[Tuple[float, float, FieldSample, FieldIntelligenceResult]] = []
        for s, intel in valid_pairs:
            lx, ly = converter.to_local(s.latitude, s.longitude)
            local_samples.append((lx, ly, s, intel))

        # 4. Construct Regular Grid
        grid_points, local_grid_coords = self._generate_grid(bounds, converter)

        # 5. Check Minimum Sample Count Requirement for Interpolation
        can_interpolate = len(valid_samples) >= self.config.minimum_samples_for_interpolation
        interpolator = IDWInterpolator(
            power=self.config.idw_power,
            max_support_distance=self.config.max_support_distance_meters,
        )

        layers: Dict[str, SpatialLayer] = {}
        layer_definitions = [
            ("soil_health", "Soil Health Map", "score [0-1]", lambda intel: intel.soil_health.score),
            ("nitrogen", "Nitrogen Index Map", "score [0-1]", lambda intel: intel.nitrogen.score),
            ("moisture", "Moisture Index Map", "score [0-1]", lambda intel: intel.moisture.score),
            ("carbon_readiness", "Carbon Readiness Index Map", "score [0-1]", lambda intel: intel.carbon_readiness.score),
        ]

        for layer_id, layer_name, units, extractor in layer_definitions:
            grid_values: List[GridValue] = []
            if can_interpolate:
                sample_tuples = [(lx, ly, extractor(intel)) for lx, ly, _, intel in local_samples]
                for gx, gy in local_grid_coords:
                    gv = interpolator.interpolate_point(gx, gy, sample_tuples)
                    grid_values.append(gv)
            else:
                # Insufficient data for interpolation: return un-interpolated grid placeholders
                for gx, gy in local_grid_coords:
                    grid_values.append(GridValue(value=None, nearest_sample_distance=0.0, supporting_sample_count=0))

            layers[layer_id] = SpatialLayer(
                layer_id=layer_id,
                layer_name=layer_name,
                units=units,
                grid_values=grid_values,
            )

        # 6. Calculate Spatial Coverage
        local_x = [lx for lx, _, _, _ in local_samples]
        local_y = [ly for _, ly, _, _ in local_samples]
        field_width = max(local_x) - min(local_x) if len(local_x) > 1 else 0.0
        field_height = max(local_y) - min(local_y) if len(local_y) > 1 else 0.0
        covered_area = round(max(1.0, field_width * field_height), 2)

        valid_interpolated_points = 0
        if can_interpolate and "soil_health" in layers:
            valid_interpolated_points = sum(1 for gv in layers["soil_health"].grid_values if gv.value is not None)

        total_grid = len(grid_points)
        cov_ratio = round(valid_interpolated_points / total_grid, 4) if total_grid > 0 else 0.0

        coverage = SpatialCoverage(
            sample_count=len(valid_samples),
            grid_point_count=total_grid,
            covered_area_estimate=covered_area,
            coverage_ratio=cov_ratio,
        )

        return SpatialFieldResult(
            bounds=bounds,
            grid_points=grid_points,
            layers=layers,
            source_sample_ids=source_ids,
            coverage=coverage,
            methodology_version=self.config.methodology_version,
        )

    def _generate_grid(
        self, bounds: FieldBounds, converter: LocalCoordinateConverter
    ) -> Tuple[List[GridPoint], List[Tuple[float, float]]]:
        """Generate regular grid points inside field bounds."""
        min_x, min_y = converter.to_local(bounds.min_latitude, bounds.min_longitude)
        max_x, max_y = converter.to_local(bounds.max_latitude, bounds.max_longitude)

        # Ensure min <= max
        start_x, end_x = min(min_x, max_x), max(min_x, max_x)
        start_y, end_y = min(min_y, max_y), max(min_y, max_y)

        spacing = self.config.grid_spacing_meters

        # If min and max are identical (e.g. single point), add small margin
        if abs(end_x - start_x) < 1.0:
            start_x -= spacing
            end_x += spacing
        if abs(end_y - start_y) < 1.0:
            start_y -= spacing
            end_y += spacing

        grid_points: List[GridPoint] = []
        local_coords: List[Tuple[float, float]] = []

        curr_y = start_y
        while curr_y <= end_y + 1e-6:
            curr_x = start_x
            while curr_x <= end_x + 1e-6:
                lat, lon = converter.to_gps(curr_x, curr_y)
                gp = GridPoint(
                    x=round(curr_x, 2),
                    y=round(curr_y, 2),
                    latitude=lat,
                    longitude=lon,
                )
                grid_points.append(gp)
                local_coords.append((curr_x, curr_y))
                curr_x += spacing
            curr_y += spacing

        return grid_points, local_coords
