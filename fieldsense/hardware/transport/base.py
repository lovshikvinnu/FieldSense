"""Abstract transport interface for physical and mock hardware communications."""

from abc import ABC, abstractmethod


class SensorTransport(ABC):
    """Abstract contract for sensor transport layers (RS485 / Modbus / Serial / Mock)."""

    @abstractmethod
    def open(self) -> None:
        """Open transport connection."""
        pass

    @abstractmethod
    def read(self, length: int = 256) -> bytes:
        """Read bytes from transport."""
        pass

    @abstractmethod
    def write(self, payload: bytes) -> None:
        """Write bytes to transport."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close transport connection."""
        pass

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """Return connection open status."""
        pass
