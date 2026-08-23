# JXBS-3001-TR Soil Sensor Hardware Test Methodology Documentation

## 1. Component

* **Sensor Model:** JXBS-3001-TR 7-in-1 Integrated Soil Sensor
* **Measured Parameters:** Soil Moisture, Temperature, Conductivity (EC), pH, Nitrogen (N), Phosphorus (P), Potassium (K)
* **Status:** `VERIFIED — Bench Verification Complete`

---

## 2. Objective

The objective of this test was to establish hardware layer communication with the JXBS-3001-TR 7-in-1 soil sensor via Modbus RTU over RS485, verify register addresses and response parsing using custom Python scripts, validate CRC calculation and scaling formulas, and observe real-time parameter changes upon altering sensor physical position.

---

## 3. Test Architecture

```text
Windows Laptop
      ↓
COM8
      ↓
FT232 USB-RS485
      ↓
RS485 A/B
      ↓
JXBS-3001-TR
      ↓
External 12–24 V DC supply
```

* **Interface Adapter:** FT232 USB-to-RS485 adapter on COM8 connected directly to sensor A/B lines.
* **Power Source:** External 12 V DC power supply adapter connected to sensor power leads. Measured supply voltage during bench test was approximately 12.24 V DC.

---

## 4. Hardware Used

| Item | Component / Model | Description |
| :--- | :--- | :--- |
| Sensor | JXBS-3001-TR | 7-in-1 Soil Sensor (Moisture, Temp, EC, pH, N, P, K) |
| Bus Adapter | FT232 USB-to-RS485 | Hardware converter on host COM8 |
| Power Supply | 12 V DC Adapter | External DC power source (Measured: 12.24 V DC) |
| Test Medium | Soil Pot | Bench soil container for probe insertion testing |
| Host Computer | Windows Laptop | Running serial inspection and python verification scripts |

---

## 5. Wiring / Connections

```text
[ Power Adapter ]
  V+ (12.24V DC) ───────────> Brown Wire  (Power +)
  V- (GND)       ───────────> Black Wire  (Power - / GND)

[ FT232 USB-RS485 (COM8) ]
  RS485 A        ───────────> Yellow Wire (RS485 A / Data+)
  RS485 B        ───────────> Blue Wire   (RS485 B / Data-)
```

---

## 6. Software / Tools

* **Modbus Diagnostic Tool:** Modbus Poll (used initially to verify basic communication, confirm slave ID, and audit register mapping).
* **Python Script:** [`hardware_test/soil sensor/jxbs_test.py`](file:///C:/Users/lovsh/Desktop/FieldSense/hardware_test/soil%20sensor/jxbs_test.py)
* **Python Libraries:** `serial` (`pyserial`), `time`

---

## 7. Configuration

* **Baud Rate:** 9600 bps
* **Data Bits:** 8
* **Parity:** None
* **Stop Bits:** 1
* **Flow Control:** None
* **Modbus Slave ID:** `0x01` (Default)
* **Modbus Function Code:** `0x03` (Read Holding Registers)

---

## 8. Test Procedure

1. Wire JXBS-3001-TR to external 12V DC supply and connect RS485 lines (Yellow/Blue) to FT232 USB adapter.
2. Verify hardware communication baseline using Modbus Poll diagnostic utility on COM8 at 9600 8-N-1.
3. Launch custom Python test script `jxbs_test.py`.
4. Script sequentially formats 8-byte Modbus RTU query frames for each of the 7 parameter registers.
5. Transmit frame over serial, await 7-byte response, calculate 16-bit CRC-16-MODBUS checksum (`0xA001` polynomial), and compare against received CRC.
6. Extract raw 16-bit register values, apply parameter scaling factors, and output formatted decoded physical values.
7. Perform physical validation by changing the sensor probe insertion depth/location within the soil container and taking repeated measurements.

---

## 9. Raw Test Data / Payloads

### Verified Register Mapping & Scaling

| Parameter | Register Address | Modbus Read Request (Hex) | Scaling Factor | Unit |
| :--- | :--- | :--- | :--- | :--- |
| **pH** | `0x0006` | `01 03 00 06 00 01 64 0B` | Raw / 100 | pH |
| **Moisture** | `0x0012` | `01 03 00 12 00 01 24 0F` | Raw / 10 | %RH |
| **Temperature** | `0x0013` | `01 03 00 13 00 01 75 CF` | Raw / 10 | °C |
| **Conductivity (EC)** | `0x0015` | `01 03 00 15 00 01 95 CD` | Raw / 1 | µS/cm |
| **Nitrogen (N)** | `0x001E` | `01 03 00 1E 00 01 E4 0C` | Raw / 1 | mg/kg |
| **Phosphorus (P)** | `0x001F` | `01 03 00 1F 00 01 B5 CC` | Raw / 1 | mg/kg |
| **Potassium (K)** | `0x0020` | `01 03 00 20 00 01 85 C0` | Raw / 1 | mg/kg |

### Sample Nitrogen Query & Response Frame Structure

* **8-Byte Request Frame:**
  `01 03 00 1E 00 01 E4 0C`
  * `01`: Slave Address
  * `03`: Function Code (Read Holding Registers)
  * `00 1E`: Register Address (`0x001E` - Nitrogen)
  * `00 01`: Number of Registers requested (1 register = 2 bytes)
  * `E4 0C`: Modbus CRC-16 Checksum (Low byte first)

* **7-Byte Response Frame Structure:**
  `01 03 02 DATA_H DATA_L CRC_L CRC_H`
  * Byte 0: `01` (Slave ID)
  * Byte 1: `03` (Function Code)
  * Byte 2: `02` (Byte Count)
  * Byte 3: `DATA_H` (High Byte of 16-bit value)
  * Byte 4: `DATA_L` (Low Byte of 16-bit value)
  * Byte 5: `CRC_L` (CRC Low Byte)
  * Byte 6: `CRC_H` (CRC High Byte)

---

## 10. Results

* **Communication Status:** 100% PASS — Response length verified at 7 bytes per register query with CRC verification passing consistently.
* **Live Reading Verification:** When sensor probe position was changed in the soil container, observed live sensor readings responded dynamically to physical position changes.
* **Parameter Decoding:** Raw 16-bit register extraction and scaling functions in `jxbs_test.py` cleanly decoded all 7 parameters.

---

## 11. Limitations

> [!NOTE]
> **Functional vs Calibration Verification:** This test verifies hardware communication, protocol compliance, frame CRC validation, and functional sensor output responsiveness. It does **NOT** constitute formal laboratory calibration against reference standards.

---

## 12. Integration Notes

* Ensure external supply stays within 12–24 V DC (measured 12.24 V DC working).
* When embedding in FieldSense pipeline, query registers sequentially with a 200 ms inter-frame delay to prevent RS485 bus collision or sensor processing timeouts.

---

## 13. Final Verification Status

`VERIFIED — Bench Verification Complete`
