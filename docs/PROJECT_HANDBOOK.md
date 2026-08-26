# FieldSense AI — Project Handbook

**STATUS:** DRAFT  
**VERSION:** 0.1.1  
**LAST UPDATED:** 2026-08-23  
**CURRENT STAGE:** V1 Integration  
**COMPONENT VERIFICATION:** 🟢 COMPLETE  
**V1 SYSTEM INTEGRATION:** 🟡 ACTIVE  
**CURRENT OBJECTIVE:** Establish unified real-data acquisition from physical hardware and feed it into the existing Phase 1 software pipeline.  

---

## 1. Executive Summary & Project Purpose

**FieldSense AI** is an offline, portable edge-intelligence platform engineered for multi-point spatial soil assessment, management zone detection, decision support, and Carbon Readiness proxy evaluation. Built to run on resource-constrained embedded edge hardware—specifically the **Arduino UNO Q** platform (Qualcomm QRB2210 MPU running Debian Linux alongside an STM32U585 MCU)—FieldSense AI resolves spatial soil variability without relying on cloud infrastructure, remote web APIs, or active internet connectivity.

> [!IMPORTANT]
> **Current Status Summary**: All major V1 hardware components (Arduino UNO Q, JXBS 7-in-1 Soil Sensor, NEO-M8N GPS Module, MAX485/USB-RS485 interface, ST7789 TFT Display, XPT2046 Touch) have passed isolated component verification (`🟢 COMPLETE`). Initial UNO Q integration has successfully demonstrated physical GPS (Serial1 $\rightarrow$ Bridge $\rightarrow$ Linux), soil-sensor (USB-RS485 $\rightarrow$ USB-C Hub $\rightarrow$ Linux), display (Native Hardware SPI), touch ($320 \times 240$ coordinate mapping), and Bridge/RPC paths. The project is now actively performing unified real-data acquisition and end-to-end `FieldSample` validation (`🟡 V1 INTEGRATION ACTIVE`).

### Current Integration Roadmap
```text
COMPONENT VERIFICATION
🟢 COMPLETE
      │
      ▼
UNIFIED REAL-DATA ACQUISITION
🟡 NEXT
      │
      ▼
GPS + JXBS SIMULTANEOUS ACQUISITION
      │
      ▼
FieldSample GENERATION
      │
      ▼
REAL HARDWARE SAMPLES
      │
      ▼
PHASE 1 DETERMINISTIC PIPELINE
      │
      ▼
SPATIAL PROCESSING
      │
      ▼
ZONES
      │
      ▼
RECOMMENDATIONS
      │
      ▼
TFT FIELD INTELLIGENCE UI
      │
      ▼
END-TO-END V1 DEMONSTRATION
```

The project bridges the gap between low-cost physical sensor hardware, spatial geostatistics, deterministic agronomic rules, and human-understandable visual interfaces.

---

## 2. Problem Statement

Agricultural fields exhibit substantial micro-spatial variability in soil chemistry, moisture, and nutrient availability due to topography, soil texture, historical management, and drainage. Traditional soil testing relies on sparse composite sampling (e.g., 1 to 3 mixed samples per field), which averages out local extremes and masks localized degraded areas.

Furthermore:
- **Cloud Dependency Failure**: Digital farming tools that require cloud processing fail in remote rural regions lacking reliable cellular networks.
- **AI Hallucination Risk**: Existing generative AI tools in agriculture often suffer from hallucination risks, attempting to predict chemical dosages or carbon credit values without deterministic validation or empirical boundary enforcement.
- **Hardware Integration Barriers**: Combining real-time physical sensor data collection with localized spatial mapping on low-power edge hardware remains a key engineering challenge.

---

## 3. The FieldSense Solution

FieldSense AI provides an integrated hardware-software edge platform that enables dense, multi-point, in-situ soil sampling across agricultural plots:

1. **Dense Sampling Workflow**: Operators collect multiple GPS-tagged readings across a field using an integrated physical sensor probe or simulated test profile.
2. **Automated Data Quality Gatekeeper**: An internal validation engine filters corrupted or physically implausible readings before spatial interpolation.
3. **Deterministic Spatial Interpolation**: Point measurements are projected to local Cartesian coordinates and interpolated into continuous 2D raster surfaces using Inverse Distance Weighting (IDW).
4. **Automated Management Zone Clustering**: Contiguous grid cells with similar health metrics are grouped into spatial management zones via graph connectivity algorithms.
5. **Non-Prescriptive Rule Guidance**: Actionable, category-mapped decision-support recommendations are generated based on identified zone deficiencies.
6. **100% Offline Visualization**: Self-contained HTML/CSS/SVG field intelligence dashboards render locally in $< 50\text{ms}$ with zero network requests.

---

## 4. Core Features & Capabilities

