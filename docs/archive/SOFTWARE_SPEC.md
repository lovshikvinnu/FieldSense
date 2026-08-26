# FieldSense AI — Software Specification

**STATUS:** DRAFT  
**VERSION:** 0.1  
**LAST UPDATED:** 2026-08-21  
**SOFTWARE BASELINE:** FROZEN (`PHASE_1_RELEASE_READY`)  

---

## 1. Software Architecture & Repository Structure

FieldSense AI is structured into 11 strictly decoupled Python modules under the core `fieldsense/` package namespace. All modules use Python 3.10+ standard libraries exclusively (`dataclasses`, `enum`, `datetime`, `math`, `json`, `uuid`, `xml.etree`). Heavy third-party dependencies (e.g. NumPy, SciPy, Pandas, PyTorch) are strictly prohibited.

```text
fieldsense/
├── domain/            # Pure data contracts (FieldSample, FieldSession, Enums)
├── input/             # Virtual sensor simulation adapter
├── hardware/          # Hardware transports, GPS adapter, HardwareSensorAdapter
├── intelligence/      # Validation, normalization, and MCDA scoring engines
│   ├── validation/    # Gatekeeper validation engine & sanity thresholds
│   ├── normalization/ # Metric normalization & reference band functions
│   └── scoring/       # Component indices (Soil Health, N, Moisture, Carbon)
├── spatial/           # Cartesian projection, bounds, grid, and IDW interpolator
├── zones/             # 4-neighbor BFS graph zone detection & merging engine
├── recommendations/   # Rule-based decision-support engine & agronomic rules
├── presentation/      # UIViewAdapter and standalone offline HTML/SVG renderer
├── storage/           # Session serialization abstractions
├── testing/           # Golden scenarios, fault injection, & benchmark suites
└── demo.py            # End-to-end competition showcase runner
```

---

## 2. Canonical Domain Model — FieldSample

`FieldSample` (`fieldsense/domain/models/sample.py`) is the immutable canonical data contract representing a single physical or virtual soil observation.

### Invariants & Guarantees
1. **Immutability**: Class is decorated `@dataclass(frozen=True)`. Raw readings cannot be silently altered downstream.
2. **Canonical Data Container**: All downstream validation, scoring, spatial, and presentation engines consume `FieldSample` instances exclusively.
3. **Serialization Integrity**: Implements `to_dict()` and `from_dict()` with strict ISO-8601 UTC timestamp parsing.

### Schema Fields

| Field Name | Type | Physical Units | Constraints / Valid Range |
| :--- | :--- | :--- | :--- |
| `sample_id` | `str` | UUIDv4 | Non-empty string |
| `timestamp` | `datetime` | ISO-8601 UTC | Valid timezone-aware datetime |
| `latitude` | `float` | Decimal Degrees | $[-90.0, +90.0]$ |
| `longitude` | `float` | Decimal Degrees | $[-180.0, +180.0]$ |
| `nitrogen` | `float` | $\text{mg/kg}$ (ppm) | $[0.0, 1000.0]$ |
| `phosphorus` | `float` | $\text{mg/kg}$ (ppm) | $[0.0, 500.0]$ |
| `potassium` | `float` | $\text{mg/kg}$ (ppm) | $[0.0, 1500.0]$ |
| `ph` | `float` | $\text{pH}$ scale | $[0.0, 14.0]$ |
| `ec` | `float` | $\mu\text{S/cm}$ | $[0.0, 20000.0]$ |
| `moisture` | `float` | $\text{VWC}\%$ | $[0.0, 100.0]$ |
| `temperature` | `float` | $^\circ\text{C}$ | $[-40.0, +80.0]$ |
| `measurement_quality`| `float` | Confidence scale | $[0.0, 1.0]$ |
| `source` | `SampleSource`| Enum | `VIRTUAL` or `HARDWARE` |
| `validation_state` | `ValidationState`| Enum | `VALID`, `VALID_WITH_WARNING`, `REJECTED` |

---

## 3. Sampling Campaign Model — FieldSession

`FieldSession` (`fieldsense/domain/models/session.py`) encapsulates a complete multi-sample field acquisition campaign.

### Behavioral Rules
- **Attributes**: `session_id`, `name`, `created_at`, `status` (`ACTIVE`, `COMPLETED`, `ABORTED`), `samples` (`List[FieldSample]`), `metadata` (`dict`).
- **Raw Sample Integrity**: `FieldSession.samples` retains **all** collected samples—including rejected ones—guaranteeing operational auditability.
- **Read-Only Pipeline Filtering**: The property `valid_samples` filters for samples marked `pipeline_eligible = True` without mutating the underlying `samples` list.

---

## 4. Sensor Abstraction Boundary

`SensorAdapter` (`fieldsense/domain/contracts/sensor.py`) defines the abstract interface for all data acquisition sources:

