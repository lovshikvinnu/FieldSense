"""Deterministic mock hardware transport for testing without physical hardware."""

import json
from typing import Optional, Dict, Any

from fieldsense.hardware.models import HardwareError, HardwareErrorCode
from .base import SensorTransport


class MockHardwareTransport(SensorTransport):
    """Deterministic Mock Hardware Transport for hardware integration testing."""

    def __init__(self, mode: str = "NORMAL", custom_payload: Optional[Dict[str, Any]] = None) -> None:
        """Initialize mock transport with simulation mode.

        Args:
            mode: Simulation mode ("NORMAL", "MALFORMED", "TIMEOUT", "TRANSPORT_FAILURE", "UNINITIALIZED").
            custom_payload: Optional custom measurement dict.
        """
        self.mode = mode
        self.custom_payload = custom_payload
        self._is_open = False

    def open(self) -> None:
        """Open mock transport."""
        if self.mode == "TRANSPORT_FAILURE":
            raise HardwareError(HardwareErrorCode.TRANSPORT_ERROR, "Failed to open physical RS485 serial port.")
        self._is_open = True

    def read(self, length: int = 256) -> bytes:
        """Read mock payload bytes according to mode."""
        if not self._is_open:
            raise HardwareError(HardwareErrorCode.DEVICE_NOT_INITIALIZED, "Transport is not open.")

        if self.mode == "TIMEOUT":
            raise HardwareError(HardwareErrorCode.TIMEOUT, "Hardware response timed out.")
        elif self.mode == "MALFORMED":
            return b"\x01\x03\x00\xFFCORRUPTED_FRAME_DATA"
        elif self.mode == "NORMAL":
            default_data = {
                "nitrogen": 45.0,
                "phosphorus": 25.0,
                "potassium": 150.0,
                "ph": 6.8,
                "ec": 1.2,
                "moisture": 32.0,
                "temperature": 22.5,
            }
            data = self.custom_payload or default_data
            return json.dumps(data).encode("utf-8")
        else:
            raise HardwareError(HardwareErrorCode.INVALID_SENSOR_FRAME, f"Unknown mock transport mode: {self.mode}")

    def write(self, payload: bytes) -> None:
        """Write mock payload bytes."""
        if not self._is_open:
            raise HardwareError(HardwareErrorCode.DEVICE_NOT_INITIALIZED, "Transport is not open.")

    def close(self) -> None:
        """Close mock transport."""
        self._is_open = False

    @property
    def is_open(self) -> bool:
        """Return whether transport is open."""
        return self._is_open
