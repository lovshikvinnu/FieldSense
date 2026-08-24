"""NEO-M8N GPS adapter reading telemetry from the STM32 side of the UNO Q.

Two transports, one parser:

    RouterBridge   Bridge.call("get_gps_data")      on-board IPC, preferred
    TCP gateway    127.0.0.1:9876                   App Lab helper process

Telemetry is a compact CSV emitted by the STM32 sketch, not raw NMEA:

    FIX_OK,1734.18667N,07825.47349E,Sats:06,HDOP:1.61
    NO_FIX,0.0,0.0,0,0.0

Coordinates arrive in NMEA DDMM.MMMM form and are converted to decimal degrees
here. `arduino.app_utils` exists only on the UNO Q, so `Bridge` is resolved
lazily and stays None elsewhere — tests patch this module-level symbol.
"""

import socket
from typing import Any, Optional

from ..models import GPSPosition, HardwareError, HardwareErrorCode
from .base import GPSAdapter

try:  # present only on the Arduino UNO Q
    from arduino.app_utils import Bridge  # type: ignore
except Exception:  # pragma: no cover - off-target default
    Bridge = None  # type: ignore


def parse_nmea_coord(coord_str: str, is_longitude: bool = False) -> float:
    """Convert an NMEA DDMM.MMMM / DDDMM.MMMM coordinate to decimal degrees.

    The two digits immediately left of the decimal point are minutes;
    everything before them is degrees. Latitude carries two degree digits and
    longitude three, which the modulo split handles without needing to know
    which is which — `is_longitude` is accepted for call-site clarity.

    Args:
        coord_str: Coordinate with trailing hemisphere, e.g. '1734.18667N'.
        is_longitude: True when parsing a longitude field.

    Returns:
        Signed decimal degrees. Negative for S and W.

    Raises:
        ValueError: Field is empty, malformed, or non-numeric.
    """
    if not coord_str or not coord_str.strip():
        raise ValueError("Empty NMEA coordinate string")

    text = coord_str.strip()
    hemisphere = text[-1].upper()
    if hemisphere not in ("N", "S", "E", "W"):
        raise ValueError("Missing hemisphere in NMEA coordinate: {!r}".format(coord_str))

    try:
        value = float(text[:-1])
    except ValueError:
        raise ValueError("Failed to parse NMEA coordinate string: {!r}".format(coord_str))

    degrees = int(value // 100)
    minutes = value % 100
    decimal = degrees + (minutes / 60.0)
    return -decimal if hemisphere in ("S", "W") else decimal


def parse_gps_telemetry(payload: str) -> GPSPosition:
    """Parse one STM32 GPS telemetry CSV line into a canonical GPSPosition.

    Raises:
        HardwareError: Payload empty or in an unrecognised format.
    """
    if not payload or not payload.strip():
        raise HardwareError(HardwareErrorCode.MALFORMED_RESPONSE, "Empty response from GPS bridge")

    parts = payload.strip().split(",")

    if parts[0] == "NO_FIX":
        return GPSPosition(latitude=0.0, longitude=0.0, fix_valid=False)

    if parts[0] == "FIX_OK" and len(parts) >= 5:
        try:
            return GPSPosition(
                latitude=parse_nmea_coord(parts[1], is_longitude=False),
                longitude=parse_nmea_coord(parts[2], is_longitude=True),
                fix_valid=True,
                quality={
                    "satellites": int(parts[3].split(":")[1]),
                    "hdop": float(parts[4].split(":")[1]),
                },
            )
        except HardwareError:
            raise
        except Exception as exc:
            raise HardwareError(
                HardwareErrorCode.MALFORMED_RESPONSE,
                "Failed to parse FIX_OK telemetry: {}".format(exc),
            )

    raise HardwareError(
        HardwareErrorCode.MALFORMED_RESPONSE, "Unrecognized telemetry format: {}".format(payload)
    )


class BridgeGPSAdapter(GPSAdapter):
    """Reads NEO-M8N telemetry over RouterBridge, falling back to a TCP gateway."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9876,
        timeout: float = 1.0,
        method: str = "get_gps_data",
        bridge_endpoint: Optional[str] = None,
    ) -> None:
        """Configure the adapter. No transport is contacted until acquisition.

        Args:
            host: TCP gateway host, used only when RouterBridge is unavailable.
            port: TCP gateway port.
            timeout: Socket timeout in seconds.
            method: RouterBridge method name to call.
            bridge_endpoint: Alias for `method`, used by SensorAdapterFactory.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.method = bridge_endpoint or method
        self.bridge_endpoint = self.method
        self._initialized = False

    def initialize(self) -> None:
        """Mark the adapter ready. Transports are contacted lazily."""
        self._initialized = True

    def shutdown(self) -> None:
        """Release adapter state. Neither transport holds a persistent handle."""
        self._initialized = False

    def read(self) -> GPSPosition:
        """Fetch and parse the latest GPS telemetry.

        Raises:
            HardwareError: No transport reachable, or the payload was malformed.
        """
        return parse_gps_telemetry(self._read_payload())

    def acquire_position(self) -> GPSPosition:
        """Frozen GPSAdapter contract: return a canonical GPSPosition."""
        return self.read()

    def _read_payload(self) -> str:
        """Return raw telemetry, preferring RouterBridge over the TCP gateway."""
        if Bridge is not None:
            try:
                payload = Bridge.call(self.method)
            except Exception as exc:
                raise HardwareError(
                    HardwareErrorCode.DEVICE_UNAVAILABLE,
                    "RouterBridge call failed: {}".format(exc),
                )
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode("utf-8", errors="ignore")
            return str(payload).strip()

        return self._read_from_gateway()

    def _read_from_gateway(self) -> str:
        """Read one telemetry line from the local App Lab TCP gateway."""
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                return sock.recv(1024).decode("utf-8").strip()
        except socket.timeout:
            raise HardwareError(
                HardwareErrorCode.DEVICE_UNAVAILABLE,
                "GPS gateway socket timeout ({}s)".format(self.timeout),
            )
        except ConnectionRefusedError:
            raise HardwareError(
                HardwareErrorCode.DEVICE_UNAVAILABLE,
                "GPS gateway connection refused (is main.py running?)",
            )
        except Exception as exc:
            raise HardwareError(
                HardwareErrorCode.DEVICE_UNAVAILABLE,
                "GPS gateway connection error: {}".format(exc),
            )
