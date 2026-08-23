"""AI explanation layer data contracts.

These models are pure data structures. They contain no generation logic and no
dependency on any model runtime, so they remain importable when no local model
weights or inference binary are present on disk.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class NarrativeStatus(str, Enum):
    """Outcome status of a narrative generation attempt."""
    OK = "OK"                                    # Generated and passed NarrativeGuard
    FALLBACK_TEMPLATE = "FALLBACK_TEMPLATE"      # Deterministic template used instead of a model
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"      # No weights / binary present on disk
    GUARD_REJECTED = "GUARD_REJECTED"            # Model output violated the safety boundary
    TIMEOUT = "TIMEOUT"                          # Generation exceeded configured timeout
    GENERATION_FAILED = "GENERATION_FAILED"      # Backend raised or returned unusable output


class AIErrorCode(str, Enum):
    """Explicit error codes for the AI explanation layer."""
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    BINARY_NOT_FOUND = "BINARY_NOT_FOUND"
    GENERATION_TIMEOUT = "GENERATION_TIMEOUT"
    GENERATION_FAILED = "GENERATION_FAILED"
    GUARD_REJECTED = "GUARD_REJECTED"
    INVALID_CONTEXT = "INVALID_CONTEXT"


class AIError(Exception):
    """Base exception for the AI explanation layer.

    Raised only for programming / configuration faults. Routine runtime
    conditions (absent weights, timeout, guard rejection) are reported through
    AINarrative.generation_status rather than by raising.
    """

    def __init__(self, error_code: AIErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class ZoneContext:
    """Compact deterministic description of a single management zone.

    Built exclusively from already-computed Zone and Recommendation objects.
    No scoring, clustering, or agronomic decision is made here.
    """
    zone_id: str
    status: str                                  # HEALTHY, MODERATE, POOR
    severity: str                                # LOW, MEDIUM, HIGH, CRITICAL
    primary_issue: Optional[str]
    affected_parameters: List[str]
    confidence: str                              # HIGH, MEDIUM, LOW (spatial support)
    area_estimate: float                         # m^2
    action_ids: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    priorities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ZoneContext to dictionary."""
        return {
            "zone_id": self.zone_id,
            "status": self.status,
            "severity": self.severity,
            "primary_issue": self.primary_issue,
            "affected_parameters": list(self.affected_parameters),
            "confidence": self.confidence,
            "area_estimate": self.area_estimate,
            "action_ids": list(self.action_ids),
            "actions": list(self.actions),
            "categories": list(self.categories),
            "priorities": list(self.priorities),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ZoneContext":
        """Deserialize dictionary to ZoneContext."""
        return cls(
            zone_id=data["zone_id"],
            status=data["status"],
            severity=data["severity"],
            primary_issue=data.get("primary_issue"),
            affected_parameters=list(data.get("affected_parameters", [])),
            confidence=data.get("confidence", "MEDIUM"),
            area_estimate=float(data.get("area_estimate", 0.0)),
            action_ids=list(data.get("action_ids", [])),
            actions=list(data.get("actions", [])),
            categories=list(data.get("categories", [])),
            priorities=list(data.get("priorities", [])),
        )


@dataclass(frozen=True)
class ExplanationContext:
    """Bounded, serializable snapshot of deterministic results for explanation.

    This is the ONLY input a LocalLLMAdapter receives. It is deliberately small
    and free of raw grid rasters so the prompt stays inside a modest context
    window on constrained edge hardware.
    """
    field_name: str
    session_id: str
    overall_soil_health: float
    soil_health_status: str
    nitrogen_score: float
    moisture_score: float
    carbon_readiness_score: float
    total_samples: int
    valid_samples: int
    rejected_samples: int
    coverage_ratio: float
    zones: List[ZoneContext] = field(default_factory=list)
    evidence_level: str = "LIMITED"
    methodology_version: str = "0.1"
    data_source: str = "VIRTUAL"

    @property
    def zone_count(self) -> int:
        """Number of detected management zones."""
        return len(self.zones)

    def allowed_numbers(self) -> Set[float]:
        """Every numeric value a narrative is permitted to state.

        NarrativeGuard rejects any number in generated text that is not in this
        set. That is the primary defence against a model inventing a quantity
        such as a fertilizer dosage. Both the raw value and its percentage form
        are admitted, because the dashboard presents scores as percentages.
        """
        allowed: Set[float] = set()

        def admit(value: Optional[float]) -> None:
            if value is None:
                return
            val = float(value)
            allowed.add(val)
            allowed.add(float(round(val)))
            if 0.0 <= val <= 1.0:
                allowed.add(float(round(val * 100)))
                allowed.add(float(round(val * 100, 1)))

        admit(self.overall_soil_health)
        admit(self.nitrogen_score)
        admit(self.moisture_score)
        admit(self.carbon_readiness_score)
        admit(self.coverage_ratio)
        admit(self.total_samples)
        admit(self.valid_samples)
        admit(self.rejected_samples)
        admit(len(self.zones))

        status_counts: Dict[str, int] = {}
        for zone in self.zones:
            admit(zone.area_estimate)
            status_counts[zone.status] = status_counts.get(zone.status, 0) + 1
            admit(len(zone.actions))

        # Narratives may state how many zones fall in each status band.
        for count in status_counts.values():
            admit(count)

        # Small ordinals used for plain list phrasing.
        for small in range(0, 11):
            allowed.add(float(small))

        return allowed

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ExplanationContext to dictionary."""
        return {
            "field_name": self.field_name,
            "session_id": self.session_id,
            "overall_soil_health": self.overall_soil_health,
            "soil_health_status": self.soil_health_status,
            "nitrogen_score": self.nitrogen_score,
            "moisture_score": self.moisture_score,
            "carbon_readiness_score": self.carbon_readiness_score,
            "total_samples": self.total_samples,
            "valid_samples": self.valid_samples,
            "rejected_samples": self.rejected_samples,
            "coverage_ratio": self.coverage_ratio,
            "zones": [z.to_dict() for z in self.zones],
            "evidence_level": self.evidence_level,
            "methodology_version": self.methodology_version,
            "data_source": self.data_source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExplanationContext":
        """Deserialize dictionary to ExplanationContext."""
        return cls(
            field_name=data["field_name"],
            session_id=data["session_id"],
            overall_soil_health=float(data.get("overall_soil_health", 0.0)),
            soil_health_status=data.get("soil_health_status", "UNKNOWN"),
            nitrogen_score=float(data.get("nitrogen_score", 0.0)),
            moisture_score=float(data.get("moisture_score", 0.0)),
            carbon_readiness_score=float(data.get("carbon_readiness_score", 0.0)),
            total_samples=int(data.get("total_samples", 0)),
            valid_samples=int(data.get("valid_samples", 0)),
            rejected_samples=int(data.get("rejected_samples", 0)),
            coverage_ratio=float(data.get("coverage_ratio", 0.0)),
            zones=[ZoneContext.from_dict(z) for z in data.get("zones", [])],
            evidence_level=data.get("evidence_level", "LIMITED"),
            methodology_version=data.get("methodology_version", "0.1"),
            data_source=data.get("data_source", "VIRTUAL"),
        )


@dataclass(frozen=True)
class AINarrative:
    """Guarded natural-language explanation of deterministic results.

    This model is NON-NORMATIVE presentation text. It never carries a computed
    metric and can never alter one. It is always safe to discard: the dashboard
    renders completely when narrative is None.
    """
    field_summary: str
    zone_narratives: Dict[str, str] = field(default_factory=dict)
    generated_by: str = "MOCK_TEMPLATE_v1"
    generation_status: NarrativeStatus = NarrativeStatus.OK
    guard_violations: List[str] = field(default_factory=list)
    is_ai_generated: bool = False
    decision_support_only: bool = True
    evidence_level: str = "LIMITED"
    generation_time_ms: float = 0.0
    methodology_version: str = "0.1"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize AINarrative to dictionary."""
        status = self.generation_status
        return {
            "field_summary": self.field_summary,
            "zone_narratives": dict(self.zone_narratives),
            "generated_by": self.generated_by,
            "generation_status": status.value if isinstance(status, Enum) else status,
            "guard_violations": list(self.guard_violations),
            "is_ai_generated": self.is_ai_generated,
            "decision_support_only": self.decision_support_only,
            "evidence_level": self.evidence_level,
            "generation_time_ms": self.generation_time_ms,
            "methodology_version": self.methodology_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AINarrative":
        """Deserialize dictionary to AINarrative."""
        raw_status = data.get("generation_status", NarrativeStatus.OK)
        status = NarrativeStatus(raw_status) if isinstance(raw_status, str) else raw_status
        return cls(
            field_summary=data["field_summary"],
            zone_narratives=dict(data.get("zone_narratives", {})),
            generated_by=data.get("generated_by", "MOCK_TEMPLATE_v1"),
            generation_status=status,
            guard_violations=list(data.get("guard_violations", [])),
            is_ai_generated=bool(data.get("is_ai_generated", False)),
            decision_support_only=bool(data.get("decision_support_only", True)),
            evidence_level=data.get("evidence_level", "LIMITED"),
            generation_time_ms=float(data.get("generation_time_ms", 0.0)),
            methodology_version=data.get("methodology_version", "0.1"),
        )
