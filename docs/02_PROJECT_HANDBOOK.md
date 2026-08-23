# FieldSense AI — Project Handbook

**Document Version:** 1.0  
**Last Updated:** 2026-08-09  
**Project Phase:** Phase 1 Complete  
**Release Status:** `PHASE_1_RELEASE_READY`  

---

## 1. Project Overview

**FieldSense AI** is an offline, portable edge-intelligence platform engineered for multi-point spatial soil assessment, management zone detection, decision support, and Carbon Readiness proxy evaluation. Designed to run on resource-constrained embedded edge devices (specifically the **Arduino UNO Q** platform running Debian Linux on a Qualcomm QRB2210 MPU alongside an STM32U585 MCU), FieldSense AI resolves spatial soil variability without relying on cloud infrastructure, remote APIs, or active internet connectivity.

---

## 2. Problem Statement

Agricultural fields exhibit substantial micro-spatial variability in soil chemistry, moisture, and nutrient availability due to topography, soil texture, historical management, and drainage. Traditional soil testing relies on sparse composite sampling (e.g. 1 to 3 mixed samples per field), which averages out local extremes and masks localized degraded areas.

Furthermore, cloud-dependent digital farming tools fail in remote rural regions lacking reliable cellular connectivity. Existing agricultural AI software often suffers from hallucination risks, attempting to predict chemical dosages or carbon sequestration without deterministic validation.

---

## 3. Project Objectives

1. **Spatial Granularity**: Enable rapid multi-point in-situ soil sampling across agricultural plots to capture micro-spatial variation.
2. **100% Deterministic Core**: Guarantee predictable, auditable, and scientifically transparent calculations for soil health, nutrient indices, continuous spatial surfaces, and management zones.
3. **Offline Sovereignty**: Perform end-to-end data acquisition, validation, interpolation, zone clustering, recommendation generation, and UI rendering entirely on edge hardware without external cloud or API dependencies.
4. **Hardware Independence**: Maintain a rigid abstraction barrier (`SensorAdapter` $\rightarrow$ canonical `FieldSample`) so software pipeline code is 100% identical whether running against virtual simulators or physical RS485 hardware.
5. **Scientific & AI Safety**: Enforce strict safety boundaries—prohibiting hallucinated fertilizer/chemical dosages, and clearly framing carbon evaluation as a decision-support proxy rather than a certified carbon storage measurement.

---

## 4. Target Users

- **Agronomists & Field Extension Officers**: Conducting rapid on-site field surveys, identifying degraded soil patches, and prescribing targeted management zones.
- **Small-to-Medium Farmers**: Requiring offline, easy-to-understand visual field health maps and actionable management guidance without expensive subscriptions.
- **Agricultural Researchers & Soil Scientists**: Collecting spatially explicit multi-parameter soil datasets with complete quality auditability.

---

## 5. Core Value Proposition

| Dimension | Standard Soil Testing | Cloud Ag-Tech Platforms | FieldSense AI |
| :--- | :--- | :--- | :--- |
| **Sampling Density** | Sparse composite (1-3 points) | Requires manual upload | Dense multi-point spatial survey |
| **Connectivity** | Manual paper reports | Requires 4G/5G / Cloud API | **100% Offline Edge Execution** |
| **Data Sanity** | Unverified manual entry | Minimal raw input filtering | **Automated Gatekeeper (`ValidationEngine`)** |
| **Spatial Analysis** | None | Cloud-computed rasters | **Local Cartesian IDW Grid Interpolation** |
| **Safety & Audit** | Variable quality | LLM hallucination risks | **Deterministic Core + Explicit Boundaries** |

---

## 6. System Overview

