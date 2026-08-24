# FieldSense AI — Hardware

Component specifications, electrical requirements, wiring, and physical
verification status.

Empirical bench-test records for each component live alongside their scripts in
`hardware_test/`:

| Record | Component |
| :--- | :--- |
| `hardware_test/soil sensor/JXBS_HARDWARE_TEST.md` | JXBS-3001-TR 7-in-1 soil probe |
| `hardware_test/RS485/RS485_HARDWARE_TEST.md` | MAX485 transceiver |
| `hardware_test/GPS/GPS_HARDWARE_TEST.md` | u-blox NEO-M8N |
| `hardware_test/TFT/TFT_HARDWARE_TEST.md` | 2.8" ST7789V display + XPT2046 touch |
| `hardware_test/arduino uno q/UNO_Q_HARDWARE_TEST.md` | Arduino UNO Q platform |
| `hardware_test/soil sensor with Max485-RS485/JXBS_MAX485_UNOQ_INTEGRATION.md` | Full acquisition chain |

Step-by-step test procedures: [../TESTING_GUIDE.md](../TESTING_GUIDE.md).

---

**STATUS:** DRAFT  
**VERSION:** 0.1.1  
**LAST UPDATED:** 2026-08-23  
**INTEGRATION STATUS:** `COMPONENT_VERIFICATION_COMPLETE` / `V1_SYSTEM_INTEGRATION_ACTIVE`  

---

## 1. Hardware Overview & Confidence Register

This document serves as the authoritative hardware specification for FieldSense AI. Every hardware statement is assigned an explicit confidence/status label:

- `RECEIVED / IN HAND`: Physical hardware components delivered and received in-hand.
- `CONFIRMED`: Verified empirically through physical hardware testing.
- `DATASHEET CONFIRMED`: Verified directly from manufacturer datasheets.
- `MEASURED`: Measured quantitatively in testing environment.
- `ASSUMED`: Engineering baseline assumption requiring physical hardware verification.
- `PENDING HARDWARE`: Awaiting physical hardware verification or field testing.
- `UNKNOWN`: Specification parameter not yet established.

---

## 2. Component Inventory & Part Numbers

| Component Name | Model / Part Number | Manufacturer | System Role | Procurement Status | Verification Status | BOM Reference |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Main Compute Platform** | Arduino UNO Q (4GB / 32GB Variant) | Arduino | Dual MCU/MPU host processing unit | `RECEIVED / IN HAND` | `🟢 VERIFIED FOR FIELDSENSE V1` | `TBD` |
| **Main Processing Unit (MPU)**| Qualcomm QRB2210 | Qualcomm | Runs Debian Linux, Python 3, spatial engine, UI | `RECEIVED / IN HAND` | `🟢 VERIFIED` | `TBD` |
| **Microcontroller Unit (MCU)**| STM32U585 | STMicroelectronics | Real-time I/O, RS485 timing, Modbus, GPS buffer | `RECEIVED / IN HAND` | `🟢 VERIFIED` | `TBD` |
| **Multi-Parameter Soil Sensor**| JXBS-3001-NPKPH-RS / JXBS 7-in-1 | JXBS / Novus | In-situ measurement of N, P, K, pH, EC, Moisture, Temp | `RECEIVED / IN HAND` | `🟢 VERIFIED` (USB-RS485 Path to Linux) | `TBD` |
| **RS485 Transceiver Module**| MAX485 / USB-RS485 Interface | Maxim / Generic | TTL/USB to RS485 differential signal converter | `RECEIVED / IN HAND` | `🟢 VERIFIED` (USB-RS485 through USB-C Hub) | `TBD` |
| **GPS Positioning Module** | u-blox NEO-M8N (`GY-GPSV3-NEO`) | u-blox | Global positioning fix (Lat, Lon, Altitude, UTC Time) | `RECEIVED / IN HAND` | `🟢 VERIFIED` (UNO Q Serial1 → Bridge → Linux) | `TBD` |
| **TFT Display & Touch Panel** | 2.8" TFT 240xRGBx320 V1.1 (ST7789V + XPT2046) | Generic / ILI | Local graphical user interface & resistive touch input | `RECEIVED / IN HAND` | `🟢 VERIFIED` (Native Hardware SPI, 320x240 landscape) | `TBD` |
| **Power Supply System** | 12V LiFePO4 / Li-ion Battery Enclosure | Generic / TBD | Portable field power delivery | `RECEIVED / IN HAND` | `MEASURED` (12.24V DC; Battery integration PENDING, not blocking V1) | `TBD` |

---

## 3. Electrical Requirements & Power Architecture

- **Main System Supply Voltage**: `12.0V DC` nominal (Measured sensor supply: `12.24V DC`) [`MEASURED`].
- **UNO Q Board Supply Input**: `5.0V DC` via USB-C or VIN pin [`DATASHEET CONFIRMED`].
- **JXBS Soil Sensor Supply Input**: `12.0V DC` (Operating range: `12V - 24V DC`, current $< 30\text{mA}$) [`CONFIRMED`].
- **MAX485 Transceiver Supply Input**: `5.0V DC` TTL logic level [`CONFIRMED`].
- **NEO-M8N GPS Module Supply Input**: `3.3V DC` direct input verified (onboard LDO present; accepts `3.3V - 5.0V DC`) [`CONFIRMED` / `MEASURED`].
- **TFT Display Module Supply Input**: `3.3V / 5.0V DC` board operating input (onboard 3.3V LDO regulator `U2` steps supply voltage to 3.3V; logic interface is **STRICTLY 3.3V LOGIC**) [`CONFIRMED`].
- **Total System Power Consumption**: `UNKNOWN` (Pending physical measurement on Arduino UNO Q hardware).

---

## 4. JXBS 7-in-1 Soil Sensor Specification

