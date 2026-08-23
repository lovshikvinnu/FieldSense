# FieldSense AI — Software Workplan

**Document Version:** 1.0  
**Last Updated:** 2026-08-09  
**Project Phase:** Phase 1 Complete  
**Release Status:** `PHASE_1_RELEASE_READY`  

---

## Project Development Philosophy

FieldSense AI is developed using a **contract-first, sprint-based, AI-assisted engineering methodology**. 

### Core Development Principles
1. **Contract Stability Before Code Implementation**: Architectural boundaries, data models, and module contracts are specified and frozen prior to implementing functional logic.
2. **Deterministic Processing Core**: All analytical routines (validation, normalization, scoring, interpolation, zone partitioning, and rule-based recommendations) are 100% deterministic, auditable, and decoupled from stochastic Large Language Models (LLMs).
3. **Hardware & Environment Abstraction**: Data acquisition sources—whether virtual field simulators or physical RS485/UART sensors—emit identical, immutable canonical domain objects (`FieldSample`), enforcing complete hardware transparency for downstream pipeline stages.
4. **Offline First**: Zero runtime dependencies on external cloud services, remote map APIs, or online AI endpoints. All computation and UI rendering execute locally on edge platforms (target runtime: Debian Linux on Qualcomm QRB2210 / Arduino UNO Q).
5. **Strict Agronomic & Hardware Boundary Labeling**: Unverified physical parameters are tagged `PENDING HARDWARE`, prototype scoring metrics are tagged `AGRONOMIC VALIDATION REQUIRED` or `PROTOTYPE_ONLY`, and carbon assessment is strictly defined as a `LIMITED` decision-support proxy.

---

## Phase 0 — Architecture Freeze

**Status:** COMPLETE

**Objective:**  
Define the high-level system context, layer boundaries, dependency hierarchy, and frozen data contracts before executing software implementation sprints.

**Key Achievements:**
- Established canonical `FieldSample` and `FieldSession` data contracts.
- Defined the 8-stage canonical pipeline: `Sensor Acquisition` $\rightarrow$ `Validation` $\rightarrow$ `Normalization` $\rightarrow$ `Deterministic Intelligence` $\rightarrow$ `Spatial Engine` $\rightarrow$ `Zone Detection` $\rightarrow$ `Recommendation Engine` $\rightarrow$ `UI Data View`.
- Formulated the module isolation rules and dependency hierarchy (prohibiting reverse dependencies such as UI $\rightarrow$ Scoring or Hardware $\rightarrow$ Recommendations).
- Defined standard validation states (`VALID`, `VALID_WITH_WARNING`, `REJECTED`) and sample sources (`VIRTUAL`, `HARDWARE`).

---

## Phase 1 — Software Architecture & Intelligence

Phase 1 focused on building a fully functional, verified, offline-capable deterministic software pipeline driven by virtual sensor abstraction.

### Sprint 1 — Core Domain Models

**Status:** COMPLETE

**Objective:**  
Implement the core, frozen domain models and foundational enumerations for FieldSense AI.

**Implementation Summary:**  
Created pure Python data models for `FieldSample` and `FieldSession` with strict validation and immutability guarantees. Implemented standard enumerations for acquisition source, validation state, and session status. Added dictionary serialization and deserialization routines.

**Key Components:**  
- `fieldsense.domain.models.enums.SampleSource` (`VIRTUAL`, `HARDWARE`)
- `fieldsense.domain.models.enums.ValidationState` (`VALID`, `VALID_WITH_WARNING`, `REJECTED`)
- `fieldsense.domain.models.enums.SessionStatus` (`ACTIVE`, `COMPLETED`, `ABORTED`)
- `fieldsense.domain.models.sample.FieldSample`
- `fieldsense.domain.models.session.FieldSession`

**Tests / Verification:**  
15 tests passing.

**Key Architectural Decision:**  
`FieldSample` instances are strictly immutable (`frozen=True` dataclass) to prevent silent mutation of raw observational data by downstream engines.

**Dependencies / Limitations:**  
Pure Python standard library implementation (`dataclasses`, `enum`, `datetime`, `uuid`). Zero external dependencies.

**Result:**  
Foundational domain models established and verified.

**Next:**  
Sprint 2 — Sensor Abstraction & Virtual Field.

---

### Sprint 2 — Sensor Abstraction & Virtual Field

**Status:** COMPLETE

**Objective:**  
Establish the `SensorAdapter` abstract interface and build a deterministic virtual field generator for offline testing and pipeline development.

