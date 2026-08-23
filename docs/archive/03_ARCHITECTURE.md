# FieldSense AI — Software Architecture

**Document Version:** 1.0  
**Last Updated:** 2026-08-09  
**Project Phase:** Phase 1 Complete  
**Release Status:** `PHASE_1_RELEASE_READY`  

---

## 1. Architecture Status

FieldSense AI Phase 1 software architecture is **FROZEN** and release-ready (`PHASE_1_RELEASE_READY`). The core software pipeline is fully verified by a 105-test regression baseline with zero failures.

All system contracts, data models, layer boundaries, and interface abstractions documented herein are authoritative. AI coding agents and human engineers must adhere strictly to these frozen contracts during Phase 2 physical hardware integration and future development.

---

## 2. Architectural Principles

1. **Deterministic Processing Priority**: All core calculations—validation, normalization, scoring, interpolation, clustering, and recommendation generation—execute deterministically. The pipeline relies entirely on explicit mathematical algorithms and rule tables.
2. **Canonical Data Boundary**: `FieldSample` serves as the sole data contract connecting acquisition sources to downstream engines. No raw hardware bytes or simulator-specific formats pass beyond the input boundary.
3. **Source Transparency**: Virtual simulators and physical hardware adapters emit identical `FieldSample` instances. Downstream processing code is 100% agnostic to sample origin.
4. **Passive Presentation**: The presentation layer is strictly passive. It transforms pre-computed intelligence objects into UI view models without performing scoring, spatial math, or zone clustering.
5. **Decoupled AI Explanation**: Large Language Models (LLMs) and generative AI modules exist exclusively downstream as passive summary generators. AI components cannot alter deterministic scores or invent unverified metrics.
6. **Zero External Dependencies**: The core software stack uses Python standard libraries exclusively, guaranteeing offline edge execution without cloud services or heavy ML frameworks.

---

## 3. System Context

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             SYSTEM CONTEXT BOUNDARY                         │
└─────────────────────────────────────────────────────────────────────────────┘

 [ JXBS 7-in-1 Soil Sensor ] ──(RS485/Modbus)──┐
                                               ├──> [ FieldSense AI Edge Engine ]
 [ NEO-M8N GPS Module ] ─────────(UART NMEA)───┘    │ (Runs on Arduino UNO Q /
                                                    │  Qualcomm QRB2210 Linux)
 [ Virtual Simulator ] ──────────(In-Memory)────┘    │
                                                    ▼
                                            [ Offline Local UI ]
                                        (Self-Contained SVG HTML)
                                                    │
                                                    ▼ (Optional)
                                            [ Edge LLM Explainer ]
                                         (Passive Natural Language)
```

---

## 4. High-Level Architecture

The canonical data pipeline follows an 8-stage linear processing flow:

```text
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  SensorAdapter  │ ──> │   FieldSample    │ ──> │ ValidationEngine │
└─────────────────┘     └──────────────────┘     └────────┬─────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  SpatialEngine  │ <── │NormalizedSample /│ <── │ IntelligenceEngine│
│ (IDW 2D Raster) │     │Scoring Engine    │     └──────────────────┘
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   ZoneEngine    │ ──> │  Recommendation  │ ──> │  UIViewAdapter / │
│(4-Neighbor BFS) │     │      Engine      │     │ LocalUIRenderer  │
└─────────────────┘     └──────────────────┘     └──────────────────┘
```

---

## 5. Layer Boundaries

FieldSense AI is organized into 11 strictly decoupled Python modules under `fieldsense/`:

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

## 6. Dependency Direction

FieldSense AI enforces strict unidirectional dependencies:

$$\text{Input / Hardware} \longrightarrow \text{Domain} \longrightarrow \text{Validation / Scoring} \longrightarrow \text{Spatial} \longrightarrow \text{Zones} \longrightarrow \text{Recommendations} \longrightarrow \text{Presentation}$$

### Forbidden Dependency Violations (Architectural Defects)
- $\text{Presentation} \longrightarrow \text{Intelligence Scoring}$ (UI must not calculate metrics)
- $\text{Hardware} \longrightarrow \text{Recommendations}$ (Hardware adapters must not access rules)
- $\text{Spatial} \longrightarrow \text{Presentation}$ (Spatial engine must remain presentation-agnostic)
- $\text{Domain} \longrightarrow \text{External Libraries}$ (Domain models must remain pure Python)
- $\text{LLM / AI} \longrightarrow \text{Deterministic Core}$ (AI must never drive scoring logic)

---

## 7. FieldSample Contract

**Module**: `fieldsense.domain.models.sample`

`FieldSample` is the immutable canonical data representation of a single physical or virtual soil observation.

```python
@dataclass(frozen=True)
class FieldSample:
    sample_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    nitrogen: float
    phosphorus: float
    potassium: float
    ph: float
    ec: float
    moisture: float
    temperature: float
    measurement_quality: float = 1.0
    source: SampleSource = SampleSource.VIRTUAL
    validation_state: ValidationState = ValidationState.VALID
