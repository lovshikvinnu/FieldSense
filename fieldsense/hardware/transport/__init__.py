"""Hardware transport package.

`SerialTransport` is imported lazily by the adapters rather than re-exported
here, because it touches platform-specific `termios` at import time.
"""

from .base import SensorTransport
from .mock import MockHardwareTransport

__all__ = [
    "SensorTransport",
    "MockHardwareTransport",
]
