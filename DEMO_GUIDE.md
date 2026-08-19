# FieldSense AI — Competition Demonstration Guide

This guide walks through demonstrating **FieldSense AI** for judging, presentations, and technical showcases.

---

## Quick Start (1-Minute Run)

```bash
python -m fieldsense.demo
```

This command executes the complete 8-stage FieldSense pipeline and generates the self-contained offline HTML dashboard artifact at:

`artifacts/fieldsense_competition_demo.html`

Open `artifacts/fieldsense_competition_demo.html` in any web browser.

---

## 10-Step Demonstration Walkthrough

### Step 1 — Start the System
Run `python -m fieldsense.demo` in the terminal to demonstrate rapid execution (< 0.5s) on resource-constrained platforms.

### Step 2 — Open the Offline Dashboard
Open `artifacts/fieldsense_competition_demo.html`. Point out the header indicators:
- `OFFLINE MODE`: FieldSense operates 100% locally without cloud dependencies.
- `Data Source: VIRTUAL`: Explicitly identifies the simulation source prior to physical hardware attachment.

### Step 3 — Explain Sampling & Acquisition
Highlight the sampling status card ($25\text{ Total Samples}$, $24\text{ Valid}$, $1\text{ Rejected}$). Explain that each measurement is GPS-tagged with latitude, longitude, timestamp, and 7 physical soil metrics ($N, P, K, \text{pH}, \text{EC}, \text{Moisture}, \text{Temperature}$).

### Step 4 — Explain the Field Intelligence Map
Show the interactive SVG grid map. Explain that spatial coordinates are projected into local Cartesian meters $(x,y)$ and continuous surfaces are generated using Inverse Distance Weighting (IDW, $p=2.0$). Click any cell on the grid to inspect exact coordinates, layer scores, and nearest sample support distances.

### Step 5 — Demonstrate Layer Switching
Use the layer dropdown to switch between:
1. **Soil Health**: Aggregate deterministic multi-criteria score.
2. **Nitrogen Index**: Soil nitrogen availability.
3. **Moisture Index**: Volumetric soil moisture percentage.
4. **Carbon Readiness**: Limited proxy index.

> **Key Point**: Switching layers operates on pre-computed data in real-time without re-running calculations.

### Step 6 — Explain Management Zones
Show how contiguous cells with similar conditions form spatially connected management zones (4-neighbor grid connectivity). Point out that each zone identifies:
- Zone Status (`HEALTHY`, `MODERATE`, `POOR`) and Severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- Primary Issue (e.g. `Nitrogen` or `Moisture`).
- Spatial Data Support Confidence (`HIGH`, `MEDIUM`, `LOW`).
- Estimated Zone Area in $\text{m}^2$.

### Step 7 — Explain Structured Recommendations
Navigate to the "What Needs Attention" panel. Show how detected zone issues trigger rule-based decision-support actions:
- `NUTRIENT`: "Review nitrogen availability and consider targeted nutrient management."
- `WATER`: "Review irrigation timing and soil moisture conditions in this zone."
- `MONITORING`: "Maintain routine soil monitoring..."

> **🔴 AI / Prescription Safety**: Point out that FieldSense provides high-level management decision support without inventing unsupported chemical/fertilizer dosages (e.g. no "25 kg/acre urea") or irrigation volumes.

### Step 8 — Explain Reliability & Auditability
Show the Diagnostics card ($1\text{ Rejected Sample: UNSTABLE\_MEASUREMENT}$). Explain that noisy/unstable hardware sensor data is rejected by the gatekeeper `ValidationEngine` and excluded from spatial maps to prevent map corruption, while remaining visible for auditability.

### Step 9 — Explain Carbon Readiness Scientific Boundary
Select the Carbon Readiness layer. Emphasize that `CarbonReadinessResult` is a decision-support index tagged `evidence_level = "LIMITED"` and `decision_support_only = True`. Point out the explicit missing indicators list (`soil_organic_carbon`, `bulk_density`, `management_history`). Explain that FieldSense does NOT claim to measure soil carbon or generate carbon credits.

### Step 10 — Explain Hardware Transition
Explain the hardware-ready architecture:

```text
┌────────────────────────┐
│  VirtualSensorAdapter  │──┐
└────────────────────────┘  │    FieldSample     SAME PIPELINE
                            ├──> (Canonical) ──> Validation ──> Intelligence ──> Spatial ──> Zones ──> UI
┌────────────────────────┐  │
│ HardwareSensorAdapter  │──┘
└────────────────────────┘
```

When connecting the physical JXBS 7-in-1 sensor and NEO-M8N GPS module via `HardwareSensorAdapter`, the downstream validation, spatial, zone, recommendation, and UI code remains **100% unchanged**.
