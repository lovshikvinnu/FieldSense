# FieldSense — MASTER HARDWARE AUDIT
## Pre-Unified-Development Architecture & Code Audit

**STATUS:** COMPLETE  
**AUDIT DATE:** 2026-08-23  
**TARGET PLATFORM:** Arduino UNO Q (Qualcomm QRB2210 Linux MPU + STMicroelectronics STM32U585 MCU)  
**AUDITED SCOPE:** Complete repository source code (`.ino`, `.py`), test scripts, hardware integration logs, and system documentation.  

---

# 1. AUDIT OBJECTIVE

This document represents the final master hardware audit before FieldSense transitions from isolated component/integration testing into unified software and hardware development. 

The audit answers the 16 core architectural questions:

1. **What hardware has actually been verified?**
   - JXBS-3001-TR 7-in-1 Soil Sensor (Moisture, Temp, EC, pH, N, P, K)
   - MAX485 RS485 Transceiver Module (`HW-097`)
   - u-blox NEO-M8N GPS Module (`GY-GPSV3-NEO`)
   - 2.8" ST7789V TFT Display (320 × 240 landscape)
   - XPT2046 / HR2046 Resistive Touch Controller
   - Arduino UNO Q Platform (Debian Linux MPU + STM32U585 MCU + RouterBridge IPC)

2. **How was each component tested?**
   - Isolated bench tests via FT232 USB-RS485, CH340 USB-UART, and ESP32 DevKit hosts.
   - Dual-core integration tests on Arduino UNO Q via native `Serial1`, `&SPI`, and RouterBridge IPC (`Bridge.provide` / `Bridge.call`).

3. **What exact code was used?**
   - 6 standalone test scripts (`jxbs_test.py`, `rs485_test1.py`, `rs485_test2.py`, `test_gps.py`, `display_test_notouch.ino`, `display_test_touch.ino`).
   - 4 Arduino UNO Q MCU sketches and 3 Linux MPU Python scripts (`hardware_test/arduino uno q/`, `hardware_test/GPS_UNO Q/`, `hardware_test/soil sensor with Max485-RS485 UNO Q/`, `hardware_test/TFT UNO Q/`).

4. **What parts of that code are reusable?**
   - Modbus register scaling and query logic from `jxbs_test.py` and `sketch.ino`.
   - GGA NMEA string indexing and coordinate formatting from `GPS_UNO Q/sketch.ino`.
   - ST7789 display initialization and XPT2046 coordinate remapping/constraining logic from `TFT UNO Q/sketch.ino`.
   - RouterBridge JSON serialization & deserialization pattern from `soil sensor with Max485-RS485 UNO Q/main.py`.

5. **What parts are only temporary test code?**
   - Serial port hardcoding (`COM8`, `COM10`), PC loopback verification, dummy loopback strings ("PING"), and standalone terminal print loops.

6. **What communication protocols and interfaces are actually working?**
   - RS485 Modbus RTU @ 9600 8-N-1 (Function Code 03)
   - TTL UART NMEA 0183 @ 9600 8-N-1 (`Serial1`)
   - 4-Wire Hardware SPI (`&SPI`) @ 3.3V logic for ST7789 & XPT2046
   - RouterBridge IPC (MPU ↔ MCU shared memory bridge)

7. **What exact UNO Q pins/interfaces are currently occupied?**
   - `Serial1` RX (Pin 0), `Serial1` TX (Pin 1)
   - Digital Pin 2 (`TOUCH_IRQ`)
   - Digital Pin 4 (`TOUCH_CS`)
   - Digital Pin 7 (**CRITICAL CONFLICT**: Claimed by `MAX485_RE_DE` AND `TFT_LED`)
   - Digital Pin 8 (`TFT_RST`)
   - Digital Pin 9 (`TFT_DC`)
   - Digital Pin 10 (`TFT_CS`)
   - Hardware SPI Pins (Pins 11 MOSI, 12 MISO, 13 SCK)

8. **What hardware assumptions are confirmed?**
   - Dual-core IPC via RouterBridge operates reliably with minimal overhead.
   - ST7789 native GRAM requires `setRotation(1)` and `tft.invertDisplay(false)` for correct landscape dark mode.
   - NEO-M8N outputs multi-constellation `$GNGGA` / `$GPGGA` sentences at 9600 baud.
   - JXBS-3001-TR requires 12V DC power and sequential 200 ms Modbus polling.

9. **What assumptions are still unverified?**
   - Simultaneous operation of all peripherals on a single STM32 MCU loop.
   - Electrical safety of 5V MAX485 RO output connected to STM32 RX without level shifting.
   - Long-term performance of shared SPI bus under rapid UI refreshes.

10. **Are there conflicting pin assignments or architecture decisions?**
    - **Pin Conflict 1 (GPIO 7):** `MAX485_RE_DE` (Soil Sensor sketch) vs `TFT_LED` (TFT sketch).
    - **Interface Conflict 2 (UART Serial1):** GPS (`Serial1`) vs MAX485 (`Serial1`). Both peripherals claim the single physical UART header of the UNO Q.
    - > **RESOLVED — see `docs/HARDWARE.md` section 9.1.** Backlight moved to D6, leaving D7 to RS485 direction control alone. `Serial1` awarded to the GPS; the soil probe moved to the Linux USB-RS485 port (`FIELDSENSE_SOURCE=HARDWARE`). Unified firmware lives in `hardware_test/fieldsense_unoq/`. This audit entry is kept as the record of how the conflicts were found.

11. **Are there duplicated implementations?**
    - Duplicate Modbus register addresses and scaling constants across Python and C++ files.
    - Duplicate NMEA parser logic in `test_gps.py` (Python) and `GPS_UNO Q/sketch.ino` (C++).

12. **What should become the unified production architecture?**
    - Modular dual-core architecture: STM32 MCU handles low-level hardware drivers (UART, RS485, SPI, GPIO) and exposes a unified JSON payload via RouterBridge; Qualcomm Linux MPU executes Python telemetry parsing, spatial interpolation, zone detection, AI engine, and UI state rendering.

13. **What code should be preserved?**
    - `ModbusMaster` callback structure (`preTransmission`, `postTransmission`).
    - NMEA GGA string index extraction logic.
    - Touch coordinate `map()` and `constrain()` algorithms.
    - RouterBridge JSON payload transport structure.

14. **What code should eventually be rewritten?**
    - MCU `loop()` structure (remove blocking `delay(1000)` / `delay(2000)` calls; convert to non-blocking state machine / `millis()`).
    - GPS parser (replace manual string manipulation with robust NMEA state machine).
    - Data transport (standardize on canonical JSON schema across all endpoints).

15. **What should NOT be carried into the unified system?**
    - Hardcoded Windows COM ports (`COM8`, `COM10`).
    - Software SPI / bit-banging functions.
    - Duplicate pin assignments on Pin 7 and `Serial1`.

