"""Deterministic Zone Detection Engine implementation."""

import math
from typing import List, Dict, Tuple, Set, Optional

from fieldsense.spatial import SpatialFieldResult, GridPoint, GridValue
from .config import ZoneConfig
from .models import Zone, ZoneDetectionResult


class ZoneDetectionEngine:
    """Deterministic Zone Detection Engine.

    Transforms continuous SpatialFieldResult maps into spatially connected management zones.
    Does NOT modify raw sensor values, interpolation, or recommendations.
    """

    def __init__(self, config: Optional[ZoneConfig] = None) -> None:
        """Initialize ZoneDetectionEngine with configuration."""
        self.config = config or ZoneConfig()

    def process(self, spatial_result: SpatialFieldResult) -> ZoneDetectionResult:
        """Process a SpatialFieldResult and generate ZoneDetectionResult.

        Args:
            spatial_result: Input spatial field representation.

        Returns:
            ZoneDetectionResult containing spatially connected Zone objects.
        """
        primary_layer_id = self.config.primary_layer
        if primary_layer_id not in spatial_result.layers:
            # Fallback to first available layer if primary layer not found
            primary_layer_id = list(spatial_result.layers.keys())[0]

        primary_layer = spatial_result.layers[primary_layer_id]
        grid_points = spatial_result.grid_points
        grid_values = primary_layer.grid_values

        if not grid_points or not grid_values:
            return ZoneDetectionResult(
                zones=[],
                primary_layer=primary_layer_id,
                methodology_version=self.config.methodology_version,
                coverage_summary={"zone_count": 0},
            )

        # 1. Map GridPoints to 2D Grid Matrix for 4-neighbor connectivity
        x_coords = sorted(list(set(gp.x for gp in grid_points)))
        y_coords = sorted(list(set(gp.y for gp in grid_points)))
        x_idx_map = {x: i for i, x in enumerate(x_coords)}
        y_idx_map = {y: j for j, y in enumerate(y_coords)}

        rows, cols = len(y_coords), len(x_coords)
        grid_matrix: List[List[Optional[int]]] = [[None for _ in range(cols)] for _ in range(rows)]

        for idx, (gp, gv) in enumerate(zip(grid_points, grid_values)):
            if gv.value is not None:
                r = y_idx_map[gp.y]
                c = x_idx_map[gp.x]
                grid_matrix[r][c] = idx

        # 2. Classify Grid Cells by Status (HEALTHY, MODERATE, POOR)
        status_matrix: List[List[Optional[str]]] = [[None for _ in range(cols)] for _ in range(rows)]
        for r in range(rows):
            for c in range(cols):
                idx = grid_matrix[r][c]
                if idx is not None:
                    val = grid_values[idx].value
                    if val is not None:
                        status_matrix[r][c] = self._classify_status(val)

        # 3. 4-Neighbor Connected-Component Detection
        visited: Set[Tuple[int, int]] = set()
        candidate_components: List[List[Tuple[int, int]]] = []

        for r in range(rows):
            for c in range(cols):
                if (r, c) not in visited and status_matrix[r][c] is not None:
                    component = self._bfs_connected_component(r, c, status_matrix, visited, rows, cols)
                    if component:
                        candidate_components.append(component)

        # 4. Minimum Zone Size Filtering & Merging
        merged_components = self._merge_small_components(candidate_components, status_matrix, rows, cols)

        # 5. Calculate Grid Cell Area Approximation
        grid_spacing = 10.0
        if len(x_coords) > 1:
            grid_spacing = abs(x_coords[1] - x_coords[0])

        grid_cell_area = grid_spacing * grid_spacing

        # 6. Build Zone objects
        zones: List[Zone] = []
        for z_idx, comp_cells in enumerate(merged_components, start=1):
            zone_point_indices = [grid_matrix[r][c] for r, c in comp_cells if grid_matrix[r][c] is not None]
            zone_grid_points = [grid_points[idx] for idx in zone_point_indices]
            zone_primary_values = [grid_values[idx].value for idx in zone_point_indices if grid_values[idx].value is not None]

            mean_primary_score = sum(zone_primary_values) / len(zone_primary_values) if zone_primary_values else 0.5
            zone_status = self._classify_status(mean_primary_score)
            zone_severity = self._classify_severity(mean_primary_score)

            # Centroid (lat, lon) calculation
            centroid_lat = sum(gp.latitude for gp in zone_grid_points) / len(zone_grid_points) if zone_grid_points else 0.0
            centroid_lon = sum(gp.longitude for gp in zone_grid_points) / len(zone_grid_points) if zone_grid_points else 0.0
            centroid = (round(centroid_lat, 6), round(centroid_lon, 6))

            # Area estimate in m^2
            area_est = round(len(comp_cells) * grid_cell_area, 2)

            # Multi-parameter enrichment and primary issue selection
            affected_params, primary_issue = self._enrich_zone_parameters(zone_point_indices, spatial_result)

            # Confidence spatial support assessment
            confidence = self._assess_confidence(zone_point_indices, primary_layer.grid_values)

            zone = Zone(
                zone_id=f"ZONE-{z_idx:02d}",
                status=zone_status,
                severity=zone_severity,
                affected_parameters=affected_params,
                primary_issue=primary_issue,
                confidence=confidence,
                grid_points=zone_grid_points,
                sample_ids=list(spatial_result.source_sample_ids),
                centroid=centroid,
                area_estimate=area_est,
                recommendation_reference="pending_recommendation_engine",
            )
            zones.append(zone)

        return ZoneDetectionResult(
            zones=zones,
            primary_layer=primary_layer_id,
            methodology_version=self.config.methodology_version,
            coverage_summary={
                "zone_count": len(zones),
                "total_zone_cells": sum(len(z.grid_points) for z in zones),
            },
        )

    def _classify_status(self, score: float) -> str:
        """Classify score into status category (HEALTHY, MODERATE, POOR)."""
        if score >= self.config.healthy_threshold:
            return "HEALTHY"
        elif score >= self.config.moderate_threshold:
            return "MODERATE"
        else:
            return "POOR"

    def _classify_severity(self, score: float) -> str:
        """Classify score into severity level (LOW, MEDIUM, HIGH, CRITICAL)."""
        if score < 0.25:
            return "CRITICAL"
        elif score < 0.40:
            return "HIGH"
        elif score < 0.70:
            return "MEDIUM"
        else:
            return "LOW"

    def _bfs_connected_component(
        self,
        start_r: int,
        start_c: int,
        status_matrix: List[List[Optional[str]]],
        visited: Set[Tuple[int, int]],
        rows: int,
        cols: int,
    ) -> List[Tuple[int, int]]:
        """Find 4-neighbor connected component with identical status."""
        target_status = status_matrix[start_r][start_c]
        if target_status is None:
            return []

        queue = [(start_r, start_c)]
        visited.add((start_r, start_c))
        component = []

        # 4-neighbor directions: Up, Down, Left, Right
        neighbors_4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        while queue:
            curr_r, curr_c = queue.pop(0)
            component.append((curr_r, curr_c))

            for dr, dc in neighbors_4:
                nr, nc = curr_r + dr, curr_c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    if (nr, nc) not in visited and status_matrix[nr][nc] == target_status:
                        visited.add((nr, nc))
                        queue.append((nr, nc))

        return component

    def _merge_small_components(
        self,
        components: List[List[Tuple[int, int]]],
        status_matrix: List[List[Optional[str]]],
        rows: int,
        cols: int,
    ) -> List[List[Tuple[int, int]]]:
        """Merge candidate components smaller than minimum_zone_cells into adjacent components."""
        if not components:
            return []

        min_cells = self.config.minimum_zone_cells
        valid_comps = [c for c in components if len(c) >= min_cells]
        small_comps = [c for c in components if len(c) < min_cells]

        if not valid_comps:
            # If all components are small, combine them into one zone to avoid deleting data
            combined = []
            for c in components:
                combined.extend(c)
            return [combined]

        # Merge small components into nearest valid component
        neighbors_4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for small in small_comps:
            # Find adjacent valid component
            merged = False
            for r, c in small:
                for dr, dc in neighbors_4:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols:
                        for target in valid_comps:
                            if (nr, nc) in target:
                                target.extend(small)
                                merged = True
                                break
                        if merged:
                            break
                if merged:
                    break

            if not merged:
                # Fallback: attach to first valid component
                valid_comps[0].extend(small)

        return valid_comps

    def _enrich_zone_parameters(
        self,
        point_indices: List[int],
        spatial_result: SpatialFieldResult,
    ) -> Tuple[List[str], Optional[str]]:
        """Enrich zone with affected parameters and select primary issue using deterministic tie-breaking."""
        affected_params: List[str] = []
        deficiencies: Dict[str, float] = {}

        for layer_id, layer in spatial_result.layers.items():
            layer_vals = [layer.grid_values[idx].value for idx in point_indices if idx < len(layer.grid_values) and layer.grid_values[idx].value is not None]
            if layer_vals:
                avg_score = sum(layer_vals) / len(layer_vals)
                if avg_score < self.config.concern_threshold:
                    affected_params.append(layer_id)
                    deficiencies[layer_id] = 1.0 - avg_score

        if not affected_params:
            return [], None

        # Select primary issue with largest deficiency and deterministic tie-breaking
        priority_list = self.config.parameter_priority

        def tie_break_key(param_name: str) -> Tuple[float, int]:
            deficiency = deficiencies.get(param_name, 0.0)
            priority_idx = priority_list.index(param_name) if param_name in priority_list else 999
            # Max deficiency (-deficiency), then min priority_idx
            return (-deficiency, priority_idx)

        sorted_affected = sorted(affected_params, key=tie_break_key)
        primary_issue = sorted_affected[0]

        return affected_params, primary_issue

    def _assess_confidence(self, point_indices: List[int], grid_values: List[GridValue]) -> str:
        """Assess zone spatial data support confidence."""
        distances = [grid_values[idx].nearest_sample_distance for idx in point_indices if idx < len(grid_values)]
        if not distances:
            return "LOW"

        avg_dist = sum(distances) / len(distances)
        if avg_dist < 25.0:
            return "HIGH"
        elif avg_dist < 50.0:
            return "MEDIUM"
        else:
            return "LOW"
