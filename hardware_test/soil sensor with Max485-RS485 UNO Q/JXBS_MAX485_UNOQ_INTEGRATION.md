# FieldSense — JXBS Soil Sensor + MAX485 + Arduino UNO Q Integration Documentation

## ROLE
Act as the repository documentation engineer for FieldSense.

The JXBS soil sensor has now been successfully integrated with the Arduino UNO Q through the verified MAX485 RS485 interface.

This is the first successful **V1 physical hardware integration**.

This technical Markdown document describes exactly how this integration was performed and verified. The existing integration code (`main.py` and `sketch.ino`) remains untouched.

---

## EXISTING FOLDER

The integration files exist inside the Soil Sensor hardware-testing area:

```text
hardware_test/
└── soil sensor with Max485-RS485/
    ├── main.py
    ├── sketch.ino
    └── JXBS_MAX485_UNOQ_INTEGRATION.md
```

Untouched working integration files:
- `main.py`
- `sketch.ino`

---

## DOCUMENT PURPOSE

This document details how the **JXBS-3001-TR** soil sensor was physically integrated with the **Arduino UNO Q** through the **MAX485 RS485 transceiver** and how the resulting sensor data was passed from the STM32 MCU to the Qualcomm Linux MPU through RouterBridge and Python.

This is an actual FieldSense hardware integration record.

---

## INTEGRATION STATUS

Final status:
```text
PASS — Full Stack Hardware & Communication Verified
```

This test goes beyond the previous isolated component tests:

**Previously:**
- JXBS: 🟢 VERIFIED
- MAX485: 🟢 VERIFIED
- UNO Q: 🟢 VERIFIED
- RouterBridge: 🟢 VERIFIED

**Now Verified End-to-End:**
```text
JXBS
 ↓
RS485
 ↓
MAX485
 ↓
UNO Q STM32
 ↓
RouterBridge
 ↓
UNO Q Linux
 ↓
Python
```

---

## 1. SYSTEM OVERVIEW

### Target Device
**JXBS-3001-TR 7-in-1 RS485 Soil Sensor**

Configuration:
```text
Slave ID: 0x01
Baud Rate: 9600
Data: 8 bits
Parity: None
Stop bits: 1
Function: Modbus RTU Function 03
```

### Host Platform
**Arduino UNO Q:**
```text
STM32U585 MCU
+
Qualcomm QRB2210 MPU
+
Debian Linux
```

### Transceiver
**MAX485 TTL-to-RS485 Module**

Direction control:
```text
RE + DE bridged
→ UNO Q Digital Pin 7
```

### IPC
Native: `Arduino_RouterBridge`

Communication path:
```text
Bridge.provide()
Bridge.call()
```

---

## 2. END-TO-END ARCHITECTURE

```text
┌─────────────────────────┐
│ JXBS-3001-TR Sensor     │
│ 12V DC External Power   │
└───────────┬─────────────┘
            │
            │ RS485 A/B
            ▼
┌─────────────────────────┐
│ MAX485 Transceiver      │
│ RE + DE → UNO Q D7      │
└───────────┬─────────────┘
            │
            │ UART / Serial1
            │ 9600 8-N-1
            ▼
┌─────────────────────────┐
│ STM32U585 MCU            │
│ Modbus RTU polling       │
│ Register decoding        │
│ JSON framing             │
└───────────┬─────────────┘
            │
            │ RouterBridge
            ▼
┌─────────────────────────┐
│ Qualcomm QRB2210 MPU    │
│ Debian Linux             │
│ Python                   │
│ JSON parsing / logging   │
└─────────────────────────┘
```

---

## 3. PHYSICAL WIRING

Verified wiring pinout:

| Component | UNO Q / Rail | Purpose |
| :--- | :--- | :--- |
| **MAX485 VCC** | 5V | MAX485 power |
| **MAX485 GND** | GND | Common ground |
| **MAX485 RO** | Serial1 RX | RS485 receiver → MCU |
| **MAX485 DI** | Serial1 TX | MCU → RS485 driver |
| **MAX485 RE + DE** | Digital Pin 7 | Direction control |
| **Sensor A** | MAX485 A | RS485 A |
| **Sensor B** | MAX485 B | RS485 B |
| **Sensor V+** | External 12V DC | Sensor power |
| **Sensor V−** | Supply GND | Sensor return |