16. **What are the remaining risks before unified development?**
    - GPIO & UART pin expansion (resolving `Serial1` dual-occupancy via SoftwareSerial or Hardware UART multiplexing).
    - Mechanical bezel lamination pinch causing phantom touch inputs on TFT.
    - Overvoltage risk of 5V MAX485 RO output into 3.3V STM32 GPIO.

---

# 2. SCOPE

This audit covers all hardware testing code, scripts, configuration files, and documentation across the repository, including:

```text
hardware_test/
├── arduino uno q/
├── GPS/
├── GPS_UNO Q/
├── RS485/
├── soil sensor/
├── soil sensor with Max485-RS485 UNO Q/
├── TFT/
└── TFT UNO Q/
```

In addition, the following repository specification and code files were inspected:
- `docs/HARDWARE_SPEC.md`
- `fieldsense/hardware/config.py`
- `fieldsense/hardware/models.py`
- `fieldsense/hardware/sensor_adapter.py`
- `fieldsense/hardware/transport/mock.py`
- `tests/test_hardware.py`

---

# 3. REPOSITORY MAP

The actual file structure of the hardware testing directory and its associated files:

```text
hardware_test/
├── arduino uno q/
│   ├── main.py                        # Linux MPU bridge reader script
│   ├── sketch.ino                     # STM32 MCU UART loopback sketch
│   └── UNO_Q_HARDWARE_TEST.md         # Component test documentation
├── GPS/
│   ├── GPS_HARDWARE_TEST.md           # PC bench test documentation
│   └── test_gps.py                    # Standalone PC serial test script (COM10)
├── GPS_UNO Q/
│   ├── main.py                        # Linux MPU GPS telemetry script
│   ├── NEO_M8N_UNOQ_UART_INTEGRATION.md # GPS UNO Q integration doc
│   ├── requirements.txt               # Dependencies file
│   └── sketch.ino                     # STM32 MCU NMEA parser & bridge sketch
├── RS485/
│   ├── RS485_HARDWARE_TEST.md         # PC MAX485 bench test documentation
│   ├── rs485_test1.py                 # PC TX test script (COM10 -> COM8)
│   └── rs485_test2.py                 # PC RX test script (COM8 -> COM10)
├── soil sensor/
│   ├── JXBS_HARDWARE_TEST.md          # PC JXBS bench test documentation
│   └── jxbs_test.py                   # PC Modbus 7-register test script (COM8)
├── soil sensor with Max485-RS485 UNO Q/
│   ├── JXBS_MAX485_UNOQ_INTEGRATION.md# Soil sensor UNO Q integration doc
│   ├── main.py                        # Linux MPU JSON telemetry subscriber
│   └── sketch.ino                     # STM32 MCU Modbus master sketch (Pin 7 DE/RE)
├── TFT/
│   ├── display_test_notouch.ino       # ESP32 ST7789 display test sketch
│   ├── display_test_touch.ino         # ESP32 XPT2046 bit-bang touch test sketch
│   └── TFT_HARDWARE_TEST.md           # TFT bench test documentation
└── TFT UNO Q/
    ├── sketch.ino                     # STM32 MCU TFT + Touch shared SPI sketch
    └── TFT_UNOQ_INTEGRATION.md        # TFT UNO Q integration doc
```

### Detailed File Audit Matrix

| Path | File Type | Purpose | Target Host | Hardware Controlled | Dependencies | Type | Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `arduino uno q/sketch.ino` | C++ (.ino) | UART loopback test | STM32 MCU | Serial1 UART | `Arduino_RouterBridge.h` | Component | 🔴 DEPRECATED |
| `arduino uno q/main.py` | Python | Bridge status logger | Linux MPU | RouterBridge | `arduino.app_utils` | Component | 🔴 DEPRECATED |
| `GPS/test_gps.py` | Python | Standalone PC GPS logger | Windows PC | NEO-M8N (COM10) | `pyserial`, `time` | Component | 🔵 TEST-ONLY |
| `GPS_UNO Q/sketch.ino` | C++ (.ino) | NMEA receiver & parser | STM32 MCU | NEO-M8N (`Serial1`) | `Arduino_RouterBridge.h` | Integration | 🟡 REUSE LOGIC |
| `GPS_UNO Q/main.py` | Python | GPS telemetry logger | Linux MPU | RouterBridge | `arduino.app_utils` | Integration | 🟡 REUSE LOGIC |
| `RS485/rs485_test1.py` | Python | MAX485 TX driver test | Windows PC | MAX485 DI (COM10) | `pyserial`, `time` | Component | 🔵 TEST-ONLY |
| `RS485/rs485_test2.py` | Python | MAX485 RX receiver test | Windows PC | MAX485 RO (COM8) | `pyserial`, `time` | Component | 🔵 TEST-ONLY |
| `soil sensor/jxbs_test.py` | Python | Modbus 7-register test | Windows PC | JXBS-3001-TR (COM8) | `pyserial`, `time` | Component | 🔵 TEST-ONLY |
| `soil sensor with.../sketch.ino` | C++ (.ino) | Modbus polling & JSON formatting | STM32 MCU | JXBS + MAX485 (`Serial1`, Pin 7) | `Arduino_RouterBridge.h`, `ModbusMaster.h` | Integration | 🟢 KEEP / REUSABLE |
| `soil sensor with.../main.py` | Python | JSON telemetry subscriber | Linux MPU | RouterBridge | `arduino.app_utils`, `json` | Integration | 🟢 KEEP / REUSABLE |
| `TFT/display_test_notouch.ino` | C++ (.ino) | ESP32 ST7789 display bringup | ESP32 DevKit | ST7789 TFT | `Adafruit_GFX`, `Adafruit_ST7789`, `SPI` | Component | 🔵 TEST-ONLY |
| `TFT/display_test_touch.ino` | C++ (.ino) | ESP32 XPT2046 bit-bang touch | ESP32 DevKit | XPT2046 Touch | Standard Arduino core | Component | 🔵 TEST-ONLY |
| `TFT UNO Q/sketch.ino` | C++ (.ino) | TFT + Touch shared SPI sketch | STM32 MCU | ST7789 + XPT2046 (Pins 2,4,7,8,9,10,SPI) | `Adafruit_GFX`, `Adafruit_ST7789`, `XPT2046_Touchscreen`, `SPI` | Integration | 🟡 REUSE LOGIC |

---

# 4. COMPONENT STATUS AUDIT

### Master Hardware Verification Matrix

