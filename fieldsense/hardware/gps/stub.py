"""Hardware GPS Adapter stub for physical NEO-M8N GPS integration."""

from fieldsense.hardware.models import GPSPosition, HardwareError, HardwareErrorCode
from fieldsense.hardware.config import HARDWARE_SPEC_REQUIRED
from .base import GPSAdapter


class HardwareGPSAdapter(GPSAdapter):
    """Hardware GPS Adapter stub for NEO-M8N integration boundary.

    Hardware protocol and serial pin mapping marked HARDWARE_SPEC_REQUIRED.
    """

    def __init__(self, port: str = HARDWARE_SPEC_REQUIRED, baudrate: str = HARDWARE_SPEC_REQUIRED) -> None:
        self.port = port
        self.baudrate = baudrate
        self._initialized = False

    def initialize(self) -> None:
        if self.port == HARDWARE_SPEC_REQUIRED:
            raise HardwareError(
                HardwareErrorCode.HARDWARE_SPEC_REQUIRED,
                "NEO-M8N GPS UART port and wiring unconfirmed. Specification required.",
            )
        self._initialized = True

    def acquire_position(self) -> GPSPosition:
        if not self._initialized:
            raise HardwareError(
                HardwareErrorCode.DEVICE_NOT_INITIALIZED,
                "GPS device not initialized.",
            )
        # Stub response if hardware specifications are provided in future
        return GPSPosition(latitude=0.0, longitude=0.0, fix_valid=False)

    def shutdown(self) -> None:
        self._initialized = False
