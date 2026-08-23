# FieldSense AI — Test & Validation Evidence Record

**STATUS:** DRAFT  
**VERSION:** 0.1  
**LAST UPDATED:** 2026-08-22  
**REGRESSION BASELINE:** 105 tests passing ($100\%$ pass rate in $< 1.0\text{s}$)  
**RELEASE STATUS:** `PHASE_1_RELEASE_READY`  

---

## 1. Executive Test Strategy

The FieldSense AI test suite (`tests/`) enforces 100% regression stability and contract compliance across 17 test modules. Testing is divided into five formal validation tiers:

1. **Unit Tests**: Granular contract verification across domain, input, validation, scoring, spatial, zone, recommendation, presentation, and hardware modules.
2. **Integration Tests**: End-to-end multi-stage pipeline flow verification.
3. **Golden Scenarios**: Synthetic field benchmarks representing standard agricultural field conditions.
4. **Fault Injection Suite**: Graceful degradation testing against noisy sensors, corrupted GPS, sparse grid samples, and serial timeouts.
5. **Demonstration & UI Tests**: Verification of single-file offline HTML/SVG visual dashboard rendering.

---

## 2. Test Execution Baseline Summary

```text
============================== test session starts ==============================
platform win32 -- Python 3.14.0a4, pytest-8.3.4, pluggy-1.5.0
rootdir: C:\Users\lovsh\Desktop\FieldSense
collected 105 items

tests/test_benchmark.py ..                                                [  1%]
tests/test_competition_demo.py ..                                         [  3%]
tests/test_demo.py ..                                                     [  5%]
tests/test_fault_injection.py .....                                       [ 10%]
tests/test_golden_scenarios.py .....                                      [ 15%]
tests/test_hardware.py ........                                           [ 22%]
tests/test_intelligence.py ..........                                     [ 32%]
tests/test_normalization.py .....                                         [ 37%]
tests/test_presentation.py ....                                           [ 41%]
tests/test_recommendations.py .........                                   [ 50%]
tests/test_sample.py .......                                              [ 56%]
tests/test_scoring.py .....                                               [ 61%]
tests/test_sensor.py .........                                            [ 70%]
tests/test_session.py ........                                            [ 77%]
tests/test_spatial.py .......                                             [ 84%]
tests/test_sprint12_hardening.py ...                                      [ 87%]
tests/test_validation.py ..........                                       [ 97%]
tests/test_zones.py ...                                                   [100%]

============================= 105 passed in 0.70s ==============================
```

---

## 3. Formal Test Evidence Register

### Test ID: `TST-001` — Canonical FieldSample Immutability
- **Objective**: Verify that `FieldSample` instances are strictly immutable and reject attribute mutation attempts.
- **Setup**: Instantiate a `FieldSample` object with standard parameter values.
- **Procedure**: Attempt to assign a new value to `sample.nitrogen` at runtime.
- **Expected Result**: Python raises `FrozenInstanceError`.
- **Actual Result**: `FrozenInstanceError` raised as expected.
- **Status**: PASSED
- **Notes**: Core architectural requirement enforcing raw observational data integrity (`D-001`).

---

### Test ID: `TST-002` — Validation Engine Gatekeeper & Sample Rejection
- **Objective**: Verify that out-of-bounds physical metrics (e.g. $\text{pH} = 15.2$, $\text{Moisture} = -5\%$) are tagged `REJECTED` and `pipeline_eligible = False`.
- **Setup**: Create synthetic `FieldSample` containing out-of-bounds pH reading ($15.2$).
- **Procedure**: Process sample through `ValidationEngine.validate_sample()`.
- **Expected Result**: Validation state returns `ValidationState.REJECTED`, `pipeline_eligible` set to `False`, and rejection reason code logged.
- **Actual Result**: Sample marked `REJECTED`, `pipeline_eligible = False`, reason `OUT_OF_BOUNDS`.
- **Status**: PASSED
- **Notes**: Rejected samples remain preserved in `FieldSession.samples` for complete auditability.

