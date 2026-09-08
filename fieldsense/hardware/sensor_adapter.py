"""Hardware Sensor Adapter implementation of SensorAdapter contract."""

import json
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone

from fieldsense.domain.contracts.sensor import SensorAdapter
from fieldsense.domain.models import FieldSample, FieldSession, SampleSource, ValidationState
from fieldsense.hardware.models import (
    RawSensorReading,
    HardwareError,
    HardwareErrorCode,
)
from fieldsense.hardware.transport import SensorTransport, MockHardwareTransport
from fieldsense.hardware.gps import GPSAdapter, VirtualGPSAdapter

# Canonical measurement keys the transport contract must supply.
MEASUREMENT_FIELDS = (
    "nitrogen", "phosphorus", "potassium", "ph", "ec", "moisture", "temperature",
)


#: Below this, the position is reported as weak. Mirrors the 0.70 the
#: ValidationEngine already treats as the good/warning boundary, so the two
#: numbers are read on the same scale. This flags; it never invalidates.
POSITION_CONFIDENCE_WARN = 0.70


class HardwareSensorAdapter(SensorAdapter):
    """Hardware Sensor Adapter implementing frozen SensorAdapter interface.

    Acquires raw physical measurements via SensorTransport and GPS positions via GPSAdapter,
    then transforms them into canonical FieldSample objects tagged with SampleSource.HARDWARE.
    """

    def __init__(
        self,
        transport: Optional[SensorTransport] = None,
        gps_adapter: Optional[GPSAdapter] = None,
        require_gps_fix: bool = True,
    ) -> None:
        """Initialize HardwareSensorAdapter with transport and GPS dependencies.

        Args:
            transport: Byte-oriented sensor transport.
            gps_adapter: Position source.
            require_gps_fix: When True (the default, and the bench contract),
                a sample without a GPS fix raises GPS_NO_FIX. Field deployments
                set this False so a cold-start receiver degrades the sample's
                measurement_quality instead of aborting the campaign — a
                receiver needs minutes for its first fix, and refusing to
                record anything until then means an unattended boot produces
                nothing at all.
        """
        self.transport = transport or MockHardwareTransport()
        self.gps_adapter = gps_adapter or VirtualGPSAdapter()
        self.require_gps_fix = require_gps_fix
        self._sample_counter = 0
        self.last_acquisition_meta: Dict[str, Any] = {}

    def initialize(self) -> None:
        """Initialize physical hardware interfaces."""
        self.transport.open()
        self.gps_adapter.initialize()

    def acquire_sample(self) -> FieldSample:
        """Acquire a single canonical FieldSample from hardware.

        Returns:
            FieldSample tagged with SampleSource.HARDWARE. `measurement_quality`
            is derived from actual acquisition health, never assumed.

        Raises:
            HardwareError: On transport, timeout, or malformed-payload error,
                and on a missing GPS fix when `require_gps_fix` is set.
        """
        if not self.transport.is_open:
            raise HardwareError(
                HardwareErrorCode.DEVICE_NOT_INITIALIZED,
                "Hardware sensor transport is not initialized.",
            )

        # 1. Read raw sensor bytes from transport
        raw_bytes = self.transport.read()
        try:
            raw_dict = json.loads(raw_bytes.decode("utf-8"))
            raw_reading = RawSensorReading(
                nitrogen=float(raw_dict["nitrogen"]),
                phosphorus=float(raw_dict["phosphorus"]),
                potassium=float(raw_dict["potassium"]),
                ph=float(raw_dict["ph"]),
                ec=float(raw_dict["ec"]),
                moisture=float(raw_dict["moisture"]),
                temperature=float(raw_dict["temperature"]),
                metadata=dict(raw_dict.get("_meta") or {}),
            )
        except Exception as err:
            raise HardwareError(
                HardwareErrorCode.MALFORMED_RESPONSE,
                f"Malformed raw sensor payload: {err}",
            ) from err

        # 2. Acquire GPS position fix
        gps_pos = self.gps_adapter.acquire_position()
        if not gps_pos.fix_valid and self.require_gps_fix:
            raise HardwareError(
                HardwareErrorCode.GPS_NO_FIX,
                "GPS fix is invalid. Cannot create GPS-tagged sample.",
            )

        # 3. Derive measurement quality from what actually happened during
        #    acquisition. Asserting 1.0 unconditionally would hide a no-fix
        #    receiver and a half-answered probe from the ValidationEngine,
        #    which is the only component allowed to judge a sample.
        quality, position_confidence = self._derive_quality(
            gps_pos, raw_reading.metadata)
        self.last_acquisition_meta = {
            "gps_fix_valid": bool(gps_pos.fix_valid),
            "gps_quality": dict(gps_pos.quality or {}),
            "sensor_meta": dict(raw_reading.metadata),
            "measurement_quality": quality,
            # Positional confidence is REPORTED, not folded into the score the
            # soil verdict is taken from. See _derive_quality.
            "position_confidence": position_confidence,
            "position_weak": position_confidence < POSITION_CONFIDENCE_WARN,
        }

        # 4. Construct canonical FieldSample
        self._sample_counter += 1
        sample_id = f"HW-SMP-{self._sample_counter:03d}"
        now_iso = datetime.now(timezone.utc).isoformat()

        return FieldSample(
            sample_id=sample_id,
            timestamp=now_iso,
            latitude=gps_pos.latitude,
            longitude=gps_pos.longitude,
            nitrogen=raw_reading.nitrogen,
            phosphorus=raw_reading.phosphorus,
            potassium=raw_reading.potassium,
            ph=raw_reading.ph,
            ec=raw_reading.ec,
            moisture=raw_reading.moisture,
            temperature=raw_reading.temperature,
            source=SampleSource.HARDWARE,
            validation_state=ValidationState.VALID,
            measurement_quality=quality,
        )

    def _derive_quality(self, gps_pos, sensor_meta: Dict[str, Any]):
        """Score the SOIL measurement, and the position, as two numbers.

        WHY THESE ARE NOT ONE NUMBER ANY MORE
        -------------------------------------
        They used to be multiplied together, and a field session lost all five
        samples to it. session_20260907T073053Z read 7 of 7 registers on every
        sample with no read errors and returned live, varying soil - EC
        0.070-0.129, pH 6.24-6.43, N 5-9, P 7-12, K 14-25 - and every sample
        came back SUSPICIOUS and map-ineligible.

        The arithmetic made it unavoidable. The combined score was
        gps_factor x hdop_factor x satellite_factor x completeness, and with
        fewer than five satellites satellite_factor is 0.75, so the ceiling was
        0.92 x 1.00 x 0.75 x 1.00 = 0.69 against a 0.70 threshold. No sample
        taken on four satellites could be VALID however good the probe reading
        was. The operator walked a field for nothing.

        A weak fix is a real problem, but it is a problem with the LOCATION. It
        says nothing about whether the probe read the soil, and folding it into
        the same number made the soil verdict answer a question about the sky.
        So the soil score is now completeness alone, and the positional term is
        returned beside it to be recorded and flagged.

        Args:
            gps_pos: The acquired GPSPosition.
            sensor_meta: The transport's `_meta` block, when it supplies one.

        Returns:
            (measurement_quality, position_confidence), both rounded to three
            decimals. A transport that reports no metadata is treated as a
            complete read, preserving the behaviour of the mock transports.
        """
        from fieldsense.hardware.gps_adapter import GPSData
        from fieldsense.hardware.hardware_sample_adapter import derive_measurement_quality
        from fieldsense.hardware.soil_adapter import JXBS_REGISTERS, SoilData

        gps_quality = gps_pos.quality or {}
        gps_view = GPSData(
            latitude=gps_pos.latitude,
            longitude=gps_pos.longitude,
            fix_quality=int(gps_quality.get("fix_quality", 1 if gps_pos.fix_valid else 0)),
            satellites=int(gps_quality.get("satellites", 0) or 0),
            hdop=gps_quality.get("hdop"),
        )

        expected = len(JXBS_REGISTERS)
        read = int(sensor_meta.get("parameters_read", expected) or 0) if sensor_meta else expected
        # Fabricate a SoilData carrying only the completeness signal the policy
        # reads. Values themselves are already in the FieldSample.
        soil_view = SoilData(**{
            name: 0.0 for name in list(JXBS_REGISTERS)[:max(0, min(read, expected))]
        })

        # The soil score, from completeness alone. Reuses the one policy rather
        # than restating the ratio, by handing it a position it cannot mark
        # down: the GPS terms all evaluate to 1.0 for a DGPS fix at HDOP 0.
        perfect_position = GPSData(latitude=0.0, longitude=0.0, fix_quality=2,
                                   satellites=99, hdop=0.0)
        measurement_quality = derive_measurement_quality(perfect_position, soil_view)

        # The positional score, from the GPS terms alone - same trick the other
        # way round: a complete soil read contributes a factor of 1.0.
        full_soil = SoilData(**{name: 0.0 for name in JXBS_REGISTERS})
        position_confidence = derive_measurement_quality(gps_view, full_soil)

        return measurement_quality, position_confidence

    def get_sample(self) -> FieldSample:
        """Alias for acquire_sample()."""
        return self.acquire_sample()

    def get_all_samples(self) -> List[FieldSample]:
        """Acquire a list of samples from hardware."""
        return [self.acquire_sample()]

    def collect_session(self, session_id: str, field_name: str = "Hardware Field") -> FieldSession:
        """Collect a FieldSession containing hardware samples."""
        now_iso = datetime.now(timezone.utc).isoformat()
        session = FieldSession(session_id=session_id, field_name=field_name, created_at=now_iso)
        sample = self.acquire_sample()
        session.add_sample(sample)
        return session

    def shutdown(self) -> None:
        """Shutdown hardware interfaces."""
        self.transport.close()
        self.gps_adapter.shutdown()