### Physical Parameters Measured
1. **Soil Moisture (VWC%)**: Range `0.0 - 100.0%`, Accuracy $\pm 3\%$, Resolution `0.1%` [`CONFIRMED`].
2. **Soil Temperature**: Range `-40.0 - +80.0 °C`, Accuracy $\pm 0.5\text{°C}$, Resolution `0.1°C` [`CONFIRMED`].
3. **Electrical Conductivity (EC)**: Range `0 - 20000 µS/cm`, Accuracy $\pm 5\%$, Resolution `1 µS/cm` [`CONFIRMED`].
4. **Soil pH**: Range `3.0 - 9.0 pH` (Operational model: `0.0 - 14.0`), Accuracy $\pm 0.3 \text{pH}$, Resolution `0.01 pH` [`CONFIRMED`].
5. **Nitrogen (N)**: Range `0 - 1000 mg/kg` (ppm), Accuracy $\pm 5\%$, Resolution `1 mg/kg` [`CONFIRMED`].
6. **Phosphorus (P)**: Range `0 - 500 mg/kg` (ppm), Accuracy $\pm 5\%$, Resolution `1 mg/kg` [`CONFIRMED`].
7. **Potassium (K)**: Range `0 - 1500 mg/kg` (ppm), Accuracy $\pm 5\%$, Resolution `1 mg/kg` [`CONFIRMED`].

### Modbus RTU Protocol Configuration
- **Interface Protocol**: RS485 Differential Half-Duplex [`CONFIRMED`].
- **Baud Rate**: `9600` bps [`CONFIRMED`].
- **Data Bits**: `8` [`CONFIRMED`].
- **Parity**: `None` (8N1) [`CONFIRMED`].
- **Stop Bits**: `1` [`CONFIRMED`].
- **Modbus Slave Address**: `0x01` [`CONFIRMED`].
- **Modbus Function**: `0x03` (Read Holding Registers) [`CONFIRMED`].
- **Buffer Reading Strategy**: Explicit byte count framing `ser.read(7)` with timeout (prevents premature 0-byte buffer checks before Modbus frame arrival) [`CONFIRMED`].

### Empirical Modbus Register Map (`0x0006 - 0x0020`)
*(Status: `CONFIRMED` — Verified on physical hardware host via FTDI USB-RS485 adapter on COM8)*

| Register Address | Hex Address | Parameter | Data Type | Multiplier / Scale | Units | Empirical Air/Foam Baseline | Empirical Soil Range |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `40007` | `0x0006` | Soil pH | 16-bit UInt | $\div 100$ ($0.01$) | $\text{pH}$ | ~7.00 | 6.37 – 6.78 |
| `40019` | `0x0012` | Volumetric Water Content (Moisture) | 16-bit UInt | $\div 10$ ($0.1$) | $\%$ RH | 0.0 % | 14.1 – 22.9 % |
| `40020` | `0x0013` | Soil Temperature | 16-bit Int (Signed)| $\div 10$ ($0.1$) | $^\circ\text{C}$ | ~29.0 °C | 26.1 – 28.9 °C |
| `40022` | `0x0015` | Electrical Conductivity (EC) | 16-bit UInt | $\times 1$ ($1.0$) | $\mu\text{S/cm}$ | 0 | 607 – 1800 µS/cm |
| `40031` | `0x001E` | Nitrogen ($N$) | 16-bit UInt | $\times 1$ ($1.0$) | $\text{mg/kg}$ | 0 | 43 – 127 mg/kg |
| `40032` | `0x001F` | Phosphorus ($P$) | 16-bit UInt | $\times 1$ ($1.0$) | $\text{mg/kg}$ | 0 | 60 – 184 mg/kg |
| `40033` | `0x0020` | Potassium ($K$) | 16-bit UInt | $\times 1$ ($1.0$) | $\text{mg/kg}$ | 0 | 121 – 351 mg/kg |

---

## 5. NEO-M8N GPS Module Specification

### 5.1 Verified Breakout Hardware Identity & Physical Findings
- **Physical Board Identity**: u-blox NEO-M8N GPS Breakout (`GY-GPSV3-NEO`, Board Marking: `NEO-M8N-0-10`) [`CONFIRMED`].
- **Pinout & Header**: 4-pin 2.54 mm header soldered (`VCC`, `RX`, `TX`, `GND`) [`CONFIRMED`].
- **Pulse-Per-Second (PPS) Availability**: No dedicated hardware PPS pin exposed on tested breakout board [`CONFIRMED`]. V1 system timing relies on NMEA UTC timestamps [`CONFIRMED`].
- **Onboard Components**: Onboard 3.3 V LDO regulator, RTC backup battery, external EEPROM, ceramic patch antenna fitted [`CONFIRMED`].
- **Antenna Connector**: U.FL connector unpopulated on tested breakout board [`CONFIRMED`].
- **Variant Distinction**: These physical findings apply specifically to the tested `GY-GPSV3-NEO` breakout board and must not be generalized to all NEO-M8N carrier-board variants [`CONFIRMED`].

### 5.2 Confirmed Communication & Protocol Parameters
- **Power Operation**: Direct 3.3 V DC applied to VCC successfully powers module via onboard LDO [`CONFIRMED`].
- **Interface Protocol**: UART Serial Interface (8-N-1 format, No Flow Control) [`CONFIRMED`].
- **Baud Rate**: `9600` bps [`CONFIRMED`].
- **Output Protocol**: Standard ASCII NMEA 0183 (`$GN`, `$GP`, and `$GL` sentence prefixes observed in raw output stream) [`CONFIRMED`].
- **Software Parser Requirement**: NMEA parser software must support `$GN` sentences and multi-GNSS prefixes and must not assume `$GP` only [`CONFIRMED`].
- **Native Update Rate**: Approximately `1 Hz` native NMEA sentence output rate [`CONFIRMED` / `MEASURED`].
- **Higher Update Rates**: Update rates $> 1\text{ Hz}$ require explicit UBX command configuration and are `PENDING HARDWARE` verification.
- **Host/Test Environment Finding (Windows CH340)**: During Windows PC CH340 host testing, DTR/RTS assertions had to be explicitly disabled to avoid serial initialization locks [`MEASURED` / Host Finding]. *(Note: Host test-environment finding; not a universal GPS hardware constraint).*

