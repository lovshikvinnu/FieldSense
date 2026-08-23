"""Golden dataset framework and scenario definitions for system validation."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from fieldsense.domain.models import FieldSample, FieldSession, SampleSource, ValidationState
from fieldsense.input import FieldScenario, VirtualSensorAdapter


@dataclass(frozen=True)
class GoldenScenario:
    """Deterministic versioned golden dataset scenario model."""
    name: str
    description: str
    seed: int
    num_samples: int
    expected_valid_count: int
    expected_rejected_count: int
    expected_primary_status: str                 # HEALTHY, MODERATE, POOR
    custom_samples: Optional[List[FieldSample]] = None
    version: str = "1.0"


class GoldenDatasetRegistry:
    """Registry providing standard, versioned golden datasets for regression testing and competition demonstration."""

    @staticmethod
    def get_scenario(scenario_name: str) -> GoldenScenario:
        """Retrieve a registered GoldenScenario by name."""
        scenarios = GoldenDatasetRegistry.get_all_scenarios()
        if scenario_name not in scenarios:
            raise KeyError(f"Unknown golden scenario: {scenario_name}")
        return scenarios[scenario_name]

    @staticmethod
    def get_all_scenarios() -> Dict[str, GoldenScenario]:
        """Get dictionary of all registered golden scenario definitions."""
        return {
            "competition_demo_v1": GoldenScenario(
                name="competition_demo_v1",
                description="Competition demonstration dataset featuring realistic spatial variation (healthy, moderate, poor sectors) and 1 rejected sample.",
                seed=2026,
                num_samples=25,
                expected_valid_count=24,
                expected_rejected_count=1,
                expected_primary_status="MODERATE",
            ),
            "healthy_field": GoldenScenario(
                name="healthy_field",
                description="Field dataset where all parameters represent optimal/healthy conditions.",
                seed=101,
                num_samples=25,
                expected_valid_count=25,
                expected_rejected_count=0,
                expected_primary_status="HEALTHY",
            ),
            "nutrient_deficient_field": GoldenScenario(
                name="nutrient_deficient_field",
                description="Field dataset with severe nitrogen deficiency in one quadrant.",
                seed=102,
                num_samples=25,
                expected_valid_count=25,
                expected_rejected_count=0,
                expected_primary_status="POOR",
            ),
            "moisture_deficient_field": GoldenScenario(
                name="moisture_deficient_field",
                description="Field dataset with low volumetric soil moisture in one region.",
                seed=103,
                num_samples=25,
                expected_valid_count=25,
                expected_rejected_count=0,
                expected_primary_status="MODERATE",
            ),
            "mixed_field": GoldenScenario(
                name="mixed_field",
                description="Field dataset containing distinct healthy, moderate, and poor zones.",
                seed=104,
                num_samples=25,
                expected_valid_count=25,
                expected_rejected_count=0,
                expected_primary_status="MODERATE",
            ),
            "spatial_gradient_field": GoldenScenario(
                name="spatial_gradient_field",
                description="Field dataset with a smooth linear spatial transition from high to low health.",
                seed=105,
                num_samples=25,
                expected_valid_count=25,
                expected_rejected_count=0,
                expected_primary_status="MODERATE",
            ),
            "outlier_field": GoldenScenario(
                name="outlier_field",
                description="Field dataset containing one extreme outlier measurement.",
                seed=106,
                num_samples=25,
                expected_valid_count=25,
                expected_rejected_count=0,
                expected_primary_status="HEALTHY",
            ),
            "unstable_field": GoldenScenario(
                name="unstable_field",
                description="Field dataset containing one unstable measurement rejected during validation.",
                seed=42,
                num_samples=25,
                expected_valid_count=24,
                expected_rejected_count=1,
                expected_primary_status="MODERATE",
            ),
        }

    @staticmethod
    def load_session(scenario: GoldenScenario) -> FieldSession:
        """Instantiate a FieldSession for the given GoldenScenario."""
        session = FieldSession(
            session_id=f"SES-GOLDEN-{scenario.name.upper()}",
            field_name=f"Golden {scenario.name.replace('_', ' ').title()}",
            created_at="2026-08-09T15:00:00Z",
        )

        if scenario.custom_samples:
            for s in scenario.custom_samples:
                session.add_sample(s)
            return session

        # Generate scenario via VirtualSensorAdapter or custom scenario logic
        if scenario.name in ["unstable_field", "competition_demo_v1"]:
            adapter = VirtualSensorAdapter(seed=scenario.seed, num_samples=scenario.num_samples, scenario=FieldScenario.WITH_UNSTABLE)
        elif scenario.name == "outlier_field":
            adapter = VirtualSensorAdapter(seed=scenario.seed, num_samples=scenario.num_samples, scenario=FieldScenario.WITH_OUTLIER)
        else:
            adapter = VirtualSensorAdapter(seed=scenario.seed, num_samples=scenario.num_samples, scenario=FieldScenario.NORMAL)

        raw_session = adapter.collect_session(session_id=session.session_id, field_name=session.field_name)

        # Modify parameter values for specific nutrient/moisture/competition demo scenarios
        samples = list(raw_session.samples)
        if scenario.name == "competition_demo_v1":
            # SW quadrant: Poor (low N, P, K, pH 4.2, EC 4.5, Moisture 10%)
            # Center: Moderate (medium N 25 mg/kg, moisture 22%)
            # NE: Healthy (N 50 mg/kg, moisture 32%)
            for i, s in enumerate(samples):
                if i < 24:
                    if i < 8:
                        samples[i] = FieldSample(
                            sample_id=s.sample_id, timestamp=s.timestamp, latitude=s.latitude, longitude=s.longitude,
                            nitrogen=5.0, phosphorus=5.0, potassium=20.0, ph=4.2, ec=4.5, moisture=10.0,
                            temperature=s.temperature, source=s.source, validation_state=s.validation_state, measurement_quality=s.measurement_quality
                        )
                    elif i < 16:
                        samples[i] = FieldSample(
                            sample_id=s.sample_id, timestamp=s.timestamp, latitude=s.latitude, longitude=s.longitude,
                            nitrogen=25.0, phosphorus=15.0, potassium=100.0, ph=5.8, ec=1.8, moisture=22.0,
                            temperature=s.temperature, source=s.source, validation_state=s.validation_state, measurement_quality=s.measurement_quality
                        )
                    else:
                        samples[i] = FieldSample(
                            sample_id=s.sample_id, timestamp=s.timestamp, latitude=s.latitude, longitude=s.longitude,
                            nitrogen=50.0, phosphorus=25.0, potassium=150.0, ph=6.8, ec=1.2, moisture=32.0,
                            temperature=s.temperature, source=s.source, validation_state=s.validation_state, measurement_quality=s.measurement_quality
                        )

        elif scenario.name == "nutrient_deficient_field":
            for i in range(10):
                s = samples[i]
                samples[i] = FieldSample(
                    sample_id=s.sample_id, timestamp=s.timestamp, latitude=s.latitude, longitude=s.longitude,
                    nitrogen=10.0, phosphorus=s.phosphorus, potassium=s.potassium, ph=s.ph, ec=s.ec, moisture=s.moisture,
                    temperature=s.temperature, source=s.source, validation_state=s.validation_state, measurement_quality=s.measurement_quality
                )
        elif scenario.name == "moisture_deficient_field":
            for i in range(10):
                s = samples[i]
                samples[i] = FieldSample(
                    sample_id=s.sample_id, timestamp=s.timestamp, latitude=s.latitude, longitude=s.longitude,
                    nitrogen=s.nitrogen, phosphorus=s.phosphorus, potassium=s.potassium, ph=s.ph, ec=s.ec, moisture=12.0,
                    temperature=s.temperature, source=s.source, validation_state=s.validation_state, measurement_quality=s.measurement_quality
                )
        elif scenario.name == "mixed_field":
            for i, s in enumerate(samples):
                if i < 8:
                    samples[i] = FieldSample(
                        sample_id=s.sample_id, timestamp=s.timestamp, latitude=s.latitude, longitude=s.longitude,
                        nitrogen=5.0, phosphorus=5.0, potassium=20.0, ph=4.2, ec=4.5, moisture=10.0,
                        temperature=s.temperature, source=s.source, validation_state=s.validation_state, measurement_quality=s.measurement_quality
                    )
                elif i < 16:
                    samples[i] = FieldSample(
                        sample_id=s.sample_id, timestamp=s.timestamp, latitude=s.latitude, longitude=s.longitude,
                        nitrogen=25.0, phosphorus=15.0, potassium=100.0, ph=5.8, ec=1.8, moisture=22.0,
                        temperature=s.temperature, source=s.source, validation_state=s.validation_state, measurement_quality=s.measurement_quality
                    )
                else:
                    samples[i] = FieldSample(
                        sample_id=s.sample_id, timestamp=s.timestamp, latitude=s.latitude, longitude=s.longitude,
                        nitrogen=50.0, phosphorus=25.0, potassium=150.0, ph=6.8, ec=1.2, moisture=32.0,
                        temperature=s.temperature, source=s.source, validation_state=s.validation_state, measurement_quality=s.measurement_quality
                    )

        new_session = FieldSession(session_id=session.session_id, field_name=session.field_name, created_at=session.created_at)
        for s in samples:
            new_session.add_sample(s)

        return new_session
