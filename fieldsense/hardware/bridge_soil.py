"""JXBS soil telemetry over the STM32 RouterBridge — the MCU-side probe path.

The repository carries two physically different soil wirings, and until now
only one of them had a Python consumer:

    JXBS -> MAX485 -> FT232 USB dongle -> QRB2210 Linux   /dev/ttyUSB0
        handled by JXBSSoilAdapter / StdlibModbusTransport

    JXBS -> MAX485 -> STM32U585 Serial1 -> RouterBridge -> QRB2210 Linux
        handled HERE

The second wiring is the one the bench sketch in
`hardware/soil-probe-unoq/sketch.ino` verified. The
STM32 owns the RS485 direction pin because Linux cannot meet the turnaround
deadline, publishes the decoded reading as a JSON string, and exposes it as
the Bridge method `get_soil_data`. Without this module that reading could not
reach the pipeline at all — the MCU had a producer and the host had no reader.

WIRE FORMAT, as emitted by the sketch
-------------------------------------
    {"temp":22.5,"moisture":25.0,"ph":6.89,"ec":603,"n":43,"p":60,"k":120}
    {"error":"MODBUS_READ_FAILED"}

Two boundary conversions happen here and nowhere else:

    1. Field names. The sketch uses the short MCU names `temp`, `n`, `p`, `k`.
       The FieldSample contract uses `temperature`, `nitrogen`, `phosphorus`,
       `potassium`. Forwarding the short names raises MALFORMED_RESPONSE.
    2. EC units. The sketch forwards the raw register in uS/cm. The validation
       contract bounds EC to 0.0-10.0 dS/m. The conversion is UNCONDITIONAL
       (see `us_cm_to_ds_m`), never threshold-based — a threshold silently
       mislabels both very low and very high salinity readings.
"""

import json
import socket
from typing import Any, Dict, Optional, Tuple

from .models import HardwareError, HardwareErrorCode
from .soil_adapter import SoilData, us_cm_to_ds_m
from .transport.base import SensorTransport

try:  # present only on the Arduino UNO Q
    from arduino.app_utils import Bridge  # type: ignore
except Exception:  # pragma: no cover - off-target default
    Bridge = None  # type: ignore

BRIDGE_SOIL_METHOD = "get_soil_data"

# Sketch field name -> canonical FieldSample field name.
FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "temperature": ("temperature", "temp", "t"),
    "moisture":    ("moisture", "hum", "humidity", "m"),
    "ph":          ("ph", "pH"),
    "ec":          ("ec", "conductivity"),
    "nitrogen":    ("nitrogen", "n"),
    "phosphorus":  ("phosphorus", "p"),
    "potassium":   ("potassium", "k"),
}

# Every canonical measurement key the FieldSample contract requires.
CANONICAL_FIELDS = tuple(FIELD_ALIASES)


