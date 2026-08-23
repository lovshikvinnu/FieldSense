# FieldSense AI — System Validation & Limitations Report (v0.1)

## 1. Proven System Capabilities (Verified in Software)

- **Deterministic 8-Stage Pipeline**: Fully reproducible data flow from raw acquisition to offline UI presentation (`SensorAdapter` $\rightarrow$ `Validation` $\rightarrow$ `Intelligence` $\rightarrow$ `Spatial` $\rightarrow$ `Zones` $\rightarrow$ `Recommendations` $\rightarrow$ `UI`).
- **Rejected Data Exclusion**: Invalid / unstable samples are safely rejected by `ValidationEngine` and excluded from spatial interpolation and zone detection while preserving auditability in diagnostics.
- **Spatial Geostatistics**: Equirectangular local Cartesian meters projection ($x,y$) and deterministic IDW interpolation ($p=2.0$) with zero-distance coincidence checks and maximum support distance limits ($100\text{m}$).
- **Connected Management Zones**: 4-neighbor grid connectivity, minimum zone merging, multi-parameter layer enrichment, and primary issue selection with fixed priority tie-breaking.
- **Rule-Based Recommendation Engine**: Structured decision-support actions with category enums (`NUTRIENT`, `WATER`, `SOIL_CONDITION`, `SALINITY`, `CARBON_READINESS`, `MONITORING`), mapped priority, deduplication, and max recommendation limits.
- **100% Offline UI**: Standalone, responsive HTML/CSS/SVG dashboard generator with zero external network script, CSS, or cloud map dependencies.
- **Hardware Integration Boundary**: `HardwareSensorAdapter` and `SensorTransport` abstractions allowing `VIRTUAL` vs `HARDWARE` source switching with zero downstream pipeline modifications.

---

## 2. Items Pending Physical Hardware Validation (`HARDWARE_PENDING`)

- **Arduino UNO Q Execution Benchmark**: Host benchmarks are labeled `HOST BENCHMARK` (Windows development machine). UNO Q (QRB2210 Debian Linux) hardware benchmarks are marked `UNO_Q_PHYSICAL_BENCHMARK = PENDING_HARDWARE`.
- **JXBS 7-in-1 Modbus Communication**: RS485 transceiver wiring, slave address, baud rate, parity, and register map are marked `HARDWARE_SPEC_REQUIRED`.
- **NEO-M8N GPS UART Connection**: Serial device path and fix acquisition parameters are marked `HARDWARE_SPEC_REQUIRED`.

---

## 3. Scientific & Agronomic Boundaries

- **PROTOTYPE_ONLY**: Scoring curves and MCDA weights are explicitly tagged `PROTOTYPE_ONLY` under `methodology_version = "0.1"`.
- **Carbon Readiness Index**: `CarbonReadinessResult` enforces `decision_support_only = True`, `evidence_level = "LIMITED"`, and explicit `missing_indicators = ["soil_organic_carbon", "bulk_density", "management_history"]`. FieldSense does NOT measure SOC or certify carbon credits.
