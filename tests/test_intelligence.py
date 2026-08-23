"""Unit tests for deterministic intelligence contracts, models, and boundaries."""

from datetime import datetime, timezone
import sys
import pytest

from fieldsense.domain import FieldSample, SampleSource, ValidationState
from fieldsense.intelligence import (
    CarbonReadinessConfig,
    CarbonReadinessResult,
    FieldIntelligenceEngine,
    FieldIntelligenceResult,
    IntelligenceConfig,
    MoistureResult,
    NitrogenResult,
    NormalizationConfig,
    NormalizedSample,
    ParameterScore,
    ScoringConfig,
    SoilHealthConfig,
    SoilHealthResult,
    ValidationResult,
    ValidationReason,
)


def make_valid_sample(sample_id: str = "SMP-INTEL-001") -> FieldSample:
    """Helper factory for valid FieldSample instances."""
    return FieldSample(
        sample_id=sample_id,
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=45.0,
        phosphorus=20.0,
        potassium=150.0,
        ph=6.5,
        ec=1.2,
        moisture=30.0,
        temperature=25.0,
        measurement_quality=0.95,
        source=SampleSource.VIRTUAL,
        validation_state=ValidationState.VALID,
    )


def test_normalized_sample_model():
    sample = make_valid_sample("SMP-NORM-1")
    norm = NormalizedSample(
        sample_id=sample.sample_id,
        nitrogen=sample.nitrogen,
        phosphorus=sample.phosphorus,
        potassium=sample.potassium,
        ph=sample.ph,
        ec=sample.ec,
        moisture=sample.moisture,
        temperature=sample.temperature,
    )

    assert norm.sample_id == "SMP-NORM-1"
    assert norm.nitrogen == 45.0
    assert norm.methodology_version == "0.1"

    # Verify raw FieldSample remains unmutated
    assert sample.nitrogen == 45.0
    with pytest.raises(AttributeError):
        sample.nitrogen = 99.0  # type: ignore


def test_parameter_score_range_enforcement():
    # Valid scores in [0.0, 1.0]
    ps = ParameterScore(parameter="nitrogen", score=0.75, interpretation="TBD")
    assert ps.score == 0.75

    # Out-of-bounds score < 0.0
    with pytest.raises(ValueError):
        ParameterScore(parameter="nitrogen", score=-0.1)

    # Out-of-bounds score > 1.0
    with pytest.raises(ValueError):
        ParameterScore(parameter="nitrogen", score=1.05)


def test_soil_health_result():
    ps = ParameterScore(parameter="ph", score=0.8)
    sh = SoilHealthResult(score=0.8, component_scores=[ps], methodology_reference="TBD")

    assert sh.score == 0.8
    assert len(sh.component_scores) == 1
    assert sh.component_scores[0].parameter == "ph"


def test_nitrogen_and_moisture_results():
    n_res = NitrogenResult(score=0.6, source_parameter="nitrogen")
    assert n_res.score == 0.6
    assert n_res.source_parameter == "nitrogen"

    m_res = MoistureResult(score=0.7, source_parameter="moisture")
    assert m_res.score == 0.7
    assert m_res.source_parameter == "moisture"


def test_carbon_readiness_scientific_boundary():
    ps = ParameterScore(parameter="ec", score=0.5)
    cr = CarbonReadinessResult(score=0.5, component_scores=[ps])

    assert cr.score == 0.5
    assert cr.decision_support_only is True

    # Attempting to override decision_support_only must raise ValueError
    with pytest.raises(ValueError):
        CarbonReadinessResult(score=0.5, decision_support_only=False)


def test_field_intelligence_result_aggregate():
    sample = make_valid_sample("SMP-INT-AGG")
    engine = FieldIntelligenceEngine()
    result = engine.process(sample)

    assert isinstance(result, FieldIntelligenceResult)
    assert result.sample_id == "SMP-INT-AGG"
    assert len(result.parameter_scores) == 7
    assert isinstance(result.soil_health, SoilHealthResult)
    assert isinstance(result.nitrogen, NitrogenResult)
    assert isinstance(result.moisture, MoistureResult)
    assert isinstance(result.carbon_readiness, CarbonReadinessResult)
    assert result.carbon_readiness.decision_support_only is True


def test_intelligence_engine_gatekeeper_rejection():
    engine = FieldIntelligenceEngine()

    # Reject sample with unusable quality (measurement_quality = 0.10)
    unusable_sample = FieldSample(
        sample_id="SMP-UNUSABLE",
        timestamp=datetime.now(timezone.utc),
        latitude=12.9716,
        longitude=77.5946,
        nitrogen=45.0,
        phosphorus=20.0,
        potassium=150.0,
        ph=6.5,
        ec=1.2,
        moisture=30.0,
        temperature=25.0,
        measurement_quality=0.10,
        source=SampleSource.VIRTUAL,
    )

    with pytest.raises(ValueError, match="not pipeline eligible"):
        engine.process(unusable_sample)

    # Test passing explicit rejected ValidationResult
    rej_val_res = ValidationResult(
        sample_id="SMP-EXPLICIT-REJ",
        state=ValidationState.REJECTED,
        pipeline_eligible=False,
        reasons=[ValidationReason.UNSTABLE_MEASUREMENT],
    )
    with pytest.raises(ValueError, match="not pipeline eligible"):
        engine.process(make_valid_sample("SMP-EXPLICIT-REJ"), validation_result=rej_val_res)


def test_batch_processing():
    engine = FieldIntelligenceEngine()
    samples = [
        make_valid_sample("SMP-BATCH-1"),
        make_valid_sample("SMP-BATCH-2"),
    ]
    results = engine.process_many(samples)

    assert len(results) == 2
    assert results[0].sample_id == "SMP-BATCH-1"
    assert results[1].sample_id == "SMP-BATCH-2"


def test_intelligence_config_versioning():
    cfg = IntelligenceConfig(
        methodology_version="0.1-draft",
        normalization=NormalizationConfig(methodology_version="0.1-draft"),
        scoring=ScoringConfig(methodology_version="0.1-draft"),
        soil_health=SoilHealthConfig(methodology_version="0.1-draft"),
        carbon_readiness=CarbonReadinessConfig(methodology_version="0.1-draft"),
    )
    engine = FieldIntelligenceEngine(config=cfg)
    res = engine.process(make_valid_sample())

    assert res.methodology_version == "0.1-draft"


def test_architecture_decoupling():
    # Verify intelligence module does not import hardware, UI, or AI modules
    intelligence_modules = [m for m in sys.modules if m.startswith("fieldsense.intelligence")]
    for mod_name in intelligence_modules:
        mod = sys.modules[mod_name]
        assert not hasattr(mod, "hardware")
        assert not hasattr(mod, "ui")
        assert not hasattr(mod, "ai")
