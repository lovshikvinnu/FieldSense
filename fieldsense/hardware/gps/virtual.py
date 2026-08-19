"""Deterministic Virtual GPS Adapter for testing."""

from fieldsense.hardware.models import GPSPosition
from .base import GPSAdapter


class VirtualGPSAdapter(GPSAdapter):
    """Deterministic Virtual GPS Adapter for simulation and testing."""

    def __init__(self, latitude: float = 12.9716, longitude: float = 77.5946, fix_valid: bool = True) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.fix_valid = fix_valid
        self._initialized = False

    def initialize(self) -> None:
        self._initialized = True

    def acquire_position(self) -> GPSPosition:
        return GPSPosition(
            latitude=self.latitude,
            longitude=self.longitude,
            fix_valid=self.fix_valid,
            timestamp="2026-08-09T15:00:00Z",
            quality={"satellites": 10, "hdop": 0.8},
        )

    def shutdown(self) -> None:
        self._initialized = False