```python
class SensorAdapter(ABC):
    @abstractmethod
    def initialize(self) -> bool: ...
    @abstractmethod
    def acquire_sample(self, lat: float, lon: float) -> FieldSample: ...
    @abstractmethod
    def shutdown(self) -> None: ...
```

### Implementations
- `VirtualSensorAdapter` (`fieldsense/input/virtual_sensor.py`): Generates deterministic multi-point test fields with configurable gradients, Gaussian hotspots, noise levels, fixed seeds, and fault profiles (`OUTLIER`, `UNSTABLE_MEASUREMENT`).
- `HardwareSensorAdapter` (`fieldsense/hardware/sensor_adapter.py`): Interfaces with physical hardware transports (`SensorTransport` and `GPSAdapter`), converting Modbus registers and NMEA strings into canonical `FieldSample` objects.

---

## 5. Automated Validation Engine

`ValidationEngine` (`fieldsense/intelligence/validation/engine.py`) acts as the automated data quality gatekeeper.

### Validation State Hierarchy & Rules
1. `REJECTED`: Triggered when physical metrics violate hard physical limits (e.g. $\text{pH} > 14$, $\text{Moisture} < 0\%$) or exhibit hardware instability flags.
   - **Behavior**: Flagged `pipeline_eligible = False`. Excluded from spatial raster interpolation and zone clustering, but preserved in `FieldSession` diagnostics for auditability.
2. `VALID_WITH_WARNING`: Triggered when metrics fall on operational boundaries (e.g. extremely high EC).
   - **Behavior**: Flagged `pipeline_eligible = True`. Included in spatial rasters with attached diagnostic warning codes.
3. `VALID`: Clean, physically plausible measurement.
   - **Behavior**: Flagged `pipeline_eligible = True`.

---

## 6. Normalization & Piecewise Scoring Curves

`SampleNormalizer` (`fieldsense/intelligence/normalization/normalizer.py`) converts raw physical values into dimensionless optimality scores $[0.0, 1.0]$.

- Uses non-linear piecewise linear functions and optimum reference bands (e.g., optimum soil $\text{pH}$ band $6.0 - 7.5$).
- Explicit Status: `PROTOTYPE_ONLY` / `AGRONOMIC_VALIDATION_REQUIRED` (`methodology_version = "0.1"`).

---

## 7. Deterministic Scoring Engine & MCDA

`IntelligenceEngine` (`fieldsense/intelligence/engine.py`) coordinates normalized metric scoring and component index synthesis.

### Multi-Criteria Decision Analysis (MCDA) Weighting Vector
Overall **Soil Health Index** ($[0.0, 1.0]$) is computed using weighted MCDA aggregation:

$$\text{SoilHealth} = 0.20 S_N + 0.15 S_P + 0.15 S_K + 0.20 S_{\text{pH}} + 0.10 S_{\text{EC}} + 0.20 S_{\text{Moisture}}$$

### Carbon Readiness Proxy Boundary
`CarbonReadinessResult` evaluates soil physical suitability for organic carbon retention:
- **Decision-Support Boundary**: Enforces `decision_support_only = True` and `evidence_level = "LIMITED"`.
- **Explicit Missing Indicators**:
  ```python
  missing_indicators = [
      "soil_organic_carbon",
      "bulk_density",
      "management_history"
  ]
  ```
- **Prohibited Claims**: Direct SOC mass measurement, carbon sequestration tonnage, and MRV/carbon credit certification claims are strictly prohibited.

---

## 8. Spatial Intelligence & IDW Interpolation Engine

`SpatialEngine` (`fieldsense/spatial/engine.py`) transforms discrete point observations into continuous 2D raster grids.

### Spatial Algorithms & Rules
1. **Local Cartesian Meter Projection**: Latitude and longitude coordinates are projected into local Cartesian meters $(x,y)$ using equirectangular projection centered on sample centroid.
2. **Inverse Distance Weighting (IDW)**: Continuous surface values are calculated using power parameter $p=2.0$:
   $$w_i = \frac{1}{d_i^2}, \quad Z(x,y) = \frac{\sum w_i z_i}{\sum w_i}$$
3. **Minimum Sample Constraint**: Requires minimum $N \ge 3$ valid samples. If $N < 3$, spatial engine returns `is_valid = False` without attempting interpolation.
4. **Maximum Support Distance**: Capped at $100\text{m}$. Grid nodes located $> 100\text{m}$ from the nearest valid sample point return `None` (unsupported) to prevent arbitrary extrapolation.
5. **Default Grid Resolution**: Configurable $10\text{m} \times 10\text{m}$ grid cells.

---

## 9. Management Zone Detection Engine

`ZoneEngine` (`fieldsense/zones/engine.py`) partitions continuous spatial grids into discrete contiguous management zones.