**Implementation Summary:**  
Created the `SensorAdapter` base contract and implemented `VirtualSensorAdapter`. Built spatial field variation models supporting smooth gradients, noise injection, reproducible random seeds, and specific boundary test configurations (e.g. out-of-range values, sensor instability).

**Key Components:**  
- `fieldsense.domain.contracts.sensor_adapter.SensorAdapter` (Abstract Base Class)
- `fieldsense.input.virtual_sensor.VirtualSensorAdapter`
- `fieldsense.input.virtual_sensor.VirtualFieldConfig`
- `fieldsense.input.virtual_sensor.VirtualFieldGenerator`

**Tests / Verification:**  
24 tests passing (+9 new tests).

**Key Architectural Decision:**  
Virtual field generators emit unvalidated raw `FieldSample` objects, guaranteeing that downstream validation engines operate identically during simulation and physical deployment.

**Dependencies / Limitations:**  
Deterministic pseudo-random generation using Python's `random.Random(seed)`.

**Result:**  
Virtual sensor simulation interface operational with 100% reproducible test fields.

**Next:**  
Sprint 3 — Validation Engine.

---

### Sprint 3 — Validation Engine

**Status:** COMPLETE

**Objective:**  
Build an automated gatekeeper to sanitize raw sensor samples, reject corrupted data, and attach audit warnings prior to intelligence calculations.

**Implementation Summary:**  
Implemented `ValidationEngine` enforcing physical sanity bounds across all 7 metrics ($N, P, K, \text{pH}, \text{EC}, \text{Moisture}, \text{Temperature}$). Developed quality evaluation rules for out-of-bounds metrics, extreme combinations, and hardware instability markers.

**Key Components:**  
- `fieldsense.intelligence.validation.engine.ValidationEngine`
- `fieldsense.intelligence.validation.models.ValidationResult`
- `fieldsense.intelligence.validation.models.ValidationReason`
- `fieldsense.intelligence.validation.config.ValidationConfig`

**Tests / Verification:**  
34 tests passing (+10 new tests).

**Key Architectural Decision:**  
Samples marked `REJECTED` are preserved inside `FieldSession.samples` for complete operational auditability, but are flagged `pipeline_eligible = False` to prevent map corruption in downstream spatial/zone engines.

**Dependencies / Limitations:**  
Sanity bounds derived from physical sensor operational ranges (e.g., JXBS 7-in-1 datasheet bounds).

**Result:**  
Sanity gatekeeper engine fully operational with clear validation state hierarchy (`REJECTED` $>$ `VALID_WITH_WARNING` $>$ `VALID`).

**Next:**  
Sprint 4A — Intelligence Contracts.

---

### Sprint 4A — Intelligence Contracts

**Status:** COMPLETE

**Objective:**  
Define data structures and interface contracts for multi-criteria scoring, soil health aggregation, and carbon readiness proxy evaluation.

**Implementation Summary:**  
Constructed data models for normalized samples, parameter scores, component intelligence results (Soil Health, Nitrogen Index, Moisture Index, Carbon Readiness), and the unified `FieldIntelligenceResult`. Defined contract boundaries without embedding scientific formula logic prematurely.

**Key Components:**  
- `fieldsense.intelligence.scoring.models.NormalizedSample`
- `fieldsense.intelligence.scoring.models.ParameterScore`
- `fieldsense.intelligence.scoring.models.SoilHealthResult`
- `fieldsense.intelligence.scoring.models.NitrogenResult`
- `fieldsense.intelligence.scoring.models.MoistureResult`
- `fieldsense.intelligence.scoring.models.CarbonReadinessResult`
- `fieldsense.intelligence.scoring.models.FieldIntelligenceResult`

**Tests / Verification:**  
44 tests passing (+10 new tests).

**Key Architectural Decision:**  
Separated contract definition (4A) from mathematical methodology implementation (4B) to enforce clean interface boundaries.

**Dependencies / Limitations:**  
Contracts established as pure data containers.

**Result:**  
Intelligence data models fully frozen.

**Next:**  
Sprint 4B — Deterministic Methodology.

---

### Sprint 4B — Deterministic Methodology

**Status:** COMPLETE

**Objective:**  
Implement deterministic piecewise scoring curves, multi-criteria decision analysis (MCDA) weighting vectors, and Carbon Readiness proxy calculations.