---

### Test ID: `TST-003` — Carbon Readiness Proxy Safety Boundary
- **Objective**: Confirm that `CarbonReadinessResult` enforces `decision_support_only = True`, `evidence_level = "LIMITED"`, and outputs explicit missing indicators.
- **Setup**: Execute `IntelligenceEngine.compute_intelligence()` on valid field samples.
- **Procedure**: Inspect returned `carbon_readiness` result object.
- **Expected Result**: `decision_support_only` is `True`, `evidence_level` is `"LIMITED"`, and `missing_indicators` contains `["soil_organic_carbon", "bulk_density", "management_history"]`.
- **Actual Result**: All safety indicators match expected contracts exactly.
- **Status**: PASSED
- **Notes**: Prevents scientific misrepresentation or uncertified carbon credit claims (`D-005`).

---

### Test ID: `TST-004` — Spatial Engine Support Distance Threshold ($100\text{m}$)
- **Objective**: Confirm that grid nodes located $> 100\text{m}$ from the nearest valid sample point return `value = None` (unsupported).
- **Setup**: Generate sample dataset with point cluster centered at $(0,0)$ and grid node at $(150,150)$ meters.
- **Procedure**: Execute `SpatialEngine.interpolate_grid()`.
- **Expected Result**: Grid node at $(150,150)$ returns `value = None` (unsupported).
- **Actual Result**: Distance exceeds $100\text{m}$; node value set to `None`.
- **Status**: PASSED
- **Notes**: Eliminates arbitrary spatial extrapolation artifacts across unmonitored field areas.

---

### Test ID: `TST-005` — Sparse Grid Handling ($N < 3$)
- **Objective**: Verify that spatial interpolation aborts safely when provided fewer than 3 valid samples.
- **Setup**: Pass a session containing only 2 valid samples to `SpatialEngine`.
- **Procedure**: Execute `SpatialEngine.interpolate_grid()`.
- **Expected Result**: Engine returns `SpatialFieldResult` with `is_valid = False` without throwing unhandled exceptions.
- **Actual Result**: Returns `is_valid = False` as expected.
- **Status**: PASSED
- **Notes**: Fault injection verification for sparse data edge cases.

---

### Test ID: `TST-006` — 4-Neighbor BFS Zone Clustering & Small Region Merging
- **Objective**: Confirm that small contiguous component clusters $< 2$ grid cells ($< 200\text{m}^2$) are merged into neighboring dominant zones.
- **Setup**: Construct a spatial grid containing a single isolated outlier cell surrounded by healthy cells.
- **Procedure**: Process grid through `ZoneEngine.detect_zones()`.
- **Expected Result**: Single isolated cell is merged into adjacent zone; total zone count simplified.
- **Actual Result**: Outlier cell merged into neighboring zone seamlessly.
- **Status**: PASSED
- **Notes**: Verifies BFS graph merging algorithm (`D-007`).

---

### Test ID: `TST-007` — Recommendation Engine Prescription Prohibition
- **Objective**: Verify that generated recommendations contain qualitative directional advice and **zero** quantitative fertilizer/chemical dosages.
- **Setup**: Run `RecommendationEngine` against a poor nitrogen zone.
- **Procedure**: Inspect recommendation text strings for chemical units (`kg/acre`, `liters`, `kg/ha`, `urea`).
- **Expected Result**: Guidance provides directional actions (e.g. *"Review nitrogen availability"*); contains zero quantitative chemical numbers or units.
- **Actual Result**: Clean qualitative text emitted; zero dosage figures found.
- **Status**: PASSED
- **Notes**: Agronomic safety boundary compliance (`D-006`).

---