| Component | Independent Test | UNO Q Integration | Interface | Status | Summary Evidence |
| :--- | :---: | :---: | :--- | :---: | :--- |
| **JXBS-3001-TR** | 🟢 Verified | 🟢 Verified | RS485 Modbus RTU | 🟢 Verified | 7-register read verified on PC (`jxbs_test.py`) and UNO Q (`sketch.ino`) |
| **MAX485** | 🟢 Verified | 🟢 Verified | TTL UART / RS485 | 🟢 Verified | Bi-directional TX/RX passed on PC; Pin 7 DE/RE control verified on UNO Q |
| **NEO-M8N GPS** | 🟢 Verified | 🟢 Verified | TTL UART (9600) | 🟢 Verified | Multi-constellation `$GNGGA` acquisition parsed & bridged to Linux Python |
| **ST7789 TFT** | 🟢 Verified | 🟢 Verified | 4-Wire Hardware SPI | 🟢 Verified | 320x240 landscape dark-mode UI rendered cleanly via native `&SPI` |
| **XPT2046 Touch** | 🟢 Verified | 🟢 Verified | SPI / Active-Low IRQ | 🟢 Verified | Raw 12-bit ADC remapped to 320x240 UI; pressure filter active |
| **Arduino UNO Q** | 🟢 Verified | 🟢 Verified | RouterBridge IPC / UART / SPI | 🟢 Verified | Dual-core MPU ↔ MCU messaging verified with zero frame drops |

---

# 5. JXBS SOIL SENSOR AUDIT

### Complete Data Paths

1. **Independent PC Test Path:**
   ```text
   JXBS-3001-TR ──(RS485 A/B)──> FT232 USB-RS485 ──(COM8)──> Windows PC ──> Python (`jxbs_test.py`)
   ```
2. **UNO Q Integration Test Path:**
   ```text
   JXBS ──(RS485 A/B)──> MAX485 ──(Serial1 TX/RX & D7 DE/RE)──> STM32 MCU (`sketch.ino`)
          ──(ModbusMaster + JSON)──> RouterBridge ──(Bridge.call)──> Linux MPU (`main.py`)
   ```

### Serial Configuration
- **Baud Rate:** 9600 bps
- **Data Bits:** 8
- **Parity:** None
- **Stop Bits:** 1
- **Flow Control:** None

### Modbus Configuration
- **Slave ID:** `0x01`
- **Function Code:** `0x03` (Read Holding Registers)

### Register Audit

| Address | Parameter | Raw Type | Scaling | Request Frame (Hex) | Response Format | Decoding Code Location | Verified Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `0x0006` | Soil pH | uint16 | $\div 100$ | `01 03 00 06 00 01 64 0B` | 7 bytes: `01 03 02 DH DL CL CH` | `jxbs_test.py`: L130<br>`sketch.ino`: L35 | 6.89 pH |
| `0x0012` | Moisture | uint16 | $\div 10$ | `01 03 00 12 00 01 24 0F` | 7 bytes: `01 03 02 DH DL CL CH` | `jxbs_test.py`: L147<br>`sketch.ino`: L40 | 0.0 – 22.9 % |
| `0x0013` | Temperature | int16 | $\div 10$ | `01 03 00 13 00 01 75 CF` | 7 bytes: `01 03 02 DH DL CL CH` | `jxbs_test.py`: L165<br>`sketch.ino`: L40 | 27.7 °C |
| `0x0015` | EC | uint16 | $\times 1$ | `01 03 00 15 00 01 95 CD` | 7 bytes: `01 03 02 DH DL CL CH` | `jxbs_test.py`: L181<br>`sketch.ino`: L40 | 603 µS/cm |
| `0x001E` | Nitrogen (N) | uint16 | $\times 1$ | `01 03 00 1E 00 01 E4 0C` | 7 bytes: `01 03 02 DH DL CL CH` | `jxbs_test.py`: L198<br>`sketch.ino`: L48 | 43 mg/kg |
| `0x001F` | Phosphorus (P)| uint16 | $\times 1$ | `01 03 00 1F 00 01 B5 CC` | 7 bytes: `01 03 02 DH DL CL CH` | `jxbs_test.py`: L215<br>`sketch.ino`: L48 | 60 mg/kg |
| `0x0020` | Potassium (K) | uint16 | $\times 1$ | `01 03 00 20 00 01 85 C0` | 7 bytes: `01 03 02 DH DL CL CH` | `jxbs_test.py`: L232<br>`sketch.ino`: L48 | 120 mg/kg |

### CRC Implementation Status
- **Independent PC Test (`jxbs_test.py`):** Explicit 16-bit CRC-16-MODBUS calculation function (`modbus_crc()`, polynomial `0xA001`) implemented on lines 9–22 and validated on lines 43–50 (`check_crc()`). 100% CRC pass rate confirmed.
- **UNO Q Integration (`sketch.ino`):** CRC generation and check are handled transparently by the third-party `<ModbusMaster.h>` C++ library (`node.readHoldingRegisters()`). The sketch checks `node.ku8MBSuccess` (line 35). Explicit raw CRC logging is absent on the MCU side.

---

# 6. MAX485 AUDIT

### Transceiver Module Specs (`HW-097`)
- **Transceiver IC:** Maxim `MAX485CSA +DNHK` (SOIC-8)
- **VCC:** 5.0 V DC
- **GND:** Shared Common Ground
- **RO (Receiver Output):** Connected to UART RX
- **RE (Receiver Enable):** Active LOW
- **DE (Driver Enable):** Active HIGH
- **DI (Driver Input):** Connected to UART TX
- **A / B:** Differential RS485 lines with onboard 120 Ω termination resistor (`R7`) and pull-up/pull-down bus bias resistors (`R5/R6` 20 kΩ).

### Direction Control Implementation
- **Independent Tests (`rs485_test1.py` / `rs485_test2.py`):** Direct jumper hardwiring (`DE=5V, RE=5V` for TX; `DE=0V, RE=0V` for RX).
- **UNO Q Integration (`sketch.ino`):** `RE` and `DE` tied together to **UNO Q Digital Pin 7**.
- **Direction Control Callbacks (`sketch.ino`):**
  ```cpp
  void preTransmission()  { digitalWrite(MAX485_RE_DE, HIGH); } // Set Pin 7 HIGH for TX
  void postTransmission() { digitalWrite(MAX485_RE_DE, LOW);  } // Set Pin 7 LOW for RX
  ```
  Registered with `ModbusMaster` via:
  ```cpp
  node.preTransmission(preTransmission);
  node.postTransmission(postTransmission);
  ```

### Critical UART Transmission Completion Timing
The `ModbusMaster` library handles flushing the UART transmit shift register before calling `postTransmission()`. In any future custom driver implementation, de-asserting DE/RE before the final byte finishes shifting out of the UART hardware register will truncate the 16-bit CRC checksum, leading to silent Modbus read failures.

---

# 7. GPS AUDIT

### GPS Subsystem Specifications
- **Module Model:** u-blox NEO-M8N Breakout (`GY-GPSV3-NEO`, Board Marking `NEO-M8N-0-10`)
- **UART Interface:** `Serial1` @ 9600 baud (8-N-1)
- **Physical Header:** 4-pin header (`VCC`, `RX`, `TX`, `GND`). *No hardware PPS pin exposed.*
- **Supported Sentences:** Multi-constellation NMEA 0183 (`$GNGGA`, `$GPGGA`, `$GNRMC`, `$GNGSA`, `$GPGSV`, `$GLGSV`).

