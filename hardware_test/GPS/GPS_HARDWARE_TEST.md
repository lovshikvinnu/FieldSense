# u-blox NEO-M8N GPS Breakout Hardware Test Methodology Documentation

## 1. Component

* **Module:** u-blox NEO-M8N GPS Breakout Board
* **Board Marking:** `GY-GPSV3-NEO`
* **Transceiver Module IC:** `NEO-M8N-0-10`
* **Status:** `VERIFIED — Bench Characterization Complete`

---

## 2. Objective

The objective of this testing was to evaluate the physical breakout board features, verify 3.3V power and UART communication on COM10, analyze raw NMEA sentence streams and talker IDs, measure satellite acquisition status and HDOP quality metrics, and document stationary position drift under indoor/near-window testing conditions.

---

## 3. Test Architecture

```text
Windows Laptop
      ↓
COM10
      ↓
CH340 USB-UART
      ↓
NEO-M8N
```

* **Power & Data Interface:** CH340 USB-to-UART converter on COM10 supplying 3.3 V DC VCC to module and bridging TTL UART lines (TX/RX).
* **Handshake Settings:** DTR and RTS signals explicitly disabled in test script to prevent hardware reset or flow control interference (`xonxoff=False`, `rtscts=False`, `dsrdtr=False`).

---

## 4. Hardware Used

| Item | Component / Model | Description |
| :--- | :--- | :--- |
| GPS Breakout | `GY-GPSV3-NEO` | Breakout board featuring u-blox `NEO-M8N-0-10` GNSS receiver |
| USB-UART Adapter | CH340 USB-to-TTL | Serial interface on COM10 supplying 3.3V power |
| Antenna | Onboard Ceramic Patch | Ceramic patch antenna connected via U.FL provision |
| Host Computer | Windows Laptop | Running Python serial verification script [`test_gps.py`](file:///C:/Users/lovsh/Desktop/FieldSense/hardware_test/GPS/test_gps.py) |

---

## 5. Wiring / Connections

```text
[ CH340 USB-UART (COM10) ]
  3.3V ──────────────> NEO-M8N VCC (3.3 V DC)
  TXD  ──────────────> NEO-M8N RX  (GPS Receive)
  RXD  <────────────── NEO-M8N TX  (GPS Transmit)
  GND  ──────────────> NEO-M8N GND (Common Ground)
```

### Breakout Board Physical Verification

Inspection of the `GY-GPSV3-NEO` breakout board confirmed:
* **Pin Header:** 4-pin header (VCC, RX, TX, GND). *No dedicated PPS (Pulse Per Second) pin exposed on this breakout.*
* **Power Regulation:** Onboard 3.3V LDO regulator.
* **Backup Battery:** Onboard rechargeable RTC battery for warm/hot restart capability.
* **Non-volatile Storage:** Onboard EEPROM for configuration saving.
* **Antenna Subsystem:** Mounted ceramic patch antenna with U.FL connector provision.

---

## 6. Software / Tools

* **Python Script:** [`hardware_test/GPS/test_gps.py`](file:///C:/Users/lovsh/Desktop/FieldSense/hardware_test/GPS/test_gps.py)
* **Python Libraries:** `serial` (`pyserial`), `time`

---

## 7. Configuration

* **Baud Rate:** 9600 bps
* **Data Bits:** 8
* **Parity:** None
* **Stop Bits:** 1
* **Flow Control:** None (DTR/RTS disabled)
* **Native Output Refresh Rate:** ~1 Hz (1 NMEA sentence set per second)

---

## 8. Test Procedure

1. Connect `GY-GPSV3-NEO` breakout board to CH340 USB-UART adapter supplying 3.3V VCC and ground.
2. Connect COM10 to host PC and position ceramic antenna near a window for satellite visibility.
3. Execute Python verification script `test_gps.py` to sample 30 valid `$GNGGA` / `$GPGGA` sentences.
4. Filter incoming NMEA sentences for valid fix quality indicator (`parts[6]` in `'1'`, `'2'`).
5. Extract and parse parameters: Satellite Count, HDOP (Horizontal Dilution of Precision), Latitude, Longitude, Altitude, and system timestamp.
6. Calculate inter-sample update intervals and log stationary drift parameters over time.

---

## 9. Raw Test Data / Payloads

### Observed NMEA Sentence Families

During bench testing, the following sentence families were continuously output by the module:
* `$GNGGA`: Global Positioning System Fix Data (Multi-GNSS)
* `$GNRMC`: Recommended Minimum Specific GNSS Data
* `$GNGSA`: GNSS DOP and Active Satellites
* `$GPGSV`: GPS Satellites in View
* `$GLGSV`: GLONASS Satellites in View

> [!IMPORTANT]
> The module outputs sentence prefixes beginning with `$GN` (e.g., `$GNGGA`, `$GNRMC`) rather than solely `$GP`. This occurs because the u-blox NEO-M8N operates in concurrent multi-constellation mode (combining GPS + GLONASS).

---

## 10. Results

* **Fix Status:** Autonomous 3D Fix established.
* **Constellation Mode:** Concurrent GPS + GLONASS operation.
* **Satellites in Use / Visible:** 8–9 satellites continuously used in navigation solution (~12 visible in view).
* **HDOP Quality:** Approximately 4.82 – 5.10 in indoor/near-window testing environment.
* **Stationary Position Drift (Over ~2 minutes):**
  * Latitude drift: ~5.5 meters
  * Longitude drift: ~3.3 meters
* **Native NMEA Output Rate:** Approximately 1 Hz (1 sample per second).

> [!NOTE]
> The ~4.12 s average sample interval recorded in `test_gps.py` represents the Python script's filtering/logging loop delay, **not** the native NMEA stream output rate from the NEO-M8N module (which was verified at ~1 Hz).

---

## 11. Limitations

* Indoor / near-window placement degrades HDOP (~4.82–5.10) compared to open-sky conditions (< 2.0).
* Observed stationary position drift (~5.5 m lat, ~3.3 m lon) reflects indoor multipath reflections and satellite geometry, not absolute open-sky receiver precision.
* The 4-pin breakout header does not expose the hardware PPS (Pulse Per Second) signal pin.

---

## 12. Integration Notes

* In FieldSense software parser, check for both `$GNGGA` and `$GPGGA` prefixes when extracting fix coordinates.
* Ensure baud rate is set to 9600 8-N-1 with flow control disabled.
* Place GPS patch antenna with an unobstructed sky view in field deployment for optimal HDOP (< 1.5).

---

## 13. Final Verification Status

`VERIFIED — Bench Characterization Complete`
