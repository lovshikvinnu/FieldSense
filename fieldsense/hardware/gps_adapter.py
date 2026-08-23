"""GPS acquisition adapter — NMEA 0183 telemetry to canonical position.

Sits between two frozen sides:

    STM32 Bridge get_gps_data()  ──┐
                                   ├──> NMEA text ──> GPSData ──> GPSPosition
    NEO-M8N UART stream ───────────┘                              (frozen model)

Parses the GGA and RMC sentence families across all talker IDs the NEO-M8N
emits ($GN multi-constellation, $GP GPS, $GL GLONASS, $GA Galileo, $BD BeiDou),
validates the NMEA checksum, and converts DDMM.MMMM to decimal degrees.

Datasheet references: docs/HARDWARE.md section 5.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .gps.base import GPSAdapter
from .models import GPSPosition

# Talker IDs the NEO-M8N emits, and the sentences we consume.
KNOWN_TALKERS = ("GN", "GP", "GL", "GA", "BD", "QZ")
POSITION_SENTENCES = ("GGA", "RMC")


class GPSParseError(Exception):
    """Raised when a sentence is structurally unusable."""


# --------------------------------------------------------------------- model


@dataclass(frozen=True)
class GPSData:
    """Structured GPS telemetry decoded from one NMEA sentence.

    Richer than the frozen `GPSPosition`: carries fix quality, satellite count
    and HDOP so the sample adapter can derive a measurement quality score.
    Convert with `to_gps_position()` when the frozen contract is required.
    """
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    fix_quality: int = 0                 # 0 no fix, 1 GPS, 2 DGPS
    satellites: int = 0
    hdop: Optional[float] = None
    utc_time: Optional[str] = None
    talker: str = ""                     # GN, GP, GL, ...
    sentence_type: str = ""              # GGA, RMC
    raw_sentence: str = ""

    @property
    def fix_valid(self) -> bool:
        """True when the receiver reports a usable position fix."""
        return self.fix_quality > 0 and self.latitude is not None and self.longitude is not None

    def to_gps_position(self) -> GPSPosition:
        """Convert to the frozen GPSPosition contract."""
        return GPSPosition(
            latitude=self.latitude if self.latitude is not None else 0.0,
            longitude=self.longitude if self.longitude is not None else 0.0,
            fix_valid=self.fix_valid,
            timestamp=self.utc_time,
            quality={
                "fix_quality": self.fix_quality,
                "satellites": self.satellites,
                "hdop": self.hdop,
                "altitude_m": self.altitude_m,
                "talker": self.talker,
                "sentence_type": self.sentence_type,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize GPSData to a dictionary."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_m": self.altitude_m,
            "fix_quality": self.fix_quality,
            "satellites": self.satellites,
            "hdop": self.hdop,
            "utc_time": self.utc_time,
            "talker": self.talker,
            "sentence_type": self.sentence_type,
            "raw_sentence": self.raw_sentence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GPSData":
        """Deserialize a dictionary into GPSData."""
        return cls(
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            altitude_m=data.get("altitude_m"),
            fix_quality=int(data.get("fix_quality", 0)),
            satellites=int(data.get("satellites", 0)),
            hdop=data.get("hdop"),
            utc_time=data.get("utc_time"),
            talker=data.get("talker", ""),
            sentence_type=data.get("sentence_type", ""),
            raw_sentence=data.get("raw_sentence", ""),
        )


# --------------------------------------------------------------------- parsing


def nmea_checksum_valid(sentence: str) -> bool:
    """Verify the XOR checksum of an NMEA sentence.

    A sentence without a '*' suffix is treated as valid, because some sources
    (including the STM32 Bridge) forward pre-validated payloads without one.
    """
    text = sentence.strip()
    if "*" not in text:
        return True
    body, _, checksum = text.partition("*")
    body = body.lstrip("$")
    checksum = checksum.strip()[:2]
    if len(checksum) != 2:
        return False
    computed = 0
    for char in body:
        computed ^= ord(char)
    try:
        return computed == int(checksum, 16)
    except ValueError:
        return False


def ddmm_to_decimal(raw: str, hemisphere: str) -> Optional[float]:
    """Convert NMEA DDMM.MMMM / DDDMM.MMMM to signed decimal degrees.

    NMEA packs degrees and minutes into one field: the two digits immediately
    left of the decimal point are minutes, everything before them is degrees.
    Latitude uses two degree digits, longitude three, so the split is derived
    from the decimal position rather than assumed.

    Args:
        raw: Coordinate field, e.g. '4807.038' or '01131.000'.
        hemisphere: One of 'N', 'S', 'E', 'W'.

    Returns:
        Signed decimal degrees, or None when the field is empty.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    dot = text.find(".")
    if dot < 0:
        dot = len(text)
    if dot < 3:
        raise GPSParseError("malformed coordinate field: {!r}".format(raw))

    try:
        degrees = float(text[:dot - 2])
        minutes = float(text[dot - 2:])
    except ValueError:
        raise GPSParseError("non-numeric coordinate field: {!r}".format(raw))

    value = degrees + minutes / 60.0
    if hemisphere.strip().upper() in ("S", "W"):
        value = -value
    return value


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_nmea_sentence(sentence: str) -> Optional[GPSData]:
    """Parse one NMEA sentence into GPSData.

    Args:
        sentence: A single sentence, with or without the trailing checksum.

    Returns:
        GPSData for a recognised GGA or RMC sentence, otherwise None.
        Returns None rather than raising for unrecognised or corrupt input, so
        a caller can stream a mixed NMEA feed without filtering it first.
    """
    if not sentence:
        return None
    text = sentence.strip()
    if not text.startswith("$"):
        return None
    if not nmea_checksum_valid(text):
        return None

    body = text[1:].split("*")[0]
    fields = body.split(",")
    header = fields[0]
    if len(header) < 5:
        return None

    talker, kind = header[:2], header[2:5]
    if talker not in KNOWN_TALKERS or kind not in POSITION_SENTENCES:
        return None

    try:
        if kind == "GGA" and len(fields) >= 10:
            return GPSData(
                latitude=ddmm_to_decimal(fields[2], fields[3]),
                longitude=ddmm_to_decimal(fields[4], fields[5]),
                altitude_m=_to_float(fields[9]),
                fix_quality=_to_int(fields[6]),
                satellites=_to_int(fields[7]),
                hdop=_to_float(fields[8]),
                utc_time=fields[1] or None,
                talker=talker,
                sentence_type=kind,
                raw_sentence=text,
            )
        if kind == "RMC" and len(fields) >= 7:
            # RMC carries a validity letter (A active / V void) instead of a
            # numeric fix quality, and reports neither satellites nor HDOP.
            active = fields[2].strip().upper() == "A"
            return GPSData(
                latitude=ddmm_to_decimal(fields[3], fields[4]),
                longitude=ddmm_to_decimal(fields[5], fields[6]),
                fix_quality=1 if active else 0,
                utc_time=fields[1] or None,
                talker=talker,
                sentence_type=kind,
                raw_sentence=text,
            )
    except GPSParseError:
        return None
    return None