### Test ID: `TST-008` — Offline Passive UI Renderer Validation
- **Objective**: Confirm that `LocalUIRenderer` compiles a single-file HTML document with zero external HTTP/HTTPS network dependencies.
- **Setup**: Execute `python -m fieldsense.demo` to produce `artifacts/fieldsense_competition_demo.html`.
- **Procedure**: Scan HTML output for external network resource calls (`http://`, `https://`, `src=`, CDN scripts, external fonts).
- **Expected Result**: Output file contains zero external URL references; all SVG graphics and CSS styling embedded inline.
- **Actual Result**: 100% self-contained HTML output verified.
- **Status**: PASSED
- **Notes**: Operational requirement for network-isolated edge deployment (`D-008`).

---

### Test ID: `TST-009` — Hardware Adapter Isolation & Mock Transport
- **Objective**: Confirm that `HardwareSensorAdapter` converts raw serial bytes into canonical `FieldSample` instances identically to `VirtualSensorAdapter`.
- **Setup**: Configure `HardwareSensorAdapter` with `MockHardwareTransport` and `MockGPSAdapter`.
- **Procedure**: Execute `acquire_sample(lat, lon)` and pass result to downstream `ValidationEngine`.
- **Expected Result**: Emits valid `FieldSample` tagged `source = SampleSource.HARDWARE`; downstream pipeline processes sample without error.
- **Actual Result**: Emits canonical sample; pipeline completes flawlessly.
- **Status**: PASSED
- **Notes**: Proves hardware transparency abstraction (`D-002`).

---

### Test ID: `TST-010` — Physical Hardware Serial Modbus & UART Communication
- **Objective**: Validate RS485 Modbus RTU communication with physical JXBS 7-in-1 sensor probe and UART serial connection to NEO-M8N GPS module.
- **Setup**: Physical connection of JXBS 7-in-1 sensor to 12.24V DC supply and FTDI USB-RS485 adapter (COM8, 9600 8N1).
- **Procedure**: Execute `hardware_test/soil sensor/jxbs_test.py` Modbus RTU query sequence across air/foam baseline and physical soil positions.
- **Expected Result**: Serial Modbus frames read without CRC error; all 7 parameters ($N, P, K, \text{pH}, \text{EC}, \text{Moisture}, \text{Temp}$) parsed correctly.
- **Actual Result**: 100% Modbus response length match (7 bytes), 0 CRC failures observed, distinct physical parameter responses for air/foam vs. soil positions.
- **Status**: PASSED (BENCH VERIFIED)
- **Notes**: Empirically verified JXBS 7-in-1 hardware component; Arduino UNO Q onboard MPU integration pending final board assembly.

---

### Test ID: `TST-011` (`NEO-M8N-GPS-001`) — GPS Hardware and NMEA Functional Verification
- **Objective**: Independently verify the physical NEO-M8N breakout's power, UART communication, NMEA output, multi-GNSS behavior, autonomous fix acquisition, satellite tracking, position behavior, and native update rate before V1 integration.
- **Setup**: Physical u-blox NEO-M8N breakout (`GY-GPSV3-NEO`, board marking `NEO-M8N-0-10`). 3.3V DC applied directly to VCC. Serial UART connection to host PC USB-serial adapter (9600 8N1 format; DTR/RTS assertions disabled). Indoor/near-window bench test environment.
- **Procedure**:
  1. Inspect physical board layout, soldered 4-pin header (`VCC`, `RX`, `TX`, `GND`), onboard components, and ceramic patch antenna.
  2. Apply 3.3V DC power to VCC and verify module startup via onboard 3.3V LDO regulator.
  3. Open UART serial connection at 9600 baud (8-N-1 format, no flow control).
  4. Capture raw serial stream to verify NMEA 0183 protocol compliance, output frequency, and sentence header prefixes (`$GN`, `$GP`, `$GL`).
  5. Monitor indoor fix acquisition sequence for satellite count, 3D autonomous fix status, HDOP metrics, position stability (2-minute stationary run), and NMEA UTC timestamp availability.
