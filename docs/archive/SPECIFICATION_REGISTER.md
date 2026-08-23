# FieldSense AI — Unresolved Specification Register

This register tracks all unresolved hardware specifications, agronomic validation boundaries, and hardware integration parameters requiring decision prior to Phase 2 physical hardware deployment.

---

## 1. Hardware Specifications (`HARDWARE_SPEC_REQUIRED`)

| ID | Description | Source | Current Assumption | Required Decision | Owner | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `HW-01` | JXBS 7-in-1 Modbus RTU Register Map | Hardware Spec | Read holding registers `0x0000–0x0006` | Confirm register offset & word order | Hardware Eng | `PENDING_HARDWARE` |
| `HW-02` | JXBS RS485 Serial Communication | Hardware Spec | `9600` baud, 8N1, slave ID `0x01` | Confirm baud rate & parity settings | Hardware Eng | `PENDING_HARDWARE` |
| `HW-03` | NEO-M8N GPS UART Device Node | Hardware Spec | Linux path `/dev/ttyS0` or `/dev/ttyAMA0` | Confirm Debian Linux serial device node | Hardware Eng | `PENDING_HARDWARE` |
| `HW-04` | UNO Q Pin Ownership (QRB2210 vs STM32U585)| Hardware Architecture | STM32 handles RS485/UART, MPU communicates via IPC | Confirm MCU/MPU bridge protocol & DE/RE pin | Embedded Systems Eng | `PENDING_HARDWARE` |

---

## 2. Agronomic & Methodological Boundaries (`AGRONOMIC_VALIDATION_REQUIRED`)

| ID | Description | Source | Current Assumption | Required Decision | Owner | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `AG-01` | Parameter Scoring Curves & Optimum Bands | Methodology v0.1 | JXBS verified ranges + prototype curves | Validate scoring curves against field trial datasets | Lead Agron | `PROTOTYPE_ONLY` |
| `AG-02` | Soil Health Weighting Vector ($\sum = 1.00$) | Methodology v0.1 | $0.20 N + 0.15 P + 0.15 K + 0.20 \text{pH} + 0.10 \text{EC} + 0.20 \text{Moisture}$ | Adjust weights for regional soil types | Lead Agron | `PROTOTYPE_ONLY` |
| `AG-03` | Carbon Readiness Proxy Weightings | Methodology v0.1 | Proxy index based on pH, moisture, EC | Maintain `decision_support_only = True` boundary | Lead Agron | `PROTOTYPE_ONLY` |

---

## 3. Physical Platform Performance (`UNO_Q_PHYSICAL_BENCHMARK`)

| ID | Description | Source | Current Assumption | Required Decision | Owner | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `PF-01` | Arduino UNO Q Processing Time | Target System | Windows host benchmark: $< 80\text{ms}$ for 500 samples | Benchmark physical QRB2210 Debian Linux environment | System Architect | `PENDING_HARDWARE` |