### 5.3 Measured Navigation & Position Observations (Indoor Bench Test)
- **Multi-GNSS Satellite Tracking**: Concurrent GPS and GLONASS satellite tracking verified; ~8–9 satellites continuously used in navigation solution [`MEASURED`].
- **Fix Acquisition**: Autonomous 3D fix successfully obtained [`CONFIRMED`].
- **Indoor HDOP Observation**: Horizontal Dilution of Precision (HDOP) measured between `4.82 – 5.10` during indoor/near-window bench testing [`MEASURED`]. *(Note: Indoor test observation; does not represent outdoor open-sky field performance).*
- **Indoor Position Stability Observation**: Minor latitude/longitude stationary drift observed during 2-minute indoor test [`MEASURED`]. *(Note: Indoor test observation; not a formal accuracy specification).*
- **Datasheet Position Accuracy (Reference)**: $< 2.5\text{m}$ CEP (Autonomous mode under open-sky conditions) [`DATASHEET CONFIRMED`].

### 5.4 Integration Readiness & Verification Boundaries
- **Physical GPS Breakout Status**: `🟢 VERIFIED FOR FIELDSENSE V1`
  - *Path*: NEO-M8N → STM32 Serial1 (9600 baud) → Arduino Bridge/RPC (`get_gps_data`) → Linux Python.
  - *NMEA Sentences*: `$GN`, `$GP`, and `$GL` parsed cleanly at native ~1 Hz output rate.
- **Pending / Unverified Verification Items**:
  - Combined GPS + JXBS acquisition in one unified process (`PENDING`).
  - Conversion of simultaneous real GPS + soil data into canonical `FieldSample` (`PENDING`).
  - Outdoor accuracy under final field conditions (`PENDING` / Open-sky testing recommended).
  - UBX-configured update rates above 1 Hz (`PENDING`).
  - Long-duration outdoor stability (`PENDING`).

---

## 6. MAX485 Interface Module Specification (`HW-097`)

### 6.1 Component Identity & Physical Findings
* **Component Model:** MAX485 RS485 Interface Module (`HW-097`) [`CONFIRMED`].
* **Transceiver IC:** `MAX485` / `MAX485CSA` SOIC-8 [`CONFIRMED`].
* **Overall Status:** `VERIFIED — Bench Verification Complete`
* **Integration Status:** `READY FOR V1 INTEGRATION`
* **Physical Observations:**
  * Physical breakout identified as a MAX485-based RS485 interface module (`HW-097`) [`CONFIRMED`].
  * TTL-side pins physically identified (`DI`, `RO`, `DE`, `RE`) [`CONFIRMED`].
  * RS485 differential terminals physically identified (`A`, `B`) [`CONFIRMED`].
  * Module powered successfully from tested 5 V DC supply [`CONFIRMED` / `MEASURED`].
  * RS485 communication path established during bench testing [`CONFIRMED`].
  * No visible physical damage or abnormal module behavior observed [`CONFIRMED`].

### 6.2 Verified Configuration & Signals
* **Interface Protocol:** TTL UART $\leftrightarrow$ RS485 Differential Half-Duplex [`CONFIRMED`].
* **Tested Power Supply:** `5.0 V DC` applied to VCC with common GND [`CONFIRMED` / `MEASURED`].
* **TTL-Side Logic Signals:**
  * `DI` (Data In): Transmit input from UART TX [`CONFIRMED`].
  * `RO` (Receive Out): Receive output to UART RX [`CONFIRMED`].
  * `DE` (Driver Enable): HIGH enables driver output [`CONFIRMED`].
  * `/RE` (Receiver Enable): LOW enables receiver [`CONFIRMED`].
* **Differential Bus Signals:**
  * `A`: RS485 Non-inverting line [`CONFIRMED`].
  * `B`: RS485 Inverting line [`CONFIRMED`].
* **Verified Direction Control Logic:**
  * **TX Mode (Driver Enabled):** `DE = HIGH (5V)`, `RE = HIGH (5V)` $\rightarrow$ Driver enabled, Receiver tri-stated [`CONFIRMED`].
  * **RX Mode (Receiver Enabled):** `DE = LOW (0V)`, `RE = LOW (0V)` $\rightarrow$ Driver disabled, Receiver enabled [`CONFIRMED`].

### 6.3 Measured / Verified Behavior
* **5 V Supply Operation:** `PASS`
* **TTL UART → RS485 Transmission:** `PASS` (Verified via `rs485_test1.py`)
* **RS485 → TTL UART Reception:** `PASS` (Verified via `rs485_test2.py`)
* **Half-Duplex Operation:** `PASS`
* **Direction Control through DE//RE:** `PASS`
* **RS485 Communication with FieldSense JXBS Soil Sensor Setup:** `PASS`
* **Valid Modbus RTU Responses Observed:** `PASS` (Raw frames passed through interface cleanly)
* **Communication Instability:** `NONE OBSERVED` during verification sequence.

### 6.4 Recommended V1 Integration Path & Physical Layer Scope
```text
JXBS 7-in-1 Soil Sensor
        │
        │ RS485 A/B
        ▼
     MAX485
        │
        │ TTL UART
        ▼
STM32U585 UART
        │
        ▼
Arduino Bridge / RPC
        │
        ▼
QRB2210 Linux
        │
        ▼
FieldSense Hardware Adapter
        │
        ▼
FieldSample
```