def parse_nmea_stream(text: str) -> List[GPSData]:
    """Parse every recognised sentence in a multi-line NMEA payload."""
    results = []
    for line in text.replace("\r", "\n").split("\n"):
        parsed = parse_nmea_sentence(line)
        if parsed is not None:
            results.append(parsed)
    return results


def best_fix(candidates: List[GPSData]) -> Optional[GPSData]:
    """Select the most trustworthy fix from a batch of parsed sentences.

    Prefers a valid fix, then a GGA sentence (it carries satellites and HDOP),
    then the higher satellite count. Deterministic for a given input order.
    """
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda g: (g.fix_valid, g.sentence_type == "GGA", g.satellites),
        reverse=True,
    )[0]


# --------------------------------------------------------------------- adapter


class NMEAGPSAdapter(GPSAdapter):
    """GPS adapter implementing the frozen GPSAdapter contract.

    Source-agnostic: it consumes NMEA text from any callable. Use the
    `from_serial` or `from_bridge` constructors for the two real sources.
    """

    def __init__(
        self,
        read_text: Callable[[], str],
        max_attempts: int = 30,
        require_fix: bool = False,
    ) -> None:
        """Build the adapter around a text source.

        Args:
            read_text: Callable returning NMEA text (one or many sentences).
            max_attempts: How many reads to make while waiting for a fix.
            require_fix: When True, keep reading until a valid fix appears.
        """
        self.read_text = read_text
        self.max_attempts = max_attempts
        self.require_fix = require_fix
        self._initialized = False
        self.last_data: Optional[GPSData] = None

    def initialize(self) -> None:
        """Mark the adapter ready. The underlying source manages its own device."""
        self._initialized = True

    def shutdown(self) -> None:
        """Release adapter state. The source owns any device handle."""
        self._initialized = False

    def acquire_gps_data(self) -> GPSData:
        """Read the source until a usable fix is found or attempts run out.

        Returns:
            The best GPSData seen. When nothing parsed, an empty GPSData with
            `fix_quality = 0` — never an exception, so an unplugged antenna
            degrades the sample rather than aborting acquisition.
        """
        seen: List[GPSData] = []
        for _ in range(max(1, self.max_attempts)):
            try:
                text = self.read_text() or ""
            except Exception:  # a dead source must not abort the campaign
                break
            batch = parse_nmea_stream(text)
            seen.extend(batch)
            candidate = best_fix(seen)
            if candidate is not None and candidate.fix_valid:
                self.last_data = candidate
                return candidate
            if not self.require_fix and batch:
                break

        result = best_fix(seen) or GPSData()
        self.last_data = result
        return result

    def acquire_position(self) -> GPSPosition:
        """Frozen GPSAdapter contract: return a canonical GPSPosition."""
        return self.acquire_gps_data().to_gps_position()

    # ----------------------------------------------------------- constructors

    @classmethod
    def from_serial(
        cls,
        port: str = "/dev/ttyS0",
        baudrate: int = 9600,
        timeout: float = 1.0,
        **kwargs: Any,
    ) -> "NMEAGPSAdapter":
        """Read NMEA directly from a UART device.

        HARDWARE_SPEC_REQUIRED — the UNO Q device node is unconfirmed (`HW-03`).
        """
        from .transport.serial_port import SerialTransport

        transport = SerialTransport(port=port, baudrate=baudrate, timeout=timeout)
        transport.open()

        def read_text() -> str:
            return transport.read_line().decode("ascii", errors="ignore")

        adapter = cls(read_text, require_fix=True, **kwargs)
        adapter._transport = transport  # type: ignore[attr-defined]
        return adapter

    @classmethod
    def from_bridge(cls, method: str = "get_gps_data", **kwargs: Any) -> "NMEAGPSAdapter":
        """Read GPS telemetry from the STM32 via the Arduino RouterBridge.

        The Bridge may return raw NMEA text or a JSON object; both are handled.
        `arduino.app_utils` exists only on the UNO Q, so it is imported lazily.
        """

        def read_text() -> str:
            from arduino.app_utils import Bridge  # type: ignore

            payload = Bridge.call(method)
            return _bridge_payload_to_nmea(payload)

        return cls(read_text, require_fix=True, **kwargs)


