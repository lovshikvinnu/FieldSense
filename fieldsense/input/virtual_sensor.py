"""Virtual Sensor Adapter and Deterministic Field Generator."""

import math
import random
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from fieldsense.domain.contracts.sensor import SensorAdapter
from fieldsense.domain.models import (
    FieldSample,
    FieldSession,
    SampleSource,
    SessionStatus,
    ValidationState,
)


class FieldScenario(str, Enum):
    """Pre-configured virtual field simulation test scenarios."""
    NORMAL = "NORMAL"
    WITH_OUTLIER = "WITH_OUTLIER"
    WITH_UNSTABLE = "WITH_UNSTABLE"


class VirtualSensorAdapter(SensorAdapter):
    """Deterministic virtual sensor adapter implementing SensorAdapter.

    Generates synthetic, spatially structured field samples for offline testing
    and pipeline simulation without physical hardware dependencies.
    """

    def __init__(
        self,
        seed: int = 42,
        num_samples: int = 25,
        base_latitude: float = 12.9716,
        base_longitude: float = 77.5946,
        scenario: FieldScenario = FieldScenario.NORMAL,
        outlier_index: Optional[int] = None,
        unstable_index: Optional[int] = None,
    ) -> None:
        """Initialize the virtual sensor adapter.

        Args:
            seed: Random seed for deterministic sample generation.
            num_samples: Total number of samples in the field (default 25, forming a 5x5 grid).
            base_latitude: Origin latitude for local field area.
            base_longitude: Origin longitude for local field area.
            scenario: Test scenario mode (NORMAL, WITH_OUTLIER, WITH_UNSTABLE).
            outlier_index: Explicit index for injecting a extreme outlier sample (if requested).
            unstable_index: Explicit index for injecting a low-quality/unstable sample (if requested).
        """
        self.seed = seed
        self.num_samples = max(1, num_samples)
        self.base_latitude = base_latitude
        self.base_longitude = base_longitude
        self.scenario = scenario

        # Configure outlier sample index if requested or specified by scenario
        if scenario == FieldScenario.WITH_OUTLIER and outlier_index is None:
            self.outlier_index = self.num_samples // 2
        else:
            self.outlier_index = outlier_index

        # Configure unstable sample index if requested or specified by scenario
        if scenario == FieldScenario.WITH_UNSTABLE and unstable_index is None:
            self.unstable_index = (self.num_samples // 2) + 1 if self.num_samples > 1 else 0
        else:
            self.unstable_index = unstable_index

        self.initialized = False
        self._samples: List[FieldSample] = []
        self._current_index = 0

    def initialize(self) -> None:
        """Initialize the virtual adapter and generate the field sample stream."""
        self._rng = random.Random(self.seed)
        self._samples = self._generate_field_samples()
        self._current_index = 0
        self.initialized = True

    def _generate_field_samples(self) -> List[FieldSample]:
        """Generate spatially coherent field samples deterministically."""
        samples: List[FieldSample] = []
        now = datetime.now(timezone.utc)

        # Calculate grid dimensions (approx square grid)
        side = int(math.ceil(math.sqrt(self.num_samples)))
        cell_size_deg = 0.00015  # ~15-20 meters per grid cell

        for i in range(self.num_samples):
            r = i // side
            c = i % side

            # Spatial coordinates with deterministic local jitter
            lat_jitter = self._rng.uniform(-0.00002, 0.00002)
            lon_jitter = self._rng.uniform(-0.00002, 0.00002)
            lat = round(self.base_latitude + r * cell_size_deg + lat_jitter, 6)
            lon = round(self.base_longitude + c * cell_size_deg + lon_jitter, 6)

            # Normalized grid relative position [0.0, 1.0]
            norm_r = r / (side - 1) if side > 1 else 0.5
            norm_c = c / (side - 1) if side > 1 else 0.5

            # Latent spatial quality factor:
            # High in Top-Left (r=0, c=0) -> 1.0 (Healthy zone)
            # Low in Bottom-Right (r=side-1, c=side-1) -> 0.0 (Poor zone)
            spatial_factor = 1.0 - 0.5 * (norm_r + norm_c)
            spatial_factor = max(0.0, min(1.0, spatial_factor))

            # Small local noise variation
            noise = self._rng.uniform(-0.04, 0.04)
            s_val = max(0.0, min(1.0, spatial_factor + noise))

            # Chemical measurements generated around spatial gradient:
            # Healthy: N=75.0, P=35.0, K=220.0, pH=6.8, EC=1.5, moisture=38.0, temp=22.0
            # Poor:    N=18.0, P=10.0, K=70.0,  pH=5.4, EC=0.6, moisture=14.0, temp=27.0
            nitrogen = round(18.0 + s_val * 57.0 + self._rng.uniform(-2.0, 2.0), 2)
            phosphorus = round(10.0 + s_val * 25.0 + self._rng.uniform(-1.0, 1.0), 2)
            potassium = round(70.0 + s_val * 150.0 + self._rng.uniform(-5.0, 5.0), 2)
            ph = round(5.4 + s_val * 1.4 + self._rng.uniform(-0.1, 0.1), 2)
            ec = round(0.6 + s_val * 0.9 + self._rng.uniform(-0.05, 0.05), 2)
            moisture = round(14.0 + s_val * 24.0 + self._rng.uniform(-1.0, 1.0), 2)
            temperature = round(27.0 - s_val * 5.0 + self._rng.uniform(-0.5, 0.5), 2)

            quality = round(0.90 + self._rng.uniform(0.0, 0.09), 2)
            val_state = ValidationState.VALID

            # Inject controlled test conditions if triggered
            if self.outlier_index is not None and i == self.outlier_index:
                nitrogen = 350.0
                ph = 3.1
                phosphorus = 120.0

            if self.unstable_index is not None and i == self.unstable_index:
                quality = 0.15
                val_state = ValidationState.VALID_WITH_WARNING

            sample = FieldSample(
                sample_id=f"VIRT-{self.seed:04d}-{i + 1:03d}",
                timestamp=now,
                latitude=lat,
                longitude=lon,
                nitrogen=nitrogen,
                phosphorus=phosphorus,
                potassium=potassium,
                ph=ph,
                ec=ec,
                moisture=moisture,
                temperature=temperature,
                measurement_quality=quality,
                source=SampleSource.VIRTUAL,
                validation_state=val_state,
            )
            samples.append(sample)

        return samples

    def acquire_sample(self) -> FieldSample:
        """Acquire the next FieldSample from the virtual adapter."""
        if not self.initialized:
            self.initialize()

        if not self._samples:
            raise RuntimeError("No virtual samples generated.")

        sample = self._samples[self._current_index]
        self._current_index = (self._current_index + 1) % len(self._samples)
        return sample

    def get_all_samples(self) -> List[FieldSample]:
        """Return all generated field samples at once."""
        if not self.initialized:
            self.initialize()
        return list(self._samples)

    def populate_session(self, session: FieldSession) -> FieldSession:
        """Populate an existing FieldSession with all virtual field samples."""
        if not self.initialized:
            self.initialize()
        for sample in self._samples:
            session.add_sample(sample)
        return session

    def collect_session(self, session_id: str, field_name: Optional[str] = None) -> FieldSession:
        """Create and populate a new FieldSession with all virtual field samples."""
        session = FieldSession(
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
            status=SessionStatus.COLLECTING,
            field_name=field_name,
        )
        return self.populate_session(session)

    def shutdown(self) -> None:
        """Shutdown the adapter and clear state."""
        self.initialized = False
        self._current_index = 0