- **Immutable Canonical Domain Model (`FieldSample`)**: Standardized data representation connecting hardware/virtual inputs to downstream software modules.
- **Hardware Transparency**: Agnostic pipeline execution whether receiving data from virtual field generators (`VIRTUAL`) or physical RS485/UART sensors (`HARDWARE`).
- **Deterministic Pipeline (No LLM in Core Path)**: 100% reproducible validation, MCDA scoring, IDW grid generation, zone detection, and rule evaluation.
- **Carbon Readiness Proxy Index**: Decision-support indicator evaluating soil physical suitability for organic carbon retention, strictly tagged `evidence_level = "LIMITED"`.
- **Offline Edge Operations**: Complete runtime sovereignty on target Debian Linux edge hardware (Qualcomm QRB2210 on Arduino UNO Q).
- **Fault-Tolerant Execution**: Graceful handling of out-of-bounds readings, sensor noise, corrupted GPS fixes, and sparse sampling grids ($N < 3$).

---

## 5. System Overview

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
  │     SpatialEngine      │ ── (Projects x,y meters & computes 2D IDW rasters)
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

## 6. Development Phases & Current Status

### Development Phases & Phase Transition
- **Phase 0 — Architecture Freeze (COMPLETE)**: Defined frozen domain contracts, canonical pipeline, module boundaries, and dependency directions.
- **Phase 1 — Software Architecture & Intelligence (COMPLETE)**: Implemented 100% offline Python software pipeline, virtual field simulation, validation, MCDA scoring, spatial IDW engine, BFS zone detection, recommendation rules, passive UI renderer, mock hardware interfaces, and 178-test regression baseline.
- **Component Verification Phase (COMPLETE 🟢)**: All individual V1 hardware components and the UNO Q main compute platform have successfully passed component-level physical validation.
- **Phase 2 — V1 Hardware Integration (STARTING 🚀)**: Connecting and validating verified components as a complete physical end-to-end FieldSense system.
- **Phase 3 — Extensions (PARTIALLY COMPLETE)**: The local edge SLM explanation layer (`fieldsense/ai/`) and the display bridge to the 2.8" panel (`fieldsense/hardware/display_bridge.py`) are **implemented**; both await physical integration. SQLite historical session storage remains `PLANNED`.

```text
Component Verification
        ↓
   🟢 COMPLETE
        ↓
V1 Hardware Integration
        ↓
GPS integration (NEO-M8N → UNO Q)
        ↓
RS485/JXBS integration
        ↓
Display/touch integration
        ↓
Complete FieldSample path
        ↓
End-to-end validation
```

> [!IMPORTANT]
> **Important System Integration Distinction:**  
> All individual V1 hardware components and the UNO Q platform have passed component-level validation. The project is now entering V1 system integration, where the verified components will be connected and validated as a complete system.

### First Planned V1 Integration Step
- **NEO-M8N GPS → Arduino UNO Q**
- **Purpose**: Establish the first real external peripheral → UNO Q → Bridge/RPC → Linux/Python data path.

### Hardware Procurement & Project Timeline
- **Components Ordered**: 17/08/2026 (Procured via Robu and TechieSMS)
- **Components Received**: 21/08/2026 (Physical hardware received in-hand)
- **Component Verification Complete**: 22/08/2026 (All core V1 hardware components & UNO Q platform verified)
- **Submission Deadline**: 23/08/2026 (Project submission deadline)
- **Integration Timeline**: Phase 2 V1 Hardware Integration active prior to submission deadline.

### Current Project Status
- **Software Baseline**: `PHASE_1_RELEASE_READY`
- **Regression Test Baseline**: $178\text{ passed}$
- **Current Component Verification Status**:
  - 🌱 JXBS 7-in-1 Soil Sensor — 🟢 **VERIFIED**
  - 📍 NEO-M8N GPS Module — 🟢 **VERIFIED**
  - 🔌 MAX485 Transceiver Module — 🟢 **VERIFIED**
  - 🖥️ ST7789 + XPT2046 Display — 🟢 **VERIFIED**
  - 🧠 Arduino UNO Q — 🟢 **VERIFIED**

**COMPONENT VERIFICATION PHASE:** 🟢 **COMPLETE**  
**NEXT PHASE:** **PHASE 2 — V1 INTEGRATION** (First step: NEO-M8N GPS → Arduino UNO Q)

---

## 7. Project & Team Structure

- **Context**: University-funded research prototype (Mahindra University) and competition submission for the **Arduino Physical AI Challenge India 2026**.
- **Roles & Responsibilities**:
  - **System Architect**: Defines domain contracts, layer boundaries, and module dependency rules.
  - **Embedded / Hardware Engineer**: Manages physical sensor selection, MAX485 wiring, serial protocols, UART device paths, and STM32 pin ownership.
  - **Agronomic Lead**: Establishes parameter sanity bounds, normalization optimum bands, MCDA weighting vectors, and recommendation rule definitions.
  - **Software / Documentation Engineer**: Implements core Python engines, maintains frozen contracts, enforces test coverage, and manages official documentation repository.

---

## 7b. AI Explanation Layer

