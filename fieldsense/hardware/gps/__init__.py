"""GPS hardware package."""

from .base import GPSAdapter
from .virtual import VirtualGPSAdapter
from .stub import HardwareGPSAdapter

__all__ = [
    "GPSAdapter",
    "VirtualGPSAdapter",
    "HardwareGPSAdapter",
]