### Clustering Algorithms & Boundaries
1. **4-Neighbor BFS Graph Clustering**: Connects grid cells sharing adjacent edges into contiguous component regions.
2. **Zone Classifications**:
   - `HEALTHY`: Score $\ge 0.70$
   - `MODERATE`: $0.45 \le \text{Score} < 0.70$
   - `POOR`: Score $< 0.45$
3. **Small Component Merging**: Contiguous regions smaller than 2 grid cells ($< 200\text{m}^2$) are merged into neighboring zones.
4. **Primary Issue Identification**: Selected by lowest metric score with deterministic tie-breaking ($N > \text{Moisture} > \text{pH} > \text{Salinity}$).
5. **Spatial Support Confidence**: Indicates spatial sample density within the zone (`HIGH`, `MEDIUM`, `LOW`), **not** agronomic certainty.

---

## 10. Rule-Based Recommendation Engine

`RecommendationEngine` (`fieldsense/recommendations/engine.py`) evaluates detected zone issues against deterministic rule matrices to generate actionable recommendations.

### Agronomic Safety & Prescription Rules
- **Rule Categories**: `NUTRIENT`, `WATER`, `SOIL_CONDITION`, `SALINITY`, `CARBON_READINESS`, `MONITORING`.
- **Directional Guidance Only**: Emits qualitative, traceable advice (e.g. *"Review nitrogen availability in Zone Z02"*).
- **ZERO QUANTITATIVE DOSAGES**: System **never** outputs chemical or fertilizer quantities (e.g. *"Apply 30 kg/ha Urea"*) or irrigation volumes.
- **Constraints**: Maximum 3 recommendations per zone; stable rule IDs; automated deduplication.

---

## 11. Passive Presentation Layer & Local UI Renderer

`LocalUIRenderer` (`fieldsense/presentation/renderer.py`) compiles self-contained HTML/CSS/SVG dashboards.

### UI Contract & Presentation Boundaries
- **Passive Contract**: UI consumes `UIFieldView` view models built by `UIViewAdapter`. Contains zero calculation or scoring logic.
- **Zero External Network Dependencies**: Operates 100% offline without external JS libraries, remote CSS fonts, or web map tiles.
- **Native SVG Generation**: Renders continuous spatial raster heatmaps, management zones, and layer switching controls as inline SVG vector graphics.

---

## 12. Hardware Integration Adapter Boundary

Hardware communication interfaces (`fieldsense/hardware/`) isolate physical communication details from the deterministic core software pipeline:

### Verified Physical Hardware Adapter Paths
- **GPS Adapter Path**: `NEO-M8N` $\rightarrow$ `Serial1` $\rightarrow$ `STM32 MCU` $\rightarrow$ `Arduino Bridge/RPC` (`get_gps_data`) $\rightarrow$ `Linux/Python`.
- **JXBS Soil Sensor Acquisition Path**: `JXBS 7-in-1` $\rightarrow$ `USB-RS485` $\rightarrow$ `USB-C Hub` $\rightarrow$ `Linux/Python` (`HardwareSensorAdapter` / Modbus RTU 9600 8N1).
- **TFT Display Boundary**: Application/UI $\rightarrow$ `Native Hardware SPI` $\rightarrow$ `ST7789` ($320 \times 240$ landscape).
- **Touch Boundary**: Application/UI $\rightarrow$ `XPT2046 touch interface` $\rightarrow$ mapped $320 \times 240$ display coordinates.

### Software Pipeline Preservation Guarantee
> [!IMPORTANT]
> The existing Phase 1 software architecture remains unchanged and strictly protected:
> $$\text{Validation} \longrightarrow \text{Normalization} \longrightarrow \text{Scoring} \longrightarrow \text{Spatial IDW} \longrightarrow \text{Zone Clustering} \longrightarrow \text{Recommendations} \longrightarrow \text{Presentation}$$
> The hardware integration work establishes physical hardware acquisition and UI presentation paths strictly around the unchanged deterministic core.

- `HardwareSensorAdapter`: Adapts physical transports to `SensorAdapter` contract.
- `SensorTransport`: Abstract base class for serial communication (implemented by `MockHardwareTransport`).
- `GPSAdapter`: Abstract base class for NMEA position fixes (implemented by `MockGPSAdapter`).
- **Structured Exception Hierarchy**: `HardwareConnectionError`, `ModbusTimeoutError`, `GPSFixError`.

---

## 13. AI Explanation Boundary

The AI Explanation Layer is optional and strictly decoupled downstream:

$$\text{Deterministic Pipeline Results} \longrightarrow \text{Structured JSON Context} \longrightarrow \text{Edge LLM Explainer}$$

- Generative AI modules consume structured JSON output as read-only context.
- AI modules cannot recalculate, modify, or override deterministic scores, spatial maps, or recommendations.
- AI modules cannot invent quantitative chemical prescriptions or unverified carbon credit claims.
