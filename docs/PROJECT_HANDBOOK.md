# FieldSense AI — Project Handbook

**STATUS:** DRAFT  
**VERSION:** 0.1  
**LAST UPDATED:** 2026-08-22  
**PROJECT PHASE:** Component Verification Complete — Phase 2 V1 Hardware Integration Starting  
**RELEASE STATUS:** `PHASE_1_RELEASE_READY`  

---

## 1. Executive Summary & Project Purpose

**FieldSense AI** is an offline, portable edge-intelligence platform engineered for multi-point spatial soil assessment, management zone detection, decision support, and Carbon Readiness proxy evaluation. Built to run on resource-constrained embedded edge hardware—specifically the **Arduino UNO Q** platform (Qualcomm QRB2210 MPU running Debian Linux alongside an STM32U585 MCU)—FieldSense AI resolves spatial soil variability without relying on cloud infrastructure, remote web APIs, or active internet connectivity.

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
- **Phase 1 — Software Architecture & Intelligence (COMPLETE)**: Implemented 100% offline Python software pipeline, virtual field simulation, validation, MCDA scoring, spatial IDW engine, BFS zone detection, recommendation rules, passive UI renderer, mock hardware interfaces, and 105-test regression baseline.
- **Component Verification Phase (COMPLETE 🟢)**: All individual V1 hardware components and the UNO Q main compute platform have successfully passed component-level physical validation.
- **Phase 2 — V1 Hardware Integration (STARTING 🚀)**: Connecting and validating verified components as a complete physical end-to-end FieldSense system.
- **Phase 3 — Future Extensions (PLANNED)**: Local edge LLM explanation layer (via `llama.cpp` / ONNX), SQLite historical session storage, and framebuffer driver for physical handheld LCD displays.

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
- **Regression Test Baseline**: $105\text{ passed}$ in $< 1.0\text{s}$
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

### Official Documentation Structure (`docs/`)
- [README.md](file:///C:/Users/lovsh/Desktop/FieldSense/README.md) — Root entry point and project overview.
- [docs/PROJECT_HANDBOOK.md](file:///C:/Users/lovsh/Desktop/FieldSense/docs/PROJECT_HANDBOOK.md) — (This document) Master overview, objectives, and constraints.
- [docs/SYSTEM_ARCHITECTURE.md](file:///C:/Users/lovsh/Desktop/FieldSense/docs/SYSTEM_ARCHITECTURE.md) — Deep technical architecture, data flows, and Mermaid diagrams.
- [docs/HARDWARE_SPEC.md](file:///C:/Users/lovsh/Desktop/FieldSense/docs/HARDWARE_SPEC.md) — Authoritative hardware component specs, register maps, and pin assignments.
- [docs/SOFTWARE_SPEC.md](file:///C:/Users/lovsh/Desktop/FieldSense/docs/SOFTWARE_SPEC.md) — Authoritative software specification, module contracts, and behavioral schemas.
- [docs/TEST_AND_VALIDATION.md](file:///C:/Users/lovsh/Desktop/FieldSense/docs/TEST_AND_VALIDATION.md) — Test suite results, golden scenario evidence, fault matrices, and benchmarks.
- [docs/DECISION_LOG.md](file:///C:/Users/lovsh/Desktop/FieldSense/docs/DECISION_LOG.md) — Log of major engineering, architectural, and protocol decisions (`D-001` to `D-009`).

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
  Executes all 105 automated unit and integration tests.