### Data Pipeline Architecture
```text
NEO-M8N ──(UART 9600)──> STM32 Serial1 ──> `parse_gga_sentence()` ──> `latest_gps_csv`
        ──> Bridge.provide("get_gps_data") ──(RouterBridge)──> MPU `main.py` ──> Print Telemetry
```

### GGA Parsing & Parameter Extraction
Implemented in `GPS_UNO Q/sketch.ino` (`parse_gga_sentence()`, lines 31–59):
- Maps comma indices across NMEA string.
- Extracts Latitude (`indices[1] + 1` to `indices[2]`), Latitude Direction (`indices[2] + 1` to `indices[3]`), Longitude (`indices[3] + 1` to `indices[4]`), Longitude Direction (`indices[4] + 1` to `indices[5]`), Fix Status (`indices[5] + 1` to `indices[6]`), Satellite Count (`indices[6] + 1` to `indices[7]`), HDOP (`indices[7] + 1` to `indices[8]`).
- Formats CSV String: `FIX_OK,1734.18667N,07825.47349E,Sats:06,HDOP:1.61`.
- RouterBridge endpoint: `get_gps_data`.

---

# 8. TFT AUDIT

### Display & Touch Specifications
- **Display Controller:** ST7789V (240 × 320 native GRAM matrix)
- **Touch Controller:** XPT2046 / HR2046 (12-bit SAR ADC resistive touch controller)
- **Display Resolution & Orientation:** 320 × 240 landscape (`tft.setRotation(1)`)
- **Color Matrix Setting:** `tft.invertDisplay(false)` (Dark mode UI verified)
- **SPI Architecture:** Shared Hardware SPI (`&SPI`) on UNO Q

### Pin Assignments (`TFT UNO Q/sketch.ino`)
- `TFT_CS`: Pin 10
- `TFT_DC`: Pin 9
- `TFT_RST`: Pin 8
- `TFT_LED`: Pin 7 (**CONFLICING PIN**)
- `TOUCH_CS`: Pin 4
- `TOUCH_IRQ`: Pin 2
- Hardware SPI: Shared SCK (Pin 13), MOSI (Pin 11), MISO (Pin 12)

### Touch Calibration & Filtering Logic
- Raw ADC range: `~200` to `~3700`
- Coordinate Mapping: `map(p.x, 200, 3700, 320, 0)` and `map(p.y, 200, 3700, 240, 0)`
- Constraining: `constrain(mapped_x, 0, 320)` and `constrain(mapped_y, 0, 240)`
- Z-Axis Pressure Filter: `if (p.z < 400 || p.z > 4000)` filters ghost touches.

### Discovered Hardware Defect
A mechanical bezel lamination pinch causes phantom touch inputs near the center of the display under stress. Accepted for V1 prototyping; capacitive touch recommended for final production.

---

# 9. UNO Q AUDIT

### Dual-Core Platform Architecture
```text
┌──────────────────────────────────────────────────────────┐
│                    ARDUINO UNO Q                         │
│                                                          │
│  ┌─────────────────────────┐  ┌───────────────────────┐  │
│  │ Qualcomm QRB2210 Linux  │  │ STMicroelectronics    │  │
│  │ MPU (Application Core)  │  │ STM32U585 MCU (Real-  │  │
│  │                         │  │ time Hardware Core)   │  │
│  │ • Debian Linux OS       │  │ • Arduino C++ Firmware│  │
│  │ • Python 3 Environment  │  │ • Physical UART/SPI   │  │
│  │ • Spatial & AI Engine   │  │ • Modbus Master Loop  │  │
│  └────────────┬────────────┘  └───────────┬───────────┘  │
│               │                           │              │
│               └───────[ RouterBridge ]────┘              │
│                       Native Shared Memory IPC           │
└──────────────────────────────────────────────────────────┘
```

### Responsibility Breakdown

| System Responsibility | Execution Host | Reason / Rationale |
| :--- | :--- | :--- |
| **Physical Serial / UART Stream Reading** | STM32 MCU | Real-time byte timing; prevents Linux OS latency drops |
| **MAX485 Direction Toggling (Pin 7)** | STM32 MCU | Strict microsecond-level timing around UART transmission |
| **NMEA Sentence Comma Indexing** | STM32 MCU | Reduces IPC payload size crossing MPU boundary |
| **ST7789 SPI Graphics Refresh** | STM32 MCU | Direct hardware SPI controller ownership |
| **XPT2046 Pen IRQ Handling** | STM32 MCU | Microcontroller hardware interrupt response |
| **Telemetry JSON Deserialization** | Linux MPU | High-level Python `json.loads()` processing |
| **Spatial IDW Interpolation** | Linux MPU | Heavy floating-point matrix calculations |
| **Zone Detection Engine** | Linux MPU | High-level data structures and clustering |
| **Rule-Based Recommendation Engine** | Linux MPU | Python business logic and rule evaluations |
| **User Interface Presentation Adapter** | Linux MPU | Render HTML/UI models for display/web |

---

# 10. COMPLETE PIN MAP

### Master UNO Q Pin Allocation & Conflict Audit

| UNO Q Pin | Peripheral | Signal Name | Direction | Logic Level | Assigned Sketch / Location | Conflict Flag |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Pin 0** | GPS / MAX485 | `RX` / `Serial1 RX` | Input | 3.3V / 5V | `GPS_UNO Q/sketch.ino`<br>`soil sensor.../sketch.ino` | 🔴 **HARDWARE CONFLICT** (UART Dual Occupancy) |
| **Pin 1** | GPS / MAX485 | `TX` / `Serial1 TX` | Output | 3.3V | `GPS_UNO Q/sketch.ino`<br>`soil sensor.../sketch.ino` | 🔴 **HARDWARE CONFLICT** (UART Dual Occupancy) |
| **Pin 2** | XPT2046 Touch | `TOUCH_IRQ` | Input (Pullup)| 3.3V | `TFT UNO Q/sketch.ino`: L19 | 🟢 OK |
| **Pin 4** | XPT2046 Touch | `TOUCH_CS` | Output | 3.3V | `TFT UNO Q/sketch.ino`: L18 | 🟢 OK |
| **Pin 7** | MAX485 / TFT | `RE_DE` / `TFT_LED` | Output | 3.3V / 5V | `soil sensor.../sketch.ino`: L5<br>`TFT UNO Q/sketch.ino`: L15 | 🔴 **HARDWARE CONFLICT** (GPIO 7 Overlap) |
| **Pin 8** | ST7789 TFT | `TFT_RST` | Output | 3.3V | `TFT UNO Q/sketch.ino`: L14 | 🟢 OK |
| **Pin 9** | ST7789 TFT | `TFT_DC` | Output | 3.3V | `TFT UNO Q/sketch.ino`: L13 | 🟢 OK |
| **Pin 10** | ST7789 TFT | `TFT_CS` | Output | 3.3V | `TFT UNO Q/sketch.ino`: L12 | 🟢 OK |
| **Pin 11** | Shared SPI | `MOSI` | Output | 3.3V | `TFT UNO Q/sketch.ino` (Hardware SPI)| 🟢 OK (Shared Bus) |
| **Pin 12** | Shared SPI | `MISO` | Input | 3.3V | `TFT UNO Q/sketch.ino` (Hardware SPI)| 🟢 OK (Shared Bus) |
| **Pin 13** | Shared SPI | `SCK` | Output | 3.3V | `TFT UNO Q/sketch.ino` (Hardware SPI)| 🟢 OK (Shared Bus) |