- **Expected Result**: Module powers up on 3.3V DC; UART serial streams valid NMEA 0183 ASCII sentences at ~1 Hz native rate at 9600 baud 8-N-1; sentence headers include `$GN` multi-GNSS prefixes; autonomous 3D fix acquired with GPS and GLONASS tracking; valid NMEA UTC timestamps parsed.
- **Actual Result**:
  - Direct 3.3V DC power operation and 9600 8-N-1 UART communication confirmed. Native sentence update rate measured at ~1 Hz.
  - Raw NMEA stream contained `$GN`, `$GP`, and `$GL` sentence prefixes (multi-GNSS output confirmed).
  - Autonomous 3D fix obtained with concurrent GPS and GLONASS tracking (8–9 satellites continuously used in solution).
  - Measured indoor HDOP range: `4.82 – 5.10`.
  - Stationary indoor position stability: minor latitude/longitude drift observed over 2 minutes.
  - Physical observations: 4-pin header soldered (`VCC`, `RX`, `TX`, `GND`); no dedicated hardware PPS pin exposed; onboard 3.3V LDO, RTC battery, external EEPROM, ceramic patch antenna present; U.FL connector unpopulated.
  - Host finding: Windows CH340 testing required disabling DTR/RTS lines to prevent initialization lock.
- **Status**: PASS — VERIFIED (Bench Verification)
- **Notes**:
  - This PASS represents functional/bench verification, not formal GNSS accuracy validation.
  - Measured HDOP range (4.82–5.10) and stationary position drift are indoor test observations, not outdoor field accuracy specifications.
  - Software NMEA parser must support `$GN` multi-GNSS sentences.
  - System timing relies on NMEA UTC timestamps as no dedicated PPS pin is exposed on the tested breakout.
  - Host DTR/RTS requirement is a test-environment finding, not a universal hardware requirement.
  - Physical breakout is `READY FOR V1 INTEGRATION`; final UNO Q UART integration remains `PENDING HARDWARE`.
  - Outdoor open-sky validation, differential GNSS accuracy, long-duration stability, and UBX update rates $> 1\text{ Hz}$ remain pending field testing.

---

### Test ID: `TST-012` (`MAX485-001`) — RS485 Physical Layer and Direction Control Verification
- **Objective**: Verify the physical MAX485 module (`HW-097`) as the UART ↔ RS485 half-duplex interface for FieldSense V1, including power operation, transmit, receive, direction control, and communication with the JXBS RS485 soil sensor.
- **Setup**: Physical MAX485 interface module (`HW-097`, transceiver `MAX485CSA +DNHK`). Powered via 5.0V DC. COM10 (CH340 USB-TTL) connected to TTL side (DI, RO, DE, RE); COM8 (FT232 USB-RS485) / JXBS sensor connected to differential A/B lines. Format 9600 8-N-1.
- **Procedure**:
  1. Apply 5.0V DC power to VCC and GND.
  2. Execute `hardware_test/RS485/rs485_test1.py` with `DE=5V, RE=5V` to test TTL UART $\rightarrow$ RS485 transmission.
  3. Execute `hardware_test/RS485/rs485_test2.py` with `DE=0V, RE=0V` to test RS485 $\rightarrow$ TTL UART reception.
  4. Transmit valid Modbus RTU query/response traffic across MAX485 interface to JXBS 7-in-1 soil sensor using `hardware_test/soil sensor/jxbs_test.py`.
- **Expected Result**: 5V supply operation, UART $\rightarrow$ RS485 transmission, RS485 $\rightarrow$ UART reception, half-duplex operation, DE//RE direction control, and JXBS communication through MAX485 all PASS with zero byte errors and zero communication instability.
- **Actual Result**:
  - 5 V operation: PASS
  - UART $\rightarrow$ RS485 transmission: PASS (bit-exact match, 0 byte errors)
  - RS485 $\rightarrow$ UART reception: PASS (bit-exact match, 0 byte errors)
  - Half-duplex operation: PASS
  - DE//RE direction control: PASS
  - JXBS communication through MAX485: PASS
  - Valid Modbus RTU responses observed: PASS
  - Communication instability: none observed during successful verification
