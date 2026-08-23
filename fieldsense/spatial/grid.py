"""Spatial grid, layers, coverage, and result models."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from .bounds import FieldBounds


@dataclass(frozen=True)
class GridPoint:
    """Individual grid cell node coordinate representation."""
    x: float
    y: float
    latitude: float
    longitude: float

    def to_dict(self) -> Dict[str, Any]:
        """Serialize GridPoint to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GridPoint":
        """Deserialize dict to GridPoint."""
        return cls(**data)


@dataclass(frozen=True)
class GridValue:
    """Interpolated value and support metadata for a grid point."""
    value: Optional[float]
    nearest_sample_distance: float
    supporting_sample_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Serialize GridValue to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GridValue":
        """Deserialize dict to GridValue."""
        return cls(**data)


@dataclass(frozen=True)
class SpatialLayer:
    """Single interpolated map layer (e.g. soil_health, nitrogen, moisture, carbon_readiness)."""
    layer_id: str
    layer_name: str
    units: str
    grid_values: List[GridValue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SpatialLayer to dict."""
        return {
            "layer_id": self.layer_id,
            "layer_name": self.layer_name,
            "units": self.units,
            "grid_values": [gv.to_dict() for gv in self.grid_values],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpatialLayer":
        """Deserialize dict to SpatialLayer."""
        values = [GridValue.from_dict(v) for v in data.get("grid_values", [])]
        return cls(
            layer_id=data["layer_id"],
            layer_name=data["layer_name"],
            units=data["units"],
            grid_values=values,
        )


@dataclass(frozen=True)
class SpatialCoverage:
    """Spatial coverage metrics for the field representation."""
    sample_count: int
    grid_point_count: int
    covered_area_estimate: float  # Estimated field area in m^2
    coverage_ratio: float         # Ratio of valid interpolated grid points

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SpatialCoverage to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpatialCoverage":
        """Deserialize dict to SpatialCoverage."""
        return cls(**data)


@dataclass(frozen=True)
class SpatialFieldResult:
    """Complete spatial representation output of a field."""
    bounds: FieldBounds
    grid_points: List[GridPoint]
    layers: Dict[str, SpatialLayer]
    source_sample_ids: List[str]
    coverage: SpatialCoverage
    methodology_version: str = "0.1"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SpatialFieldResult to dictionary."""
        return {
            "bounds": self.bounds.to_dict(),
            "grid_points": [gp.to_dict() for gp in self.grid_points],
            "layers": {lid: layer.to_dict() for lid, layer in self.layers.items()},
            "source_sample_ids": list(self.source_sample_ids),
            "coverage": self.coverage.to_dict(),
            "methodology_version": self.methodology_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpatialFieldResult":
        """Deserialize dictionary to SpatialFieldResult."""
        bounds = FieldBounds.from_dict(data["bounds"])
        grid_points = [GridPoint.from_dict(gp) for gp in data["grid_points"]]
        layers = {lid: SpatialLayer.from_dict(l_data) for lid, l_data in data.get("layers", {}).items()}
        coverage = SpatialCoverage.from_dict(data["coverage"])
        return cls(
            bounds=bounds,
            grid_points=grid_points,
            layers=layers,
            source_sample_ids=list(data.get("source_sample_ids", [])),
            coverage=coverage,
            methodology_version=data.get("methodology_version", "0.1"),
        )