* **Recommended Serial Configuration:** `9600` baud, `8` data bits, `No` parity, `1` stop bit, `No` flow control (9600 8-N-1) [`CONFIRMED`].
* **Physical-Layer Responsibility Scope:**
  > [!IMPORTANT]
  > The MAX485 is **only** the physical RS485 transceiver layer. Modbus framing, CRC validation, register decoding, parameter scaling, and sensor validation exist strictly above the MAX485 layer in software/firmware and must not be attributed to the MAX485 hardware module.

### 6.5 Integration Warnings
* **Do not treat MAX485 as a complete Modbus controller.**
* **Do not assume DE//RE should be permanently enabled during half-duplex operation.** Direction control must explicitly follow the transmit/receive sequence.
* **Do not reverse RS485 A/B lines without deliberate testing.**
* **Do not assume 3.3 V supply operation for this tested 5 V MAX485 module.**
* **Do not assume the MAX485 performs CRC checking, register decoding, or validation.**
* **Do not change the verified JXBS Modbus configuration without a specific reason and test.**

---

## 7. 2.8" SPI TFT Display & XPT2046 Touch Panel Specification

### 7.1 Verified Hardware Identity & Inspection Findings
* **Board Identity:** `2.8" TFT 240xRGBx320 V1.1` breakout board [`CONFIRMED`].
* **Display Controller IC:** **ST7789V** [`CONFIRMED`].
* **Touch Controller IC:** **XPT2046 / HR2046** (12-bit SAR ADC resistive touch controller) [`CONFIRMED`].
* **Overall Subsystem Status:** `VERIFIED — Display & Touch Subsystems Fully Operational` [`CONFIRMED`].
* **Physical Inspection Findings:**
  * Red breakout PCB featuring a single-row 14-pin main header [`CONFIRMED`].
  * Onboard 3.3 V LDO linear regulator designated `U2` [`CONFIRMED`].
  * **No onboard 5 V logic level shifter ICs observed** [`CONFIRMED`].
  * Onboard full-size SD card slot designated `SD1` [`CONFIRMED`].
  * Surface-mount touch controller IC `U1` marked `HR2046` [`CONFIRMED`].

### 7.2 Verified Display Subsystem Configuration
* **Native Matrix Resolution:** `240 × 320` pixels [`CONFIRMED`].
* **Tested Landscape Orientation:** `320 × 240` landscape frame (`setRotation(1)`) [`CONFIRMED`].
* **Display Interface:** 4-wire hardware SPI (`CS`, `DC`, `MOSI`, `SCK`, `RST`) [`CONFIRMED`].
* **Power Supply Input:** `3.3 V / 5.0 V DC` input supported via onboard 3.3 V LDO regulator `U2` [`CONFIRMED`].
* **Signal Logic Voltage:** **STRICTLY 3.3 V LOGIC ONLY** [`CONFIRMED`].
  > [!CAUTION]
  > The display breakout board may accept 3.3 V / 5.0 V power supply inputs due to onboard LDO regulator `U2`, but its signal interface lines (SPI and control pins) operate strictly at 3.3 V CMOS levels. Do NOT drive logic lines with 5.0 V signals without level shifting.

### 7.3 Verified Touch Subsystem Configuration
* **Touch Controller:** XPT2046 / HR2046 12-bit SAR ADC controller [`CONFIRMED`].
* **Pen Interrupt Line (`T_IRQ`):** Active-LOW hardware interrupt pin (`TOUCH_IRQ = Pin 2`) [`CONFIRMED` / `MEASURED`].
  * `T_IRQ = 0` (LOW) $\rightarrow$ Active screen press / contact detected [`MEASURED`].
  * `T_IRQ = 1` (HIGH) $\rightarrow$ Idle / no active screen touch [`MEASURED`].
* **Raw Coordinate Remapping:** Analog 12-bit raw coordinates mapped to `320 × 240` landscape UI coordinates (`map(p.x, 200, 3700, 320, 0)`, `map(p.y, 200, 3700, 240, 0)` constrained to $[0, 320]$ and $[0, 240]$) [`CONFIRMED`].
* **Z-Axis Pressure Filtering:** Noise threshold filter ($p.z < 400 \lor p.z > 4000$) applied to suppress floating noise [`CONFIRMED`].

### 7.4 Verified SPI Integration & Hardware Defect Analysis
* **Verified Bus Architecture:** Native Hardware SPI (`&SPI`) on Arduino UNO Q with separate Chip Select lines (`TFT_CS = Pin 10`, `TOUCH_CS = Pin 4`, `TFT_DC = Pin 9`, `TFT_RST = Pin 8`, `TFT_LED = Pin 6`) [`CONFIRMED`].
  > [!CAUTION]
  > **Backlight is Pin 6, not Pin 7.** Pin 7 is `MAX485_RE_DE`, the RS485 direction line. The TFT and soil bench sketches were validated separately and both originally claimed D7; assembled together, holding the backlight on parks the transceiver in transmit and the probe can never answer. All three UNO Q sketches (`frame_receiver`, `link_probe`, `touch_demo`) now pin the backlight to D6 and never touch D7. Tie `LED`/`BLK` straight to 3.3 V if software brightness control is not needed.
* **Observed Color Matrix Correction:** Corrected via `tft.invertDisplay(false)` for FieldSense dark-mode UI [`CONFIRMED`].
* **Known Hardware Defect — Mechanical Bezel Pinch:**
  > [!WARNING]
  > A mechanical lamination pinch in the display's outer bezel causes occasional phantom Z-axis touch inputs near the center of the screen. This is classified as a physical hardware defect (not a software bug).
  > 
  > **Status**: Accepted for V1 prototype testing.
  > **Recommended Action**: Evaluate capacitive-touch displays for final field production units.