**Implementation Summary:**  
Implemented normalization functions converting raw physical values to $[0.0, 1.0]$ optimality scores. Created weighted aggregation for overall Soil Health ($20\% N + 15\% P + 15\% K + 20\% \text{pH} + 10\% \text{EC} + 20\% \text{Moisture}$). Built the Carbon Readiness proxy evaluator with explicit safety constraints.

**Key Components:**  
- `fieldsense.intelligence.normalization.normalizer.SampleNormalizer`
- `fieldsense.intelligence.scoring.engine.ScoringEngine`
- `fieldsense.intelligence.engine.IntelligenceEngine`
- `fieldsense.intelligence.scoring.config.IntelligenceConfig`

**Tests / Verification:**  
49 tests passing (+5 new tests).

**Key Architectural Decision:**  
Tagged methodology version as `0.1` (`PROTOTYPE_ONLY`) and enforced `decision_support_only = True` with `evidence_level = "LIMITED"` on Carbon Readiness results to prevent unwarranted commercial carbon credit claims.

**Dependencies / Limitations:**  
Scoring parameters require regional agronomic field trial validation (`AGRONOMIC_VALIDATION_REQUIRED`).

**Result:**  
Deterministic intelligence calculations complete and validated against baseline test vectors.

**Next:**  
Sprint 5 — Spatial Intelligence Engine.

---

### Sprint 5 — Spatial Intelligence Engine

**Status:** COMPLETE

**Objective:**  
Build a continuous spatial interpolation engine using Inverse Distance Weighting (IDW) to transform discrete point samples into 2D raster grids.

**Implementation Summary:**  
Created local Cartesian coordinate conversion (latitude/longitude degrees to local meters $x,y$), bounding box calculator, uniform grid generator, and IDW spatial interpolator ($p=2.0$). Implemented support distance thresholds ($100\text{m}$) and minimum sample requirements ($N \ge 3$).

**Key Components:**  
- `fieldsense.spatial.bounds.FieldBounds`
- `fieldsense.spatial.grid.SpatialGrid`
- `fieldsense.spatial.idw.IDWInterpolator`
- `fieldsense.spatial.engine.SpatialEngine`
- `fieldsense.spatial.config.SpatialConfig`

**Tests / Verification:**  
56 tests passing (+7 new tests).

**Key Architectural Decision:**  
Grid nodes located beyond the maximum support distance ($100\text{m}$) from any valid sample point return `value = None` (unsupported), avoiding spatial extrapolation artifacts.

**Dependencies / Limitations:**  
Equirectangular local projection suitable for field scales ($< 10\text{km}$). Standard library math calculations (`math.hypot`, `math.radians`).

**Result:**  
Deterministic spatial interpolation engine operational across Soil Health, Nitrogen, Moisture, and Carbon Readiness layers.

**Next:**  
Sprint 6 — Zone Detection.

---

### Sprint 6 — Zone Detection

**Status:** COMPLETE

**Objective:**  
Partition continuous spatial grids into contiguous management zones based on grid cell classification and spatial proximity.

**Implementation Summary:**  
Developed a 4-neighbor Breadth-First Search (BFS) graph clustering algorithm to group continuous grid cells into discrete management zones (`HEALTHY`, `MODERATE`, `POOR`). Implemented minimum zone area merging ($< 2$ cells merged into neighboring zones), primary issue identification, and zone centroid calculation.

**Key Components:**  
- `fieldsense.zones.engine.ZoneEngine`
- `fieldsense.zones.models.Zone`
- `fieldsense.zones.models.ZoneDetectionResult`
- `fieldsense.zones.config.ZoneConfig`

**Tests / Verification:**  
62 tests passing (+6 new tests).

**Key Architectural Decision:**  
Zone spatial confidence reflects data point proximity/density within the zone rather than agronomic certainty.

**Dependencies / Limitations:**  
Requires active spatial grid input from Sprint 5.

**Result:**  
Management zone detection engine functional with robust component clustering and boundary merging.

**Next:**  
Sprint 7 — Recommendation Engine.

---

### Sprint 7 — Recommendation Engine

**Status:** COMPLETE

**Objective:**  
Generate traceable, rule-based, non-prescriptive management guidance based on identified zone issues and soil anomalies.

**Implementation Summary:**  
Implemented a rule-based decision support system evaluating zone metrics against agronomic threshold rules (`NutrientRule`, `MoistureRule`, `SalinityRule`, `SoilConditionRule`, `CarbonReadinessRule`, `MonitoringRule`). Added priority sorting, issue evidence tracking, ID deduplication, and max recommendation constraints ($3$ per zone).