> [!CAUTION]
> **CRITICAL HARDWARE BLOCKERS IDENTIFIED:**
> 1. **Pin 7 Conflict:** `soil sensor.../sketch.ino` defines `#define MAX485_RE_DE 7`. `TFT UNO Q/sketch.ino` defines `#define TFT_LED 7`. Toggling RS485 direction turns off display backlight; keeping backlight on locks RS485 in TX mode!
> 2. **Serial1 Dual-Occupancy Conflict:** Both GPS (`GPS_UNO Q/sketch.ino`) and MAX485 (`soil sensor.../sketch.ino`) claim `Serial1` (Pins 0 & 1). A single physical UART cannot serve both devices simultaneously without hardware multiplexing or SoftwareSerial reallocation.

---

# 11. VOLTAGE / POWER AUDIT

### Master Power & Voltage Compatibility Matrix

| Component | VCC Input | Logic Level | UNO Q Compatible? | Operational Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Arduino UNO Q** | 5.0 V DC | 3.3 V CMOS | **N/A (Host)** | USB-C main power input |
| **JXBS-3001-TR** | 12.0–24.0 V DC | RS485 Differential | 🟢 YES (Isolated) | Powered by external 12.24V DC battery/adapter; common GND required |
| **MAX485 Module** | 5.0 V DC | 5.0 V TTL Logic | 🟡 NEEDS VERIFICATION | VCC from UNO Q 5V rail. **RO output is 5V TTL**. Must verify if STM32 Pin 0 (RX) is 5V tolerant. |
| **NEO-M8N GPS** | 3.3 V DC | 3.3 V CMOS | 🟢 YES | Powered by 3.3V rail or 5V (onboard 3.3V LDO present). |
| **ST7789 TFT** | 3.3 V / 5.0 V DC | 3.3 V CMOS | 🟢 YES | Power via 3.3V/5V. **Signals are strictly 3.3V logic only**. |
| **XPT2046 Touch** | 3.3 V DC | 3.3 V CMOS | 🟢 YES | Power and logic strictly 3.3V. |

---

# 12. COMMUNICATION PROTOCOL AUDIT

| Peripheral | Physical Layer | Protocol Layer | Speed / Baud | Execution Host | Inter-Core Transport |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **JXBS Soil Sensor** | RS485 Differential | Modbus RTU (Func 03) | 9600 8-N-1 | STM32 MCU | RouterBridge (`get_soil_data` JSON) |
| **MAX485 Module** | TTL UART / RS485 | Half-Duplex Physical | 9600 8-N-1 | STM32 MCU | Direct GPIO / UART Control |
| **NEO-M8N GPS** | TTL UART | NMEA 0183 (`$GN`/`$GP`) | 9600 8-N-1 | STM32 MCU | RouterBridge (`get_gps_data` CSV) |
| **ST7789 TFT** | 4-Wire SPI | ST7789 Command Protocol| Hardware SPI | STM32 MCU | Native SPI Driver (`Adafruit_ST7789`) |
| **XPT2046 Touch** | 4-Wire SPI + IRQ | 12-Bit SAR ADC Frame | Hardware SPI | STM32 MCU | Native SPI Driver (`XPT2046_Touchscreen`) |
| **MPU ↔ MCU IPC** | Internal SoC Bus | RouterBridge API | High Speed | QRB2210 & STM32 | `Bridge.provide()` / `Bridge.call()` |

---

# 13. CODING STRUCTURE AUDIT

### MCU Firmware Architecture (`.ino` Sketches)
1. **Header & Initialization (`setup()`):**
   - Initializes `Bridge.begin()` and registers RouterBridge functions (`Bridge.provide()`).
   - Configures UART `Serial1.begin(9600)` and SPI `SPI.begin()`.
   - Configures pinMode for direction pins (`MAX485_RE_DE`), display control (`TFT_CS`, `TFT_DC`, `TFT_RST`, `TFT_LED`), and touch interrupts (`TOUCH_IRQ`, `TOUCH_CS`).
2. **Main Execution Loop (`loop()`):**
   - Polls Modbus registers using `ModbusMaster` or reads serial NMEA lines using `Serial1.readStringUntil('\n')`.
   - Formats parsed telemetry into in-memory global buffers (`soil_data`, `latest_gps_csv`).
   - Utilizes blocking `delay()` calls (2000 ms in Soil Sensor sketch, 1000 ms in GPS sketch).

### Python MPU Application Architecture (`main.py` Scripts)
1. **Imports & Setup:** `from arduino.app_utils import *`, `import json`, `import time`.
2. **Polling Loop (`loop()`):**
   - Calls `Bridge.call("get_soil_data")` or `Bridge.call("get_gps_data")`.
   - Deserializes JSON payloads (`json.loads()`) or formats CSV output.
   - Handles exceptions (`json.JSONDecodeError`) gracefully without crashing loop.
   - Enforces execution via `App.run(user_loop=loop)`.

### Software Dependencies Audit

| Dependency Library | Language / Framework | Used By | Purpose | Required in Unified Build? |
| :--- | :--- | :--- | :--- | :---: |
| `Arduino_RouterBridge.h` | C++ (Arduino Core) | MCU Sketches | MPU ↔ MCU Inter-Process Communication | 🟢 YES (Runtime Core) |
| `ModbusMaster.h` | C++ (Arduino Library) | `soil sensor.../sketch.ino` | Modbus RTU frame construction & parsing | 🟢 YES (Runtime Core) |
| `Adafruit_GFX.h` | C++ (Adafruit) | `TFT UNO Q/sketch.ino` | Base graphics drawing primitive library | 🟢 YES (Runtime Core) |
| `Adafruit_ST7789.h` | C++ (Adafruit) | `TFT UNO Q/sketch.ino` | ST7789 display controller driver | 🟢 YES (Runtime Core) |
| `XPT2046_Touchscreen.h` | C++ (PaulStoffregen)| `TFT UNO Q/sketch.ino` | XPT2046 touch controller SPI driver | 🟢 YES (Runtime Core) |
| `SPI.h` | C++ (Arduino Core) | `TFT UNO Q/sketch.ino` | Hardware SPI bus interface | 🟢 YES (Runtime Core) |
| `arduino.app_utils` | Python (Arduino Linux)| MPU Python scripts | MPU side RouterBridge client wrapper | 🟢 YES (Runtime Core) |
| `pyserial` | Python (Standard PyPI) | `jxbs_test.py`, `rs485_test1.py`| PC bench test serial communication | 🔵 NO (Test-Only) |

---

# 14. CODE REUSE AUDIT

