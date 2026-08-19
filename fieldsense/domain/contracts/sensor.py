"""Sensor adapter abstraction contract."""

from abc import ABC, abstractmethod
from fieldsense.domain.models import FieldSample


class SensorAdapter(ABC):
    """Minimal abstract interface for all FieldSense sensor adapters."""

    @abstractmethod
    def initialize(self) -> None:
        """Initialize connection or state for the sensor adapter."""
        pass

    @abstractmethod
    def acquire_sample(self) -> FieldSample:
        """Acquire a single FieldSample from the adapter."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Safely release or close resources associated with the adapter."""
        pass

    def __enter__(self) -> "SensorAdapter":
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()