**Key Components:**  
- `fieldsense.recommendations.engine.RecommendationEngine`
- `fieldsense.recommendations.models.Recommendation`
- `fieldsense.recommendations.models.RecommendationResult`
- `fieldsense.recommendations.rules.base.RecommendationRule`

**Tests / Verification:**  
71 tests passing (+9 new tests).

**Key Architectural Decision:**  
FieldSense recommendations strictly deliver high-level directional guidance (e.g. "Review nitrogen management") and **never** output unsupported quantitative chemical dosages (e.g. "Apply 25 kg/acre urea") or exact irrigation volumes.

**Dependencies / Limitations:**  
Rule trigger thresholds set to prototype defaults (`PROTOTYPE_ONLY`).

**Result:**  
Actionable, safe, rule-based recommendation engine verified across all test scenarios.

**Next:**  
Sprint 8 — Offline UI / Field Intelligence Map.

---

### Sprint 8 — Offline UI / Field Intelligence Map

**Status:** COMPLETE

**Objective:**  
Develop a passive presentation layer and offline HTML/CSS/SVG dashboard renderer for interactive field visualization without external web dependencies.

**Implementation Summary:**  
Created `UIViewAdapter` to transform backend intelligence objects into passive UI view models (`UIFieldView`). Implemented `LocalUIRenderer` which compiles raw HTML/CSS and inline SVG graphics to render spatial grid heatmaps, management zones, layer toggles, diagnostic cards, and structured recommendations.

**Key Components:**  
- `fieldsense.presentation.adapter.UIViewAdapter`
- `fieldsense.presentation.models.UIFieldView`
- `fieldsense.presentation.renderer.LocalUIRenderer`

**Tests / Verification:**  
75 tests passing (+4 new tests).

**Key Architectural Decision:**  
The presentation layer is strictly passive—it contains zero scoring, interpolation, or clustering logic, consuming pre-computed `UIFieldView` data structures exclusively.

**Dependencies / Limitations:**  
Self-contained HTML5 file output. Zero external network resources (no CDN scripts, web fonts, or remote tile maps).

**Result:**  
Standalone offline HTML visualizer generating interactive field dashboards in $< 50\text{ms}$.

**Next:**  
Sprint 9 — Hardware Integration Boundary.

---

### Sprint 9 — Hardware Integration Boundary

**Status:** COMPLETE

**Objective:**  
Define hardware transport abstractions, GPS position adapters, and the `HardwareSensorAdapter` boundary to enable physical sensor integration without altering downstream software pipelines.

**Implementation Summary:**  
Created `SensorTransport` interface, `GPSAdapter` model, `HardwareSensorAdapter`, `MockHardwareTransport`, and hardware data factory. Defined explicit error categories (`HardwareConnectionError`, `ModbusTimeoutError`, `GPSFixError`). Documented physical hardware parameters as unresolved (`HARDWARE_SPEC_REQUIRED`).

**Key Components:**  
- `fieldsense.hardware.sensor_adapter.HardwareSensorAdapter`
- `fieldsense.hardware.transport.base.SensorTransport`
- `fieldsense.hardware.gps.base.GPSAdapter`
- `fieldsense.hardware.factory.SensorSourceFactory`
- `fieldsense.hardware.config.HardwareConfig`

**Tests / Verification:**  
83 tests passing (+8 new tests).

**Key Architectural Decision:**  
`HardwareSensorAdapter` converts raw Modbus registers and GPS NMEA strings directly into canonical `FieldSample` objects, guaranteeing 100% downstream code reuse between virtual and physical operational modes.

**Dependencies / Limitations:**  
Physical serial parameters (baud rate, register offsets, dev paths) marked `PENDING HARDWARE`.

**Result:**  
Hardware isolation layer completed with mock transport verification.

**Next:**  
Sprint 10 — System Validation & Demonstration.

---

### Sprint 10 — System Validation & Demonstration

**Status:** COMPLETE

**Objective:**  
Validate complete end-to-end pipeline execution across golden test scenarios, fault injection matrices, and benchmark suites.

**Implementation Summary:**  
Constructed standard field test scenarios (`HEALTHY_FIELD`, `NUTRIENT_DEFICIENT`, `MOISTURE_DEFICIENT`, `MIXED_STRESS`, `SPATIAL_GRADIENT`). Added fault injection tests verifying graceful handling of corrupted GPS, extreme metric values, noisy sensors, and sparse sampling grids. Built execution latency benchmarks and CLI demo scripts.