---

## 8. Arduino UNO Q Specification & Physical Verification

**STATUS:** `VERIFIED FOR FIELDSENSE V1`

### 8.1 Physical Verification Results

The Arduino UNO Q has successfully passed ground-level hardware validation for the core capabilities required by FieldSense V1:

- **POWER & BOOT**:
  - Clean boot observed.
  - Linux OS starts successfully.
  - Stable operating behavior observed.
- **STM32U585 MCU**:
  - STM32 accepts and executes deployed code.
  - MCU hardware pins can be controlled.
  - Physical UART hardware is operational.
- **LINUX / QRB2210**:
  - Linux core executes Python successfully.
  - Python loops execute correctly.
  - Python environment can receive and process data.
- **ARDUINO BRIDGE / RPC**:
  - Bidirectional structured data successfully flows between the STM32-side application and Linux/Python side.
  - Physical MCU-originated data successfully reaches Linux.
  - Linux/Python can receive and process the bridged data.
  - No meaningful lag or communication failure was observed during the successful verification sequence.
- **PHYSICAL UART**:
  - STM32 UART TX/RX pins successfully transmitted and received real physical UART signals.
  - Physical UART behavior was verified using the actual board.

### 8.2 Engineering Conclusion & Verification Boundaries

> [!IMPORTANT]
> The Arduino UNO Q has successfully passed ground-level hardware validation for the core capabilities required by FieldSense V1 (power & boot, STM32 MCU execution, Linux/Python execution, Arduino Bridge/RPC communication, physical UART TX/RX).  
>   
> **UNO Q Component Status: 🟢 VERIFIED FOR FIELDSENSE V1**  
>   
> This does **NOT** mean the complete FieldSense hardware system is integrated. It means the UNO Q platform itself has passed component-level validation.

#### Status Distinction Matrix
- **DATASHEET CONFIRMED**: Board specifications and documented interfaces.
- **MEASURED / VERIFIED**: Capabilities physically demonstrated during the FieldSense component test.
- **PENDING HARDWARE**: Actual FieldSense peripheral integration.

#### Unverified / Pending Peripheral Integrations (`PENDING HARDWARE`)
- JXBS → MAX485 → UNO Q complete integration
- GPS → UNO Q complete integration
- TFT → UNO Q complete integration
- Complete FieldSample generation from physical hardware
- End-to-end FieldSense pipeline on physical hardware
- Full battery-powered system
- Complete field workflow

### 8.3 Pin Mappings & Node Paths

*(Status: `VERIFIED FOR V1 INTEGRATION`)*

| Signal Name | Connected Hardware Device | Target Controller | Pin / Node Path | Confidence / Status |
| :--- | :--- | :--- | :--- | :--- |
| `GPS_TX` / `GPS_RX` | NEO-M8N GPS Module | STM32U585 MCU | `Serial1` (9600 8N1) | `🟢 VERIFIED` (Bridge → Linux) |
| `USB_RS485` | JXBS 7-in-1 via USB-RS485 | Qualcomm QRB2210 Linux | USB-C Hub (`/dev/ttyUSB0`) | `🟢 VERIFIED` (Linux Modbus, `FIELDSENSE_SOURCE=HARDWARE`) |
| `MCU_RS485` | JXBS 7-in-1 via MAX485 on the MCU | STM32U585 MCU | `Serial1` (9600 8N1) + Bridge `get_soil_data` | `🟡 BENCH ONLY — BLOCKED BY UART CONTENTION` (see 9.1) |
| `TFT_SPI_CS` | ST7789 Display Chip Select | STM32U585 MCU | Pin 10 | `🟢 VERIFIED` (Hardware SPI) |
| `TFT_DC` | ST7789 Data/Command | STM32U585 MCU | Pin 9 | `🟢 VERIFIED` |
| `TFT_RST` | ST7789 Reset | STM32U585 MCU | Pin 8 | `🟢 VERIFIED` |
| `TFT_LED` | ST7789 Backlight | STM32U585 MCU | Pin 6 | `🟡 REASSIGNED` (was Pin 7 — see the conflict note below) |
| `MAX485_RE_DE` | MAX485 direction control (DE and RE tied) | STM32U585 MCU | Pin 7 | `🟢 VERIFIED` (exclusive to RS485) |
| `TOUCH_SPI_CS`| XPT2046 Touch Chip Select | STM32U585 MCU | Pin 4 | `🟢 VERIFIED` (Hardware SPI) |
| `TOUCH_IRQ` | XPT2046 Pen Interrupt | STM32U585 MCU | Pin 2 | `🟢 VERIFIED` |
| `SPI_BUS` | Shared Display/Touch SPI | STM32U585 MCU | Hardware `&SPI` (SCK, MOSI, MISO) | `🟢 VERIFIED` |
| `MCU_MPU_IPC` | Internal High-Speed Bridge | Shared Bridge | Arduino Bridge / RPC | `🟢 VERIFIED` |

> [!CAUTION]
> **Resolved pin conflict: digital pin 7.** The two bench sketches were
> validated independently and both claimed pin 7. The RS485 sketch drives the
> MAX485's tied `DE`/`RE` line from pin 7 (section 6); the TFT sketch used pin 7
> for the display backlight. Each worked alone. In the assembled unit, where
> both peripherals are on the same STM32, that single line would have driven the
> transceiver into transmit whenever the backlight was lit — jamming the Modbus
> bus — while every soil read flickered the screen.
>
> **Resolution:** the backlight moves to **pin 6**. Pin 7 is reserved
> exclusively for `MAX485_RE_DE`. Applied in
> `hardware_test/New folder/sketch.ino`. Re-flash the STM32 before wiring both
> peripherals together, and confirm no other peripheral claims pin 6.

### 8.4 Power Domain Isolation