- **Status**: `IMPLEMENTED` (`fieldsense/ai/`) — downstream consumer, optional and out of band.
- **Boundary**: Optional local SLM / LLM module. Consumes deterministic results reduced to an `ExplanationContext` and generates natural language summaries. Cannot alter deterministic scores or invent new metrics.
- **Contract**: `LocalLLMAdapter` ABC, mirroring `SensorAdapter` (`initialize` / `explain` / `shutdown`, plus `is_available`).
- **Backends**: `MockAIAdapter` (deterministic templates, always available, no weights required) and `LlamaCppAdapter` (quantized GGUF via a `llama.cpp` binary). `AIAdapterFactory` resolves between them; absent weights is a normal condition, not an error.
- **Safety Gate**: `NarrativeGuard` deterministically rejects generated text containing dose units, agrochemical names, carbon credit or sequestration claims, or any number absent from the `ExplanationContext`. Rejected sections degrade to deterministic templates. This is the language-side counterpart to the data-side `ValidationEngine`.
- **Timing Boundary**: Real model inference costs tens of seconds, far exceeding the `< 500 ms` deterministic pipeline budget. The layer therefore runs **after** the pipeline completes and is always discardable — the dashboard renders fully when `narrative` is `None`.
- **Determinism**: `AINarrative` is **non-normative presentation text**, excluded from the bit-exact guarantee when produced by a model. `MockAIAdapter` is bit-exact and is used by all golden scenario and benchmark tests. See [CCR-001_UIFieldView_Narrative.md](archive/CCR-001_UIFieldView_Narrative.md).
- **Dependencies**: None added. `llama.cpp` is invoked as an external binary via stdlib `subprocess`, so `dependencies` remains `[]`.

Deployment: [AI_DEPLOYMENT.md](AI_DEPLOYMENT.md).

---

## 8. Important Constraints & Scientific Boundaries

1. **No Direct Soil Organic Carbon (SOC) Measurement**: FieldSense AI does **NOT** directly measure certified Soil Organic Carbon mass or percentage.
2. **Carbon Readiness as Decision Support Only**: Carbon Readiness is an engineering proxy signal (`decision_support_only = True`, `evidence_level = "LIMITED"`). It does **NOT** constitute MRV (Measurement, Reporting, and Verification) or certified carbon credit issuance.
3. **Authoritative Deterministic Pipeline**: All validation, scoring, spatial interpolation, zone partitioning, and rule actions execute deterministically without LLM involvement.
4. **AI Explains Only**: Generative AI / LLM components exist exclusively downstream as passive summary explainers. AI must **NEVER** calculate, modify, replace, or invent soil metrics or deterministic scores.
5. **No Unsupported Quantitative Prescriptions**: The recommendation engine outputs qualitative directional guidance (e.g. *"Review nitrogen availability"*) and strictly prohibits quantitative fertilizer dosages (e.g. *"Apply 25 kg/acre urea"*) or irrigation volumes.
6. **GPS-Derived Spatial Intelligence Map**: Field Intelligence Maps are generated locally using Cartesian projections of GPS coordinates. Google Maps / satellite tile imagery is a future visual enhancement, not a Phase 1 operational dependency.
7. **100% Offline Sovereignty**: All calculations and UI rendering execute locally on edge hardware with zero HTTP/HTTPS network dependencies.

---

## 9. Competition Objective & Target Audience

### Competition Objective
Designed for technical showcases, hackathon judging, and peer review during the **Arduino Physical AI Challenge India 2026**, demonstrating how physical microcontrollers and edge MPUs can deliver real-time, trustworthy, offline AI solutions to resource-constrained domains like precision agriculture.

### Target Audience
- **Agronomists & Field Extension Workers**: Rapid on-site soil variability diagnosis and management zone boundary setup.
- **Small-to-Medium Farmers**: Simple, intuitive, offline spatial visual maps highlighting field stress areas without software subscription fees.
- **Faculty Reviewers & Hackathon Judges**: Auditable, contract-first software architecture with high test coverage and transparent scientific boundaries.

---

## 10. How to Navigate the Project Repository

### Official Documentation Structure

| Document | Contents |
| :--- | :--- |
| [../README.md](../README.md) | Entry point, directory map, quick start |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | How to test every component + the test evidence register |
| [PROJECT_HANDBOOK.md](PROJECT_HANDBOOK.md) | *(this document)* Purpose, objectives, constraints |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, software specification, decision log |
| [HARDWARE.md](HARDWARE.md) | Component specs, register maps, wiring, verification |
| [AI_DEPLOYMENT.md](AI_DEPLOYMENT.md) | Local SLM layer and the 2.8" display bridge |
| [STATUS.md](STATUS.md) | Requirements matrix and every open specification item |
| [DEMO_GUIDE.md](DEMO_GUIDE.md) | Presentation walkthrough |
| `archive/` | Superseded Phase 1 documentation |

### Quick Start Commands
- **Run Competition Demonstration Runner**:
  ```bash
  python -m fieldsense.demo
  ```
  Generates `artifacts/fieldsense_competition_demo.html`.
- **Run Full Regression Test Suite**:
  ```bash
  pytest
  ```
  Executes all 178 automated unit and integration tests.
