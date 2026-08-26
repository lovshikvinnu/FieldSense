# FieldSense — NEO-M8N GPS + Arduino UNO Q UART Integration Documentation

## ROLE

Act as the repository documentation engineer for FieldSense.

The NEO-M8N GPS has now been successfully integrated with the Arduino UNO Q using the UNO Q's physical `Serial1` UART and the internal RouterBridge between the STM32 MCU and Qualcomm Linux MPU.

Create a technical Markdown document describing exactly how this integration was performed and verified.

This is an actual FieldSense V1 hardware integration record, NOT a generic GPS tutorial.

---

# EXISTING FOLDER

The GPS integration folder has already been created:

```text
hardware/
└── GPS_UART_Serial1/
    ├── main.py
    └── sketch.ino
```

The files:

```text
main.py
sketch.ino
```

will be added separately.

Do NOT create, modify, rename, or overwrite those files.

---

# DOCUMENT TO CREATE

Create:

```text
hardware/gps_UART_Serial1/NEO_M8N_UNOQ_UART_INTEGRATION.md
```

If a suitable documentation file already exists, update it instead of creating a duplicate.

---

# OBJECTIVE

Document the successful verification of this complete pipeline:

```text
NEO-M8N GPS
     ↓
Physical UART
     ↓
UNO Q STM32 MCU
     ↓
NMEA parsing
     ↓
RouterBridge
     ↓
Qualcomm Linux MPU
     ↓
Python
     ↓
GPS telemetry
```

Final status:

```text
VERIFIED — Core Pipeline Complete
```

---

# 1. ARCHITECTURE STRATEGY

Document the asymmetric dual-core architecture used for this integration.

### STM32 MCU

The STM32 handles:

* Physical UART communication
* Continuous NMEA reception
* NMEA sentence filtering
* Lightweight NMEA parsing
* GPS data staging
* RouterBridge data provider

The MCU handles the real-time UART stream so the Linux side does not need to directly manage the continuous serial stream.

### Qualcomm Linux MPU

The Linux side handles:

* RouterBridge polling
* Python execution
* Retrieval of structured GPS data
* Telemetry output/logging

Architecture:

```text
STM32 MCU
  ↓
Physical GPS UART
  ↓
NMEA acquisition
  ↓
NMEA parsing
  ↓
Structured GPS payload
  ↓
Bridge.provide()
  ↓
RouterBridge
  ↓
Bridge.call()
  ↓
Linux Python
```

---

# 2. HARDWARE CONFIGURATION

Document the actual tested hardware:

### GPS

```text
Module: NEO-M8N
Interface: UART
Baud: 9600 bps
```

### UNO Q

```text
UART: Serial1
```

### Physical connections

```text
GPS TX  ─────────→ UNO Q Pin 0 (RX)

GPS RX  ─────────→ UNO Q Pin 1 (TX)

GPS VCC ─────────→ UNO Q 5V

GPS GND ─────────→ UNO Q GND
```

Clearly identify:

```text
GPS TX → UNO Q RX
GPS RX → UNO Q TX
```

Do not reverse this in the documentation.

These are the actual integration-test connections.

---

# 3. POWER CONFIGURATION

Document the actual tested power arrangement:

```text
UNO Q 5V
   ↓
NEO-M8N VCC

UNO Q GND
   ↓
NEO-M8N GND
```

Do not invent current measurements or power-consumption values.

---

# 4. SOFTWARE FILES

Document the purpose of the two integration files.

### `sketch.ino`

Runs on the UNO Q STM32 MCU.

Responsibilities:

* Initialize `Serial1`
* Receive NMEA data
* Filter GPS sentences
* Parse GGA information
* Store structured GPS data
* Expose GPS data through RouterBridge

### `main.py`

Runs on the Qualcomm Linux MPU.

Responsibilities:

* Initialize the Linux-side environment
* Call the RouterBridge GPS provider
* Poll every 1 second
* Retrieve GPS telemetry
* Print telemetry to the console

Do not modify these files.

---

# 5. MCU UART INITIALIZATION

Document:

```text
Serial1
9600 baud
```

The baud rate matches the NEO-M8N default configuration used during the integration test.

The MCU continuously reads the incoming UART stream.

---

# 6. NMEA DATA ACQUISITION

The MCU receives standard ASCII NMEA sentences from the GPS.

The integration specifically filters for:

```text
$GNGGA
```

and:

```text
$GPGGA
```

Do not claim that every possible NMEA sentence is parsed.

The integration parser is specifically based on GGA data.

---

# 7. GGA PARSER

Document the lightweight parser:

```text
parse_gga_sentence
```

It extracts:

* Latitude
* Latitude direction
* Longitude
* Longitude direction
* Satellite count
* HDOP
* Fix status

