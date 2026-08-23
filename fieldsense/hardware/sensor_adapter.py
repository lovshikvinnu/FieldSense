"""Hardware Sensor Adapter implementation of SensorAdapter contract."""

import json
from typing import Optional, List
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


class HardwareSensorAdapter(SensorAdapter):
    """Hardware Sensor Adapter implementing frozen SensorAdapter interface.

    Acquires raw physical measurements via SensorTransport and GPS positions via GPSAdapter,
    then transforms them into canonical FieldSample objects tagged with SampleSource.HARDWARE.
    """

    def __init__(
        self,
        transport: Optional[SensorTransport] = None,
        gps_adapter: Optional[GPSAdapter] = None,
    ) -> None:
        """Initialize HardwareSensorAdapter with transport and GPS dependencies."""
        self.transport = transport or MockHardwareTransport()
        self.gps_adapter = gps_adapter or VirtualGPSAdapter()
        self._sample_counter = 0

    def initialize(self) -> None:
        """Initialize physical hardware interfaces."""
        self.transport.open()
        self.gps_adapter.initialize()

    def acquire_sample(self) -> FieldSample:
        """Acquire a single canonical FieldSample from hardware.

        Returns:
            FieldSample tagged with SampleSource.HARDWARE.

        Raises:
            HardwareError: On transport, timeout, or hardware error.
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
            )
        except Exception as err:
            raise HardwareError(
                HardwareErrorCode.MALFORMED_RESPONSE,
                f"Malformed raw sensor payload: {err}",
            ) from err

        # 2. Acquire GPS position fix
        gps_pos = self.gps_adapter.acquire_position()
        if not gps_pos.fix_valid:
            raise HardwareError(
                HardwareErrorCode.GPS_NO_FIX,
                "GPS fix is invalid. Cannot create GPS-tagged sample.",
            )

        # 3. Construct canonical FieldSample
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
            measurement_quality=1.0,
        )

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
