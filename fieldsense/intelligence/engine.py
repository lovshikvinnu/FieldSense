"""Deterministic FieldIntelligenceEngine implementation."""

from typing import List, Optional

from fieldsense.domain.models import FieldSample
from fieldsense.intelligence.validation.engine import ValidationEngine
from fieldsense.intelligence.validation.result import ValidationResult
from fieldsense.intelligence.normalization.normalizer import StandardNormalizer, Normalizer
from fieldsense.intelligence.normalization.sample import NormalizedSample
from fieldsense.intelligence.scoring.models import (
    ParameterScore,
    SoilHealthResult,
    NitrogenResult,
    MoistureResult,
    CarbonReadinessResult,
    FieldIntelligenceResult,
)
from fieldsense.intelligence.scoring.config import IntelligenceConfig
from fieldsense.intelligence.scoring.functions import (
    optimum_range_score,
    upper_limit_penalty_score,
    adequacy_band_score,
    interpret_score,
)


class FieldIntelligenceEngine:
    """High-level deterministic intelligence engine implementation.

    Enforces validation gatekeeper boundary and computes structured intelligence outputs.
    """

    def __init__(
        self,
        config: Optional[IntelligenceConfig] = None,
        normalizer: Optional[Normalizer] = None,
    ) -> None:
        """Initialize intelligence engine with versioned configuration."""
        self.config = config or IntelligenceConfig()
        self.normalizer = normalizer or StandardNormalizer()
        self._validator = ValidationEngine()

    def process(
        self,
        sample: FieldSample,
        validation_result: Optional[ValidationResult] = None,
    ) -> FieldIntelligenceResult:
        """Process a single validated FieldSample and compute FieldIntelligenceResult.

        Raises:
            ValueError: If sample is rejected / not pipeline eligible.
        """
        # Enforce validation gatekeeper boundary
        val_res = validation_result if validation_result is not None else self._validator.validate(sample)
        if not val_res.pipeline_eligible:
            raise ValueError(f"Sample '{sample.sample_id}' is not pipeline eligible (state: {val_res.state.value})")

        # Step 1: Unit Normalization (converts EC µS/cm -> dS/m)
        normalized = self.normalizer.normalize(sample)

        # Step 2: Parameter Scoring
        param_scores = self._score_parameters(normalized)

        # Step 3: Soil Health Aggregation
        soil_health = self._compute_soil_health(param_scores)

        # Step 4: Primary Intelligence Outputs (Nitrogen & Moisture)
        nitrogen_res = self._compute_nitrogen(param_scores)
        moisture_res = self._compute_moisture(param_scores)

        # Step 5: Carbon Readiness Decision-Support Proxy
        carbon_res = self._compute_carbon_readiness(param_scores)

        return FieldIntelligenceResult(
            sample_id=sample.sample_id,
            parameter_scores=param_scores,
            soil_health=soil_health,
            nitrogen=nitrogen_res,
            moisture=moisture_res,
            carbon_readiness=carbon_res,
            methodology_version=self.config.methodology_version,
        )

    def process_many(
        self,
        samples: List[FieldSample],
        validation_results: Optional[List[ValidationResult]] = None,
    ) -> List[FieldIntelligenceResult]:
        """Process a batch of FieldSample objects in sequence."""
        if validation_results is not None:
            if len(validation_results) != len(samples):
                raise ValueError("Mismatch between samples count and validation_results count")
            results = []
            for sample, val_res in zip(samples, validation_results):
                if val_res.pipeline_eligible:
                    results.append(self.process(sample, val_res))
            return results

        results = []
        for sample in samples:
            val_res = self._validator.validate(sample)
            if val_res.pipeline_eligible:
                results.append(self.process(sample, val_res))
        return results

    def _score_parameters(self, norm: NormalizedSample) -> List[ParameterScore]:
        """Compute per-parameter deterministic scores using configured reference bands."""
        cfg = self.config.scoring
        version = self.config.methodology_version

        # 1. Nitrogen (N mg/kg)
        n_score = round(adequacy_band_score(norm.nitrogen, cfg.n_band), 4)
        n_ps = ParameterScore(
            parameter="nitrogen",
            score=n_score,
            interpretation=interpret_score(n_score),
            methodology_version=version,
        )

        # 2. Phosphorus (P mg/kg)
        p_score = round(adequacy_band_score(norm.phosphorus, cfg.p_band), 4)
        p_ps = ParameterScore(
            parameter="phosphorus",
            score=p_score,
            interpretation=interpret_score(p_score),
            methodology_version=version,
        )

        # 3. Potassium (K mg/kg)
        k_score = round(adequacy_band_score(norm.potassium, cfg.k_band), 4)
        k_ps = ParameterScore(
            parameter="potassium",
            score=k_score,
            interpretation=interpret_score(k_score),
            methodology_version=version,
        )

        # 4. pH
        ph_score = round(optimum_range_score(norm.ph, cfg.ph_band), 4)
        ph_ps = ParameterScore(
            parameter="ph",
            score=ph_score,
            interpretation=interpret_score(ph_score),
            methodology_version=version,
        )

        # 5. Electrical Conductivity (EC dS/m)
        ec_score = round(upper_limit_penalty_score(norm.ec, cfg.ec_ideal_max, cfg.ec_severe_max), 4)
        ec_ps = ParameterScore(
            parameter="ec",
            score=ec_score,
            interpretation=interpret_score(ec_score),
            methodology_version=version,
        )

        # 6. Moisture (volumetric %)
        m_score = round(optimum_range_score(norm.moisture, cfg.moisture_band), 4)
        m_ps = ParameterScore(
            parameter="moisture",
            score=m_score,
            interpretation=interpret_score(m_score),
            methodology_version=version,
        )

        # 7. Temperature (°C) - Contextual parameter (score = 1.0)
        t_ps = ParameterScore(
            parameter="temperature",
            score=1.0,
            interpretation="CONTEXTUAL",
            methodology_version=version,
        )

        return [n_ps, p_ps, k_ps, ph_ps, ec_ps, m_ps, t_ps]

    def _compute_soil_health(self, param_scores: List[ParameterScore]) -> SoilHealthResult:
        """Compute Soil Health weighted aggregation."""
        weights = self.config.soil_health.weights
        score_map = {ps.parameter: ps.score for ps in param_scores}

        total_weight = sum(weights.values())
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(f"SoilHealth weights must sum to 1.0, got {total_weight}")

        sh_score = sum(weights[p] * score_map[p] for p in weights if p in score_map)
        sh_score = round(min(1.0, max(0.0, sh_score)), 4)

        return SoilHealthResult(
            score=sh_score,
            component_scores=param_scores,
            methodology_reference=f"FieldSense Prototype Methodology v{self.config.methodology_version}",
        )

    def _compute_nitrogen(self, param_scores: List[ParameterScore]) -> NitrogenResult:
        """Expose Nitrogen score directly from primary parameter scoring."""
        n_score = next((ps.score for ps in param_scores if ps.parameter == "nitrogen"), 0.0)
        return NitrogenResult(
            score=n_score,
            source_parameter="nitrogen",
            methodology_reference=f"FieldSense Prototype Nitrogen Reference Band v{self.config.methodology_version}",
        )

    def _compute_moisture(self, param_scores: List[ParameterScore]) -> MoistureResult:
        """Expose Moisture score directly from primary parameter scoring."""
        m_score = next((ps.score for ps in param_scores if ps.parameter == "moisture"), 0.0)
        return MoistureResult(
            score=m_score,
            source_parameter="moisture",
            methodology_reference=f"FieldSense Prototype Moisture Optimum Range v{self.config.methodology_version}",
        )

    def _compute_carbon_readiness(self, param_scores: List[ParameterScore]) -> CarbonReadinessResult:
        """Compute Carbon Readiness proxy index based on soil condition, moisture, and nutrient balance."""
        cfg = self.config.carbon_readiness
        score_map = {ps.parameter: ps.score for ps in param_scores}

        # 1. Nutrient Balance = (N + P + K) / 3
        n_score = score_map.get("nitrogen", 0.0)
        p_score = score_map.get("phosphorus", 0.0)
        k_score = score_map.get("potassium", 0.0)
        nutrient_balance = (n_score + p_score + k_score) / 3.0

        # 2. Soil Condition = weighted sum of non-carbon physical/chemical indicators normalized by weight sum (0.80)
        ph_score = score_map.get("ph", 0.0)
        ec_score = score_map.get("ec", 0.0)
        soil_condition = (0.20 * n_score + 0.15 * p_score + 0.15 * k_score + 0.20 * ph_score + 0.10 * ec_score) / 0.80

        # 3. Moisture Condition
        moisture_condition = score_map.get("moisture", 0.0)

        # 4. Carbon Readiness Index = 0.50 * Soil Condition + 0.25 * Moisture Condition + 0.25 * Nutrient Balance
        cr_score = (
            cfg.w_soil_condition * soil_condition
            + cfg.w_moisture_condition * moisture_condition
            + cfg.w_nutrient_balance * nutrient_balance
        )
        cr_score = round(min(1.0, max(0.0, cr_score)), 4)

        return CarbonReadinessResult(
            score=cr_score,
            component_scores=param_scores,
            methodology_reference=f"FieldSense Prototype Carbon Readiness Methodology v{self.config.methodology_version}",
            decision_support_only=True,
            evidence_level="LIMITED",
            missing_indicators=[
                "soil_organic_carbon",
                "bulk_density",
                "management_history",
            ],
        )