### Source File Classification Summary

| File Path | Current Role | Classification | Reuse Strategy |
| :--- | :--- | :---: | :--- |
| `soil sensor with Max485-RS485 UNO Q/sketch.ino` | Soil sensor integration sketch | 🟢 **KEEP / REUSABLE** | Extract `ModbusMaster` callbacks and 7-register polling loop into unified firmware `soil_driver.cpp`. |
| `soil sensor with Max485-RS485 UNO Q/main.py` | Soil telemetry subscriber | 🟢 **KEEP / REUSABLE** | Extract JSON parsing logic into Python `HardwareSensorAdapter`. |
| `GPS_UNO Q/sketch.ino` | GPS integration sketch | 🟡 **REUSE LOGIC** | Extract `parse_gga_sentence()` logic; remove blocking string reads. |
| `GPS_UNO Q/main.py` | GPS telemetry subscriber | 🟡 **REUSE LOGIC** | Extract string parsing into Python `HardwareGPSAdapter`. |
| `TFT UNO Q/sketch.ino` | Display & Touch sketch | 🟡 **REUSE LOGIC** | Extract ST7789 init, color inversion, and touch mapping algorithms into display driver module. Re-assign `TFT_LED` pin. |
| `arduino uno q/sketch.ino` | Basic UART loopback sketch | 🔴 **DEPRECATED** | Do not carry forward (temporary bench verification code). |
| `arduino uno q/main.py` | Basic bridge caller | 🔴 **DEPRECATED** | Do not carry forward (temporary bench verification code). |
| `soil sensor/jxbs_test.py` | Standalone PC Modbus script | 🔵 **TEST-ONLY** | Keep as ground-truth bench verification tool for JXBS probe. |
| `RS485/rs485_test1.py` & `rs485_test2.py` | Standalone PC RS485 scripts | 🔵 **TEST-ONLY** | Keep as reference scripts for hardware transceiver testing. |
| `GPS/test_gps.py` | Standalone PC GPS script | 🔵 **TEST-ONLY** | Keep as reference script for NEO-M8N characterization. |
| `TFT/display_test_notouch.ino` & `...touch.ino` | ESP32 TFT test sketches | 🔵 **TEST-ONLY** | Keep as hardware reference for ESP32 bench setup. |

---

# 15. DUPLICATION AUDIT

### Discovered Code & Logic Duplications

1. **Modbus Register Maps:** Register addresses (`0x0006`, `0x0012`, `0x0013`, `0x0015`, `0x001E`, `0x001F`, `0x0020`) and scaling factors ($\div 100, \div 10, \times 1$) are defined independently in `jxbs_test.py`, `soil sensor with Max485-RS485 UNO Q/sketch.ino`, and `docs/HARDWARE_SPEC.md`.
2. **CRC Calculation:** Modbus CRC-16 polynomial math (`0xA001`) is manually written in `jxbs_test.py` and hidden inside `<ModbusMaster.h>` on the MCU.
3. **GPS GGA Parsing:** NMEA sentence splitting logic is duplicated across `GPS/test_gps.py` (Python string split) and `GPS_UNO Q/sketch.ino` (C++ char array searching).
4. **RouterBridge Setup:** `Bridge.begin()` and `Bridge.provide()` boilerplate duplicated across 3 separate MCU sketches.

---

# 16. ERROR-HANDLING AUDIT

| Subsystem | Failure Scenario | Implemented Handling Status | Current Code Behavior | Required Unified Behavior |
| :--- | :--- | :---: | :--- | :--- |
| **JXBS** | No Response / Timeout | 🟢 Implemented | `sketch.ino`: returns `{"error":"MODBUS_READ_FAILED"}` | Set status flag; attempt retry after interval; emit hardware error code |
| **JXBS** | Invalid CRC Checksum | 🟢 Implemented | `<ModbusMaster.h>` returns error code; sketch catches failure | Increment error counter; log CRC failure metric |
| **GPS** | No Satellite Fix (Fix=0) | 🟢 Implemented | `sketch.ino`: returns `FIX_OK` vs `NO_FIX` status in CSV | Flag fix invalid; retain last known fix with stale timestamp |
| **GPS** | Malformed NMEA Frame | 🟡 Partial | `sketch.ino`: checks sentence prefix `$GNGGA`/`$GPGGA` and comma count | Add full NMEA checksum validation (`*XX`) |
| **TFT** | Init Failure / Bus Lock | 🔴 Missing | None (Assumes SPI succeeds) | Timeout SPI init; fallback to headless console mode |
| **Touch** | Floating Touch Noise | 🟢 Implemented | `sketch.ino`: filters `p.z < 400 || p.z > 4000` | Maintain Z-axis pressure bounds filter |
| **RouterBridge**| IPC Call Failure / MPU Lock| 🟡 Partial | Python `main.py`: `try...except json.JSONDecodeError` | Add timeout wrapper & bridge reset watchdog |

---

# 17. TIMING / REAL-TIME AUDIT

### Polling Intervals & Delays
- `soil sensor with Max485-RS485 UNO Q/sketch.ino`: Contains hardcoded `delay(2000)` on line 67.
- `GPS_UNO Q/sketch.ino`: Reads `Serial1` synchronously inside `loop()`.
- `TFT UNO Q/sketch.ino`: Contains `delay(10)` per loop iteration.
- `main.py` scripts: Contain `time.sleep(1)` or `time.sleep(2)` blocking loops.

### Real-Time Execution Hazard
If all three peripherals are combined into a single MCU sketch, executing synchronous `delay(2000)` during soil sensor Modbus reads will block the MCU from reading incoming UART characters from the NEO-M8N GPS, leading to `Serial1` RX buffer overflows (buffer size 64 bytes) and corrupted NMEA sentence parsing. 

> [!IMPORTANT]
> The unified MCU firmware MUST eliminate all `delay()` calls and implement a non-blocking `millis()` state machine scheduler.

---

# 18. DATA MODEL AUDIT

### Current Inter-Core Boundary Payload Formats

1. **Soil Sensor Subsystem (`soil sensor with Max485-RS485 UNO Q/sketch.ino`):**
   - Format: **Structured JSON String**
   - Payload: `{"temp":27.7,"moisture":0.0,"ph":6.89,"ec":603,"n":43,"p":60,"k":120}`
2. **GPS Subsystem (`GPS_UNO Q/sketch.ino`):**
   - Format: **Delimited CSV String**
   - Payload: `FIX_OK,1734.18667N,07825.47349E,Sats:06,HDOP:1.61`
3. **Basic Test (`arduino uno q/sketch.ino`):**
   - Format: **Raw Text String**
   - Payload: `PASS: TX/RX WORKING`

### Fragmentation Finding
The data models crossing the RouterBridge boundary are fragmented (JSON vs CSV vs Text). The unified architecture must standardize on a single, clean JSON payload envelope for all MCU $\rightarrow$ MPU communications.

---

# 19. UNIFIED ARCHITECTURE READINESS

### Readiness Assessment

