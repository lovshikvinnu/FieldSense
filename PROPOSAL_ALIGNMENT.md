# FieldSense AI — Proposal Alignment & Requirements Matrix

This document tracks alignment between the **FieldSense AI Project Architecture / Proposal** and the **Phase 1 Software Implementation**.

---

## Requirements Alignment Matrix

| Module | Requirement | Status | Evidence | Gap |
| :--- | :--- | :--- | :--- | :--- |
| **Domain** | Canonical `FieldSample` & `FieldSession` contracts | `IMPLEMENTED` | `fieldsense/domain/models/` | None. 100% pure data contract. |
| **Sensor** | `SensorAdapter` ABC & `VirtualSensorAdapter` | `IMPLEMENTED` | `fieldsense/input/` | None. Deterministic simulation. |
| **Validation** | Sanity gatekeeper (`VALID`, `VALID_WITH_WARNING`, `REJECTED`) | `IMPLEMENTED` | `fieldsense/intelligence/validation/` | None. Rejected data excluded from spatial engine. |
| **Intelligence** | Deterministic MCDA scoring ($[0,1]$ scale) | `IMPLEMENTED` | `fieldsense/intelligence/scoring/` | Prototype methodology tagged `0.1`. |
| **Carbon Readiness**| Engineering decision-support signal (`decision_support_only = True`) | `IMPLEMENTED` | `fieldsense/intelligence/scoring/models.py` | Missing indicators explicit (`SOC`, `bulk_density`). |
| **Spatial Engine** | IDW ($p=2.0$), local meters projection, bounds, coverage | `IMPLEMENTED` | `fieldsense/spatial/` | Minimum sample limit ($3+$) enforced. |
| **Zone Engine** | 4-neighbor BFS connectivity, primary issue selection | `IMPLEMENTED` | `fieldsense/zones/` | Candidate component merging ($< 2$ cells). |
| **Recommendations**| Traceable, rule-based decision support actions | `IMPLEMENTED` | `fieldsense/recommendations/` | Max limit ($3$/zone), zero unsupported dosages. |
| **Presentation** | Passive `UIFieldView` & offline HTML/CSS/SVG dashboard | `IMPLEMENTED` | `fieldsense/presentation/` | Zero external network URL dependencies. |
| **AI Explanation** | Passive downstream narrative layer (`LocalLLMAdapter`) | `IMPLEMENTED` | `fieldsense/ai/` | Optional & out of band. Model weights absent by default. |
| **AI Safety Gate** | `NarrativeGuard` blocks dosages, agrochemicals, carbon claims, invented numbers | `IMPLEMENTED` | `fieldsense/ai/guard.py` | None. Rejected text degrades to deterministic template. |
| **Hardware Boundary**| `HardwareSensorAdapter`, `SensorTransport`, `GPSAdapter` | `IMPLEMENTED` | `fieldsense/hardware/` | Specs marked `HARDWARE_SPEC_REQUIRED`. |
| **Physical Hardware**| JXBS 7-in-1, NEO-M8N GPS, Arduino UNO Q platform | `PENDING_HARDWARE` | `fieldsense/hardware/` | Pending physical hardware delivery & testing. |

---

## Detailed Requirement Notes

1. **Hardware Independence**: Both `VirtualSensorAdapter` and `HardwareSensorAdapter` produce canonical `FieldSample` objects. Downstream intelligence operates identically regardless of source origin (`SampleSource.VIRTUAL` vs `SampleSource.HARDWARE`).
2. **Offline Operating Constraint**: All visual assets (SVG map canvas, CSS flex layouts, layer switching logic) are embedded self-contained inside `LocalUIRenderer` without external HTTP/HTTPS dependencies.
3. **Agronomic Boundary Discipline**: Carbon Readiness explicitly enforces `decision_support_only = True` and `evidence_level = "LIMITED"`. Fertilizer/chemical dosages (`kg/acre`, `liters`) are prohibited in recommendations.
4. **AI Boundary Discipline**: The explanation layer is strictly downstream and cannot alter a score, raster, zone, or recommendation. Generated language passes `NarrativeGuard` before display; any statement carrying a dose unit, an agrochemical name, a carbon credit claim, or a number absent from the deterministic context is rejected and replaced by a deterministic template. Violations are recorded on `AINarrative.guard_violations` for audit rather than silently discarded.