FieldSense AI processes raw soil measurements through an 8-stage canonical pipeline:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FIELDSENSE SYSTEM PIPELINE                        │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────┐
  │  VirtualSensorAdapter  │──┐
  └────────────────────────┘  │
                              ├──> FieldSample (Canonical Domain Model)
  ┌────────────────────────┐  │
  │ HardwareSensorAdapter  │──┘
  └────────────────────────┘
               │
               ▼
  ┌────────────────────────┐
  │    ValidationEngine    │ ── (Rejects corrupted samples; tags warnings)
  └────────────┬───────────┘
               │ valid / valid_with_warning
               ▼
  ┌────────────────────────┐
  │   IntelligenceEngine   │ ── (Normalizes metrics & computes MCDA scores)
  └────────────┬───────────┘
               │
               ▼
  ┌────────────────────────┐
  │     SpatialEngine      │ ── (Projects (x,y) & computes 2D IDW rasters)
  └────────────┬───────────┘
               │
               ▼
  ┌────────────────────────┐
  │       ZoneEngine       │ ── (4-neighbor BFS spatial zone clustering)
  └────────────┬───────────┘
               │
               ▼
  ┌────────────────────────┐
  │  RecommendationEngine  │ ── (Rule-based non-prescriptive action engine)
  └────────────┬───────────┘
               │
               ▼
  ┌────────────────────────┐
  │     UIViewAdapter      │ ── (Transforms results into passive UI model)
  └────────────┬───────────┘
               │
               ▼
  ┌────────────────────────┐
  │    LocalUIRenderer     │ ── (Generates offline interactive SVG HTML UI)
  └────────────────────────┘
```

---

## 7. Hardware Platform

### Arduino UNO Q
- **Primary Host System**: High-performance dual-core/quad-core Linux edge module (`HARDWARE_STATUS: PENDING HARDWARE`).
- **Memory / Storage**: 4 GB RAM / 32 GB eMMC variant.

### Qualcomm QRB2210
- **Role**: Main Application Processing Unit (MPU) running Debian Linux.
- **Responsibilities**: Runs Python 3 runtime, FieldSense pipeline, deterministic spatial interpolation, zone clustering, and local HTML UI rendering.

### STM32U585
- **Role**: Ultra-low-power Microcontroller Unit (MCU).
- **Responsibilities**: Manages real-time peripheral interfaces, RS485 DE/RE transceiver timing, Modbus RTU timing, and GPS NMEA sentence buffering (`HARDWARE_STATUS: PENDING HARDWARE`).

### JXBS 7-in-1 Soil Sensor
- **Parameters Measured**: Nitrogen ($N$), Phosphorus ($P$), Potassium ($K$), Soil $\text{pH}$, Electrical Conductivity ($\text{EC}$), Moisture ($\text{VWC}\%$), and Temperature ($^\circ\text{C}$).
- **Interface**: RS485 differential bus running Modbus RTU protocol (`HARDWARE_STATUS: PENDING HARDWARE`).

### NEO-M8N GPS
- **Role**: Acquires spatial coordinates (Latitude, Longitude, Altitude, Fix Quality, Satellite Count).
- **Interface**: NMEA 0183 protocol over UART serial node (`HARDWARE_STATUS: PENDING HARDWARE`).

### RS485 / Modbus Boundary
- **Status**: Interfaces isolated inside `fieldsense/hardware/`. Physical baud rate (`9600`), slave address (`0x01`), register maps (`0x0000-0x0006`), and serial paths (`/dev/ttyS0`) are documented as `HARDWARE_SPEC_REQUIRED` / `PENDING HARDWARE`.

---

## 8. Software Architecture

FieldSense AI enforces strict layered modularity and explicit dependency directions:

```text
[Hardware / Virtual Input] ──> [Domain Models] ──> [Validation & Intelligence]
                                                          │
[Presentation / Offline UI] <── [Recommendations] <── [Zones] <── [Spatial Engine]
```

- **Domain Core**: Pure data contracts (`FieldSample`, `FieldSession`) without external framework dependencies.
- **Input / Hardware Isolation**: Transports convert external signals directly into canonical `FieldSample` instances.
- **Deterministic Core**: Validation, scoring, spatial processing, zone detection, and rule evaluation executed deterministically without LLM calls.
- **Presentation**: Passive view model mapping and self-contained HTML/SVG renderer.

---

## 9. End-to-End Data Flow

```text
JXBS Sensor ──RS485/Modbus──> Hardware Adapter ──┐
                                                 │
NEO-M8N GPS ─────UART────────> GPS Adapter ──────┼──> FieldSample (Immutable)
                                                 │