```

### Invariants & Requirements
- **Immutability**: Enforced via `frozen=True`. Downstream engines cannot alter raw measurements.
- **Serialization**: Supports `to_dict()` and `from_dict()` with strict ISO-8601 UTC timestamp parsing.
- **Canonical Status**: All downstream engines consume `FieldSample` instances exclusively.

---

## 8. FieldSession Contract

**Module**: `fieldsense.domain.models.session`

`FieldSession` manages a complete multi-sample field acquisition campaign.

```python
@dataclass
class FieldSession:
    session_id: str
    name: str
    created_at: datetime
    status: SessionStatus = SessionStatus.ACTIVE
    samples: List[FieldSample] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### Invariants & Requirements
- **Data Lineage**: `samples` retains all collected readings, including rejected samples, ensuring full auditability.
- **Read-Only Derived Views**: `valid_samples` property filters for `pipeline_eligible` samples without mutating `samples`.

---

## 9. SensorAdapter Contract

**Module**: `fieldsense.domain.contracts.sensor_adapter`

The standard interface for all sample acquisition adapters.

```python
class SensorAdapter(ABC):
    @abstractmethod
    def initialize(self) -> bool: ...
    
    @abstractmethod
    def acquire_sample(self, lat: float, lon: float) -> FieldSample: ...
    
    @abstractmethod
    def shutdown(self) -> None: ...
```

---

## 10. VirtualSensorAdapter

**Module**: `fieldsense.input.virtual_sensor`

Implements `SensorAdapter` to generate synthetic, spatially consistent soil fields for offline testing. Accepts `VirtualFieldConfig` specifying spatial gradients, multi-center hotspots, noise levels, and fixed random seeds.

---

## 11. HardwareSensorAdapter

**Module**: `fieldsense.hardware.sensor_adapter`

Implements `SensorAdapter` to interface with physical edge hardware.

```text
┌─────────────────────────────────────────────────────────────┐
│                   HardwareSensorAdapter                     │
│                                                             │
│  ┌──────────────────────┐        ┌──────────────────────┐   │
│  │   SensorTransport    │        │      GPSAdapter      │   │
│  │ (Modbus RTU / RS485) │        │ (UART NMEA 0183)     │   │
│  └──────────┬───────────┘        └──────────┬───────────┘   │
│             │ Raw Metrics                   │ GPS Fix       │
│             └───────────────┬───────────────┘               │
│                             ▼                               │
│                    Canonical FieldSample                    │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼ (Downstream Pipeline)
```

---

## 12. Validation Contract

**Module**: `fieldsense.intelligence.validation`

Gatekeeper engine verifying physical plausibility before data enters spatial rasters.

```python
class ValidationEngine:
    def validate_sample(self, sample: FieldSample) -> ValidationResult: ...
```

### Validation State Semantics
- `REJECTED`: Out-of-bounds metrics (e.g. $\text{pH} > 14$, $\text{Moisture} < 0\%$). `pipeline_eligible = False`. Excluded from spatial maps; stored in session for audit.
- `VALID_WITH_WARNING`: Borderline values or high noise. `pipeline_eligible = True`. Included in spatial rasters with diagnostic warnings.
- `VALID`: Fully plausible measurement. `pipeline_eligible = True`.

---

## 13. Normalization Contract

**Module**: `fieldsense.intelligence.normalization`

Transforms raw physical metric values into dimensionless optimality scores $[0.0, 1.0]$.

$$\text{Normalizer}: \text{Raw Physical Value} \xrightarrow{\text{Piecewise Linear / Band Functions}} [0.0, 1.0]$$

