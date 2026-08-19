"""Deterministic validation engine for FieldSample pipeline eligibility."""

import math
from typing import List, Optional, Tuple, Any

from fieldsense.domain.models import FieldSample, FieldSession, ValidationState
from .config import ValidationConfig, MeasurementRange
from .reasons import ValidationReason
from .result import ValidationResult


class ValidationEngine:
    """Deterministic validation engine evaluating FieldSample eligibility.

    Acts as gatekeeper between raw sample acquisition and downstream intelligence.
    Does NOT mutate input FieldSample objects or alter raw FieldSession sample lists.
    """

    def __init__(self, config: Optional[ValidationConfig] = None) -> None:
        """Initialize validation engine with configuration."""
        self.config = config or ValidationConfig()

    def validate(self, sample: FieldSample) -> ValidationResult:
        """Evaluate a single FieldSample and return a ValidationResult."""
        reasons: List[ValidationReason] = []
        is_rejected = False
        is_warning = False

        # 1. GPS Coordinate Validation
        lat_valid, lat_reason = self._check_numeric(sample.latitude, self.config.lat_range)
        lon_valid, lon_reason = self._check_numeric(sample.longitude, self.config.lon_range)

        if not lat_valid or not lon_valid:
            is_rejected = True
            if lat_reason == ValidationReason.GPS_OUT_OF_RANGE or lon_reason == ValidationReason.GPS_OUT_OF_RANGE:
                if ValidationReason.GPS_OUT_OF_RANGE not in reasons:
                    reasons.append(ValidationReason.GPS_OUT_OF_RANGE)
            else:
                reason_to_add = lat_reason or lon_reason
                if reason_to_add and reason_to_add not in reasons:
                    reasons.append(reason_to_add)

        # 2. Measurement Numeric & Sanity Bounds Validation
        measurement_fields = [
            "nitrogen", "phosphorus", "potassium",
            "ph", "ec", "moisture", "temperature"
        ]

        for field_name in measurement_fields:
            val = getattr(sample, field_name, None)
            target_range = self.config.measurement_ranges.get(field_name)

            valid, reason = self._check_numeric(val, target_range)
            if not valid:
                is_rejected = True
                if reason and reason not in reasons:
                    reasons.append(reason)

        # 3. Measurement Quality Evaluation
        q_valid, q_reason = self._check_numeric(sample.measurement_quality, MeasurementRange(0.0, 1.0))
        if not q_valid:
            is_rejected = True
            if q_reason and q_reason not in reasons:
                reasons.append(q_reason)
        else:
            q_val = float(sample.measurement_quality)
            if q_val < self.config.quality_reject_threshold:
                is_rejected = True
                if ValidationReason.UNSTABLE_MEASUREMENT not in reasons:
                    reasons.append(ValidationReason.UNSTABLE_MEASUREMENT)
            elif q_val < self.config.quality_warning_threshold:
                is_warning = True
                if ValidationReason.LOW_MEASUREMENT_QUALITY not in reasons:
                    reasons.append(ValidationReason.LOW_MEASUREMENT_QUALITY)

        # Determine final state & pipeline eligibility (precedence: REJECTED > VALID_WITH_WARNING > VALID)
        if is_rejected:
            final_state = ValidationState.REJECTED
            pipeline_eligible = False
        elif is_warning:
            final_state = ValidationState.VALID_WITH_WARNING
            pipeline_eligible = True
        else:
            final_state = ValidationState.VALID
            pipeline_eligible = True

        return ValidationResult(
            sample_id=sample.sample_id,
            state=final_state,
            pipeline_eligible=pipeline_eligible,
            reasons=reasons,
        )

    def _check_numeric(
        self, val: Any, target_range: Optional[MeasurementRange]
    ) -> Tuple[bool, Optional[ValidationReason]]:
        """Helper to validate numeric type, finite value, and range bounds."""
        if val is None:
            return False, ValidationReason.MISSING_VALUE

        if not isinstance(val, (int, float)) or isinstance(val, bool):
            return False, ValidationReason.INVALID_NUMERIC_VALUE

        val_float = float(val)
        if math.isnan(val_float) or math.isinf(val_float):
            return False, ValidationReason.INVALID_NUMERIC_VALUE

        if target_range is not None and not target_range.is_valid(val_float):
            if target_range is self.config.lat_range or target_range is self.config.lon_range:
                return False, ValidationReason.GPS_OUT_OF_RANGE
            else:
                return False, ValidationReason.MEASUREMENT_OUT_OF_RANGE

        return True, None

    def validate_many(self, samples: List[FieldSample]) -> List[ValidationResult]:
        """Validate a batch of FieldSample objects in sequence."""
        return [self.validate(sample) for sample in samples]

    def get_eligible_samples(self, samples: List[FieldSample]) -> List[FieldSample]:
        """Filter a list of FieldSample objects to return only pipeline-eligible ones."""
        return [sample for sample in samples if self.validate(sample).pipeline_eligible]

    def validate_session(self, session: FieldSession) -> List[ValidationResult]:
        """Validate all samples in a FieldSession without altering session.samples."""
        return self.validate_many(session.samples)

    def get_session_eligible_samples(self, session: FieldSession) -> List[FieldSample]:
        """Return pipeline-eligible samples from a FieldSession without modifying raw samples."""
        return self.get_eligible_samples(session.samples)