*(Status: `MEASURED` for each rail; whole-system draw still `UNKNOWN`)*

| Rail | Supplies | Source | Isolation rule |
| :--- | :--- | :--- | :--- |
| `12 V DC` | JXBS-3001 soil probe only | Battery, direct | Never share a rail with the UNO Q. The probe's 12–24 V input is not tolerated by anything else in the enclosure. |
| `5 V DC` | Arduino UNO Q, MAX485 module | 12 V → regulator → 5 V bus | The MAX485 breakout under test is a 5 V part; do not run it at 3.3 V. |
| `3.3 V DC` | NEO-M8N GPS, ST7789V display board | UNO Q 3.3 V / onboard LDO | Board power only. Every **signal** line on the display is strictly 3.3 V CMOS. |
| `GND` | Common | — | Single common ground. The RS485 pair needs a shared reference or the differential receiver floats. |

> [!WARNING]
> The 12 V probe rail and the 5 V board rail are separate domains sharing only
> ground. Bridging them puts 12 V onto the UNO Q's 5 V bus and destroys it.
> Confirm with a meter before first power-on, every time the harness is rebuilt.

---

## 9. System Wiring & Physical Integration Status

```text
  ┌─────────────────────────────────────────────────────────────┐
  │                    PHYSICAL ENCLOSURE                       │
  │                                                             │
  │  [ 12V Battery ] ───────> Power Regulator ──> 5V Bus       │
  │         │                                                   │
  │         ▼ 12V Power                                         │
  │  [ JXBS Soil Probe ] ──(RS485 A/B)──> [ MAX485 Board ]     │
  │                                              │ TTL          │
  │  [ NEO-M8N GPS ] ──────(UART TX/RX)──────────┼───┐          │
  │                                              │   │          │
  │  [ 2.8" TFT + Touch ] ─(SPI + Touch IRQ)────┼───┤          │
  │                                              ▼   ▼          │
  │                           [ Arduino UNO Q Platform ]        │
  │                           (STM32 MCU <-> QRB2210 Linux)     │
  └─────────────────────────────────────────────────────────────┘
```

- **Hardware Procurement Status**: `RECEIVED / IN HAND` (Components ordered on 17/08/2026 via Robu and TechieSMS; received in-hand on 21/08/2026).
- **Physical Component Verification Status**: `COMPLETE` (All individual V1 hardware components and the UNO Q platform have passed component-level validation as of 2026-08-22).
- **Physical System Integration**: Phase 2 V1 Hardware Integration active. The verified components are now being connected and validated as a complete system.

### 9.1 Shared-Resource Ownership (D7 and `Serial1`)

Three bench sketches were each verified alone, and two board resources ended up
claimed twice. Neither conflict can appear in a single-component test — both
only bite once the components share one board, which is precisely when the
system stops collecting data.

| Resource | Claimed by | Resolution | Status |
| :--- | :--- | :--- | :--- |
| **Pin D7** | `MAX485_RE_DE` (soil) vs `TFT_LED` (display) | Backlight moved to **D6**. D7 is RS485 direction control and nothing else. | `🟢 RESOLVED` |
| **`Serial1` (D0/D1)** | NEO-M8N GPS vs MAX485 soil transceiver | **GPS owns `Serial1`.** The probe moves to the Linux side over USB-RS485. | `🟢 RESOLVED` |

**Why D7 mattered.** `RE` and `DE` are tied, so the pin selects transmit or
receive for the whole transceiver. Holding it HIGH to light the backlight parks
the MAX485 in transmit, and the probe's reply is driven over before Linux ever
sees it. All three UNO Q sketches now pin the backlight to D6 and never touch D7.

**Why `Serial1` mattered.** The UNO Q exposes exactly one hardware UART on the
headers. GPS needs it continuously for a 1 Hz NMEA stream; Modbus needs it for
half-duplex request/response. Worse, only one sketch can be flashed at a time,
and `get_gps_data` and `get_soil_data` lived in different sketches — so
`FIELDSENSE_SOURCE=BRIDGE` could never serve both endpoints, whatever the wiring.

**The resolution.** The single UART goes to the GPS, which cannot be moved
without a second dongle. The soil probe moves to the Linux side, where the
USB-RS485 adapter already provides an independent port:

| Device | Bus | Owner | Source setting |
| :--- | :--- | :--- | :--- |
| NEO-M8N GPS | `Serial1` 9600 8N1 | STM32U585 | Bridge `get_gps_data` |
| JXBS probe | USB-RS485 → `/dev/ttyUSB0` | QRB2210 Linux | `FIELDSENSE_SOURCE=HARDWARE` |
| ST7789 panel | Hardware SPI + D6 backlight | STM32U585 | `FS\|` value record over Monitor |

Firmware: **`hardware_test/fieldsense_unoq/`** is the single flashable sketch for
the assembled unit — `dashboard.ino` verbatim plus non-blocking GPS in one
`loop()`. The GPS read had to become non-blocking to get there: the bench
sketch's blocking `readStringUntil` waits up to a second, and this loop also
services the Monitor transport, where one `available()` already costs ~595 ms.
GPS runs on `Serial1`, a real UART, so servicing it costs microseconds and
never touches that transport.

> [!NOTE]
> `FIELDSENSE_SOURCE=BRIDGE` remains valid in code and is still the right path
> if the probe is ever moved back onto the MCU. It requires firmware that
> provides `get_soil_data`, which the unified sketch deliberately does not —
> there is no second header UART to give it.

---

## 10. Hardware Test Findings & Evidence Summary

