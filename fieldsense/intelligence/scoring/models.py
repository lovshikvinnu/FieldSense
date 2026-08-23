"""Deterministic scoring and intelligence result data models."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass(frozen=True)
class ParameterScore:
    """Deterministic score for an individual soil measurement parameter.

    Scores are represented on an internal normalized scale from 0.0 to 1.0:
    0.0 = poorest condition according to scoring function
    1.0 = strongest condition according to scoring function
    """
    parameter: str
    score: float
    interpretation: Optional[str] = "TBD"
    methodology_version: str = "0.1"

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"ParameterScore for '{self.parameter}' must be within [0.0, 1.0], got {self.score}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParameterScore":
        return cls(**data)


@dataclass(frozen=True)
class SoilHealthResult:
    """Aggregate Soil Health score and component score traceability."""
    score: float
    component_scores: List[ParameterScore] = field(default_factory=list)
    methodology_reference: str = "FieldSense Prototype Methodology v0.1"

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"SoilHealthResult score must be within [0.0, 1.0], got {self.score}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "component_scores": [cs.to_dict() for cs in self.component_scores],
            "methodology_reference": self.methodology_reference,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SoilHealthResult":
        component_scores = [
            cs if isinstance(cs, ParameterScore) else ParameterScore.from_dict(cs)
            for cs in data.get("component_scores", [])
        ]
        return cls(
            score=data["score"],
            component_scores=component_scores,
            methodology_reference=data.get("methodology_reference", "FieldSense Prototype Methodology v0.1"),
        )


@dataclass(frozen=True)
class NitrogenResult:
    """Nitrogen intelligence score result."""
    score: float
    source_parameter: str = "nitrogen"
    methodology_reference: str = "FieldSense Prototype Nitrogen Reference Band v0.1"

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"NitrogenResult score must be within [0.0, 1.0], got {self.score}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NitrogenResult":
        return cls(**data)


@dataclass(frozen=True)
class MoistureResult:
    """Moisture intelligence score result."""
    score: float
    source_parameter: str = "moisture"
    methodology_reference: str = "FieldSense Prototype Moisture Optimum Range v0.1"

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"MoistureResult score must be within [0.0, 1.0], got {self.score}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MoistureResult":
        return cls(**data)


@dataclass(frozen=True)
class CarbonReadinessResult:
    """Carbon Readiness decision-support intelligence result.

    SCIENTIFIC BOUNDARY NOTICE:
    FieldSense does not measure Soil Organic Carbon (SOC), certify carbon credits,
    or replace accredited MRV systems. Carbon Readiness is an engineering decision-support signal.
    """
    score: float
    component_scores: List[ParameterScore] = field(default_factory=list)
    methodology_reference: str = "FieldSense Prototype Carbon Readiness Methodology v0.1"
    decision_support_only: bool = True
    evidence_level: str = "LIMITED"
    missing_indicators: List[str] = field(
        default_factory=lambda: [
            "soil_organic_carbon",
            "bulk_density",
            "management_history",
        ]
    )

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"CarbonReadinessResult score must be within [0.0, 1.0], got {self.score}")
        if not self.decision_support_only:
            raise ValueError("CarbonReadinessResult must maintain decision_support_only = True")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "component_scores": [cs.to_dict() for cs in self.component_scores],
            "methodology_reference": self.methodology_reference,
            "decision_support_only": self.decision_support_only,
            "evidence_level": self.evidence_level,
            "missing_indicators": list(self.missing_indicators),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CarbonReadinessResult":
        component_scores = [
            cs if isinstance(cs, ParameterScore) else ParameterScore.from_dict(cs)
            for cs in data.get("component_scores", [])
        ]
        return cls(
            score=data["score"],
            component_scores=component_scores,
            methodology_reference=data.get("methodology_reference", "FieldSense Prototype Carbon Readiness Methodology v0.1"),
            decision_support_only=data.get("decision_support_only", True),
            evidence_level=data.get("evidence_level", "LIMITED"),
            missing_indicators=data.get("missing_indicators", ["soil_organic_carbon", "bulk_density", "management_history"]),
        )


@dataclass(frozen=True)
class FieldIntelligenceResult:
    """Aggregate intelligence results for a single validated FieldSample."""
    sample_id: str
    parameter_scores: List[ParameterScore]
    soil_health: SoilHealthResult
    nitrogen: NitrogenResult
    moisture: MoistureResult
    carbon_readiness: CarbonReadinessResult
    methodology_version: str = "0.1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "parameter_scores": [ps.to_dict() for ps in self.parameter_scores],
            "soil_health": self.soil_health.to_dict(),
            "nitrogen": self.nitrogen.to_dict(),
            "moisture": self.moisture.to_dict(),
            "carbon_readiness": self.carbon_readiness.to_dict(),
            "methodology_version": self.methodology_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldIntelligenceResult":
        param_scores = [
            ps if isinstance(ps, ParameterScore) else ParameterScore.from_dict(ps)
            for ps in data.get("parameter_scores", [])
        ]
        sh = data["soil_health"]
        sh_obj = sh if isinstance(sh, SoilHealthResult) else SoilHealthResult.from_dict(sh)

        n = data["nitrogen"]
        n_obj = n if isinstance(n, NitrogenResult) else NitrogenResult.from_dict(n)

        m = data["moisture"]
        m_obj = m if isinstance(m, MoistureResult) else MoistureResult.from_dict(m)

        c = data["carbon_readiness"]
        c_obj = c if isinstance(c, CarbonReadinessResult) else CarbonReadinessResult.from_dict(c)

        return cls(
            sample_id=data["sample_id"],
            parameter_scores=param_scores,
            soil_health=sh_obj,
            nitrogen=n_obj,
            moisture=m_obj,
            carbon_readiness=c_obj,
            methodology_version=data.get("methodology_version", "0.1"),
        )