**Sensor Cable Color Wiring:**
```text
Brown  → Power+ (External 12V DC)
Black  → Power− (Supply GND / Common GND)
Yellow → RS485 A
Blue   → RS485 B
```

---

## 4. POWER ARCHITECTURE

Communication power and sensor power are cleanly isolated:

```text
External 12V DC
      ↓
JXBS sensor

UNO Q 5V
      ↓
MAX485

UNO Q GND
      ↓
MAX485 GND
```

- The JXBS sensor is powered externally from a 12V DC power supply.
- The MAX485 transceiver is powered from the UNO Q 5V rail.
- All systems share a common ground reference (12V Supply GND connected to UNO Q GND).

---

## 5. DIRECTION CONTROL

Verified MAX485 direction pin control behavior:

```text
UNO Q GPIO 7
      │
      ├── DE
      └── RE
```

Direction states:
```text
GPIO HIGH → MAX485 transmit mode
GPIO LOW  → MAX485 receive mode
```

The MAX485 module does not feature automatic direction sensing. The STM32 MCU firmware explicitly controls the bus direction.

**Firmware Execution Sequence:**
```text
Set GPIO HIGH
↓
Transmit UART frame
↓
WAIT FOR UART TRANSMISSION TO COMPLETE
↓
Set GPIO LOW
↓
Listen for sensor response
```
*Note: Switching to receive mode before the UART shift register completes transmission will truncate the frame.*

---

## 6. STM32 MCU RESPONSIBILITIES

The STM32 side is responsible for the real-time hardware layer.

**Responsibilities:**
- Real-time UART communication (`Serial1` at `9600 8-N-1`)
- MAX485 direction control (GPIO Pin 7)
- Modbus RTU polling (`ModbusMaster` library)
- Register requests & frame transmission
- Response reception & error validation
- Register decoding & numerical scaling
- JSON telemetry framing
- RouterBridge data provider (`Bridge.provide("get_soil_data", ...)`)

---

## 7. MODBUS REGISTER POLLING

All seven JXBS parameters are integrated using Modbus RTU Function 03 (Read Holding Registers).

| Parameter | Register | Scaling | Function Code |
| :--- | ---: | ---: | :--- |
| **pH** | `0x0006` | ÷100 | Function 03 |
| **Moisture** | `0x0012` | ÷10 | Function 03 |
| **Temperature** | `0x0013` | ÷10 | Function 03 |
| **Conductivity (EC)** | `0x0015` | ÷1 | Function 03 |
| **Nitrogen (N)** | `0x001E` | ÷1 | Function 03 |
| **Phosphorus (P)** | `0x001F` | ÷1 | Function 03 |
| **Potassium (K)** | `0x0020` | ÷1 | Function 03 |

---

## 8. VERIFIED LIVE TELEMETRY

Actual live hardware integration readings captured during verification:

| Parameter | Register | Verified Reading | Status |
| :--- | ---: | ---: | :--- |
| **pH** | `0x0006` | 6.89 pH | PASS |
| **Moisture** | `0x0012` | 0.0 %RH → responsive in liquid | PASS |
| **Temperature** | `0x0013` | 27.7 °C | PASS |
| **EC / Conductivity** | `0x0015` | 603 µS/cm | PASS |
| **Nitrogen (N)** | `0x001E` | 43 mg/kg | PASS |
| **Phosphorus (P)** | `0x001F` | 60 mg/kg | PASS |
| **Potassium (K)** | `0x0020` | 120 mg/kg | PASS |

*Note: These values are live hardware integration readings confirming physical and communication integrity, not certified calibration measurements.*

---

## 9. JSON / ROUTERBRIDGE ARCHITECTURE

Data pipeline from sensor to Linux user space:

```text
JXBS raw Modbus response
        ↓
STM32 decoding
        ↓
Scaling
        ↓
Structured JSON
        ↓
Bridge.provide()
        ↓
RouterBridge
        ↓
Bridge.call()
        ↓
Python
        ↓
json.loads()
        ↓
Telemetry output
```

**Why JSON was chosen:**
- Structured data representation
- Explicit field/value mapping
- Simple, reliable Python deserialization (`json.loads()`)
- Eliminates fragile delimiter splitting or manual string parsing
- Maintains strict separation of concerns between MCU hardware execution and Linux application logic

---