def normalise_bridge_payload(payload: Any) -> SoilData:
    """Decode one `get_soil_data` response into canonical SoilData.

    Args:
        payload: Bridge response: a JSON string, bytes, or an already-decoded
            mapping.

    Returns:
        SoilData with EC in dS/m. Missing or unparseable fields are left None
        and recorded in `read_errors`, so a partial reading degrades the sample
        instead of destroying it.

    Raises:
        HardwareError: The payload is empty or is not a JSON object at all.
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="ignore")

    if payload is None or (isinstance(payload, str) and not payload.strip()):
        raise HardwareError(
            HardwareErrorCode.MALFORMED_RESPONSE, "Empty response from soil bridge"
        )

    if isinstance(payload, dict):
        obj: Dict[str, Any] = payload
    else:
        text = str(payload).strip()
        try:
            obj = json.loads(text)
        except ValueError:
            raise HardwareError(
                HardwareErrorCode.MALFORMED_RESPONSE,
                "Soil bridge payload is not JSON: {!r}".format(text[:120]),
            )
        if not isinstance(obj, dict):
            raise HardwareError(
                HardwareErrorCode.MALFORMED_RESPONSE,
                "Soil bridge payload is not a JSON object: {!r}".format(text[:120]),
            )

    # The sketch reports its own Modbus failure in-band. Surface it as a fully
    # degraded reading rather than an exception: the campaign continues, and
    # ValidationEngine rejects the sample on its zeroed pH.
    if "error" in obj:
        return SoilData(read_errors=["STM32: {}".format(obj["error"])])

    values: Dict[str, Optional[float]] = {}
    errors = []
    raw_registers: Dict[str, int] = {}

    for canonical, aliases in FIELD_ALIASES.items():
        raw = next((obj[a] for a in aliases if a in obj), None)
        if raw is None:
            values[canonical] = None
            errors.append("{}: absent from bridge payload".format(canonical))
            continue
        try:
            values[canonical] = float(raw)
        except (TypeError, ValueError):
            values[canonical] = None
            errors.append("{}: non-numeric value {!r}".format(canonical, raw))

    ec_us_cm = values.get("ec")
    if ec_us_cm is not None:
        raw_registers["ec"] = int(ec_us_cm)

    return SoilData(
        ph=values.get("ph"),
        moisture=values.get("moisture"),
        temperature=values.get("temperature"),
        # Unconditional unit conversion at the boundary. See module docstring.
        ec=us_cm_to_ds_m(ec_us_cm) if ec_us_cm is not None else None,
        nitrogen=values.get("nitrogen"),
        phosphorus=values.get("phosphorus"),
        potassium=values.get("potassium"),
        ec_raw_us_cm=ec_us_cm,
        raw_registers=raw_registers,
        read_errors=errors,
    )


class BridgeSoilAdapter:
    """Reads JXBS telemetry from the STM32 over RouterBridge or a TCP gateway.

    Mirrors `BridgeGPSAdapter` exactly: RouterBridge when running on the UNO Q,
    a localhost TCP gateway when an App Lab helper process is relaying instead.
    `arduino.app_utils` is resolved lazily and stays None off-target, so this
    module imports cleanly on a laptop.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9877,
        timeout: float = 2.0,
        method: str = BRIDGE_SOIL_METHOD,
    ) -> None:
        """Configure the adapter. No transport is contacted until a read.

        Args:
            host: TCP gateway host, used only when RouterBridge is unavailable.
            port: TCP gateway port. Distinct from the GPS gateway's 9876.
            timeout: Socket timeout in seconds.
            method: RouterBridge method name the sketch registered.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.method = method
        self._initialized = False

    def initialize(self) -> None:
        """Mark the adapter ready. Transports are contacted lazily."""
        self._initialized = True

    def shutdown(self) -> None:
        """Release adapter state. Neither transport holds a persistent handle."""
        self._initialized = False

    def read(self) -> SoilData:
        """Fetch and decode the latest soil telemetry.

        Raises:
            HardwareError: No transport reachable, or the payload was unusable.
        """
        return normalise_bridge_payload(self._read_payload())

    def _read_payload(self) -> str:
        """Return the raw payload, preferring RouterBridge over the gateway."""
        if Bridge is not None:
            try:
                payload = Bridge.call(self.method)
            except Exception as exc:
                raise HardwareError(
                    HardwareErrorCode.DEVICE_UNAVAILABLE,
                    "RouterBridge call '{}' failed: {}".format(self.method, exc),
                )
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode("utf-8", errors="ignore")
            return str(payload).strip()

        return self._read_from_gateway()

    def _read_from_gateway(self) -> str:
        """Read one telemetry frame from the local App Lab TCP gateway."""
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                return sock.recv(4096).decode("utf-8", errors="ignore").strip()
        except socket.timeout:
            raise HardwareError(
                HardwareErrorCode.DEVICE_UNAVAILABLE,
                "Soil gateway socket timeout ({}s)".format(self.timeout),
            )
        except ConnectionRefusedError:
            raise HardwareError(
                HardwareErrorCode.DEVICE_UNAVAILABLE,
                "Soil gateway connection refused (is the App Lab main.py running?)",
            )
        except Exception as exc:
            raise HardwareError(
                HardwareErrorCode.DEVICE_UNAVAILABLE,
                "Soil gateway connection error: {}".format(exc),
            )


class BridgeSoilTransport(SensorTransport):
    """SensorTransport facade over BridgeSoilAdapter.

    Lets `HardwareSensorAdapter` consume the STM32 soil path through the same
    byte-oriented contract it already uses for the USB dongle, so the pipeline
    above it is identical for both wirings.
    """

    def __init__(self, adapter: Optional[BridgeSoilAdapter] = None, **kwargs: Any) -> None:
        """Build the transport.

        Args:
            adapter: Optional pre-built BridgeSoilAdapter.
            **kwargs: Forwarded to BridgeSoilAdapter when `adapter` is None.
        """
        self.adapter = adapter or BridgeSoilAdapter(**kwargs)
        self._is_open = False

    def open(self) -> None:
        """Mark the transport open. The Bridge holds no persistent handle."""
        self.adapter.initialize()
        self._is_open = True

    def close(self) -> None:
        """Mark the transport closed."""
        self.adapter.shutdown()
        self._is_open = False

    @property
    def is_open(self) -> bool:
        """Return True once open() has been called."""
        return self._is_open

    def write(self, payload: bytes) -> None:
        """Not supported. The STM32 polls the probe on its own schedule."""
        raise HardwareError(
            HardwareErrorCode.TRANSPORT_ERROR,
            "BridgeSoilTransport is read-only; the STM32 owns the RS485 bus.",
        )

    def read(self, length: int = 256) -> bytes:
        """Return one canonical soil reading as UTF-8 JSON bytes."""
        if not self.is_open:
            raise HardwareError(
                HardwareErrorCode.DEVICE_NOT_INITIALIZED,
                "Bridge soil transport is not open.",
            )
        return soil_data_to_canonical_json(self.adapter.read())


def soil_data_to_canonical_json(soil: SoilData) -> bytes:
    """Serialize SoilData into the JSON byte contract HardwareSensorAdapter reads.

    Every canonical measurement key is always present, so the consumer never
    raises on a partial read. A register that failed is emitted as 0.0, which
    ValidationEngine rejects on its own range bounds — the correct owner of
    that decision. `_meta` carries the acquisition health the sample's
    measurement_quality is derived from.

    Args:
        soil: Decoded soil telemetry, EC already in dS/m.

    Returns:
        UTF-8 encoded JSON bytes.
    """
    payload: Dict[str, Any] = {
        field: (getattr(soil, field) if getattr(soil, field) is not None else 0.0)
        for field in CANONICAL_FIELDS
    }
    payload["_meta"] = {
        "parameters_read": soil.parameters_read,
        "parameters_expected": len(CANONICAL_FIELDS),
        "read_errors": list(soil.read_errors),
        "ec_raw_us_cm": soil.ec_raw_us_cm,
    }
    return json.dumps(payload).encode("utf-8")