- **Mock Hardware Transport (`MockHardwareTransport`)**: Verified in Sprint 9 across 8 unit/integration tests (`tests/test_hardware.py`).
- **Data Model Round-Tripping**: Confirmed raw byte-to-sample serialization for `RawSensorReading` and `GPSPosition`.
- **Fault Recovery**: Verified structured error handling (`HardwareConnectionError`, `ModbusTimeoutError`, `GPSFixError`) on lost serial connections or malformed Modbus frames.
- **Physical JXBS 7-in-1 Bench Test**: `CONFIRMED` / `FUNCTIONALLY VERIFIED`.
  - Host: Windows PC via FTDI USB-RS485 Adapter (COM8, 9600 8N1, Slave ID 0x01, Function 03).
  - Power Supply: 12.24V DC.
  - Parameter Registers: Verified all 7 parameters (`0x0006` pH, `0x0012` Moisture, `0x0013` Temp, `0x0015` EC, `0x001E` N, `0x001F` P, `0x0020` K).
  - Protocol Integrity: 100% CRC validation pass rate; zero CRC errors observed across air/foam and multi-position soil tests.
  - Framing Strategy: Explicit 7-byte read buffer (`ser.read(7)` with timeout) resolved initial 0-byte buffer read race condition.
- **Physical NEO-M8N GPS Breakout Bench Test**: `CONFIRMED` / `READY FOR V1 INTEGRATION`.
  - Date: 2026-08-22.
  - Physical Board: u-blox NEO-M8N Breakout (`GY-GPSV3-NEO`, Board Marking `NEO-M8N-0-10`).
  - Pinout & Power: 4-pin header soldered (`VCC`, `RX`, `TX`, `GND`), direct 3.3V DC operation verified; no dedicated PPS pin exposed (uses NMEA UTC timestamps).
  - UART & Protocol: 9600 8-N-1 UART stream verified with `$GN`, `$GP`, and `$GL` NMEA sentences at native ~1 Hz output rate.
  - Navigation Fix: Autonomous 3D fix obtained with concurrent GPS + GLONASS multi-GNSS tracking (8–9 satellites active).
  - Observations: Measured indoor HDOP `4.82 – 5.10`; minor stationary indoor position drift observed over 2 minutes (indoor test observations, not outdoor specs).
  - Host Finding: Host Windows CH340 testing required disabling DTR/RTS lines to prevent initialization lock.
- **Physical MAX485 RS485 Interface Bench Test**: `VERIFIED` / `READY FOR V1 INTEGRATION`.
  - Date: 2026-08-22.
  - Physical Module: MAX485 RS485 Interface Module (`HW-097`, Transceiver `MAX485CSA +DNHK`).
  - Power Supply: 5.0V DC operation verified (`PASS`).
  - Signal Paths: Verified TTL UART $\rightarrow$ RS485 TX (`rs485_test1.py`) and RS485 $\rightarrow$ TTL UART RX (`rs485_test2.py`) (`PASS`, zero byte errors, bit-exact match).
  - Transceiver Flow Control: Verified explicit DE/RE direction pin control (`DE=5V, RE=5V` for TX; `DE=0V, RE=0V` for RX).
  - JXBS Sensor Communication: Valid Modbus RTU frames passed cleanly across interface (`PASS`). Zero communication instability observed.
  - Scope Distinction: Physical layer transceiver verified; higher-layer Modbus framing/parsing remains software responsibility.
  - Integration Status: Module ready for V1 integration; final UNO Q STM32U585 UART pin wiring remains `PENDING HARDWARE`.
- **Physical 2.8" SPI TFT Display & XPT2046 Touch Bench Test**: `VERIFIED` / `READY FOR V1 INTEGRATION`.
  - Date: 2026-08-22.
  - Physical Board: `2.8" TFT 240xRGBx320 V1.1` breakout board with ST7789V display driver and HR2046/XPT2046 touch controller.
  - Power & Logic: 3.3V power supply operation verified (`PASS`); logic interface confirmed **strictly 3.3V**.
  - Display Verification (`display_test_notouch.ino`): ST7789V initialized with `Adafruit_ST7789`, 320 × 240 landscape frame (`setRotation(1)`) rendered full-screen colors, border rectangle, and text cleanly with zero edge clipping (`PASS`).
  - Touch Verification (`display_test_touch.ino`): XPT2046/HR2046 direct bit-banged SPI command frames (`0x90`, `0xD0`) produced dynamic 12-bit ADC raw values (`~500` to `~3500`) across X/Y axes (`PASS`). Active-low `T_IRQ` pen interrupt line verified (`IRQ=0` pressed, `IRQ=1` idle) (`PASS`).
  - Bus Isolation Finding: Isolated SPI channel recommended for touch controller to prevent MISO line loading/contention with display.
  - Integration Status: Component fully verified on bench setup; final Arduino UNO Q pin wiring, touch calibration matrix, and GUI integration remain `PENDING HARDWARE`.
- **Physical Arduino UNO Q Platform Test**: `PASS — VERIFIED FOR FIELDSENSE V1`.
  - Date: 2026-08-22.
  - Physical Platform: Arduino UNO Q (Qualcomm QRB2210 Linux MPU + STM32U585 MCU).
  - Verification Scope: Ground-level hardware validation of core platform capabilities.
  - Power & Boot: Clean boot and stable Linux OS verified (`PASS`).
  - STM32 MCU: Code execution, pin control, and physical UART hardware verified (`PASS`).
  - Linux Core: Python loop execution, data reception, and processing verified (`PASS`).
  - Arduino Bridge / RPC: Bidirectional structured data transfer between STM32 and Linux/Python verified (`PASS`, zero lag/communication failure).
  - Physical UART: TX/RX signals physically transmitted and received on board pins (`PASS`).
  - Integration Status: UNO Q platform component verified; peripheral wiring to external sensors/display remains `PENDING HARDWARE`.
- **Physical MPU Benchmarks**: `UNO_Q_PHYSICAL_BENCHMARK = PENDING_HARDWARE` (Awaiting complete V1 hardware system pipeline benchmarks).

---

## Component Datasheets & Reference Documents

