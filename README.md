# FieldSense AI

**Offline Portable Edge-Intelligence Platform for Multi-Point Soil Assessment & Carbon Readiness**

**STATUS:** DRAFT | **VERSION:** 0.1 | **RELEASE STATUS:** `PHASE_1_RELEASE_READY`  

---

## Overview

**FieldSense AI** is an offline, portable edge-intelligence system designed for dense, multi-point spatial soil assessment, management zone detection, non-prescriptive decision support, and Carbon Readiness proxy evaluation. Developed to run on resource-constrained edge hardware—specifically the **Arduino UNO Q** platform (Qualcomm QRB2210 MPU running Debian Linux alongside an STM32U585 MCU)—FieldSense AI resolves micro-spatial soil variability without relying on cloud infrastructure, remote web APIs, or active internet connectivity.

---

## Key Capabilities

- **Dense In-Situ Soil Surveying**: Collects multi-parameter physical soil metrics ($N, P, K, \text{pH}, \text{EC}, \text{Moisture}, \text{Temperature}$) tagged with GPS coordinates.
- **Automated Data Gatekeeper**: `ValidationEngine` filters corrupted or implausible sensor data prior to spatial mapping.
- **Deterministic Spatial Mapping**: Projects GPS coordinates to local Cartesian meters and generates continuous 2D raster surfaces via Inverse Distance Weighting (IDW, $p=2.0$).
- **Management Zone Clustering**: Groups continuous spatial cells into discrete contiguous management zones (`HEALTHY`, `MODERATE`, `POOR`) using 4-neighbor BFS graph connectivity.
- **Rule-Based Decision Support**: Emits category-mapped qualitative guidance while strictly prohibiting unsupported quantitative chemical or fertilizer dosages.
- **100% Offline Visualization**: Renders interactive HTML/CSS/SVG field intelligence dashboards locally in $< 50\text{ms}$ with zero network requests.

---

## High-Level Architecture

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
  └────────────┬───────────┘
               │ (Optional)
               ▼
  ┌────────────────────────┐
  │   Edge LLM Explainer   │ ── (Passive local natural language summaries)
  └────────────────────────┘
```

---

## Official Documentation Repository

The official project documentation is structured under `docs/`:

1. [Project Handbook](file:///C:/Users/lovsh/Desktop/FieldSense/docs/PROJECT_HANDBOOK.md) — Master project overview, purpose, problem, core features, team structure, and scientific constraints.
2. [System Architecture](file:///C:/Users/lovsh/Desktop/FieldSense/docs/SYSTEM_ARCHITECTURE.md) — Technical architecture, layer boundaries, data flows, Arduino UNO Q MPU/MCU split, and Mermaid diagrams.
3. [Hardware Specification](file:///C:/Users/lovsh/Desktop/FieldSense/docs/HARDWARE_SPEC.md) — Authoritative hardware component specs, JXBS Modbus register map, NEO-M8N GPS settings, MAX485 interfaces, and status confidence tags.
4. [Software Specification](file:///C:/Users/lovsh/Desktop/FieldSense/docs/SOFTWARE_SPEC.md) — Authoritative software specification, module schemas, domain contracts (`FieldSample`, `FieldSession`), algorithms, and layer contracts.
5. [Test & Validation Record](file:///C:/Users/lovsh/Desktop/FieldSense/docs/TEST_AND_VALIDATION.md) — Evidence log, 105-test regression baseline, golden scenarios, fault injection suite, and performance benchmarks.
6. [Decision Log](file:///C:/Users/lovsh/Desktop/FieldSense/docs/DECISION_LOG.md) — Log of major engineering, architectural, protocol, and boundary decisions (`D-001` through `D-009`).

---

## Current Status & Quick Start

- **Phase 1 Status**: COMPLETE (`PHASE_1_RELEASE_READY`)
- **Automated Regression Suite**: 105 tests passing in $< 1.0\text{s}$

### Quick Start (Competition Showcase Run)
Generate the self-contained offline competition dashboard:
```bash
python -m fieldsense.demo
```
Open `artifacts/fieldsense_competition_demo.html` in any browser.

### Run Automated Tests
Execute the full test suite:
```bash
pytest
```