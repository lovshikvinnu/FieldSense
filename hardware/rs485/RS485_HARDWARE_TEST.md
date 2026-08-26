# RS485 Hardware Test Methodology Documentation

## 1. Component

* **Module:** MAX485 RS485 Interface Module (`HW-097`)
* **Transceiver IC:** `MAX485CSA +DNHK` (SOIC-8)
* **Status:** `VERIFIED — Bench Verification Complete`

---

## 2. Objective

The objective of this testing was to independently verify the bi-directional communication capabilities of the MAX485 interface module (`HW-097`) under physical bench conditions prior to FieldSense microcontroller integration. This includes validating TTL-to-RS485 transmission, RS485-to-TTL reception, explicit manual transceiver direction control (DE/RE), line termination, and raw frame integrity without byte corruption.

---

## 3. Test Architecture

The physical test bench configuration utilized two independent USB interfaces connected to a host Windows computer to allow loopback and multi-port verification:

```text
Windows Laptop
     │
     ├── COM10
     │     │
     │     ▼
     │   CH340 USB-UART
     │     │
     │     ▼
     │   MAX485 DI / RO
     │
     └── COM8
           │
           ▼
       FT232 USB-RS485
           │
           ▼
         A / B
```

* **Power Supply:** 5.0 V DC applied to MAX485 VCC with common GND across adapters.
* **TTL-Side Interface (COM10):** CH340 USB-to-UART adapter connected to MAX485 DI (Data In) and RO (Receive Out). Handshake signals disabled (`xonxoff=False`, `rtscts=False`, `dsrdtr=False`).
* **Differential-Side Interface (COM8):** FT232 USB-to-RS485 converter connected directly to differential lines A and B.

---

## 4. Hardware Used

| Item | Component / Part Number | Description / Role |
| :--- | :--- | :--- |
| Interface Module | MAX485 Module (`HW-097`) | RS485 Transceiver Breakout Board |
| Transceiver IC | `MAX485CSA +DNHK` | Low-power RS485 transceiver in SOIC-8 package |
| USB-UART Adapter | CH340 USB-to-TTL | TTL serial adapter for COM10 (transceiver logic side) |
| USB-RS485 Adapter | FT232 USB-to-RS485 | Hardware RS485 bus adapter for COM8 (differential side) |
| Host Computer | Windows Laptop | Running python serial verification scripts |
| Power Supply | Bench 5V DC | Supplies VCC for MAX485 module |

---

## 5. Wiring / Connections

### MAX485 Module Connections

```text
[ CH340 USB-UART (COM10) ]
  TXD ──────────────> MAX485 DI  (Data In)
  RXD <────────────── MAX485 RO  (Receive Out)
  5V  ──────────────> MAX485 VCC (5.0 V DC)
  GND ──────────────> MAX485 GND (Common Ground)

[ Transceiver Direction Control ]
  5V  ──────────────> DE (Driver Enable - HIGH for TX)
  5V  ──────────────> RE (Receiver Enable - HIGH tri-states RX for TX)
  GND ──────────────> DE/RE (LOW for RX mode)

[ FT232 USB-RS485 (COM8) ]
  A   ──────────────> MAX485 A (Non-inverting line)
  B   ──────────────> MAX485 B (Inverting line)
```

### PCB Physical Verification

Inspection of the MAX485 breakout board confirmed the following components onboard:
* **IC Marking:** `MAX485CSA +DNHK` SOIC-8 IC.
* **Logic Pins:** RO, RE, DE, DI headers present.
* **Bus Terminals:** A, B screw terminals / headers.
* **Termination Resistor (R7):** 120 Ω bus termination resistor installed across A/B.
* **Bus Bias Resistors (R5/R6):** 20 kΩ bus pull-up / pull-down resistors present.
* **Logic Pull-up Resistors (R1–R4):** 10 kΩ resistors present on logic inputs.

---

## 6. Software / Tools

* **Python Version:** Python 3.x
* **Serial Library:** `pyserial`
* **Test Scripts:**
  * [`hardware/rs485/rs485_test1.py`](rs485_test1.py) (MAX485 Transmit / Driver Test)
  * [`hardware/rs485/rs485_test2.py`](rs485_test2.py) (MAX485 Receive / Receiver Test)

---

## 7. Configuration

* **Baud Rate:** 9600 bps
* **Data Bits:** 8
* **Parity:** None (N)
* **Stop Bits:** 1
* **Flow Control:** None (Hardware and Software flow control disabled)
* **Transceiver Direction Modes:**
  * **TX Mode (Driver Enabled):** `DE = 5V` (HIGH), `RE = 5V` (HIGH) → Receiver tri-stated.
  * **RX Mode (Receiver Enabled):** `DE = 0V` (LOW), `RE = 0V` (LOW) → Driver disabled.