| Subsystem | Readiness Status | Blockers / Action Required |
| :--- | :---: | :--- |
| **JXBS Soil Sensor Driver** | 🟢 Ready | Fully verified; requires non-blocking timer refactoring. |
| **MAX485 Transceiver Layer** | 🟡 Needs Refactoring | **Re-assign GPIO Pin 7** to resolve TFT backlight conflict. |
| **NEO-M8N GPS Driver** | 🔴 Hardware Blocker | **Resolve UART Serial1 conflict** (GPS and MAX485 both claim Serial1). |
| **ST7789 TFT Driver** | 🟡 Needs Refactoring | **Re-assign TFT_LED pin** away from GPIO Pin 7. |
| **XPT2046 Touch Driver** | 🟢 Ready | Remapping and pressure filtering verified. |
| **RouterBridge IPC Layer** | 🟢 Ready | Standardize JSON serialization format across all endpoints. |

---

# 20. PROPOSED UNIFIED SOFTWARE STRUCTURE

```text
FieldSense/
│
├── firmware/                              # STM32U585 Microcontroller Firmware (C++)
│   ├── platformio.ini / sketch.ino        # Main entry point
│   ├── config/
│   │   ├── pin_map.h                      # FREEZED Master Pin Assignments (Conflict-Free)
│   │   └── config.h                       # Baud rates, intervals, Modbus IDs
│   ├── drivers/
│   │   ├── jxbs_sensor.cpp/.h             # JXBS Modbus RTU non-blocking driver
│   │   ├── max485.cpp/.h                  # MAX485 direction pin controller
│   │   ├── neo_m8n.cpp/.h                 # GPS UART reader & NMEA stream parser
│   │   ├── st7789_display.cpp/.h          # ST7789 TFT SPI graphics renderer
│   │   └── xpt2046_touch.cpp/.h           # XPT2046 touch driver & calibration
│   └── bridge/
│       └── router_bridge_provider.cpp/.h  # Unified RouterBridge JSON IPC provider
│
└── fieldsense/                            # Qualcomm QRB2210 Linux Application (Python)
    ├── main.py                            # Application entry point & loop runner
    ├── hardware/                          # Hardware Integration Layer
    │   ├── bridge_client.py               # RouterBridge IPC client
    │   ├── sensor_adapter.py              # HardwareSensorAdapter implementation
    │   ├── gps_adapter.py                 # HardwareGPSAdapter implementation
    │   └── models.py                      # Telemetry data models
    ├── intelligence/                      # Validation & AI Engine
    ├── spatial/                           # IDW Spatial Engine
    ├── zones/                             # Management Zone Engine
    ├── recommendations/                   # Rule-Based Recommendation Engine
    └── presentation/                      # UI Rendering Engine
```

---

# 21. UNIFIED DATA FLOW

```text
 ┌─────────────────┐       ┌─────────────────┐
 │ JXBS Soil Probe │       │ NEO-M8N GPS     │
 └────────┬────────┘       └────────┬────────┘
          │ RS485                   │ TTL UART
          ▼                         │
     MAX485 Module                  │
          │ TTL UART                │
          └───────────┬─────────────┘
                      │
                      ▼
 ┌───────────────────────────────────────────┐
 │             STM32U585 MCU                 │
 │  • Non-blocking state machine scheduler   │
 │  • ModbusMaster register poller           │
 │  • NMEA stream parser                     │
 │  • ST7789 TFT & XPT2046 touch controller  │
 │  • Standardized JSON builder              │
 └────────────────────┬──────────────────────┘
                      │
                      │ RouterBridge IPC (`Bridge.provide`)
                      ▼
 ┌───────────────────────────────────────────┐
 │            Qualcomm Linux MPU             │
 │  • Python `HardwareSensorAdapter`         │
 │  • Canonical `FieldSample` construction   │
 │  • Validation Engine                      │
 │  • Spatial Engine (IDW Grid)              │
 │  • Zone Detection Engine                  │
 │  • Recommendation Engine                  │
 │  • Presentation / UI Engine               │
 └───────────────────────────────────────────┘
```

---

# 22. HARDWARE TEST → PRODUCTION TRANSITION

| Component / Test | Existing Test Code | Unified Production Driver |
| :--- | :--- | :--- |
| **JXBS Soil Sensor** | `soil sensor/jxbs_test.py` (PC) | `firmware/drivers/jxbs_sensor.cpp` |
| **MAX485 Direction** | JXBS UNO Q `sketch.ino` (Pin 7) | `firmware/drivers/max485.cpp` (Re-assigned Pin) |
| **GPS NMEA Parsing** | `GPS_UNO Q/sketch.ino` | `firmware/drivers/neo_m8n.cpp` |
| **TFT Graphics** | `TFT UNO Q/sketch.ino` | `firmware/drivers/st7789_display.cpp` |
| **Touch Calibration** | `TFT UNO Q/sketch.ino` | `firmware/drivers/xpt2046_touch.cpp` |
| **IPC Boundary** | `soil sensor.../main.py` | `fieldsense/hardware/bridge_client.py` |

---

# 23. KNOWN ISSUES / RISKS

### Itemized Risk Register

1. **ISSUE: Pin 7 Duplicate Claim**
   - *Evidence:* `soil sensor.../sketch.ino:L5` vs `TFT UNO Q/sketch.ino:L15`.
   - *Current Status:* Unresolved conflict.
   - *Impact:* System failure if loaded simultaneously.
   - *Recommended Action:* Move `TFT_LED` to Pin 6 or dedicated PWM pin.

2. **ISSUE: UART Serial1 Dual Occupancy**
   - *Evidence:* GPS and MAX485 both claim `Serial1` (Pins 0 & 1).
   - *Current Status:* Unresolved conflict.
   - *Impact:* Cannot read GPS and Soil Sensor simultaneously.
   - *Recommended Action:* Assign MAX485 to SoftwareSerial or secondary MCU UART pins (`Serial2`), leaving `Serial1` for GPS.

3. **ISSUE: MAX485 5V RO Overvoltage Risk**
   - *Evidence:* MAX485 VCC powered from 5V; RO outputs 5V TTL logic.
   - *Current Status:* Unverified electrical safety on STM32 RX pin.
   - *Impact:* Potential degradation of STM32 GPIO over time.
   - *Recommended Action:* Insert 1k/2k resistor divider or 3.3V logic level shifter on RO line.

4. **ISSUE: Mechanical Touch Bezel Pinch**
   - *Evidence:* `TFT UNO Q/TFT_UNOQ_INTEGRATION.md:L297`.
   - *Current Status:* Accepted for V1 prototype.
   - *Impact:* Occasional phantom touch inputs.
   - *Recommended Action:* Pressure filter in software; evaluate capacitive touch for field build.

5. **ISSUE: Blocking `delay()` Calls in MCU Loop**
   - *Evidence:* `soil sensor.../sketch.ino:L67` (`delay(2000)`).
   - *Current Status:* Code present in test sketches.
   - *Impact:* Serial RX buffer overflow during GPS polling.
   - *Recommended Action:* Refactor MCU code to non-blocking `millis()` scheduler.

