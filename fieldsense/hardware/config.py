"""Centralized configuration for hardware integration boundary."""

from dataclasses import dataclass
from .models import HardwareReadinessState

# Explicit unconfirmed specification tag
HARDWARE_SPEC_REQUIRED = "HARDWARE_SPEC_REQUIRED"


@dataclass(frozen=True)
class HardwareConfig:
    """Centralized configuration for hardware interfaces.

    Unconfirmed parameters are explicitly marked HARDWARE_SPEC_REQUIRED.
    Do NOT guess register maps, baud rates, or pin assignments.
    """
    sensor_port: str = HARDWARE_SPEC_REQUIRED
    sensor_baudrate: str = HARDWARE_SPEC_REQUIRED
    sensor_parity: str = HARDWARE_SPEC_REQUIRED
    sensor_stop_bits: str = HARDWARE_SPEC_REQUIRED
    sensor_slave_address: str = HARDWARE_SPEC_REQUIRED

    gps_port: str = HARDWARE_SPEC_REQUIRED
    gps_baudrate: str = HARDWARE_SPEC_REQUIRED
    gps_update_rate: str = HARDWARE_SPEC_REQUIRED

    readiness_state: HardwareReadinessState = HardwareReadinessState.HARDWARE_PENDING
