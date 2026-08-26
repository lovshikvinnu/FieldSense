# FieldSense AI — Official Decision Log

**STATUS:** DRAFT  
**VERSION:** 0.1.1  
**LAST UPDATED:** 2026-08-23  

This document logs all major engineering, architectural, scientific boundary, and protocol decisions for FieldSense AI. Trivial implementation details are excluded.

---

### D-001 — Frozen Domain Core & Immutability of FieldSample

**Date:** 2026-08-09  
**Status:** APPROVED / FROZEN  

**Decision:**  
Implement `FieldSample` as a pure, immutable (`frozen=True`) dataclass in Python standard library containing 14 canonical fields (`sample_id`, `timestamp`, `latitude`, `longitude`, `nitrogen`, `phosphorus`, `potassium`, `ph`, `ec`, `moisture`, `temperature`, `measurement_quality`, `source`, `validation_state`).

**Reason:**  
Prevents downstream processing engines (validation, scoring, spatial IDW, zone detection, presentation) from silently modifying raw observational measurements. Raw data integrity is preserved across the entire system lifecycle.

**Impact:**  
Downstream modules must create new objects or derived views rather than mutating raw samples. Raw data remains 100% auditable.

**Related system:**  
Domain Core (`fieldsense.domain.models.sample`)

---

### D-002 — Sensor Abstraction & Hardware Independence

**Date:** 2026-08-09  
**Status:** APPROVED / FROZEN  

**Decision:**  
Establish an abstract `SensorAdapter` interface. Both `VirtualSensorAdapter` (simulation) and `HardwareSensorAdapter` (physical RS485/UART hardware) emit identical, immutable `FieldSample` objects.

**Reason:**  
Enables complete software pipeline development, spatial algorithm testing, and local UI rendering prior to physical hardware availability, guaranteeing 100% code reuse when physical sensors are connected.

**Impact:**  
Downstream engines are 100% agnostic to data origin (`SampleSource.VIRTUAL` vs `SampleSource.HARDWARE`). Zero downstream code changes are required when switching sources.

**Related system:**  
Input & Hardware Abstraction Boundary (`fieldsense.input`, `fieldsense.hardware`)

---

### D-003 — Automated Validation Gatekeeper & Raw Sample Retention

**Date:** 2026-08-09  
**Status:** APPROVED / FROZEN  

**Decision:**  
Implement `ValidationEngine` to sanitize raw measurements before spatial processing. Samples violating physical bounds are tagged `REJECTED` and `pipeline_eligible = False`. Rejected samples are excluded from spatial interpolation but remain preserved in `FieldSession.samples`.

**Reason:**  
Prevents corrupted sensor data or electrical noise from corrupting spatial maps and management zones while preserving complete operational data lineage for auditability.

**Impact:**  
Spatial and zone engines filter for `pipeline_eligible` samples, while diagnostics cards report rejected samples with failure reason codes.

**Related system:**  
Validation Engine (`fieldsense.intelligence.validation`)

---

### D-004 — 100% Deterministic Core (No LLM in Analytical Path)

**Date:** 2026-08-09  
**Status:** APPROVED / FROZEN  

**Decision:**  
All validation, normalization scoring, MCDA aggregation, spatial IDW interpolation, 4-neighbor BFS zone detection, and recommendation rules must execute 100% deterministically using explicit mathematical algorithms. Large Language Models (LLMs) are forbidden from calculating or modifying scores.

**Reason:**  
Guarantees mathematical reproducibility, complete auditability, zero AI hallucination risk, and rapid execution ($< 50\text{ms}$) on resource-constrained edge hardware.

**Impact:**  
LLMs are strictly isolated downstream as optional, passive summary explainers that consume structured JSON results.

**Related system:**  
Intelligence, Spatial, Zone, and Recommendation Engines

---

### D-005 — Carbon Readiness Scientific & Agronomic Safety Boundary

**Date:** 2026-08-09  
**Status:** APPROVED / FROZEN  

**Decision:**  
Carbon Readiness is strictly defined as an engineering decision-support proxy index (`decision_support_only = True`, `evidence_level = "LIMITED"`). Direct Soil Organic Carbon (SOC) mass claims, carbon tonnage calculations, and MRV/carbon credit certification claims are strictly prohibited. Missing indicators (`soil_organic_carbon`, `bulk_density`, `management_history`) are explicitly declared.

**Reason:**  
Physical 7-in-1 sensors ($N, P, K, \text{pH}, \text{EC}, \text{Moisture}, \text{Temp}$) do not measure direct soil carbon. Claiming carbon credit verification based only on proxy sensors is scientifically invalid.