> [!IMPORTANT]
> The MAX485 (`HW-097`) module does **NOT** feature automatic direction control hardware. Direction pin control (DE/RE) must be managed manually via MCU GPIO pins in the final FieldSense implementation.

---

## 8. Test Procedure

### Test 1 — Transmit / Driver Test (`rs485_test1.py`)

1. Set MAX485 DE and RE pins to HIGH (5.0V) to enable the driver and disable the receiver.
2. Initialize COM10 (CH340 TTL) as transmitter and COM8 (FT232 RS485) as receiver at 9600 8-N-1.
3. Flush input and output buffers on both serial instances.
4. Execute sequence of test payloads (ASCII strings and Modbus RTU query frame) over COM10.
5. Read matching frame byte length from COM8 and evaluate for exact match.

```text
COM10 CH340 TX  ──>  MAX485 DI  ──>  MAX485 DRIVER  ──>  RS485 A/B  ──>  COM8 FT232 RS485
```

### Test 2 — Receive / Receiver Test (`rs485_test2.py`)

1. Set MAX485 DE and RE pins to LOW (0V / GND) to disable the driver and enable the receiver.
2. Initialize COM8 (FT232 RS485) as transmitter and COM10 (CH340 TTL) as receiver at 9600 8-N-1.
3. Flush buffers on both serial instances.
4. Send test payloads (ASCII strings and Modbus RTU response frame) over COM8 onto the RS485 bus.
5. Read matching byte length from COM10 (MAX485 RO pin) and evaluate for exact match.

```text
COM8 FT232 RS485  ──>  RS485 A/B  ──>  MAX485 RECEIVER  ──>  MAX485 RO  ──>  COM10 CH340 RX
```

---

## 9. Raw Test Data / Payloads

### Transmit Test Payloads (`rs485_test1.py`)

1. ASCII Header: `b"HELLO_MAX485\n"`
2. Modbus RTU Query: `01 03 00 1E 00 01 E4 0C` (`b"\x01\x03\x00\x1E\x00\x01\xE4\x0C"`)
3. ASCII Verification: `b"FIELDSENSE_HARDWARE_VERIFIED\n"`

### Receive Test Payloads (`rs485_test2.py`)

1. ASCII Header: `b"MAX485_RECEIVE_TEST\n"`
2. Modbus RTU Response: `01 03 02 00 00 B8 44` (`b"\x01\x03\x02\x00\x00\xB8\x44"`)
3. ASCII Verification: `b"HARDWARE_RX_CONFIRMED\n"`

---

## 10. Results

| Test | Python File | Direction | Payload Type | Result |
| :--- | :--- | :--- | :--- | :--- |
| TX / Driver | `rs485_test1.py` | TTL → RS485 | ASCII & Modbus RTU | **PASS (0 byte errors, Bit-exact match)** |
| RX / Receiver | `rs485_test2.py` | RS485 → TTL | ASCII & Modbus RTU | **PASS (0 byte errors, Bit-exact match)** |

### Verified Summary

* **Driver Verification:** Proved conversion path `TTL UART → MAX485 driver → RS485 A/B`.
* **Receiver Verification:** Proved conversion path `RS485 A/B → MAX485 receiver → TTL UART`.
* **Error Rate:** 0 observed byte errors or framing corruption across all test runs at 9600 baud.

---

## 11. Limitations

* **Bench Setup:** Tested with short cable distance (< 1m). Long cable run termination impedance and noise rejection were not evaluated in this bench setup.
* **Manual Control:** Verification required hardwired high/low control on DE/RE pins.

---

## 12. Integration Notes

When integrating MAX485 into the final FieldSense microcontroller architecture:

```text
MCU GPIO
   ├── DE  (Driver Enable)
   └── RE  (Receiver Enable - Active LOW)
```

1. **Direction Switching Sequence (TX Mode):**
   * Assert DE/RE GPIO to HIGH.
   * Transmit packet over MCU UART.
   * **Wait for UART Transmission Complete flag (Shift Register empty).**
   * Assert DE/RE GPIO to LOW to re-enable receiver mode.

> [!CAUTION]
> Do NOT drop the DE/RE pin to LOW immediately when the software transmit queue/buffer becomes empty. De-asserting direction control before the final bit leaves the UART shift register will truncate the CRC byte and corrupt RS485 communications.

---

## 13. Final Verification Status

`VERIFIED — Bench Verification Complete`