Virtual Sim ─────Math────────> Virtual Adapter ──┘
                                 │
                                 ▼
                          Validation Engine
                         /                \
                [REJECTED]                [VALID / WARNING]
                    │                             │
             Audit Log Only                       ▼
                                         Intelligence Engine
                                         (Normalization/MCDA)
                                                  │
                                                  ▼
                                            Spatial Engine
                                         (Cartesian Meter IDW)
                                                  │
                                                  ▼
                                             Zone Engine
                                       (4-Neighbor Clustering)
                                                  │
                                                  ▼
                                         Recommendation Engine
                                          (Traceable Rules)
                                                  │
                                                  ▼
                                            Offline UI Render
                                         (Standalone HTML/SVG)
```

---

## 10. FieldSample

`FieldSample` (`fieldsense/domain/models/sample.py`) is the immutable canonical data representation of a single point observation.

### Schema Specifications

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

`FieldSample` is defined as a `frozen=True` dataclass (`IMPLEMENTED`). Raw readings cannot be silently altered downstream.

---

## 11. FieldSession

`FieldSession` (`fieldsense/domain/models/session.py`) encapsulates a complete field sampling campaign (`IMPLEMENTED`).

- **Attributes**: `session_id`, `name`, `created_at`, `status` (`ACTIVE`, `COMPLETED`, `ABORTED`), `samples` (`List[FieldSample]`), `metadata` (`dict`).
- **Raw Sample Integrity**: `FieldSession.samples` stores all collected samples—including rejected samples—ensuring complete data lineage and operational auditability.

---

## 12. Sensor Abstraction

The `SensorAdapter` abstract base class (`fieldsense/domain/contracts/sensor_adapter.py`) enforces a single lifecycle contract (`IMPLEMENTED`):

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

## 13. Virtual Field Simulator

`VirtualSensorAdapter` (`fieldsense/input/virtual_sensor.py`) provides deterministic multi-point simulation (`IMPLEMENTED`).
- **Features**: Configurable spatial gradients, multi-center Gaussian hotspots, controlled noise injection, fixed random seeds for reproducible testing, and built-in fault profiles (`OUTLIER`, `UNSTABLE_MEASUREMENT`).

---

## 14. Validation

`ValidationEngine` (`fieldsense/intelligence/validation/engine.py`) serves as the system's sanity gatekeeper (`IMPLEMENTED`).

### Validation State Hierarchy
1. `REJECTED`: Out-of-bounds physical readings (e.g. $\text{pH} = 15.2$ or $\text{Moisture} = -5\%$) or extreme sensor noise. Flagged `pipeline_eligible = False`.
2. `VALID_WITH_WARNING`: Metrics on physical threshold boundaries (e.g., extremely high EC). Flagged `pipeline_eligible = True`.
3. `VALID`: Clean, physically plausible soil measurement. Flagged `pipeline_eligible = True`.

---

## 15. Normalization

`SampleNormalizer` (`fieldsense/intelligence/normalization/normalizer.py`) converts raw physical values into dimensionless optimality scores $[0.0, 1.0]$ (`IMPLEMENTED`).
- Uses non-linear piecewise linear functions and optimum reference bands (e.g. optimum soil $\text{pH}$ band $6.0 - 7.5$).
- Explicit Status: `PROTOTYPE_ONLY` / `AGRONOMIC_VALIDATION_REQUIRED`.

---

## 16. Deterministic Intelligence

`IntelligenceEngine` (`fieldsense/intelligence/engine.py`) coordinates normalized metric scoring and component index synthesis (`IMPLEMENTED`).
- **No LLM Involvement**: All scores are computed deterministically via mathematical functions.

---

## 17. Soil Health

Overall **Soil Health Index** ($[0.0, 1.0]$) is computed using Multi-Criteria Decision Analysis (MCDA) weighting (`IMPLEMENTED`):

$$\text{SoilHealth} = 0.20 S_N + 0.15 S_P + 0.15 S_K + 0.20 S_{\text{pH}} + 0.10 S_{\text{EC}} + 0.20 S_{\text{Moisture}}$$

- Explicit Status: `PROTOTYPE_ONLY` / `AGRONOMIC_VALIDATION_REQUIRED`.

---

## 18. Carbon Readiness

`CarbonReadinessResult` (`fieldsense/intelligence/scoring/models.py`) evaluates soil conditions suitable for organic carbon retention (`IMPLEMENTED`).

### CRITICAL SCIENTIFIC SAFETY BOUNDARIES
- **Category**: Decision-Support Proxy Index (`decision_support_only = True`).
- **Evidence Level**: `LIMITED`.
- **Explicit Missing Indicators**:
  ```python
  missing_indicators = [
      "soil_organic_carbon",
      "bulk_density",
      "management_history"
  ]
  ```
- **PROHIBITED CLAIMS**: FieldSense AI does **NOT** perform direct SOC lab measurement, carbon storage tonnage calculation, MRV certification, or carbon credit issuance.

---

## 19. Spatial Intelligence

`SpatialEngine` (`fieldsense/spatial/engine.py`) projects geographic coordinates into local Cartesian meters $(x, y)$ and interpolates regular 2D raster grids (`IMPLEMENTED`).
- **Coordinate Projection**: Local equirectangular planar projection centered on sample centroid.
- **Interpolation Algorithm**: Inverse Distance Weighting (IDW, $p=2.0$).
- **Support Boundary**: Max support distance $100\text{m}$. Grid cells beyond support distance return `None` (unsupported) to prevent arbitrary extrapolation. Minimum valid sample threshold $N \ge 3$.

---

## 20. Field Intelligence Maps

Field Intelligence Maps are 2D raster layers generated across 4 distinct visual projections (`IMPLEMENTED`):
1. **Soil Health Layer**: Aggregate multi-criteria soil quality.
2. **Nitrogen Index Layer**: Soil nitrogen status.
3. **Moisture Index Layer**: Volumetric water content distribution.
4. **Carbon Readiness Layer**: Carbon proxy suitability map.

---

## 21. Zone Detection

`ZoneEngine` (`fieldsense/zones/engine.py`) groups continuous spatial cells into discrete management zones (`IMPLEMENTED`).
- **Clustering Algorithm**: 4-neighbor Breadth-First Search (BFS) graph component labeling.
- **Zone Classifications**: `HEALTHY` (Score $\ge 0.70$), `MODERATE` ($0.45 \le \text{Score} < 0.70$), `POOR` ($\text{Score} < 0.45$).
- **Small Component Merging**: Contiguous regions $< 2$ cells ($200\text{m}^2$) are merged into neighboring zones.
- **Primary Issue Selection**: Identified by lowest metric score with deterministic tie-breaking.
- **Spatial Support Confidence**: Indicates spatial data density (`HIGH`, `MEDIUM`, `LOW`), **not** agronomic certainty.

---

## 22. Recommendation Engine

`RecommendationEngine` (`fieldsense/recommendations/engine.py`) evaluates zone conditions against rule matrices to generate actionable recommendations (`IMPLEMENTED`).

### SAFETY & PRESCRIPTION RULES
- **Rule Categories**: `NUTRIENT`, `WATER`, `SOIL_CONDITION`, `SALINITY`, `CARBON_READINESS`, `MONITORING`.
- **Directional Guidance Only**: Emits qualitative, traceable advice (e.g. *"Review nitrogen availability in Zone Z02"*).
- **ZERO QUANTITATIVE DOSAGES**: System **never** outputs chemical or fertilizer quantities (e.g. *"Apply 30 kg/ha Urea"*) or irrigation volumes.
- **Constraints**: Maximum 3 recommendations per zone; stable rule IDs; automated deduplication.

---

## 23. Offline UI

`LocalUIRenderer` (`fieldsense/presentation/renderer.py`) compiles self-contained HTML/CSS/SVG dashboards (`IMPLEMENTED`).
- **Passive Contract**: UI consumes `UIFieldView` data structures built by `UIViewAdapter`. Contains zero calculation or scoring logic.
- **Zero External Dependencies**: Operates 100% offline without external JS libraries, remote CSS fonts, or web map tiles.

---

## 24. AI Explanation Layer

- **Status**: `IMPLEMENTED` (`fieldsense/ai/`) — downstream consumer, optional and out of band.
- **Boundary**: Optional local SLM / LLM module. Consumes structured deterministic results (`FieldIntelligenceResult`, `ZoneDetectionResult`, `RecommendationResult`) reduced to an `ExplanationContext`, and generates natural language summaries. Cannot alter deterministic scores or invent new metrics.
- **Contract**: `LocalLLMAdapter` ABC, mirroring `SensorAdapter` (`initialize` / `explain` / `shutdown`, plus `is_available`).
- **Backends**: `MockAIAdapter` (deterministic templates, always available, no model weights required) and `LlamaCppAdapter` (quantized GGUF via a `llama.cpp` binary, selected only when weights and binary are present). `AIAdapterFactory` resolves the active backend; absence of weights is a normal condition, not an error.
- **Safety Gate**: `NarrativeGuard` deterministically rejects generated text containing dose units, agrochemical names, carbon credit / sequestration claims, or any number absent from the `ExplanationContext`. Rejected sections degrade to deterministic templates. This is the language-side counterpart to the data-side `ValidationEngine`.
- **Timing Boundary**: Real model inference costs tens of seconds on edge hardware, far exceeding the `< 500 ms` deterministic pipeline budget (section 26 of the architecture document). The explanation layer therefore runs **after** the deterministic pipeline completes and is always discardable. The dashboard renders fully when `narrative` is `None`.
- **Determinism**: `AINarrative` is declared **non-normative presentation text** and is excluded from the bit-exact guarantee when produced by a model backend. `MockAIAdapter` is bit-exact and is used by all golden scenario, determinism, and benchmark tests. See `docs/CCR-001_UIFieldView_Narrative.md`.
- **Dependencies**: None added. `llama.cpp` is invoked as an external system binary via the standard library `subprocess` module, so `pyproject.toml` `dependencies` remains `[]`.

---

## 25. Storage / Serialization

- **Status**: `IMPLEMENTED` (Dictionary & JSON serialization/deserialization across all models).
- **Persistence Extension**: `PLANNED` (Lightweight SQLite file adapter for historical session tracking).

---

## 26. Hardware Integration

- **Status**: `IMPLEMENTED` (`HardwareSensorAdapter`, `SensorTransport`, `GPSAdapter` abstractions in `fieldsense/hardware/`).
- **Physical Execution**: `PENDING HARDWARE` (Awaiting physical serial bus wiring and hardware verification).

---

## 27. Testing Strategy

The test suite (`tests/`) enforces 100% regression stability using `pytest` (`IMPLEMENTED`).

### Current Verification Baseline
```text
105 passed in 0.70s
Release Baseline Status: PHASE_1_RELEASE_READY
```

---

## 28. Golden Scenarios

Verified end-to-end operational profiles (`tests/test_golden_scenarios.py`):
1. `HEALTHY_FIELD`: Uniform high-scoring metrics.
2. `NUTRIENT_DEFICIENT`: Nitrogen and phosphorus depression.
3. `MOISTURE_DEFICIENT`: Low volumetric water content.
4. `MIXED_STRESS`: Combined salinity and pH stress.
5. `SPATIAL_GRADIENT`: Continuous linear nutrient transition across plot.

---

## 29. Fault Handling

Verified error recovery behaviors (`tests/test_fault_injection.py`):
- **Sensor Outliers**: Rejected by `ValidationEngine` without pipeline crash.
- **Sensor Instability**: Flagged and excluded from spatial maps.
- **Sparse Data ($N < 3$)**: Spatial engine safely aborts grid calculation and returns empty spatial result.
- **Hardware Failure**: Transports raise structured `HardwareConnectionError` / `ModbusTimeoutError`.

---

## 30. Performance

Host Machine Execution Benchmarks (`tests/test_benchmark.py`):
- **Full Pipeline Run (25 samples, 10m grid)**: $< 45\text{ms}$.
- **Memory Footprint**: $< 25\text{MB}$ peak RAM.
- **Physical Target (Arduino UNO Q QRB2210)**: Marked `UNO_Q_PHYSICAL_BENCHMARK = PENDING_HARDWARE`.

---

## 31. Offline Operation

FieldSense AI is architected for total network isolation:
- No HTTP/HTTPS network calls.
- SVG vector graphics generated natively in Python code.
- Zero cloud API dependencies.

---

## 32. Security / Reliability Considerations

- **Data Privacy**: All field data remains stored locally on edge eMMC storage.
- **Deterministic Execution**: Zero risk of unvetted LLM recommendations altering core output.
- **Audit Lineage**: All raw samples (including rejected ones) logged with timestamps and source tags.

---

## 33. Known Limitations

1. **Physical Hardware Verification**: Serial Modbus RTU communication with physical JXBS sensors is pending physical hardware delivery (`PENDING HARDWARE`).
2. **Local Planar Projection**: Coordinate projection uses equirectangular planar math suitable for local agricultural plots ($< 10\text{km}$). Not designed for continent-scale projections.
3. **Carbon Readiness Scope**: Proxy indicator only; does not provide certified soil carbon measurements (`LIMITED`).

---

## 34. Agronomic Validation Boundaries

- **Reference Scoring Curves**: Normative functions set to prototype default ranges (`PROTOTYPE_ONLY`).
- **MCDA Weighting Vectors**: Default weighting matrix requires local field-trial recalibration for specific crop species and regional soil types (`AGRONOMIC_VALIDATION_REQUIRED`).

---

## 35. Current Development Status

```text
Phase 1 Status: COMPLETE
Release Status: PHASE_1_RELEASE_READY
Regression Test Baseline: 105 passed
Current Data Source: Virtual Simulator + Hardware Abstraction Boundary Ready
Target Next Step: Phase 2 Physical Hardware Integration
```

---

## 36. Phase 2 Roadmap

1. Connect physical JXBS 7-in-1 sensor to Arduino UNO Q RS485 transceiver.
2. Verify NEO-M8N GPS UART serial stream on `/dev/ttyS0`.
3. Validate physical hardware acquisition via `HardwareSensorAdapter`.
4. Execute physical field trials and benchmark execution latency on QRB2210 Debian Linux.

---

## 37. Future Development

- **Local LLM Explanation Adapter**: Quantized edge LLM integration via `llama.cpp` for natural language voice/text summaries.
- **SQLite Historical Database**: Session persistence and year-over-year field trends.
- **On-Device LCD Driver**: Direct framebuffer GUI rendering for handheld hardware enclosures.

---

## 38. How to Run the Project

Execute the CLI demo pipeline:
```bash
python -m fieldsense.demo
```

---

## 39. How to Run Tests

Run the complete 105-test regression suite:
```bash
pytest
```

---

## 40. How to Run the Demonstration

1. Execute `python -m fieldsense.demo`.
2. Locate the generated self-contained HTML artifact at `artifacts/fieldsense_competition_demo.html`.
3. Open `artifacts/fieldsense_competition_demo.html` in any standard browser.

---

## 41. New Engineer Onboarding

1. Read `docs/02_PROJECT_HANDBOOK.md` to understand system context and scientific boundaries.
2. Read `docs/03_ARCHITECTURE.md` to understand frozen data contracts and module boundaries.
3. Inspect `PROPOSAL_ALIGNMENT.md` and `SPECIFICATION_REGISTER.md`.
4. Run `pytest` to confirm local environment baseline ($105\text{ passed}$).
5. Review `docs/01_SOFTWARE_WORKPLAN.md` before making any code modifications.

---

## 42. AI Agent Onboarding

1. **Inspect First**: Read `01_SOFTWARE_WORKPLAN.md`, `02_PROJECT_HANDBOOK.md`, and `03_ARCHITECTURE.md`.
2. **Preserve Contracts**: Treat all contracts in `fieldsense/domain/` as frozen. Never modify a frozen contract without issuing a `CONTRACT_CHANGE_REQUIRED` report.
3. **No Unapproved Dependencies**: Avoid adding heavy external libraries (e.g. NumPy, Pandas, PyTorch) or network dependencies.
4. **Enforce Boundaries**: Ensure all unverified hardware specs remain `PENDING HARDWARE` and prototype scoring rules remain `AGRONOMIC_VALIDATION_REQUIRED`.
5. **Verify Baseline**: Run `pytest` and verify that all 105 tests pass before declaring completion.

---

## 43. Glossary

- **FieldSample**: Canonical, immutable data container representing a single GPS-tagged multi-parameter soil observation.
- **FieldSession**: Collection of raw field samples, metadata, and computed spatial results for a sampling campaign.
- **IDW**: Inverse Distance Weighting, a deterministic spatial interpolation algorithm.
- **MCDA**: Multi-Criteria Decision Analysis, a mathematical framework for combining multiple metric scores into a unified index.
- **Carbon Readiness**: Decision-support index evaluating soil physical condition for organic carbon retention.
- **JXBS 7-in-1**: Integrated RS485 soil sensor measuring N, P, K, pH, EC, Moisture, and Temperature.
- **NEO-M8N**: High-precision GPS module emitting standard NMEA 0183 sentences over UART.
- **Arduino UNO Q**: Embedded Linux + MCU edge platform housing a Qualcomm QRB2210 MPU and STM32U585 MCU.
