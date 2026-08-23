"""Normalizer contract interface and standard implementation."""

from abc import ABC, abstractmethod
from fieldsense.domain.models import FieldSample
from .sample import NormalizedSample


class Normalizer(ABC):
    """Abstract interface for sample normalization."""

    @abstractmethod
    def normalize(self, sample: FieldSample) -> NormalizedSample:
        """Normalize a raw validated FieldSample into a NormalizedSample."""
        pass


class StandardNormalizer(Normalizer):
    """Standard unit normalizer preserving native JXBS units and converting EC (µS/cm -> dS/m)."""

    def normalize(self, sample: FieldSample) -> NormalizedSample:
        """Normalize FieldSample.

        Preserves:
        - Nitrogen, Phosphorus, Potassium in mg/kg
        - pH in pH units
        - Moisture in volumetric %
        - Temperature in °C

        Converts EC:
        - 1 dS/m = 1000 µS/cm. If raw EC >= 20.0, converts µS/cm to dS/m (raw / 1000.0).
        """
        raw_ec = float(sample.ec)
        ec_ds_m = raw_ec / 1000.0 if raw_ec >= 20.0 else raw_ec

        return NormalizedSample(
            sample_id=sample.sample_id,
            nitrogen=float(sample.nitrogen),
            phosphorus=float(sample.phosphorus),
            potassium=float(sample.potassium),
            ph=float(sample.ph),
            ec=round(ec_ds_m, 4),
            moisture=float(sample.moisture),
            temperature=float(sample.temperature),
            methodology_version="0.1",
        )
