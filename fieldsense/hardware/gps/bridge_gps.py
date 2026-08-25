"""NEO-M8N GPS adapter reading telemetry from the STM32 side of the UNO Q.

Two transports, one parser:

    RouterBridge   Bridge.call("get_gps_data")      on-board IPC, preferred
    TCP gateway    127.0.0.1:9876                   App Lab helper process

Telemetry is a compact CSV emitted by the STM32 sketch, not raw NMEA:

    FIX_OK,1734.18667N,07825.47349E,Sats:06,HDOP:1.61,UI:3,TP:1,TZ:1820
    NO_FIX,0.0,0.0,0,0.0

Everything after the fifth field is diagnostic and optional. `parse_gps_telemetry`
ignores it by contract, which is what lets the sketch carry receiver counters
and the operator's START press counter on the same string without a second RPC
endpoint - see `parse_ui_event` below.

Coordinates arrive in NMEA DDMM.MMMM form and are converted to decimal degrees
here. `arduino.app_utils` exists only on the UNO Q, so `Bridge` is resolved
lazily and stays None elsewhere — tests patch this module-level symbol.
"""

import os
import socket
from dataclasses import dataclass
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


@dataclass(frozen=True)
class UIEvent:
    """Operator-control state, as reported by the MCU on the telemetry line.

    The press counter is monotonic and is never reset by the firmware. That is
    deliberate: the host polls at about 1 Hz and a press lasts a few hundred
    milliseconds, so a boolean "is pressed" would be missed roughly as often as
    it was seen. A counter cannot be missed - the caller compares it against
    the value it read last, and any increase is at least one press.
    """

    press_count: Optional[int] = None
    touch_present: Optional[bool] = None
    touch_pressure: Optional[int] = None
    #: Raw XPT2046 pressure channels. Kept because the derived pressure is zero
    #: for three different faults - no controller, an untouched controller, and
    #: a MISO stuck at a rail - and only the raw pair tells them apart.
    touch_raw: Optional[tuple] = None
    #: FS| records the MCU has PARSED. The panel link is a TCP socket into
    #: arduino-router, so a successful write says nothing about whether the MCU
    #: collected the bytes. This counter is the only delivery evidence there is:
    #: if it does not move after a push, the record did not land.
    records_parsed: Optional[int] = None
    #: Panel Y of the last contact, or None. The bottom-bar target starts at
    #: y=182, so a press there should land in the 180s-230s; a small value means
    #: the touch axis is inverted on this panel.
    touch_y: Optional[int] = None

    @property
    def reported(self) -> bool:
        """True when the firmware sent operator-control fields at all.

        False means the board is running firmware that predates the control,
        which is a different situation from a board whose operator has simply
        not pressed anything yet.
        """
        return self.press_count is not None

    def presses_since(self, previous: Optional[int]) -> int:
        """How many presses happened since `previous` was observed.

        A counter that went backwards means the MCU restarted - a reflash, a
        reset, or a power blip on the STM32 alone. That is reported as zero
        presses rather than as a huge number, because the alternative is a
        board reset silently firing a burst of sample triggers.
        """
        if self.press_count is None or previous is None:
            return 0
        delta = self.press_count - previous
        return delta if delta > 0 else 0


def parse_ui_event(payload: str) -> UIEvent:
    """Extract the operator-control fields from a raw telemetry line.

    Tolerant by design: firmware without these fields yields an empty UIEvent
    rather than an error, so an older board still produces positions.
    """
    press: Optional[int] = None
    present: Optional[bool] = None
    pressure: Optional[int] = None
    raw_z1: Optional[int] = None
    raw_z2: Optional[int] = None
    records: Optional[int] = None
    touch_y: Optional[int] = None

    for part in str(payload or "").strip().split(","):
        key, sep, value = part.partition(":")
        if not sep:
            continue
        key = key.strip().upper()
        value = value.strip()
        try:
            if key == "UI":
                press = int(value)
            elif key == "TP":
                present = bool(int(value))
            elif key == "TZ":
                pressure = int(value)
            elif key == "Z1":
                raw_z1 = int(value)
            elif key == "Z2":
                raw_z2 = int(value)
            elif key == "RC":
                records = int(value)
            elif key == "TY":
                touch_y = int(value)
        except ValueError:
            continue
    raw = (raw_z1, raw_z2) if raw_z1 is not None and raw_z2 is not None else None
    return UIEvent(press_count=press, touch_present=present,
                   touch_pressure=pressure, touch_raw=raw, records_parsed=records,
                   touch_y=touch_y)


class BridgeGPSAdapter(GPSAdapter):
    """Reads NEO-M8N telemetry over RouterBridge, falling back to a TCP gateway."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        timeout: float = 1.0,
        method: str = "get_gps_data",
        bridge_endpoint: Optional[str] = None,
    ) -> None:
        """Configure the adapter. No transport is contacted until acquisition.

        Args:
            host: TCP gateway host, used only when RouterBridge is unavailable.
                Defaults to environment variable FIELDSENSE_GPS_GATEWAY_HOST or "127.0.0.1".
            port: TCP gateway port.
                Defaults to environment variable FIELDSENSE_GPS_GATEWAY_PORT or 9876.
            timeout: Socket timeout in seconds.
            method: RouterBridge method name to call.
            bridge_endpoint: Alias for `method`, used by SensorAdapterFactory.
        """
        if host is None:
            host = os.environ.get("FIELDSENSE_GPS_GATEWAY_HOST", "127.0.0.1")
        if port is None:
            raw_port = os.environ.get("FIELDSENSE_GPS_GATEWAY_PORT")
            port = int(raw_port) if raw_port is not None and raw_port.strip() else 9876
        else:
            port = int(port)

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

    def read_raw(self) -> str:
        """Return the telemetry line verbatim, trailing diagnostics included.

        `read()` discards everything past the fifth field, which is correct for
        a position but throws away the receiver counters and the operator's
        press counter. The field workflow needs both, and needs them from the
        same poll - asking twice would double the RPC traffic on a link where
        one round trip already costs about 595 ms.

        Raises:
            HardwareError: No transport was reachable.
        """
        return self._read_payload()

    def read_ui_event(self) -> "UIEvent":
        """Return just the operator-control state from one telemetry poll.

        Raises:
            HardwareError: No transport was reachable.
        """
        return parse_ui_event(self._read_payload())

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
