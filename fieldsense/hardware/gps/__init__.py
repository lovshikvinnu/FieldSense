"""GPS hardware package."""

from .base import GPSAdapter
from .virtual import VirtualGPSAdapter
from .stub import HardwareGPSAdapter
from .bridge_gps import BridgeGPSAdapter

__all__ = [
    "GPSAdapter",
    "VirtualGPSAdapter",
    "HardwareGPSAdapter",
    "BridgeGPSAdapter",
]
