"""Contract adapter — hardware telemetry to the canonical FieldSample.

This is the single crossing point between the two frozen sides:

    ┌───────────────── HARDWARE SIDE (frozen) ─────────────────┐
    │  NMEAGPSAdapter -> GPSData                               │
    │  JXBSSoilAdapter -> SoilData                             │
    └────────────────────────┬─────────────────────────────────┘
                             │
                   HardwareSampleAdapter          <- this module
                             │
    ┌────────────────────────▼─────────────────────────────────┐
    │  FieldSample (frozen contract)                           │
    │      -> ValidationEngine -> Intelligence -> Spatial       │
    │      -> Zones -> Recommendations -> UI -> AI narrative    │
    └───────────── SOFTWARE SIDE (frozen) ─────────────────────┘

Responsibilities, and nothing else:

    1. Compose GPSData + SoilData + a timestamp into one FieldSample.
    2. Convert units so values land inside the software contract's domain.
    3. Derive a measurement_quality score from acquisition health.

Explicit NON-responsibilities. These belong to the frozen software side and
duplicating them here would create two sources of truth:

    - Deciding whether a sample is VALID or REJECTED  -> ValidationEngine
    - Scoring soil health or any index                -> IntelligenceEngine
    - Interpolating, clustering, recommending         -> downstream engines
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fieldsense.domain.models import FieldSample, SampleSource, ValidationState

from .gps_adapter import GPSData
from .soil_adapter import JXBS_REGISTERS, SoilData


@dataclass(frozen=True)
class QualityPolicy:
    """Weights for deriving measurement_quality from acquisition health.

    The result feeds `ValidationConfig`, which treats
    `>= 0.70` as good, `0.30 - 0.70` as a warning, and `< 0.30` as unusable.
    PROTOTYPE_ONLY — these factors are engineering judgement, not calibrated.
    """
    no_fix_factor: float = 0.35
    dgps_factor: float = 1.00
    gps_factor: float = 0.92

    hdop_excellent: float = 1.0    # <= this -> 1.00
    hdop_good: float = 2.0         # <= this -> 0.95
    hdop_moderate: float = 5.0     # <= this -> 0.80
    hdop_poor_factor: float = 0.55

    satellites_strong: int = 8     # >= this -> 1.00
    satellites_usable: int = 5     # >= this -> 0.92
    satellites_weak_factor: float = 0.75


def derive_measurement_quality(
    gps: Optional[GPSData],
    soil: Optional[SoilData],
    policy: Optional[QualityPolicy] = None,
) -> float:
    """Derive a [0.0, 1.0] measurement quality score from acquisition health.

    Deterministic: the same inputs always give the same score. Combines
    positional confidence (fix type, HDOP, satellite count) with sensor
    completeness (how many of the seven registers answered).

    Args:
        gps: Decoded GPS telemetry, or None when unavailable.
        soil: Decoded soil telemetry, or None when unavailable.
        policy: Optional weighting policy.

    Returns:
        Quality score rounded to three decimals.
    """
    policy = policy or QualityPolicy()
    quality = 1.0

    if gps is None or not gps.fix_valid:
        quality *= policy.no_fix_factor
    else:
        quality *= policy.dgps_factor if gps.fix_quality >= 2 else policy.gps_factor

        if gps.hdop is not None:
            if gps.hdop <= policy.hdop_excellent:
                quality *= 1.00
            elif gps.hdop <= policy.hdop_good:
                quality *= 0.95
            elif gps.hdop <= policy.hdop_moderate:
                quality *= 0.80
            else:
                quality *= policy.hdop_poor_factor

        if gps.satellites >= policy.satellites_strong:
            quality *= 1.00
        elif gps.satellites >= policy.satellites_usable:
            quality *= 0.92
        elif gps.satellites > 0:
            quality *= policy.satellites_weak_factor

    if soil is None:
        quality = 0.0
    else:
        total = len(JXBS_REGISTERS)
        quality *= soil.parameters_read / total if total else 0.0

    return round(max(0.0, min(1.0, quality)), 3)


class HardwareSampleAdapter:
    """Builds canonical FieldSample objects from hardware telemetry."""

    def __init__(
        self,
        policy: Optional[QualityPolicy] = None,
        sample_id_prefix: str = "HW",
    ) -> None:
        """Configure the adapter.

        Args:
            policy: Optional measurement quality weighting policy.
            sample_id_prefix: Prefix for generated sample identifiers.
        """
        self.policy = policy or QualityPolicy()
        self.sample_id_prefix = sample_id_prefix

    def build_sample(
        self,
        gps: Optional[GPSData],
        soil: Optional[SoilData],
        timestamp: Optional[datetime] = None,
        sample_id: Optional[str] = None,
    ) -> FieldSample:
        """Compose one FieldSample from hardware telemetry.

        Args:
            gps: Decoded GPS telemetry.
            soil: Decoded soil telemetry, already unit-converted by
                `JXBSSoilAdapter` (EC in dS/m, not the probe's uS/cm).
            timestamp: Acquisition time. Defaults to now in UTC.
            sample_id: Explicit identifier. Defaults to a generated one.

        Returns:
            A FieldSample tagged `SampleSource.HARDWARE`.

        Note:
            `validation_state` is left at its `VALID` default. This adapter
            does not judge samples — `ValidationEngine` is the gatekeeper and
            must remain the only one. A missing GPS fix or a failed register
            read shows up as a low `measurement_quality`, which is the signal
            the validation engine acts on.
        """
        stamp = timestamp or datetime.now(timezone.utc)

        return FieldSample(
            sample_id=sample_id or self.generate_sample_id(stamp),
            timestamp=stamp,
            latitude=gps.latitude if gps and gps.latitude is not None else 0.0,
            longitude=gps.longitude if gps and gps.longitude is not None else 0.0,
            nitrogen=soil.nitrogen if soil and soil.nitrogen is not None else 0.0,
            phosphorus=soil.phosphorus if soil and soil.phosphorus is not None else 0.0,
            potassium=soil.potassium if soil and soil.potassium is not None else 0.0,
            ph=soil.ph if soil and soil.ph is not None else 0.0,
            ec=soil.ec if soil and soil.ec is not None else 0.0,
            moisture=soil.moisture if soil and soil.moisture is not None else 0.0,
            temperature=soil.temperature if soil and soil.temperature is not None else 0.0,
            measurement_quality=derive_measurement_quality(gps, soil, self.policy),
            source=SampleSource.HARDWARE,
            validation_state=ValidationState.VALID,
        )

    def generate_sample_id(self, timestamp: Optional[datetime] = None) -> str:
        """Generate a traceable sample identifier."""
        stamp = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S")
        return "{}-{}-{}".format(self.sample_id_prefix, stamp, uuid.uuid4().hex[:6].upper())

    def acquisition_report(
        self, gps: Optional[GPSData], soil: Optional[SoilData]
    ) -> Dict[str, Any]:
        """Summarise acquisition health for logging and the runbook.

        Diagnostic only. Nothing downstream consumes this.
        """
        return {
            "gps_fix_valid": bool(gps and gps.fix_valid),
            "gps_fix_quality": gps.fix_quality if gps else 0,
            "gps_satellites": gps.satellites if gps else 0,
            "gps_hdop": gps.hdop if gps else None,
            "soil_parameters_read": soil.parameters_read if soil else 0,
            "soil_parameters_expected": len(JXBS_REGISTERS),
            "soil_read_errors": list(soil.read_errors) if soil else ["no soil data"],
            "ec_raw_us_cm": soil.ec_raw_us_cm if soil else None,
            "ec_converted_ds_m": soil.ec if soil else None,
            "measurement_quality": derive_measurement_quality(gps, soil, self.policy),
        }