The parser operates directly on the NMEA comma-separated fields.

The implementation intentionally avoids a large external GPS library.

Do not add functionality that was not actually implemented.

---

# 8. DATA STAGING

Document that the MCU converts the extracted information into a standardized string format:

```text
FIX_OK,Lat,Lon,Sats,HDOP
```

Example structure:

```text
FIX_OK,1734.18667N,07825.47349E,Sats:06,HDOP:1.61
```

The formatted result is stored by the MCU for retrieval through RouterBridge.

---

# 9. ROUTERBRIDGE

Document the IPC path:

```text
STM32
   ↓
Bridge.provide("get_gps_data")
   ↓
RouterBridge
   ↓
Bridge.call("get_gps_data")
   ↓
Linux Python
```

The function exposed to Linux is:

```text
get_gps_data
```

The Linux side requests the latest staged GPS telemetry.

---

# 10. LINUX PYTHON POLLING

Document that `main.py` performs synchronous polling:

```text
Every 1000 ms
        ↓
Bridge.call("get_gps_data")
        ↓
Receive GPS telemetry
        ↓
Print to console
```

Telemetry is prefixed with:

```text
[GPS TELEMETRY]
```

---

# 11. VERIFIED OUTPUT

Include the actual captured output:

```text
[GPS TELEMETRY] | FIX_OK,1734.18667N,07825.47349E,Sats:06,HDOP:1.61
[GPS TELEMETRY] | FIX_OK,1734.18754N,07825.47225E,Sats:06,HDOP:1.60
```

Explain that this demonstrates:

* GPS data reached the physical UART
* STM32 received the NMEA stream
* GGA data was parsed
* A valid fix was detected
* Latitude was extracted
* Longitude was extracted
* Satellite count was extracted
* HDOP was extracted
* Data crossed the RouterBridge
* Linux Python received the telemetry
* Repeated polling produced updated coordinates

Do not claim centimeter-level accuracy or precision synchronization.

---

# 12. END-TO-END VERIFICATION

Create a clear verification chain:

```text
┌──────────────────────┐
│ NEO-M8N GPS          │
│ NMEA @ 9600          │
└──────────┬───────────┘
           │ UART
           ▼
┌──────────────────────┐
│ UNO Q STM32          │
│ Serial1              │
│ GGA parsing          │
└──────────┬───────────┘
           │
           │ Bridge.provide()
           ▼
┌──────────────────────┐
│ RouterBridge         │
└──────────┬───────────┘
           │
           │ Bridge.call()
           ▼
┌──────────────────────┐
│ UNO Q Linux / Python │
│ main.py              │
└──────────┬───────────┘
           │
           ▼
    GPS TELEMETRY
```

---

# 13. TEST RESULT TABLE

Include:

| Test | Result |
| --- | --- |
| GPS power | PASS |
| Physical UART connection | PASS |
| Serial1 @ 9600 | PASS |
| NMEA reception | PASS |
| GGA detection | PASS |
| 3D fix acquisition | PASS |
| Latitude extraction | PASS |
| Longitude extraction | PASS |
| Satellite count extraction | PASS |
| HDOP extraction | PASS |
| RouterBridge transfer | PASS |
| Linux Python retrieval | PASS |
| Repeated telemetry polling | PASS |

Only include results supported by the provided integration evidence.

---

# 14. WHAT THIS TEST PROVES

This integration verifies:

* NEO-M8N can communicate with UNO Q through physical UART
* UNO Q `Serial1` can receive GPS NMEA data
* STM32 can continuously process the incoming stream
* GGA sentences can be parsed without an external GPS library
* GPS fix information can be extracted
* Structured GPS telemetry can be staged on the MCU
* RouterBridge can transport the data to Linux
* Python can retrieve the telemetry
* Repeated polling produces live GPS data

---

# 15. WHAT THIS TEST DOES NOT PROVE

Do NOT claim this test proves:

* GPS accuracy certification
* RTK-level positioning
* Differential GPS
* PPS timing
* Long-term GPS stability
* Outdoor field accuracy
* Final FieldSense UI integration
* GPS + soil sensor simultaneous operation
* Full system integration

Those require separate tests.

---

# 16. INTEGRATION BOUNDARY

Clearly state that this is:

```text
V1 Physical Integration — GPS
```

It verifies:

```text
GPS → UNO Q → RouterBridge → Linux/Python
```

It does not yet combine the GPS with the other FieldSense peripherals.

---

# 17. FINAL STATUS

End the document with:

```text
Component:
NEO-M8N GPS

Interface:
UNO Q Serial1 UART

Baud:
9600 bps

Integration:
GPS → STM32 → RouterBridge → Linux Python

Status:
🟢 VERIFIED — Core Pipeline Complete
```
