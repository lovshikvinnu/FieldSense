"""Abstract contract for GPS adapters."""

from abc import ABC, abstractmethod
from fieldsense.hardware.models import GPSPosition


class GPSAdapter(ABC):
    """Abstract contract for GPS position acquisition."""

    @abstractmethod
    def initialize(self) -> None:
        """Initialize GPS hardware connection."""
        pass

    @abstractmethod
    def acquire_position(self) -> GPSPosition:
        """Acquire current GPS position fix.

        Returns:
            GPSPosition object.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown GPS connection."""
        pass