Vendor **product pages** are linked rather than deep PDF URLs, because product
pages stay stable while direct PDF links rot. Where a vendor assigns a document
number (u-blox `UBX-…`), that number is the durable identifier — search it on
the vendor site if a link moves.

> Verify each link before relying on it. These were compiled from vendor
> identifiers, not fetched and checked in an offline build environment.

### Soil probe — JXBS-3001-TR 7-in-1

| Item | Reference |
| :--- | :--- |
| Product class | RS485 soil moisture / temperature / EC / pH / NPK integrated probe |
| Protocol | Modbus RTU over RS485, function `0x03`, 9600 8-N-1, slave `0x01` |
| Modbus specification | <https://modbus.org/docs/Modbus_Application_Protocol_V1_1b3.pdf> |
| Modbus serial line spec | <https://modbus.org/docs/Modbus_over_serial_line_V1_02.pdf> |
| Register map | **Section 4 of this document** — empirically verified against the physical probe |

> [!IMPORTANT]
> JXBS probes are sold by many resellers under near-identical part numbers with
> **different register maps**. Do not substitute a generic datasheet for the
> verified map in section 4. The map in this repository was read off the actual
> unit; a downloaded PDF for a similar-looking probe may not match.
> Register decoding is implemented once, in `fieldsense/hardware/soil_adapter.py`.

### GPS — u-blox NEO-M8N (`GY-GPSV3-NEO` breakout)

| Item | Reference |
| :--- | :--- |
| Product page | <https://www.u-blox.com/en/product/neo-m8-series> |
| Data sheet | u-blox document `UBX-15031086` (NEO-M8 series) |
| Receiver description & protocol spec | u-blox document `UBX-13003221` — covers NMEA output and UBX binary |
| NMEA 0183 practical reference | <https://gpsd.gitlab.io/gpsd/NMEA.html> |
| Sentences consumed | `GGA` (position, fix quality, satellites, HDOP), `RMC` (position, validity) |
| Talker IDs handled | `$GN` `$GP` `$GL` `$GA` `$BD` `$QZ` |

Parsing and DDMM.MMMM → decimal degrees conversion: `fieldsense/hardware/gps_adapter.py`.

### RS485 transceiver — MAX485

| Item | Reference |
| :--- | :--- |
| Product page | <https://www.analog.com/en/products/max485.html> |
| Data sheet | Analog Devices / Maxim `MAX481/483/485/487–MAX491` family data sheet |
| Standard | TIA/EIA-485-A differential signalling |
| Module identity | Breakout marked `HW-097`, IC `MAX485CSA +DNHK`, onboard 120 Ω terminator `R7` |

> No automatic direction control. `DE`/`RE` are tied together and driven by the
> STM32 on digital pin 7. Transmission must fully complete before switching to
> receive, or the frame truncates. See section 6.

### Display — ST7789V + XPT2046 (2.8" 240×320 SPI)

| Item | Reference |
| :--- | :--- |
| Display controller | Sitronix **ST7789V** — 240×320 RGB TFT controller/driver |
| Sitronix product listing | <https://www.sitronix.com.tw/en/products/display-driver-ic/> |
| Touch controller | XPT2046 / HR2046 — 12-bit SAR ADC resistive touch controller |
| Pin-compatible reference part | Texas Instruments ADS7846: <https://www.ti.com/product/ADS7846> |
| Board marking | `2.8" TFT 240xRGBx320 V1.1`, onboard 3.3 V LDO `U2`, SD slot `SD1` |

> [!CAUTION]
> **ST7789V, not ILI9341.** These boards are widely mislabelled. An ILI9341
> driver will not initialise this panel correctly. Bench verification used
> `Adafruit_ST7789`. Signal lines are **strictly 3.3 V** — the power pin accepts
> 5 V only because of the onboard LDO.

Framebuffer path to this panel: [AI_DEPLOYMENT.md](AI_DEPLOYMENT.md) Part II.

### Compute — Arduino UNO Q (Qualcomm QRB2210 + STM32U585)

| Item | Reference |
| :--- | :--- |
| Board documentation | <https://docs.arduino.cc/hardware/uno-q/> |
| Board product page | <https://store.arduino.cc/products/uno-q> |
| MPU — Qualcomm QRB2210 | <https://www.qualcomm.com/products/internet-of-things/industrial/industrial-processors/qrb2210> |
| MPU cores | 4× ARM Cortex-A53, ARMv8.0-A (no `SDOT`, no FP16 extensions) |
| MCU — STM32U585 | <https://www.st.com/en/microcontrollers-microprocessors/stm32u5-series.html> |
| MCU↔MPU IPC | Arduino RouterBridge (`Bridge.provide()` / `Bridge.call()`) |

The dual-processor split matters: Linux on the QRB2210 cannot meet hard
microsecond deadlines, so the STM32 owns RS485 direction timing and other
real-time I/O. Confirm `asimddp` presence with `cat /proc/cpuinfo` before
sizing any on-device model — see [AI_DEPLOYMENT.md](AI_DEPLOYMENT.md) Part I.

### Where each specification is implemented

| Specification | Implementation | Never duplicated in |
| :--- | :--- | :--- |
| Modbus framing, CRC-16, register map, scaling | `fieldsense/hardware/soil_adapter.py` | `hardware_test/` scripts |
| NMEA parsing, checksum, DDMM → decimal | `fieldsense/hardware/gps_adapter.py` | `hardware_test/` scripts |
| Serial 8-N-1 device access | `fieldsense/hardware/transport/serial_port.py` | anywhere else |
| Telemetry → `FieldSample` contract | `fieldsense/hardware/hardware_sample_adapter.py` | the pipeline |

One implementation per specification. Bench scripts in `hardware_test/` are
thin console harnesses over these adapters and hold no protocol logic.