---

# 24. CRITICAL INCONSISTENCY CHECK

| Conflict / Parameter | Source A | Source B | Why It Matters | Needs Resolution |
| :--- | :--- | :--- | :--- | :--- |
| **GPIO Pin 7 Usage** | Soil Sensor Sketch: `MAX485_RE_DE = 7` | TFT Sketch: `TFT_LED = 7` | Hardware control signal collision | YES — Re-assign `TFT_LED` to Pin 6 |
| **UART Serial1 Usage** | GPS Sketch: `Serial1` (9600) | Soil Sensor Sketch: `Serial1` (9600) | Peripheral bus collision | YES — Re-assign MAX485 to SoftwareSerial/Serial2 |
| **Touch SPI Architecture**| TFT Test Doc: Dedicated Touch SPI required | TFT UNO Q Sketch: Shared `&SPI` bus used | MISO bus loading / contention risk | YES — Verify SPI transaction stability under high load |
| **Bridge Data Format** | Soil Sensor: JSON String | GPS Sketch: CSV String | Fragile, inconsistent MPU parsing | YES — Standardize on JSON envelope |
| **GPS NMEA Filtering** | `test_gps.py`: `$GNGGA`/`$GPGGA` split string | `sketch.ino`: Comma index substring search | Logic inconsistency across hosts | YES — Standardize C++ NMEA parser |

---

# 25. FINAL HARDWARE MASTER TABLE

| Hardware Component | Independent Verified | UNO Q Integrated | Interface | Current Status | Production Ready for Unified Dev? |
| :--- | :---: | :---: | :--- | :---: | :---: |
| **JXBS-3001-TR** | 🟢 PASS | 🟢 PASS | RS485 Modbus RTU | 🟢 Verified | 🟢 YES |
| **MAX485 Module** | 🟢 PASS | 🟢 PASS | TTL UART / RS485 | 🟡 Conflict | 🟡 YES (Requires Pin Re-assignment) |
| **NEO-M8N GPS** | 🟢 PASS | 🟢 PASS | TTL UART | 🟡 Conflict | 🟡 YES (Requires UART Re-assignment) |
| **ST7789 TFT** | 🟢 PASS | 🟢 PASS | Hardware SPI | 🟡 Conflict | 🟡 YES (Requires Pin Re-assignment) |
| **XPT2046 Touch** | 🟢 PASS | 🟢 PASS | Hardware SPI / IRQ | 🟢 Verified | 🟢 YES |
| **Arduino UNO Q** | 🟢 PASS | 🟢 PASS | Dual-Core IPC | 🟢 Verified | 🟢 YES |

---

# 26. FINAL SOFTWARE MASTER TABLE

| File | Relative Path | Language | Purpose | Execution Host | Classification |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `sketch.ino` | `hardware_test/soil sensor with.../` | C++ | Modbus RTU & JSON framing | STM32 MCU | 🟢 KEEP / REUSABLE |
| `main.py` | `hardware_test/soil sensor with.../` | Python | JSON telemetry subscriber | Linux MPU | 🟢 KEEP / REUSABLE |
| `sketch.ino` | `hardware_test/GPS_UNO Q/` | C++ | NMEA reception & GGA parsing | STM32 MCU | 🟡 REUSE LOGIC |
| `main.py` | `hardware_test/GPS_UNO Q/` | Python | GPS telemetry logger | Linux MPU | 🟡 REUSE LOGIC |
| `sketch.ino` | `hardware_test/TFT UNO Q/` | C++ | ST7789 & XPT2046 SPI driver | STM32 MCU | 🟡 REUSE LOGIC |
| `jxbs_test.py` | `hardware_test/soil sensor/` | Python | Standalone PC Modbus test | Windows PC | 🔵 TEST-ONLY |
| `rs485_test1.py`| `hardware_test/RS485/` | Python | Standalone PC MAX485 TX test | Windows PC | 🔵 TEST-ONLY |
| `rs485_test2.py`| `hardware_test/RS485/` | Python | Standalone PC MAX485 RX test | Windows PC | 🔵 TEST-ONLY |
| `test_gps.py` | `hardware_test/GPS/` | Python | Standalone PC GPS test | Windows PC | 🔵 TEST-ONLY |
| `display_...ino`| `hardware_test/TFT/` | C++ | Standalone ESP32 TFT tests | ESP32 DevKit | 🔵 TEST-ONLY |
| `sketch.ino` | `hardware_test/arduino uno q/` | C++ | Basic UART loopback | STM32 MCU | 🔴 DEPRECATED |
| `main.py` | `hardware_test/arduino uno q/` | Python | Basic bridge caller | Linux MPU | 🔴 DEPRECATED |

---

# 27. FINAL VERDICT

## 🟢 VERIFIED
- All 6 core hardware components physically verified on bench and integrated with Arduino UNO Q.
- Dual-core MPU ↔ MCU Inter-Process Communication via RouterBridge proven stable.
- Modbus RTU 7-register acquisition, GPS NMEA coordinate extraction, and 320x240 dark-mode UI rendering fully validated.

## 🟡 NEEDS ATTENTION
- Re-assignment of GPIO Pin 7 (eliminate MAX485 vs TFT LED collision).
- Electrical level shifting for 5V MAX485 RO line into 3.3V STM32 RX pin.
- Elimination of blocking `delay()` calls in MCU firmware.
- Standardization of RouterBridge JSON payload envelope across all endpoints.

## 🔴 BLOCKERS
```text
CRITICAL CONFLICT 1: Pin 7 collision (MAX485 DE/RE vs TFT LED).
CRITICAL CONFLICT 2: Serial1 UART dual-occupancy collision (GPS vs MAX485).

NO OTHER HARD BLOCKERS IDENTIFIED.
```

## 🚀 RECOMMENDED UNIFIED DEVELOPMENT ORDER

```text
 1. Freeze Master Pin Assignment Matrix (resolve Pin 7 and Serial1 UART conflicts).
 2. Establish single unified firmware project structure (`firmware/`).
 3. Implement non-blocking millis() scheduler on STM32 MCU.
 4. Extract verified JXBS Modbus RTU driver into `firmware/drivers/jxbs_sensor.cpp`.
 5. Extract verified NEO-M8N NMEA driver into `firmware/drivers/neo_m8n.cpp`.
 6. Extract verified ST7789 & XPT2046 drivers into `firmware/drivers/tft_touch.cpp`.
 7. Standardize unified RouterBridge JSON IPC provider on MCU.
 8. Implement Python `HardwareSensorAdapter` and `HardwareGPSAdapter` in `fieldsense/hardware/`.
 9. Integrate unified hardware pipeline into Validation, Spatial, Zone, and AI engines.
10. Conduct simultaneous multi-peripheral hardware test on Arduino UNO Q bench setup.
11. Run end-to-end FieldSense system validation.
12. Finalize field deployment documentation.
```
