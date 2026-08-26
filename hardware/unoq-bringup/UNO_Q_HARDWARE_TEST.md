# Arduino UNO Q Hardware Test Procedure & Verification Documentation

## Component Overview

* **Board Model:** Arduino UNO Q
* **MPU System:** Qualcomm QRB2210 System-on-Chip (SoC) running Debian Linux
* **MCU Subsystem:** STM32U585 Microcontroller Unit (MCU) running Arduino Firmware
* **Test Scope:** Independent Component Verification (Bench Test)
* **Status:** `VERIFIED — Component Bench Verification Complete`

---

## Objective

The objective of this procedure is to verify the core hardware operation and communication features of the **Arduino UNO Q** in isolation. This procedure validates power/boot stability, Linux MPU functionality, STM32 MCU code execution, native MPU ↔ MCU RouterBridge IPC, physical UART hardware loopback with disconnect detection, and host logging prior to FieldSense system-level integration.

> [!NOTE]
> This document specifies **component-level bench verification** for the Arduino UNO Q only. System-level integration (sensors, displays, transceivers) is covered in subsequent integration phases.

---

## Test Architecture

```text
Arduino UNO Q
│
├── Qualcomm QRB2210 MPU
│      └── Debian Linux OS
│             └── Python Execution (`test_q.py`)
│
└── STM32U585 MCU
       └── Arduino Firmware Execution (`test_q.ino`)
```

---

## Pre-requisites & File Layout

The following test script pair is dedicated to this verification step:

```text
hardware/
└── arduino uno q/
    ├── test_q.py                  # Python monitoring & bridge test script (Linux MPU side)
    ├── test_q.ino                 # Arduino firmware sketch (STM32 MCU side)
    └── UNO_Q_HARDWARE_TEST.md     # Hardware test procedure & execution record
```

---

## Step-by-Step Test Plan

### TEST 01 — Physical Inspection

**Purpose:** Perform visual and mechanical verification of the Arduino UNO Q board prior to applying power.

**Procedure:**
1. Inspect the Arduino UNO Q PCB for visible manufacturing defects, solder bridges, or physical damage.
2. Confirm main system components: Qualcomm QRB2210 MPU and STM32U585 MCU architecture.
3. Locate USB-C power/data port and board status LEDs.
4. Locate exposed expansion headers and relevant GPIO/UART headers.

**Verification Checklist:**
* Board identification and markings confirmed.
* USB-C port physical integrity verified.
* Connectors and header pins intact.
* No short circuits or physical anomalies observed.

*(Note: Do not assume pin assignments that have not been explicitly verified on the physical hardware.)*

---

### TEST 02 — Power & Boot

**Purpose:** Verify stable board power delivery, successful boot sequencing, and Debian Linux startup without brownouts or boot loops.

**Procedure:**
1. Connect the Arduino UNO Q to a reliable power source via the USB-C port.
2. Observe status LEDs during initial power-up.
3. Monitor system boot sequence and allow Debian Linux to complete initial boot.
4. Confirm system stability over an extended period.

**Record:**
* **Power Source:** USB-C (5V DC)
* **Boot Result:** Stable startup
* **OS Availability:** Debian Linux prompt / system active
* **Abnormal Behavior:** None observed

**Expected Result:**
`PASS — Stable boot`

---

### TEST 03 — Linux / MPU Verification

**Purpose:** Verify that the Qualcomm QRB2210 MPU and Linux operating system are fully operational, and demonstrate Python script execution.

**Procedure:**
1. Access the Debian Linux command line environment on the MPU.
2. Execute system identification command:
   ```bash
   uname -a
   ```