- Status: `PROTOTYPE_ONLY` / `AGRONOMIC_VALIDATION_REQUIRED`.

---

## 14. Intelligence Contract

**Module**: `fieldsense.intelligence`

Aggregates normalized metric scores into unified domain intelligence results.

```python
@dataclass
class FieldIntelligenceResult:
    sample_scores: List[NormalizedSample]
    soil_health: SoilHealthResult
    nitrogen: NitrogenResult
    moisture: MoistureResult
    carbon_readiness: CarbonReadinessResult
```

### Carbon Readiness Proxy Boundary
- Enforces `decision_support_only = True` and `evidence_level = "LIMITED"`.
- Explicitly outputs missing indicators (`soil_organic_carbon`, `bulk_density`, `management_history`).
- Prohibits direct soil organic carbon mass claims or carbon credit certification.

---

## 15. Methodology Configuration

**Module**: `fieldsense.intelligence.scoring.config`

Encapsulates reference scoring bands and MCDA weighting vectors (`IntelligenceConfig`).

$$\text{Soil Health Weighting}: 0.20 N + 0.15 P + 0.15 K + 0.20 \text{pH} + 0.10 \text{EC} + 0.20 \text{Moisture} = 1.00$$

- All parameters tagged `PROTOTYPE_ONLY` under `methodology_version = "0.1"`.

---

## 16. Spatial Contract

**Module**: `fieldsense.spatial`

Projects geographic coordinates to local Cartesian meters $(x,y)$ and interpolates 2D continuous rasters using Inverse Distance Weighting (IDW, $p=2.0$).

### Spatial Constraints
- **Minimum Valid Samples**: $N \ge 3$. If $N < 3$, spatial engine returns `is_valid = False` without attempting grid interpolation.
- **Maximum Support Distance**: $100\text{m}$. Grid nodes located $> 100\text{m}$ from the nearest valid sample return `None` (unsupported).
- **Grid Resolution**: Configurable default $10\text{m} \times 10\text{m}$ grid cells.

---

## 17. Zone Contract

**Module**: `fieldsense.zones`

Partitions continuous spatial rasters into discrete contiguous management zones using 4-neighbor Breadth-First Search (BFS) graph clustering.

### Zone Parameters
- **Zone Classifications**: `HEALTHY` ($\ge 0.70$), `MODERATE` ($0.45 - 0.69$), `POOR` ($< 0.45$).
- **Minimum Component Merging**: Small contiguous components $< 2$ grid cells ($< 200\text{m}^2$) are merged into neighboring zones.
- **Primary Issue Selection**: Identified by lowest metric score with fixed priority tie-breaking ($N > \text{Moisture} > \text{pH} > \text{Salinity}$).
- **Zone Confidence**: Represents spatial data support density within the zone, **not** agronomic certainty.

---

## 18. Recommendation Contract

**Module**: `fieldsense.recommendations`

Evaluates detected zone issues against deterministic rule tables to emit structured decision support actions.

### Recommendation Constraints
- **Directional Guidance Only**: Emits qualitative advice (e.g., *"Review nitrogen management"*).
- **ZERO QUANTITATIVE DOSAGES**: Prohibits chemical/fertilizer dosages ($\text{kg/ha}$) or irrigation volumes ($\text{L/m}^2$).
- **Limits**: Maximum 3 recommendations per zone; stable rule IDs; automated deduplication.

---

## 19. UI Contract

**Module**: `fieldsense.presentation`

Transforms raw backend intelligence objects into passive view models (`UIFieldView`) consumed by `LocalUIRenderer`.

```text
FieldSession + SpatialResult + Zones + Recommendations
                         │
                         ▼
                  UIViewAdapter
                         │
                         ▼
             UIFieldView (Passive Model)
                         │
                         ▼
        LocalUIRenderer (HTML/CSS/SVG)
```

- UI contains **zero** scoring, interpolation, or clustering logic.

---

## 20. Storage / Serialization Contract

All core domain models implement explicit dictionary conversion:
- `to_dict() -> Dict[str, Any]`
- `from_dict(d: Dict[str, Any]) -> ModelClass`

Timestamps are serialized strictly as ISO-8601 strings in UTC timezone.

---

## 21. Hardware Boundary

