"""Zone detection models."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from fieldsense.spatial.grid import GridPoint


@dataclass(frozen=True)
class Zone:
    """Spatially connected field management zone."""
    zone_id: str
    status: str                                  # HEALTHY, MODERATE, POOR
    severity: str                                # LOW, MEDIUM, HIGH, CRITICAL
    affected_parameters: List[str]               # Parameters needing attention in this zone
    primary_issue: Optional[str]                 # Single parameter with largest deficiency
    confidence: str                              # HIGH, MEDIUM, LOW (spatial data support indicator)
    grid_points: List[GridPoint]                 # Grid points inside the zone
    sample_ids: List[str]                        # Contributing sample IDs
    centroid: Tuple[float, float]                # (latitude, longitude)
    area_estimate: float                         # Estimated zone area in m^2
    recommendation_reference: Optional[str] = "pending_recommendation_engine"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Zone to dictionary."""
        return {
            "zone_id": self.zone_id,
            "status": self.status,
            "severity": self.severity,
            "affected_parameters": list(self.affected_parameters),
            "primary_issue": self.primary_issue,
            "confidence": self.confidence,
            "grid_points": [gp.to_dict() for gp in self.grid_points],
            "sample_ids": list(self.sample_ids),
            "centroid": list(self.centroid),
            "area_estimate": self.area_estimate,
            "recommendation_reference": self.recommendation_reference,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Zone":
        """Deserialize dictionary to Zone."""
        grid_points = [GridPoint.from_dict(gp) for gp in data["grid_points"]]
        centroid_val = tuple(data["centroid"]) if isinstance(data.get("centroid"), (list, tuple)) else (0.0, 0.0)
        return cls(
            zone_id=data["zone_id"],
            status=data["status"],
            severity=data["severity"],
            affected_parameters=list(data.get("affected_parameters", [])),
            primary_issue=data.get("primary_issue"),
            confidence=data.get("confidence", "MEDIUM"),
            grid_points=grid_points,
            sample_ids=list(data.get("sample_ids", [])),
            centroid=centroid_val,  # type: ignore
            area_estimate=float(data.get("area_estimate", 0.0)),
            recommendation_reference=data.get("recommendation_reference", "pending_recommendation_engine"),
        )


@dataclass(frozen=True)
class ZoneDetectionResult:
    """Complete zone detection result containing spatial management zones."""
    zones: List[Zone]
    primary_layer: str = "soil_health"
    methodology_version: str = "0.1"
    coverage_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ZoneDetectionResult to dictionary."""
        return {
            "zones": [z.to_dict() for z in self.zones],
            "primary_layer": self.primary_layer,
            "methodology_version": self.methodology_version,
            "coverage_summary": dict(self.coverage_summary),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ZoneDetectionResult":
        """Deserialize dictionary to ZoneDetectionResult."""
        zones = [Zone.from_dict(z) for z in data.get("zones", [])]
        return cls(
            zones=zones,
            primary_layer=data.get("primary_layer", "soil_health"),
            methodology_version=data.get("methodology_version", "0.1"),
            coverage_summary=dict(data.get("coverage_summary", {})),
        )