- **Status**: PASS — VERIFIED
- **Notes**:
  - This is a physical-layer verification.
  - Does not constitute verification of the Modbus protocol implementation itself (Modbus CRC validation, register decoding, and scaling are handled in software/firmware layers above the MAX485).
  - Integration Status: `READY FOR V1 INTEGRATION` (Final UNO Q STM32U585 UART pin wiring remains `PENDING HARDWARE`).

---

### Test ID: `TST-013` (`TFT-TOUCH-001`) — ST7789V Display and XPT2046 Touch Verification
- **Objective**: Verify the physical 2.8" TFT display and XPT2046 resistive touch subsystem before FieldSense V1 integration.
- **Setup**: 2.8" SPI TFT Display + XPT2046 Resistive Touch breakout (`2.8" TFT 240xRGBx320 V1.1`). Powered via 3.3V DC. ESP32 DevKit host during bench testing (`display_test_notouch.ino` and `display_test_touch.ino`).
- **Procedure**:
  1. Connect TFT display module hardware SPI lines (`CS`, `DC`, `MOSI`, `SCK`, `RST`) to host microcontroller.
  2. Supply 3.3V DC power to VCC and LED backlight anode.
  3. Execute `display_test_notouch.ino` to verify ST7789V initialization, 240 × 320 native resolution, 320 × 240 landscape orientation (`setRotation(1)`), color bars, border alignment, and typography rendering.
  4. Connect XPT2046 / HR2046 touch controller lines (`T_CLK`, `T_CS`, `T_DIN`, `T_DO`, `T_IRQ`) to isolated host GPIO pins.
  5. Execute `display_test_touch.ino` using bit-banged 8-bit SPI command frames (`0x90` X-axis conversion, `0xD0` Y-axis conversion).
  6. Measure dynamic 12-bit SAR ADC responses and monitor active-low pen interrupt (`T_IRQ`) behavior during physical screen touches.
- **Expected Result**:
  - Display: ST7789V initialization PASS, 240 × 320 native matrix PASS, 320 × 240 landscape operation PASS, 4-wire hardware SPI communication PASS, display control signals PASS, power operation PASS with zero edge clipping.
  - Touch: XPT2046/HR2046 operation PASS, `T_IRQ` active-low interrupt behavior PASS (`IRQ=0` pressed, `IRQ=1` idle), 12-bit ADC raw output PASS (~500–3500 range across X/Y), touch subsystem functional operation PASS.
- **Actual Result**:
  - Display: PASS — ST7789V initialized with `Adafruit_ST7789`, 320 × 240 landscape frame rendered cleanly with no GRAM offset shifts or edge clipping.
  - Touch: PASS — Dynamic raw ADC coordinates measured spanning approximately `500` to `3500` across active X/Y axes; `T_IRQ` active-low pen down transition physically confirmed (`0` pressed, `1` idle).
- **Status**: PASS — VERIFIED
- **Notes**:
  - Verification Scope: Functional bench verification of physical display and resistive touch hardware.
  - Dedicated SPI bus recommended for touch controller to prevent MISO line loading/contention with display.
  - Does NOT claim final UI integration, final UNO Q pin mapping, final touch calibration matrix, or final enclosure mounting.

---

### Test ID: `TST-014` (`UNO-Q-001`) — Arduino UNO Q Platform and Physical UART Verification
- **Objective**: Verify the Arduino UNO Q platform's core hardware/software capabilities required for FieldSense V1, including boot, STM32 execution, Linux/Python execution, Arduino Bridge/RPC communication, and physical UART TX/RX operation.
- **Setup**:
  - Arduino UNO Q main compute platform
  - STM32U585 MCU
  - QRB2210 Linux environment
  - Arduino Bridge / RPC
  - Python runtime environment
  - Physical UART TX/RX connection
  - UNO Q platform verification test firmware/software
- **Procedure**:
  1. Boot the Arduino UNO Q platform; inspect power distribution, boot sequence, and Linux OS startup stability.
  2. Deploy and execute compiled code on the STM32U585 MCU; verify MCU hardware pin control and execution integrity.
  3. Initialize Python 3 runtime environment on the QRB2210 Linux core; execute continuous data reception/processing loops.
  4. Exercise the Arduino Bridge / RPC IPC protocol; send structured data packets bidirectionally between the STM32 application and Linux Python process.
  5. Connect physical UART test signals to STM32 UART TX/RX pins; monitor real voltage-level transmission and reception activity on the board.
- **Expected Result**:
  1. Power & Boot: Clean boot observed; Linux OS starts successfully; stable operating behavior observed.
  2. STM32 MCU: STM32 accepts and executes deployed code; MCU hardware pins controlled; physical UART operational.
  3. Linux Core: Linux core executes Python successfully; Python loops execute correctly; Python environment receives and processes data.
  4. Arduino Bridge/RPC: Bidirectional structured data flows between STM32 and Linux/Python side; physical MCU-originated data reaches Linux; Linux/Python receives and processes bridged data with no lag or communication failure observed.
  5. Physical UART: STM32 UART TX/RX pins successfully transmit and receive real physical UART signals on actual hardware board.
- **Actual Result**:
  - Power & Boot: PASS — Clean boot, stable Linux OS startup.
  - STM32 MCU Execution: PASS — MCU accepts/executes code, pin control operational.
  - Linux Python Environment: PASS — Python process executes loops, processes data stream cleanly.
  - Arduino Bridge / RPC: PASS — Bidirectional structured data transfer confirmed with zero observed lag or dropouts.
  - Physical UART TX/RX: PASS — Real physical voltage-level UART activity observed and verified on physical pins.
- **Status**: PASS — VERIFIED FOR FIELDSENSE V1
- **Notes**:
  - Ground-level hardware validation of core Arduino UNO Q platform capabilities complete.
  - Component Verification Phase officially closed (`🟢 COMPLETE`).
  - Real hardware communication paths verified (`🟢 VERIFIED`): GPS (Serial1 → Bridge → Linux), JXBS (USB-RS485 → USB-C Hub → Linux), Display (Native Hardware SPI → ST7789), Touch (XPT2046 mapped $320 \times 240$).

---

### Milestone Test ID: `V1-INTEGRATION-001` — Initial Multi-Peripheral UNO Q Integration

- **Objective**: Verify physical hardware communication paths across all individual peripherals connected to the Arduino UNO Q target host.
- **Hardware Integration Setup**:
  - Arduino UNO Q (Qualcomm QRB2210 Linux MPU + STM32U585 MCU)
  - NEO-M8N GPS Module connected to STM32 `Serial1` (9600 baud)
  - JXBS 7-in-1 Soil Sensor connected via MAX485 / USB-RS485 through USB-C Hub to UNO Q Linux
  - 2.8" ST7789 TFT Display + XPT2046 Touch Panel connected via Native Hardware SPI (`&SPI`)
- **Verified Hardware Communication Paths**:
  - **GPS Path**: `🟢 VERIFIED` — NEO-M8N $\rightarrow$ STM32 `Serial1` $\rightarrow$ Arduino Bridge/RPC (`get_gps_data`) $\rightarrow$ Linux Python ($9600$ baud, `$GN`, `$GP`, `$GL` NMEA sentences at native $\sim 1\text{ Hz}$ update rate).
  - **JXBS Soil Path**: `🟢 VERIFIED` — JXBS 7-in-1 $\rightarrow$ RS485 $\rightarrow$ USB-RS485 $\rightarrow$ USB-C Hub $\rightarrow$ UNO Q Linux $\rightarrow$ FieldSense Python (Modbus RTU $9600\text{ 8N1}$).
  - **TFT Display Path**: `🟢 VERIFIED` — UNO Q $\rightarrow$ Native Hardware SPI (`&SPI`) $\rightarrow$ ST7789 TFT ($320 \times 240$ landscape, `tft.invertDisplay(false)` dark-mode UI).
  - **Touch Interface Path**: `🟢 VERIFIED` — XPT2046 Touch $\rightarrow$ Hardware SPI $\rightarrow$ Mapped $320 \times 240$ display coordinates ($p.z$ pressure filtering $400 \le p.z \le 4000$).
- **Resolved Hardware Test Failures & Root Causes**:
  - **Failure 1 — TFT White Screen**:
    - *Root Cause*: Faulty physical jumper cable / connection.
    - *Fix*: Faulty jumper wire identified during wire-by-wire audit and replaced.
    - *Status*: `RESOLVED`
  - **Failure 2 — Software SPI Instability**:
    - *Root Cause*: Software SPI bit-banging caused signal integrity issues and breadboard crosstalk.
    - *Fix*: Migrated display driver implementation to native hardware SPI (`&SPI`).
    - *Status*: `RESOLVED`
  - **Failure 3 — Touch Phantom Input Near Screen Center**:
    - *Root Cause*: Mechanical lamination pinch in outer display bezel causing phantom $Z$-axis touch triggers near center.
    - *Classification*: `KNOWN PROTOTYPE HARDWARE DEFECT` (Physical hardware limitation, not a software bug).
    - *Status*: `ACCEPTED FOR V1 PROTOTYPE` (Hardware revision required for production; evaluate capacitive touch).
- **Pending End-to-End Validation Items (`🟡 PENDING`)**:
  1. Combined GPS + JXBS acquisition in one unified process.
  2. Conversion of simultaneous real GPS + soil data into the existing `FieldSample` contract.
  3. Real hardware samples through the complete Phase 1 pipeline.
  4. Multi-point field collection using 8–10 real GPS-tagged samples.
  5. Spatial interpolation using real field coordinates.
  6. Real zones generated from hardware data.
  7. Real recommendations generated from hardware data.
  8. Final TFT Field Intelligence UI driven by actual Phase 1 output.
  9. Complete end-to-end V1 demonstration timing.
  10. Final portable battery configuration (pending, but does not block V1 integration).
- **Milestone Status**:
  - Component Verification: `🟢 COMPLETE`
  - V1 System Integration: `🟡 ACTIVE` (Successful partial integration milestone; unified end-to-end validation `PENDING`).

---

## 4. Golden Scenarios Summary Table

| Scenario Name | Description | Key Metric Pattern | Primary Zone Status | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| `HEALTHY_FIELD` | Uniform high-fertility soil | All metric scores $> 0.80$ | `HEALTHY` (Score 0.88) | PASSED |
| `NUTRIENT_DEFICIENT` | Severely depressed N & P | $N < 20\,\text{ppm}$, $P < 10\,\text{ppm}$ | `POOR` (Issue: Nitrogen) | PASSED |
| `MOISTURE_DEFICIENT` | Extreme soil drought | $\text{Moisture} < 10\%$ VWC | `POOR` (Issue: Moisture)| PASSED |
| `MIXED_STRESS` | Salinity & pH imbalance | $\text{EC} > 4000\,\mu\text{S/cm}$, $\text{pH} = 4.8$ | `POOR` (Issue: Salinity)| PASSED |
| `SPATIAL_GRADIENT` | Continuous N transition across plot | Linear slope $(0.20 \rightarrow 0.90)$ | `POOR` $\rightarrow$ `MOD` $\rightarrow$ `HEALTHY` | PASSED |

---

## 5. Performance & Execution Latency Benchmarks

- **Test Machine Host**: Windows 11 Dev Workstation (AMD/Intel 64-bit Architecture).
- **Full Pipeline Execution Time (25 samples, $10\text{m}$ grid)**: $42.5\text{ms}$ (`MEASURED (Host Windows)`).
- **Peak RAM Footprint**: $< 22\text{MB}$ (`MEASURED (Host Windows)`).
- **Physical Edge Latency (Arduino UNO Q QRB2210 Debian Linux)**: `PENDING HARDWARE` (`UNO_Q_PHYSICAL_BENCHMARK = PENDING_HARDWARE`).