Hardware communication interfaces (`fieldsense/hardware/`) isolate RS485 differential transceivers, Modbus RTU register decoding, and UART NMEA GPS parsing. Physical serial parameters are tracked as `HARDWARE_SPEC_REQUIRED` / `PENDING HARDWARE`.

---

## 22. AI Boundary

The downstream AI Explanation Layer is optional and decoupled:

$$\text{Deterministic Results} \longrightarrow \text{Structured JSON Context} \longrightarrow \text{Edge LLM Explainer}$$

- The AI layer cannot alter deterministic scores, modify spatial maps, or inject quantitative chemical dosages.

---

## 23. Error Handling

FieldSense uses explicit exception hierarchies:
- `FieldSenseError`: Base application exception.
- `ValidationException`: Raised on fatal data contract breaches.
- `HardwareConnectionError`: Raised on serial physical transport failures.
- `ModbusTimeoutError`: Raised on slave response timeout.
- `GPSFixError`: Raised on invalid GPS fix.

Silent `except Exception: pass` blocks are strictly forbidden.

---

## 24. Configuration Ownership

Configuration objects own defaults and bounds:
- `ValidationConfig`: Sanity bounds and tolerance thresholds.
- `IntelligenceConfig`: Scoring curves and MCDA weights.
- `SpatialConfig`: Grid resolution ($10\text{m}$), IDW power ($2.0$), max support distance ($100\text{m}$).
- `ZoneConfig`: Classification thresholds and min component size.
- `HardwareConfig`: Serial parameters, baud rate, dev nodes.

---

## 25. Determinism Requirements

Given identical input `FieldSample` collections and system configuration, FieldSense AI must produce **bit-exact identical** outputs for:
- Validation results
- Normalized metrics & Soil Health scores
- Spatial raster grids
- Zone boundaries and centroids
- Recommendations and UI views

---

## 26. Resource Constraints

- **Target Hardware**: Arduino UNO Q (Qualcomm QRB2210 Debian Linux).
- **Execution Time**: $< 500\text{ms}$ for 100 samples on $10\text{m}$ grid.
- **RAM Limit**: $< 50\text{MB}$ peak memory consumption.
- **Dependencies**: Standard Python 3.10+ library modules exclusively.

---

## 27. Testing Architecture

The test suite (`tests/`) enforces 100% contract compliance across 17 test modules:
- Unit tests (`test_sample.py`, `test_validation.py`, `test_spatial.py`, `test_zones.py`, etc.)
- Golden scenarios (`test_golden_scenarios.py`)
- Fault injection (`test_fault_injection.py`)
- Latency benchmarks (`test_benchmark.py`)
- System hardening (`test_sprint12_hardening.py`)

---

## 28. Extension Points

Future modules must integrate through explicit extension contracts:
- New acquisition sources: Implement `SensorAdapter`.
- New recommendation rules: Inherit from `RecommendationRule`.
- New presentation formats: Consume `UIFieldView`.

---

## 29. Frozen Contracts

The following data models and interfaces are **FROZEN** as of Phase 1:
1. `FieldSample` (`fieldsense.domain.models.sample`)
2. `FieldSession` (`fieldsense.domain.models.session`)
3. `SensorAdapter` (`fieldsense.domain.contracts.sensor_adapter`)
4. `ValidationResult` (`fieldsense.intelligence.validation.models`)
5. `NormalizedSample` (`fieldsense.intelligence.scoring.models`)
6. `FieldIntelligenceResult` (`fieldsense.intelligence.scoring.models`)
7. `SpatialFieldResult` (`fieldsense.spatial.engine`)
8. `Zone` (`fieldsense.zones.models`)
9. `Recommendation` (`fieldsense.recommendations.models`)
10. `UIFieldView` (`fieldsense.presentation.models`)
11. `HardwareSensorAdapter` boundary (`fieldsense.hardware`)

---

## 30. Change Control

Any modification to a frozen contract requires a formal **Contract Change Request**:

```text
CONTRACT CHANGE REQUEST PROTOCOL
-------------------------------
1. Change ID & Title
2. Target Frozen Contract
3. Current Behavior & Signature
4. Proposed Modification
5. Rationale & Architectural Necessity
6. Backward Compatibility & Migration Impact
7. Affected Code Modules & Test Files
8. Human Architect Sign-off & Approval
```

AI coding agents must **NEVER** silently modify frozen contracts.