3. Execute standard Python interpreter check and execute the project test script [`test_q.py`](file:///C:/Users/lovsh/Desktop/FieldSense/hardware/arduino%20uno%20q/test_q.py).

**Verification Criteria:**
* `uname -a` returns valid Linux kernel information for the QRB2210 architecture.
* Python runtime environment executes scripts normally on the Linux core.

---

### TEST 04 — STM32 MCU Verification

**Purpose:** Verify firmware upload and execution on the STM32U585 microcontroller core.

**Procedure:**
1. Open Arduino App Lab (or standard Arduino IDE setup configured for UNO Q).
2. Connect to the board and compile/upload [`test_q.ino`](file:///C:/Users/lovsh/Desktop/FieldSense/hardware/arduino%20uno%20q/test_q.ino).
3. Confirm firmware upload completes successfully without flashing errors.
4. Verify execution of uploaded code on the STM32 MCU core.

**Record:**
* **Board Recognition:** Arduino App Lab / IDE recognizes UNO Q.
* **Firmware Upload:** Successfully uploaded `test_q.ino`.
* **Execution:** STM32 MCU code active and executing.

---

### TEST 05 — MPU ↔ MCU RouterBridge

**Purpose:** Validate the native software Inter-Process Communication (IPC) path between the Linux MPU core and the STM32 MCU core using RouterBridge.

**Communication Path:**
```text
Linux Python (`test_q.py`)
     ↓
Bridge.call()
     ↓
RouterBridge Subsystem
     ↓
STM32 MCU (`test_q.ino`)
     ↓
Bridge.provide()
     ↓
Structured Response
     ↓
Linux Python Output
```

**Procedure:**
1. Configure `test_q.ino` on the STM32 MCU to provide a structured response via `Bridge.provide()`.
   * *Example Test Payload:* `moisture = 45` *(Note: Used strictly as a structured test payload, not a physical sensor reading).*
2. Execute `test_q.py` on the Linux MPU side calling `Bridge.call()`.
3. Verify request transmission from Python to MCU.
4. Verify structured response transmission from MCU back to Python.
5. Perform repeated polling to ensure bridge stability over time.

> [!IMPORTANT]
> The RouterBridge IPC channel is a software bridge between the MPU host OS and MCU firmware. Do **NOT** confuse or describe this test as a physical UART wiring test.

---

### TEST 06 — Physical UART Loopback

**Purpose:** Test the physical hardware UART serial transceivers and electrical TX/RX paths using an isolated hardware loopback jumper.

**Loopback Wiring Diagram:**
```text
UNO Q UART TX
      │
      └──────────┐
                 │
            jumper wire
                 │
      ┌──────────┘
      │
UNO Q UART RX
```

*(Note: Use the exact verified physical UART pins designated during hardware testing. Do not invent unverified pin numbers).*

**Procedure:**
1. Attach a physical jumper wire between the UNO Q hardware UART TX pin and RX pin.
2. Execute `test_q.ino` firmware programmed to transmit a known test pattern repeatedly over the physical UART port.
3. Verify whether transmitted serial data is received back on the RX pin.
4. Disconnect the physical jumper wire while the test is running.
5. Observe and record state transition.

**Expected Behavior:**
```text
Jumper Wire Connected:
PASS: TX/RX WORKING

Jumper Wire Removed:
FAIL: DISCONNECTED
```

---

### TEST 07 — UART Data Integrity

**Purpose:** Verify byte-for-byte data fidelity over the physical UART hardware loopback path under continuous transmission.

**Procedure:**
1. With physical UART loopback jumper connected, transmit known binary/text payload via `test_q.ino`.
2. Compare transmitted byte stream (TX) against received byte stream (RX).
3. Validate payload accuracy across multiple consecutive iterations.

**Verification Criteria:**
* TX data matches RX data byte-for-byte.
* Zero frame errors, parity errors, or data corruption detected during continuous polling.
* Actual payload defined in `test_q.ino` verified.

---

### TEST 08 — Python Logging

**Purpose:** Verify end-to-end logging of UNO Q hardware and communication states through Python scripts running on Linux to the terminal output.

**Data Flow:**
```text
STM32 Hardware Core
      ↓
UART / Bridge Path
      ↓
Linux MPU Core
      ↓
Python Script (`test_q.py`)
      ↓
Terminal Output / Console Log
```

**Procedure:**
1. Launch `test_q.py` on the Linux MPU core.
2. Monitor real-time terminal output logs.
3. Confirm clean output formatting, timestamping (if applicable), and accurate reporting of MCU states.

---

### TEST 09 — Disconnect Detection

**Purpose:** Confirm that the physical UART hardware monitoring dynamically reflects physical link disconnection and reconnection events rather than outputting a static software mock.

**Procedure:**
1. Connect physical loopback jumper wire — observe terminal state: `PASS`.
2. Disconnect physical loopback jumper wire — observe terminal state: `FAIL`.
3. Reconnect physical loopback jumper wire — observe terminal state: `PASS`.

**Verification Criteria:**
* State change explicitly corresponds to real-time physical wire connection status.
* Demonstrates live hardware monitoring on the physical electrical interface.

---

## Test Result Table

| Test | Purpose | Result | Evidence |
| :--- | :--- | :--- | :--- |
| **Physical inspection** | Board identification & visual check | PASS | Physical PCB verified; main SoC/MCU components intact |
| **Power / boot** | Stable startup without boot loops | PASS | USB-C power stable; Debian Linux booted cleanly |
| **Linux / MPU** | OS execution & Python environment | PASS | `uname -a` returns QRB2210 Linux; Python script execution verified |
| **STM32 MCU** | Firmware execution on microcontroller | PASS | App Lab recognized board; `test_q.ino` uploaded and executed |
| **RouterBridge** | MPU ↔ MCU software IPC | PASS | `Bridge.call()` / `Bridge.provide()` verified (`moisture = 45` test payload) |
| **UART loopback** | Physical TX/RX electrical verification | PASS | Hardware TX-to-RX jumper loopback operational |
| **Data integrity** | Byte-for-byte accuracy check | PASS | Transmitted and received serial payloads match exactly |
| **Python logging** | Terminal logging on Linux MPU | PASS | Real-time console monitoring via `test_q.py` verified |
| **Disconnect detection** | Physical link state dynamic response | PASS | Dynamic transition: Connected (PASS) → Disconnected (FAIL) → Reconnected (PASS) |

---

## Key Technical Distinctions

To ensure clarity in technical reporting, maintain explicit distinctions between the following three communication and execution paths:

### 1. RouterBridge IPC
```text
Python (`test_q.py`) ──> Bridge.call() ──> RouterBridge ──> STM32 MCU (`test_q.ino`)
```
*Native software IPC framework for high-level MPU-to-MCU messaging over internal SoC inter-processor bridge.*

### 2. Physical UART Interface
```text
STM32 TX Pin ──> Physical Jumper Wire ──> STM32 RX Pin
```
*Physical hardware serial transceiver interface requiring external electrical loopback for hardware verification.*

### 3. Linux MPU Python Execution
```text
Qualcomm QRB2210 ──> Debian Linux OS ──> Python 3 Runtime ──> `test_q.py`
```
*Linux userspace application execution environment host.*

> [!CAUTION]
> Do not claim that successful RouterBridge communication proves physical UART pin functionality, or vice-versa. Each path addresses a distinct hardware/software layer.

---

## Future Integration Note

This document verifies the **Arduino UNO Q component independently** on the test bench.

It does **NOT** cover or imply verification of:
* JXBS Soil Sensor + Arduino UNO Q
* u-blox GPS + Arduino UNO Q
* MAX485 RS485 Transceiver + Arduino UNO Q
* TFT Display + Arduino UNO Q
* Full FieldSense End-to-End System

Integrations of the Arduino UNO Q with external sensors, communication transceivers, and displays belong strictly to the upcoming project milestone:

`V1 Physical Integration`

---

## Final Status

```text
Arduino UNO Q
Status: VERIFIED — Component Bench Verification Complete
```