**Key Components:**  
- `fieldsense.testing.golden_scenarios`
- `fieldsense.testing.fault_injection`
- `fieldsense.demo`
- `tests/test_golden_scenarios.py`
- `tests/test_fault_injection.py`
- `tests/test_benchmark.py`

**Tests / Verification:**  
98 tests passing (+15 new tests).

**Key Architectural Decision:**  
Faulty samples injected during testing confirmed that `ValidationEngine` successfully isolates bad data without crashing the spatial or zone engines.

**Dependencies / Limitations:**  
Benchmark results recorded on Windows host system (`HOST BENCHMARK`). Physical Debian/UNO Q benchmark marked `PENDING HARDWARE`.

**Result:**  
End-to-end pipeline robustness demonstrated across all test conditions.

**Next:**  
Sprint 11 — Competition Demo & Showcase Readiness.

---

### Sprint 11 — Competition Demo & Showcase Readiness

**Status:** COMPLETE

**Objective:**  
Finalize competition demonstration datasets, showcase visual layout, and step-by-step presentation documentation for technical showcases and judging.

**Implementation Summary:**  
Built `fieldsense.demo` entry point executing the full 8-stage pipeline to generate `artifacts/fieldsense_competition_demo.html`. Created `DEMO_GUIDE.md` detailing a 10-step demonstration walkthrough. Configured realistic 25-sample field dataset incorporating valid and rejected measurements.

**Key Components:**  
- `fieldsense/demo.py`
- `DEMO_GUIDE.md`
- `tests/test_competition_demo.py`
- `tests/test_demo.py`

**Tests / Verification:**  
102 tests passing (+4 new tests).

**Key Architectural Decision:**  
Demo runner explicitly highlights operational badges (`OFFLINE MODE`, `Data Source: VIRTUAL`, `Carbon Readiness: LIMITED PROXY`) on the dashboard header to uphold scientific and architectural honesty during showcases.

**Dependencies / Limitations:**  
Outputs single-file self-contained HTML artifact.

**Result:**  
Competition showcase runner complete and fully reproducible via `python -m fieldsense.demo`.

**Next:**  
Sprint 12 — Final Architecture Audit & Hardening.

---

### Sprint 12 — Final Architecture Audit & Hardening

**Status:** COMPLETE

**Objective:**  
Conduct a comprehensive system audit, resolve serialization edge cases, verify contract integrity, and establish release readiness for Phase 1.

**Implementation Summary:**  
Audited all 12 modules for architectural compliance, frozen contract alignment, type safety, and error handling. Discovered and resolved serialization gaps (ISO timestamp parsing, hardware model dictionaries, intelligence result round-tripping). Authored `PROPOSAL_ALIGNMENT.md` and `SPECIFICATION_REGISTER.md`.

**Key Components:**  
- `tests/test_sprint12_hardening.py`
- `PROPOSAL_ALIGNMENT.md`
- `SPECIFICATION_REGISTER.md`
- `docs/validation_and_limitations.md`

**Tests / Verification:**  
105 tests passing (+3 new tests).

**Key Architectural Decision:**  
Confirmed baseline release readiness tag `PHASE_1_RELEASE_READY`. All 105 tests verified passing with zero warnings or failures.

**Dependencies / Limitations:**  
All unresolved hardware and agronomic items logged in `SPECIFICATION_REGISTER.md`.

**Result:**  
Phase 1 core software architecture fully hardened, audited, tested, and release-ready.

---

## Phase 2 — Physical Hardware Integration

**Status:** PLANNED / PENDING HARDWARE

Phase 2 will integrate physical sensor hardware and embedded microcontrollers with the frozen Phase 1 software pipeline.

### Target Physical Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                       PHYSICAL SENSORS                      │
│  JXBS 7-in-1 Soil Sensor (RS485)    NEO-M8N GPS (UART)      │
└──────────────────────────────┬──────────────────────────────┘
                               │ RS485 / Serial Modbus RTU
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               ARDUINO UNO Q HARDWARE PLATFORM               │
│                                                             │
│  ┌──────────────────────┐        ┌──────────────────────┐   │
│  │   STM32U585 MCU      │        │  Qualcomm QRB2210    │   │
│  │  (Real-Time / I/O)   │──IPC──>│   (Debian Linux)     │   │
│  └──────────────────────┘        └──────────┬───────────┘   │
└─────────────────────────────────────────────┼───────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │  HardwareSensorAdapter  │
                                 └────────────┬────────────┘
                                              │ canonical FieldSample
                                              ▼
                                  PHASE 1 FROZEN PIPELINE
