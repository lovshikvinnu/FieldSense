"""UI data contract models for presentation layer."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple

from fieldsense.ai.models import AINarrative


@dataclass(frozen=True)
class FieldSummary:
    """Farmer-facing summary of field assessment."""
    field_name: str
    session_id: str
    sample_count: int
    valid_sample_count: int
    rejected_sample_count: int
    coverage_ratio: float
    overall_soil_health: float
    soil_health_status: str
    methodology_version: str = "0.1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldSummary":
        return cls(**data)


@dataclass(frozen=True)
class GPSStatus:
    """GPS status information."""
    available: bool
    latitude: Optional[float]
    longitude: Optional[float]
    status: str                                  # FIXED, NO_FIX
    mode: str = "SIMULATED"                      # SIMULATED, HARDWARE

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GPSStatus":
        return cls(**data)


@dataclass(frozen=True)
class SamplingStatus:
    """Field sampling progress status."""
    total_samples: int
    valid_samples: int
    rejected_samples: int
    expected_samples: int
    progress_ratio: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SamplingStatus":
        return cls(**data)


@dataclass(frozen=True)
class HealthSummary:
    """Aggregate health summary for dashboard."""
    score: float
    status: str
    nitrogen_score: float
    moisture_score: float
    carbon_readiness_score: float
    evidence_level: str = "LIMITED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HealthSummary":
        return cls(**data)


@dataclass(frozen=True)
class MapPoint:
    """Lightweight rendering map grid point."""
    latitude: float
    longitude: float
    value: Optional[float]
    support_distance: float
    status: str                                  # HEALTHY, MODERATE, POOR, UNAVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MapPoint":
        return cls(**data)


@dataclass(frozen=True)
class MapView:
    """UI map representation containing grid layers."""
    bounds: Dict[str, float]
    grid_by_layer: Dict[str, List[MapPoint]]
    active_layer: str = "soil_health"
    available_layers: List[str] = field(
        default_factory=lambda: ["soil_health", "nitrogen", "moisture", "carbon_readiness"]
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bounds": dict(self.bounds),
            "grid_by_layer": {k: [p.to_dict() for p in v] for k, v in self.grid_by_layer.items()},
            "active_layer": self.active_layer,
            "available_layers": list(self.available_layers),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MapView":
        grid_by_layer = {
            k: [MapPoint.from_dict(p) for p in v] for k, v in data.get("grid_by_layer", {}).items()
        }
        return cls(
            bounds=dict(data.get("bounds", {})),
            grid_by_layer=grid_by_layer,
            active_layer=data.get("active_layer", "soil_health"),
            available_layers=list(data.get("available_layers", [])),
        )


@dataclass(frozen=True)
class UIZone:
    """UI zone model for spatial management display."""
    zone_id: str
    status: str
    severity: str
    primary_issue: Optional[str]
    affected_parameters: List[str]
    confidence: str
    centroid: Tuple[float, float]
    area_estimate: float
    recommendation_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "status": self.status,
            "severity": self.severity,
            "primary_issue": self.primary_issue,
            "affected_parameters": list(self.affected_parameters),
            "confidence": self.confidence,
            "centroid": list(self.centroid),
            "area_estimate": self.area_estimate,
            "recommendation_count": self.recommendation_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UIZone":
        centroid_val = tuple(data["centroid"]) if isinstance(data.get("centroid"), (list, tuple)) else (0.0, 0.0)
        return cls(
            zone_id=data["zone_id"],
            status=data["status"],
            severity=data["severity"],
            primary_issue=data.get("primary_issue"),
            affected_parameters=list(data.get("affected_parameters", [])),
            confidence=data.get("confidence", "MEDIUM"),
            centroid=centroid_val,  # type: ignore
            area_estimate=float(data.get("area_estimate", 0.0)),
            recommendation_count=int(data.get("recommendation_count", 0)),
        )


@dataclass(frozen=True)
class UIRecommendation:
    """UI recommendation model."""
    recommendation_id: str
    zone_id: str
    category: str
    priority: str
    action: str
    reason: str
    confidence: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UIRecommendation":
        return cls(**data)


@dataclass(frozen=True)
class SystemStatus:
    """System operational status for local offline operation."""
    application_status: str = "READY"
    data_source: str = "VIRTUAL"                 # VIRTUAL, HARDWARE
    processing_status: str = "COMPLETE"
    offline_mode: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemStatus":
        return cls(**data)


@dataclass(frozen=True)
class UIFieldView:
    """Root UI Data Contract view model."""
    field: FieldSummary
    gps_status: GPSStatus
    sampling_status: SamplingStatus
    health_summary: HealthSummary
    map: MapView
    zones: List[UIZone]
    recommendations: List[UIRecommendation]
    system_status: SystemStatus
    # Optional passive explanation text from the AI layer. Defaults to None so
    # every existing caller, test, and serialized payload stays valid, and the
    # dashboard renders completely when no explanation backend is present.
    narrative: Optional[AINarrative] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field.to_dict(),
            "gps_status": self.gps_status.to_dict(),
            "sampling_status": self.sampling_status.to_dict(),
            "health_summary": self.health_summary.to_dict(),
            "map": self.map.to_dict(),
            "zones": [z.to_dict() for z in self.zones],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "system_status": self.system_status.to_dict(),
            "narrative": self.narrative.to_dict() if self.narrative else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UIFieldView":
        return cls(
            field=FieldSummary.from_dict(data["field"]),
            gps_status=GPSStatus.from_dict(data["gps_status"]),
            sampling_status=SamplingStatus.from_dict(data["sampling_status"]),
            health_summary=HealthSummary.from_dict(data["health_summary"]),
            map=MapView.from_dict(data["map"]),
            zones=[UIZone.from_dict(z) for z in data.get("zones", [])],
            recommendations=[UIRecommendation.from_dict(r) for r in data.get("recommendations", [])],
            system_status=SystemStatus.from_dict(data["system_status"]),
            narrative=AINarrative.from_dict(data["narrative"]) if data.get("narrative") else None,
        )