## 10. SOFTWARE FILES

The two existing integration files remain untouched:

### `sketch.ino`
- **Role:** STM32 MCU firmware
- **Responsibilities:**
  - Manages `Serial1` hardware UART @ 9600 baud
  - Controls MAX485 direction via Pin 7 callbacks (`preTransmission`, `postTransmission`)
  - Executes Modbus polling loops for all 7 registers
  - Decodes responses and formats structured JSON strings
  - Exposes `get_soil_data` to RouterBridge via `Bridge.provide()`

### `main.py`
- **Role:** Linux / Qualcomm MPU Python application
- **Responsibilities:**
  - Invokes `Bridge.call("get_soil_data")` via `arduino.app_utils`
  - Receives JSON telemetry string from MCU
  - Deserializes string using `json.loads()`
  - Handles JSON decoding errors and logs telemetry output

---

## 11. IMPLEMENTATION DEVELOPMENT PATH

### Step 1 — Baseline Extraction
The working standalone PC script (`jxbs_test.py`) served as ground truth.
Extracted settings:
- Slave ID `0x01`
- 9600 baud rate (8-N-1)
- Modbus Function Code 03
- Register addresses (`0x0006`, `0x0012-0x0015`, `0x001E-0x0020`)
- Register scaling factors
- Communication timing behavior

### Step 2 — Architecture Mapping
The PC architecture was translated to the dual-core UNO Q platform:
- The real-time Modbus RTU layer, UART handling, and MAX485 pin toggling were placed on the **STM32 MCU** (which owns hardware UART timing).
- The high-level telemetry consumer and application logic remained on the **Qualcomm MPU Linux Python environment**.

### Step 3 — RouterBridge Integration
Connected MCU and MPU layers using native IPC:
- `STM32` → `Bridge.provide("get_soil_data", get_soil_data)`
- `Linux Python` → `Bridge.call("get_soil_data")`

### Step 4 — Iterative Validation
1. Validated basic bridge telemetry using a partial register subset (Moisture, Temp, N, P, K).
2. Confirmed JSON string transport and Python deserialization stability.
3. Expanded firmware polling to include pH (`0x0006`) and EC (`0x0015`).
4. Verified end-to-end telemetry across all 7 parameters.

---

## 12. VERIFICATION RESULT

Final result:
```text
🟢 PASS
```

The entire hardware and communication chain has been end-to-end verified:
```text
JXBS sensor
      ↓
RS485 A/B
      ↓
MAX485
      ↓
STM32U585 Serial1
      ↓
Modbus RTU
      ↓
Register decoding
      ↓
JSON
      ↓
RouterBridge
      ↓
QRB2210 Linux
      ↓
Python
      ↓
Live telemetry
```

---

## 13. WHAT THIS TEST PROVES

- JXBS sensor communicates reliably through the MAX485 module.
- UNO Q STM32 hardware UART (`Serial1`) successfully interfaces with MAX485.
- GPIO Pin 7 effectively manages RS485 transmit/receive direction control.
- Embedded Modbus RTU polling operates accurately on the MCU.
- All seven sensor registers are successfully read and decoded.
- Unit scaling factors are correctly applied.
- STM32 constructs valid structured JSON payloads.
- RouterBridge reliably transfers telemetry from STM32 to Linux MPU.
- Python application successfully parses and displays live sensor telemetry.

---

## 14. WHAT THIS TEST DOES NOT PROVE

This hardware integration test does **NOT** prove:
- Agronomic measurement accuracy or field calibration.
- Soil sensor accuracy across different soil types or moisture extremes.
- Long-term environmental durability or weatherproofing.
- Field deployment electrical noise immunity.
- GPS integration.
- TFT display integration.
- Full FieldSense V1 system integration.

*(These items will be evaluated in subsequent dedicated testing phases.)*

---

## 15. FINAL STATUS

```text
JXBS-3001-TR + MAX485 + Arduino UNO Q

Integration Status:
🟢 VERIFIED

Communication:
🟢 PASS

Modbus:
🟢 PASS

Direction Control:
🟢 PASS

7-Parameter Telemetry:
🟢 PASS

RouterBridge:
🟢 PASS

Linux Python:
🟢 PASS
```

> This is the first verified FieldSense V1 physical integration path. The next peripherals can now be integrated one at a time using the same isolated-validation methodology.