**Impact:**  
UI dashboards, exports, and reports explicitly display safety warnings and proxy limits.

**Related system:**  
Intelligence Scoring (`fieldsense.intelligence.scoring`)

---

### D-006 — Non-Prescriptive Directional Guidance in Recommendation Engine

**Date:** 2026-08-09  
**Status:** APPROVED / FROZEN  

**Decision:**  
The recommendation engine outputs qualitative directional advice (e.g. *"Review nitrogen availability"*) and strictly prohibits quantitative fertilizer or chemical dosage figures (e.g. *"Apply 25 kg/acre urea"*) or irrigation volumes.

**Reason:**  
Quantitative chemical prescriptions require laboratory soil buffer testing and localized crop response calibration. Emitting unverified chemical dosages creates severe agronomic and safety risks for farmers.

**Impact:**  
Recommendation rules remain safe, traceable, non-prescriptive, and category-mapped.

**Related system:**  
Recommendation Engine (`fieldsense.recommendations`)

---

### D-007 — Equirectangular Cartesian Projection & Capped IDW Support Distance

**Date:** 2026-08-09  
**Status:** APPROVED / FROZEN  

**Decision:**  
Project geographic GPS coordinates to local Cartesian meters $(x,y)$ using equirectangular projection centered on sample centroid. Execute IDW interpolation ($p=2.0$) with max support distance capped at $100\text{m}$ and minimum valid sample count $N \ge 3$.

**Reason:**  
Avoids heavy GIS dependencies (e.g., GDAL, PROJ) while providing accurate distance math for field-scale plots ($< 10\text{km}$). Capping support distance prevents arbitrary spatial extrapolation into unmonitored field areas.

**Impact:**  
Grid nodes $> 100\text{m}$ from the nearest valid sample point return `value = None` (unsupported).

**Related system:**  
Spatial Engine (`fieldsense.spatial`)

---

### D-008 — Passive Presentation Layer & Local Offline Renderer

**Date:** 2026-08-09  
**Status:** APPROVED / FROZEN  

**Decision:**  
Map backend intelligence objects to passive `UIFieldView` view models via `UIViewAdapter`. Render local dashboards using `LocalUIRenderer` compiling single-file HTML with inline CSS and native Python SVG vector graphics. Zero external CDN, font, or web map dependencies.

**Reason:**  
Guarantees 100% offline sovereignty on edge devices in remote agricultural fields without internet connectivity.

**Impact:**  
Presentation layer contains zero calculation logic. Dashboard opens instantly in any standard web browser.

**Related system:**  
Presentation Layer (`fieldsense.presentation`)

---

### D-009 — Standard Library Execution Architecture

**Date:** 2026-08-09  
**Status:** APPROVED / FROZEN  

**Decision:**  
Build the software pipeline using Python standard libraries exclusively (`dataclasses`, `enum`, `datetime`, `math`, `json`, `uuid`, `xml.etree`). Prohibit heavy third-party packages (NumPy, SciPy, Pandas, PyTorch).

**Reason:**  
Enables lightweight deployment on target Debian Linux edge hardware (Qualcomm QRB2210 on Arduino UNO Q) with $< 25\text{MB}$ RAM footprint and sub-50ms execution times.

**Impact:**  
Zero complex package installation or binary cross-compilation required for edge hardware.

**Related system:**  
Entire System Architecture

---

### D-010 — Physical JXBS 7-in-1 Register Mapping & Byte-Framed Modbus Read Strategy

**Date:** 2026-08-22  
**Status:** APPROVED / CONFIRMED  

**Decision:**  
Adopt the empirical JXBS 7-in-1 Modbus RTU register map (`0x0006` pH, `0x0012` Moisture, `0x0013` Temperature, `0x0015` EC, `0x001E` Nitrogen, `0x001F` Phosphorus, `0x0020` Potassium) and enforce explicit 7-byte read buffer framing (`ser.read(7)` with timeout) over serial transport.

**Reason:**  
Empirical hardware bench testing demonstrated that relying on `ser.read(ser.in_waiting)` creates buffer race conditions returning 0 bytes before Modbus frame arrival over RS485. Fixed-length 7-byte reads with serial timeout guarantee frame arrival and 100% Modbus CRC pass rate.

**Impact:**  
Hardware sensor adapter and test drivers read physical sensor registers reliably without frame truncation or silent empty buffer reads.

**Related system:**  
Hardware Interface Boundary (`fieldsense.hardware`, `hardware/soil-probe/jxbs_test.py`)