def _bridge_payload_to_nmea(payload: Any) -> str:
    """Normalise a Bridge response into NMEA text.

    Accepts a raw sentence, a newline-joined block, or a JSON object carrying
    either an 'nmea'/'sentences' field or already-decoded lat/lon values.
    """
    if payload is None:
        return ""
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("ascii", errors="ignore")
    if not isinstance(payload, str):
        return str(payload)

    text = payload.strip()
    if not text.startswith("{"):
        return text

    try:
        obj = json.loads(text)
    except ValueError:
        return text

    for key in ("nmea", "sentences", "raw"):
        if key in obj:
            value = obj[key]
            return "\n".join(value) if isinstance(value, list) else str(value)

    # Pre-decoded JSON fix: synthesise a GGA so one parser handles every source.
    lat, lon = obj.get("lat", obj.get("latitude")), obj.get("lon", obj.get("longitude"))
    if lat is None or lon is None:
        return ""
    return _synthesise_gga(
        float(lat), float(lon),
        fix_quality=int(obj.get("fix", obj.get("fix_quality", 1))),
        satellites=int(obj.get("sats", obj.get("satellites", 0))),
        hdop=float(obj.get("hdop", 0.0) or 0.0),
        altitude_m=float(obj.get("alt", obj.get("altitude_m", 0.0)) or 0.0),
        utc_time=str(obj.get("time", obj.get("utc_time", "")) or ""),
    )


def _synthesise_gga(
    latitude: float,
    longitude: float,
    fix_quality: int = 1,
    satellites: int = 0,
    hdop: float = 0.0,
    altitude_m: float = 0.0,
    utc_time: str = "",
) -> str:
    """Build a checksummed $GNGGA sentence from decoded values."""

    def encode(value: float, degree_digits: int) -> str:
        magnitude = abs(value)
        degrees = int(magnitude)
        minutes = (magnitude - degrees) * 60.0
        return "{:0{}d}{:07.4f}".format(degrees, degree_digits, minutes)

    body = "GNGGA,{},{},{},{},{},{},{:02d},{:.1f},{:.1f},M,0.0,M,,".format(
        utc_time,
        encode(latitude, 2), "N" if latitude >= 0 else "S",
        encode(longitude, 3), "E" if longitude >= 0 else "W",
        fix_quality, satellites, hdop, altitude_m,
    )
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return "${}*{:02X}".format(body, checksum)