```

### Planned Phase 2 Sprints (Future Template)

```markdown
## Sprint 13 — Physical Hardware Specification & RS485 Transport

**Status:** PLANNED / PENDING HARDWARE

**Objective:**  
Implement production `RS485Transport` connecting to physical JXBS 7-in-1 soil sensor via serial Modbus RTU protocol based on confirmed hardware specs.

**Implementation Summary:**  
[To be populated upon sprint completion]

**Key Components:**  
- `fieldsense.hardware.transport.rs485.RS485Transport`
- `fieldsense.hardware.transport.modbus.ModbusRTUFrame`

**Tests / Verification:**  
[Target test count]

**Key Architectural Decision:**  
[To be populated upon sprint completion]

**Dependencies / Limitations:**  
Requires physical Arduino UNO Q board and JXBS 7-in-1 sensor hardware (`HW-01`, `HW-02`).

**Result:**  
[To be populated upon sprint completion]

**Next:**  
Sprint 14 — GPS UART Adapter Integration.
```

---

## Phase 3 — Future Development

**Status:** PLANNED

Phase 3 will expand system capabilities after hardware integration is validated.

1. **AI Explanation Layer**: Integrate an offline quantized LLM (e.g. Llama-3-8B / Phi-3 running locally via `llama.cpp` or ONNX on Qualcomm QRB2210) to parse structured `FieldSession` results into natural language farmer summaries without altering deterministic scores.
2. **Persistent Storage Layer**: Implement lightweight SQLite / JSON file storage adapter for session management, historical field tracking, and multi-temporal trend analysis.
3. **Advanced Display Rendering**: Extend passive UI rendering adapters to support physical touchscreens (e.g. 7-inch LCD display attached to Arduino UNO Q).

---

## Sprint Management Methodology

FieldSense software development follows strict sprint management procedures:

```text
  ┌──────────┐      ┌───────────────┐      ┌────────────────┐      ┌────────────┐
  │ 1. DEFINE│ ───> │ 2. IMPLEMENT  │ ───> │ 3. VERIFY      │ ───> │ 4. FREEZE  │
  │ Contract │      │ Bounded Scope │      │ Test & Audit   │      │ Baseline   │
  └──────────┘      └───────────────┘      └────────────────┘      └────────────┘
```

1. **Define Stage**: Human architect specifies single sprint objective, allowed file bounds, input/output contracts, and explicit constraints.
2. **Implementation Stage**: AI coding agent implements changes exclusively within bounded files. Unrelated modules must remain untouched.
3. **Verification Stage**: Agent executes targeted unit tests and full suite regression. Zero test failures allowed.
4. **Freeze Stage**: Once approved, sprint baseline is tagged frozen. Subsequent sprints must build upon frozen contracts without silent retrofitting.

---

## AI Agent Implementation Workflow

When instructing an AI coding agent (e.g., Antigravity, Gemini, Claude) to execute a sprint:

1. **Briefing**: Provide the agent with `01_SOFTWARE_WORKPLAN.md`, `03_ARCHITECTURE.md`, and the targeted Sprint Contract.
2. **Inspection Mandate**: Require the agent to inspect existing source files and test suites before writing code.
3. **Contract Preservation**: If an agent determines that an existing frozen contract must change, it must **STOP** and issue a formal request:
   ```text
   CONTRACT_CHANGE_REQUIRED:
   - Target Contract: [Name]
   - Proposed Change: [Details]
   - Architectural Rationale: [Reason]
   - Affected Modules: [List]
   - Migration Strategy: [Plan]
   ```
4. **Verification Requirement**: The agent must run `pytest` and confirm that all existing and new tests pass cleanly before returning.

---

## Sprint Completion Rules

A sprint is considered **COMPLETE** if and only if:
- [x] All sprint contract requirements are fully implemented.
- [x] Targeted unit tests cover 100% of newly added logic and edge cases.
- [x] Full regression test suite passes with **zero failures** (Current baseline: 105 passed).
- [x] Architectural boundaries and dependency directions are preserved.
- [x] No unauthorized external dependencies or cloud calls were added.
- [x] Unresolved hardware items are explicitly marked `PENDING HARDWARE` or `HARDWARE_SPEC_REQUIRED`.
- [x] Prototype agronomic boundaries are explicitly marked `PROTOTYPE_ONLY` or `AGRONOMIC_VALIDATION_REQUIRED`.
- [x] A compact sprint entry is appended to `01_SOFTWARE_WORKPLAN.md` without modifying historical entries.
