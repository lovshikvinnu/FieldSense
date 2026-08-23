"""Unit tests for deterministic intelligence methodology implementation (Sprint 4B)."""

from datetime import datetime, timezone
import pytest

from fieldsense.domain import FieldSample, SampleSource, ValidationState
from fieldsense.intelligence import (
    CarbonReadinessResult,
    FieldIntelligenceEngine,
    FieldIntelligenceResult,
    IntelligenceConfig,
    MoistureResult,
    NitrogenResult,
    NormalizedSample,
    ParameterScore,
    SoilHealthResult,
    StandardNormalizer,
    adequacy_band_score,
    optimum_range_score,
    upper_limit_penalty_score,
)


def make_sample(
    n: float = 45.0,
    p: float = 20.0,
    k: float = 150.0,
    ph: float = 6.8,
    ec: float = 1.2,  # dS/m
    moisture: float = 30.0,
    temp: float = 25.0,
) -> FieldSample:
    """Helper factory for FieldSample."""
    return FieldSample(
        sample_id="SMP-METH-001",
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=n,
        phosphorus=p,
        potassium=k,
        ph=ph,
        ec=ec,
        moisture=moisture,
        temperature=temp,
        measurement_quality=0.95,
        source=SampleSource.VIRTUAL,
        validation_state=ValidationState.VALID,
    )


def test_unit_normalization_ec_conversion():
    normalizer = StandardNormalizer()
    sample = make_sample(ec=1500.0)  # 1500 µS/cm (exceeds validation when passed through engine, but raw normalizer test)

    norm = normalizer.normalize(sample)
    assert isinstance(norm, NormalizedSample)
    assert norm.nitrogen == 45.0
    assert norm.ec == 1.5  # 1500 / 1000 = 1.5 dS/m
    assert norm.ph == 6.8
    assert norm.moisture == 30.0

    # Ensure raw FieldSample remains unchanged
    assert sample.ec == 1500.0


def test_scoring_functions():
    cfg = IntelligenceConfig().scoring

    # pH Optimum range [6.0, 7.5]
    assert optimum_range_score(6.8, cfg.ph_band) == 1.0
    assert optimum_range_score(4.0, cfg.ph_band) == 0.0
    assert optimum_range_score(9.0, cfg.ph_band) == 0.0

    # EC Upper limit penalty (ideal <= 2.0, severe >= 4.0)
    assert upper_limit_penalty_score(1.0, cfg.ec_ideal_max, cfg.ec_severe_max) == 1.0
    assert upper_limit_penalty_score(3.0, cfg.ec_ideal_max, cfg.ec_severe_max) == 0.5
    assert upper_limit_penalty_score(5.0, cfg.ec_ideal_max, cfg.ec_severe_max) == 0.0

    # Nitrogen Adequacy band [30.0, 90.0]
    assert adequacy_band_score(50.0, cfg.n_band) == 1.0
    assert adequacy_band_score(0.0, cfg.n_band) == 0.0


def test_soil_health_deterministic_aggregation():
    engine = FieldIntelligenceEngine()
    sample = make_sample(
        n=50.0,    # Adequate -> score 1.0
        p=25.0,    # Adequate -> score 1.0
        k=150.0,   # Adequate -> score 1.0
        ph=6.8,    # Optimum -> score 1.0
        ec=1.0,    # 1.0 dS/m <= 2.0 -> score 1.0
        moisture=30.0, # Optimum -> score 1.0
    )
    result = engine.process(sample)

    assert isinstance(result.soil_health, SoilHealthResult)
    # All scores optimal -> Soil Health = 1.0
    assert result.soil_health.score == 1.0
    assert "Prototype" in result.soil_health.methodology_reference


def test_carbon_readiness_calculation_and_boundaries():
    engine = FieldIntelligenceEngine()
    sample = make_sample()
    result = engine.process(sample)

    cr = result.carbon_readiness
    assert isinstance(cr, CarbonReadinessResult)
    assert cr.decision_support_only is True
    assert cr.evidence_level == "LIMITED"
    assert "soil_organic_carbon" in cr.missing_indicators
    assert "bulk_density" in cr.missing_indicators
    assert "management_history" in cr.missing_indicators
    assert 0.0 <= cr.score <= 1.0


def test_determinism():
    engine = FieldIntelligenceEngine()
    sample = make_sample()

    res1 = engine.process(sample)
    res2 = engine.process(sample)

    assert res1.soil_health.score == res2.soil_health.score
    assert res1.carbon_readiness.score == res2.carbon_readiness.score
    assert [p.score for p in res1.parameter_scores] == [p.score for p in res2.parameter_scores]
