# FieldSense AI — Testing Guide

How to test FieldSense, from pure software up to the fully assembled instrument.

Every hardware procedure here is derived from a test that was **actually performed** and recorded in `hardware_test/*/`. Where something has not been done yet, this guide says so rather than guessing.

---

## Contents

1. [Before you start](#1-before-you-start)
2. [The test ladder](#2-the-test-ladder)
3. [Level 0 — Software only, no hardware](#3-level-0--software-only-no-hardware)
4. [Level 1 — Standalone component tests](#4-level-1--standalone-component-tests)
   - [1A · JXBS soil probe](#1a--jxbs-7-in-1-soil-probe)
   - [1B · MAX485 transceiver](#1b--max485-rs485-transceiver)
   - [1C · NEO-M8N GPS](#1c--neo-m8n-gps-module)
   - [1D · 2.8" TFT display + touch](#1d--28-tft-display--touch)
   - [1E · Arduino UNO Q](#1e--arduino-uno-q-platform)
5. [Level 2 — Integrated subsystems](#5-level-2--integrated-subsystems)
6. [Level 3 — Full system](#6-level-3--full-system)
7. [Troubleshooting](#7-troubleshooting)
8. [What is not yet testable](#8-what-is-not-yet-testable)
9. [Test evidence register](#9-test-evidence-register)

---

## 1. Before you start

### Install

```bash
python3 -m pip install -e ".[dev]"
```

Hardware scripts additionally need one package:

```bash
python3 -m pip install pyserial
```

### Serial port names

Every hardware script currently hardcodes a **Windows** port near the top of the file:

```python
PORT = "COM8"     # jxbs_test.py
PORT = "COM10"    # test_gps.py
```

On Linux (including the UNO Q itself) change these to the matching device node:

| Host | Typical node | Find it with |
| :--- | :--- | :--- |
| Windows | `COM8`, `COM10` | Device Manager → Ports |
| Linux / UNO Q | `/dev/ttyUSB0`, `/dev/ttyACM0` | `ls /dev/ttyUSB* /dev/ttyACM*` |
| macOS | `/dev/cu.usbserial-*` | `ls /dev/cu.*` |

On Linux add yourself to the `dialout` group once, then log out and back in:

```bash
sudo usermod -aG dialout $USER
```

### Safety — read once

> **3.3 V logic on the TFT.** The display board accepts 3.3 V *or* 5 V on its power pin because it has an onboard LDO. Its **signal** pins are strictly 3.3 V. Driving them from a 5 V pin without level shifting can destroy the controller.

> **Common ground.** The probe runs from a separate 12 V supply. Its ground **must** be tied to the UNO Q ground, or RS485 has no shared reference and you will read garbage or nothing.

> **Check polarity before applying 12 V.** Brown is V+, black is V−. Reversing them can kill the probe.

> **RS485 A/B are not interchangeable.** Yellow is A, blue is B. Swapping them gives silence, not damage — so if a healthy-looking bus reads nothing, try swapping.

---

## 2. The test ladder

Test in this order. Each rung assumes the one below it passed. When something fails at a higher rung, drop down and re-verify the rung underneath rather than debugging the whole stack at once.

```
   LEVEL 3   Full system: probe → zones → dashboard
        ▲
   LEVEL 2   Integrated: sensor + transceiver + UNO Q
        ▲
   LEVEL 1   Standalone: each component alone on a bench host
        ▲
   LEVEL 0   Software only: no hardware attached at all
```

This is the same discipline as bringing up any board: prove the rails, then each peripheral, then the buses, then the application.

---

## 3. Level 0 — Software only, no hardware

Nothing needs to be plugged in. This is the fastest way to know the analytics stack is healthy.

### 0.1 Run the automated suite

```bash
python3 -m pytest -q
```

**Expected:** `147 passed`. Any failure here means the software regressed — fix it before touching hardware.

### 0.2 Run the end-to-end pipeline

```bash
python3 -m fieldsense.demo
```

**Expected:**

```
Samples:            25 Total | 24 Valid | 1 Rejected
Overall Health:     67% [MODERATE]
Zones Detected:     4 Spatially Connected Management Zones
Explanation Layer:  MOCK_TEMPLATE_v1 [FALLBACK_TEMPLATE] | Guard Blocks: 0
```

The `1 Rejected` is deliberate — the golden dataset plants one unstable sample so you can see the validation gatekeeper working.

### 0.3 Check the dashboard

Open `artifacts/fieldsense_competition_demo.html`. Resize the window narrow (~240 px) to preview the panel layout, or leave it wide for the desktop view — both come from the same file.

**Why this matters:** the virtual sensor produces the same `FieldSample` objects the real probe will. Everything downstream of stage 1 is already proven before hardware arrives.

---

## 4. Level 1 — Standalone component tests

Each component is tested alone, on a laptop, using a USB adapter. No UNO Q involved.

---

### 1A · JXBS 7-in-1 soil probe

**What you are proving:** the probe powers up, answers Modbus, and returns physically sensible values.

**You need:** JXBS-3001-TR · FT232 USB-RS485 adapter · 12 V DC supply · a pot of soil.

#### Wiring

```
  12 V DC supply
     V+ ──────────────> BROWN   (probe power +)
     V− ──────────────> BLACK   (probe power −)
                          │
                          └───── common ground with the adapter

  FT232 USB-RS485
      A  ──────────────> YELLOW  (RS485 A / Data+)
      B  ──────────────> BLUE    (RS485 B / Data−)
```

#### Serial settings

`9600` baud · `8` data bits · no parity · `1` stop bit · no flow control · Modbus slave ID `0x01` · function code `0x03`.

#### Run

```bash
python3 "hardware_test/soil sensor/jxbs_test.py"
```

#### Verified register map

The script asks for one register at a time and applies these scale factors:

| Parameter | Register | Request frame | Scale | Unit |
| :--- | :--- | :--- | :--- | :--- |
| pH | `0x0006` | `01 03 00 06 00 01 64 0B` | ÷ 100 | pH |
| Moisture | `0x0012` | `01 03 00 12 00 01 24 0F` | ÷ 10 | %RH |
| Temperature | `0x0013` | `01 03 00 13 00 01 75 CF` | ÷ 10 | °C |
| EC | `0x0015` | `01 03 00 15 00 01 95 CD` | ÷ 1 | µS/cm |
| Nitrogen | `0x001E` | `01 03 00 1E 00 01 E4 0C` | ÷ 1 | mg/kg |
| Phosphorus | `0x001F` | `01 03 00 1F 00 01 B5 CC` | ÷ 1 | mg/kg |
| Potassium | `0x0020` | `01 03 00 20 00 01 85 C0` | ÷ 1 | mg/kg |

Each reply is 7 bytes: `01 03 02 DATA_H DATA_L CRC_L CRC_H`. The script recomputes CRC-16-MODBUS (`0xA001`) and rejects any frame that fails.

#### Pass criteria

- Every one of the seven registers answers with a CRC-valid frame.
- Temperature reads close to room temperature.
- Moisture changes when you push the probe into wet soil versus holding it in air.

**The moisture check is the important one.** A probe that returns a constant plausible number is not necessarily working — it may be echoing a default. Physically changing the environment and seeing the number move is what proves the measurement chain.

📄 Full record: `hardware_test/soil sensor/JXBS_HARDWARE_TEST.md`

---

### 1B · MAX485 RS485 transceiver

**What you are proving:** the transceiver converts TTL ↔ differential in both directions, and that you can steer its direction.

**You need:** MAX485 module (`HW-097`) · CH340 USB-TTL adapter · FT232 USB-RS485 adapter · 5 V.

RS485 is a **differential pair**: the receiver reads the *difference* between A and B, so noise that hits both wires equally cancels out. That is why it survives long muddy cable runs where plain UART would not.

#### Wiring

```
  CH340 USB-TTL  (logic side)          MAX485 module
      TXD ──────────────────────────>  DI   (data in)
      RXD <──────────────────────────  RO   (receive out)
      5V  ──────────────────────────>  VCC
      GND ──────────────────────────>  GND

  Direction control (tie DE and RE together)
      5 V  → transmit mode
      GND  → receive mode

  FT232 USB-RS485 (differential side)
       A  <────────────────────────>  A
       B  <────────────────────────>  B
```

#### Run

```bash
python3 hardware_test/RS485/rs485_test1.py    # transmit / driver test
python3 hardware_test/RS485/rs485_test2.py    # receive / receiver test
```

#### Pass criteria

- Test 1: bytes sent into `DI` appear on the FT232 side.
- Test 2: bytes sent from the FT232 appear on `RO`.

> **This module has no automatic direction sensing.** `DE`/`RE` must be driven explicitly. In the final build the STM32 does this on GPIO 7. Get the timing wrong and frames truncate — see [1E](#1e--arduino-uno-q-platform).

The board already carries its own 120 Ω termination resistor (`R7`) across A/B, so no external terminator is needed on a short bench bus.

📄 Full record: `hardware_test/RS485/RS485_HARDWARE_TEST.md`

---

### 1C · NEO-M8N GPS module

**What you are proving:** the receiver powers up, streams NMEA, and achieves a real satellite fix.

**You need:** `GY-GPSV3-NEO` breakout · CH340 USB-TTL adapter · a window.

#### Wiring

```
  CH340 USB-TTL
     3.3V ──────────────> VCC
     TXD  ──────────────> RX      (crossed: our TX → their RX)
     RXD  <────────────── TX      (crossed: their TX → our RX)
     GND  ──────────────> GND
```

**TX and RX cross over.** Wiring them straight through is the single most common reason a GPS appears dead.

#### Serial settings

`9600` baud · `8N1` · no flow control · ~1 Hz output.

#### Run

```bash
python3 hardware_test/GPS/test_gps.py
```

#### Pass criteria

- NMEA sentences stream immediately (`$GNGGA`, `$GPGGA`, `$GNRMC` …). This proves the module is alive **even with no fix**.
- Within a few minutes near a window, the fix-quality field (index 6 of `$GNGGA`) becomes `1` or `2`, and latitude, longitude, altitude, satellite count and HDOP populate.
- The script samples 30 valid fixes and reports stationary drift.

**Cold start takes minutes, not seconds.** The onboard backup battery makes later restarts much faster. Sentences flowing with `fix quality = 0` means the receiver is fine and simply cannot see enough satellites — go outdoors before you suspect the hardware.

📄 Full record: `hardware_test/GPS/GPS_HARDWARE_TEST.md`

---

### 1D · 2.8" TFT display + touch

**What you are proving:** the panel initialises, fills the full 240×320 frame with no clipping, and the touch controller returns live coordinates.

**You need:** the 2.8" TFT breakout · a **3.3 V** host. Bench verification used an **ESP32 DevKit**, chosen precisely because its GPIO is natively 3.3 V.

#### Wiring (as bench-tested on ESP32)

```
  ESP32 3V3 ──────> TFT VCC and LED (backlight)
  ESP32 GND ──────> TFT GND

  Display, 4-wire SPI            Touch, SEPARATE SPI
    CS   → GPIO 15                 T_CS
    DC   → GPIO 2                  T_CLK
    RST  → GPIO 4                  T_DIN
    MOSI, SCK → hardware SPI       T_DO
                                   T_IRQ  (active LOW when pressed)
```

#### Run

Open in Arduino IDE and upload:

- `hardware_test/TFT/display_test_notouch.ino` — display only
- `hardware_test/TFT/display_test_touch.ino` — display + touch

#### Pass criteria

- **Display:** a white rectangle traces the exact perimeter with no clipped edge, and colour bars render. `setRotation(1)` gives a 320×240 landscape frame.
- **Touch:** `T_IRQ` reads HIGH idle and LOW while pressed; raw X and Y move through roughly 500–3500 as you drag across the panel.

> **Give the touch controller its own SPI lines.** Sharing SPI with the display caused MISO contention on the bench — the symptom was frozen readings of `Z=4095, X=0, Y=0`. Isolating the touch signals restored live values. If you see that exact signature, this is why.

Controller is **ST7789V** (not ILI9341 — a common mislabel for this board), touch is **XPT2046/HR2046**.

📄 Full record: `hardware_test/TFT/TFT_HARDWARE_TEST.md`

---

### 1E · Arduino UNO Q platform

**What you are proving:** both processors boot, run their own code, and talk to each other.

The UNO Q is **two computers on one board**:

```
 ┌──────────────────────────────────────────────┐
 │  Qualcomm QRB2210  ──  Debian Linux, Python  │   the "brain"
 │            ▲                                 │   analytics, UI
 │            │  RouterBridge IPC               │
 │            ▼                                 │
 │  STM32U585         ──  Arduino firmware      │   the "reflexes"
 │                                              │   RS485 timing, GPIO
 └──────────────────────────────────────────────┘
```

Linux cannot meet hard microsecond deadlines, so the MCU owns anything timing-critical — exactly the split you would make between an FPGA/MCU and an applications processor.

#### Run

Open `hardware_test/arduino uno q/` as an app in **Arduino App Lab**. It uploads `sketch.ino` to the STM32 and runs `main.py` on the Linux side.

> ⚠️ `UNO_Q_HARDWARE_TEST.md` calls these files `test_q.py` and `test_q.ino`. The actual files are **`main.py`** and **`sketch.ino`**. The document is out of date, not the code.

#### Pass criteria

- Board boots to a Debian shell; `python3 --version` works.
- Sketch uploads to the STM32 without flashing errors.
- `main.py` calls `Bridge.call("get_uart_status")` and receives a reply — this proves the IPC link.
- Physical UART loopback passes, and **unplugging the loopback wire is detected**. Negative-case detection matters as much as the positive case; a test that passes when disconnected is testing nothing.

📄 Full record: `hardware_test/arduino uno q/UNO_Q_HARDWARE_TEST.md`

---

## 5. Level 2 — Integrated subsystems

### 2A · Soil probe → MAX485 → UNO Q

**Status: ✅ verified end-to-end.**

The full acquisition chain, end to end:

```
  JXBS probe ──RS485──> MAX485 ──TTL──> STM32 Serial1
                                           │
                                    RouterBridge IPC
                                           ▼
                                  Linux Python (main.py)
```

#### Wiring

| From | To | Note |
| :--- | :--- | :--- |
| MAX485 `VCC` | UNO Q 5 V | |
| MAX485 `GND` | UNO Q GND | |
| MAX485 `RO` | Serial1 RX | transceiver → MCU |
| MAX485 `DI` | Serial1 TX | MCU → transceiver |
| MAX485 `RE` + `DE` | **Digital pin 7** | tied together, one GPIO |
| Probe yellow | MAX485 `A` | |
| Probe blue | MAX485 `B` | |
| Probe brown | External 12 V + | **not** from the UNO Q |
| Probe black | 12 V supply GND | **must** also join UNO Q GND |

Two power domains, one ground:

```
  External 12 V ──> probe          UNO Q 5 V ──> MAX485
                       └────────── common GND ──────────┘
```

#### Direction control — the part that bites

```
  Set GPIO 7 HIGH          → transmit mode
  Send the Modbus frame
  WAIT for the UART shift register to empty     ← do not skip
  Set GPIO 7 LOW           → receive mode
  Listen for the reply
```

Flipping to receive before the last bit has physically left the shift register truncates your own frame and the sensor never answers. If reads work intermittently, suspect this first.

#### Run

Open `hardware_test/soil sensor with Max485-RS485/` in Arduino App Lab.

#### Pass criteria

Live telemetry on the Linux console every 2 seconds:

```
T: 24.3°C | M: 31.2% | pH: 6.8 | EC: 210 µS/cm | NPK: 12-8-45
```

📄 Full record: `hardware_test/soil sensor with Max485-RS485/JXBS_MAX485_UNOQ_INTEGRATION.md`

---

### 2B · GPS → UNO Q

**Status: ⚠️ not yet done.**

The module is verified standalone (1C), but has never been wired to the UNO Q. Blocked on `HW-03`: which UART node the QRB2210 or STM32 exposes for it. Assumption on record is `/dev/ttyS0` or `/dev/ttyAMA0`, unconfirmed.

**When the pin assignment is fixed:** wire 3.3 V, GND, crossed TX/RX; confirm NMEA arrives on the UNO Q; then feed the parsed fix into `HardwareSensorAdapter` so each sample carries a real position instead of a simulated one.

---

### 2C · TFT → UNO Q

**Status: ⚠️ not yet done — and needs an architectural decision first.**

Verified standalone on an ESP32 (1D), never attached to the UNO Q. Two open questions, one of them architectural:

1. **Pin assignment** — unassigned (`PENDING HARDWARE`).
2. **Which processor owns the panel?** This one is not just wiring:

| Route | Wire TFT to | How the dashboard gets there | Work needed |
| :--- | :--- | :--- | :--- |
| **A — Linux framebuffer** | QRB2210 SPI | `fbtft` exposes `/dev/fb1`; run a kiosk browser on the existing HTML | Kernel module + browser setup. UI needs **no** changes — it is already 240×320. |
| **B — MCU renders** | STM32 SPI | Write a second renderer that pushes drawing commands over RouterBridge | New renderer, new UI code, but no Linux graphics stack |

**Route A is now implemented** in `fieldsense/hardware/display_bridge.py` with the `scripts/launch_display.sh` launcher. It renders the dashboard at an exact 240×320 CSS viewport, decodes to RGB888, packs to RGB565, and writes a framebuffer — all standard library, 31 tests covering it.

What remains is physical:

```bash
./scripts/launch_display.sh probe    # tells you exactly what is missing
```

1. Move the panel from the STM32 to the **QRB2210 SPI bus** (`HW-04`).
2. Confirm `fbtft` / `fb_st7789v` exists in the shipped kernel (`DSP-02`) — check this **first**, it is the biggest schedule risk.
3. Load the driver, confirm `/dev/fb1` reports `240,320` at `16` bpp.
4. `./scripts/launch_display.sh fb`

Full procedure: `docs/AI_DEPLOYMENT.md` Part II.

You can verify everything except the device write on a laptop right now:

```bash
python3 -m fieldsense.hardware.display_bridge --target png
```

`artifacts/panel_frame.png` is pixel-for-pixel what the panel will show.

---

## 6. Level 3 — Full system

Not yet achievable — 2B and 2C are open. When they close, the acceptance run is:

1. Power the instrument from the 3S battery pack through the buck converters. Confirm 12 V at the probe and 5 V at the board **before** connecting either.
2. Boot the UNO Q, confirm GPS fix.
3. Walk a field, taking ~25 samples across the area.
4. Confirm each sample carries a real lat/lon and seven soil parameters.
5. Confirm the pipeline produces a map, zones, and recommendations in **under 500 ms** for 100 samples on a 10 m grid — the documented budget, still to be measured on the QRB2210.
6. Confirm the dashboard renders on the 2.8" panel.
7. Confirm the whole run completes with networking disabled — this is an offline instrument, and the offline claim should be tested, not assumed.

### Software-side rehearsal you can do today

Swap the data source and everything downstream is unchanged:

```python
from fieldsense.hardware.factory import SensorAdapterFactory, DataSourceConfig

adapter = SensorAdapterFactory.create_adapter(DataSourceConfig(source="HARDWARE"))
```

That is the point of the adapter boundary: the pipeline cannot tell whether a sample came from a probe or a simulator, so it needs no changes on the day the hardware lands.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| No serial port found | Driver missing, or no permission | Install CH340/FT232 driver; on Linux `sudo usermod -aG dialout $USER` then re-login |
| `PermissionError` on `/dev/ttyUSB0` | Not in `dialout` group | As above |
| Probe silent, no reply at all | A/B swapped, no common ground, or no 12 V | Swap yellow/blue; tie grounds; measure the 12 V rail |
| Probe replies with CRC failures | Baud or framing wrong | Confirm 9600 8N1, slave `0x01` |
| Probe reads a constant plausible value | Not actually measuring | Move probe between air and wet soil; the value must change |
| Reads work sometimes, truncate often | DE/RE flipped too early | Wait for UART transmission to complete before going LOW |
| GPS totally silent | TX/RX not crossed, or no 3.3 V | Cross them; check VCC |
| GPS streams but fix quality stays `0` | Indoors | Go outside or to a window; allow several minutes cold start |
| TFT stays white or blank | 3.3 V logic violated, or RST/DC wrong | Check every signal line is 3.3 V; re-check CS/DC/RST |
| Touch frozen at `Z=4095, X=0, Y=0` | Touch sharing SPI with display | Move touch to dedicated SPI lines |
| Sketch will not upload | Wrong board profile, or port busy | Select UNO Q; close other serial monitors |
| `Bridge.call` times out | Sketch not running on the STM32 | Re-upload; confirm `Bridge.provide()` name matches the `Bridge.call()` name exactly |
| `pytest` fails before any hardware | Software regression | Fix at Level 0; do not proceed upward |

---

## 8. What is not yet testable

Stated plainly so nobody reports these as bugs.

| Item | Status | Blocked on |
| :--- | :--- | :--- |
| Dashboard on the 2.8" panel | ❌ Not possible | Route A or B decision in [2C](#2c--tft--uno-q) |
| GPS on the UNO Q | ⚠️ Pending | `HW-03` UART node |
| TFT on the UNO Q | ⚠️ Pending | `HW-04` pin assignment |
| Touch → pixel coordinates | ⚠️ Pending | Calibration matrix not derived |
| QRB2210 timing benchmark | ⚠️ Pending | `PF-01`; only a Windows host figure exists |
| Total power draw / battery life | ⚠️ Unknown | Never measured |
| Field accuracy of scoring curves | ⚠️ `PROTOTYPE_ONLY` | `AG-01`/`AG-02`; needs agronomist validation against trial data |
| Local SLM narrative on hardware | ⚠️ Pending | No `.gguf` installed; see `docs/AI_DEPLOYMENT.md` |

The last one deserves emphasis: the scoring curves and MCDA weights are **unvalidated prototype values** at `methodology_version = "0.1"`. Every hardware test above can pass perfectly while the agronomic interpretation remains unproven. Those are different claims — keep them separate when presenting.

---

## 9. Test evidence register

Formal evidence for each verified capability, software and hardware. Previously `docs/TEST_AND_VALIDATION.md`, merged here.

**STATUS:** DRAFT  
**VERSION:** 0.1  
**LAST UPDATED:** 2026-08-22  
**REGRESSION BASELINE:** 178 tests passing ($100\%$ pass rate in $< 1.0\text{s}$)  
**RELEASE STATUS:** `PHASE_1_RELEASE_READY`  

---

### 1. Executive Test Strategy

The FieldSense AI test suite (`tests/`) enforces 100% regression stability and contract compliance across 17 test modules. Testing is divided into five formal validation tiers:

1. **Unit Tests**: Granular contract verification across domain, input, validation, scoring, spatial, zone, recommendation, presentation, and hardware modules.
2. **Integration Tests**: End-to-end multi-stage pipeline flow verification.
3. **Golden Scenarios**: Synthetic field benchmarks representing standard agricultural field conditions.
4. **Fault Injection Suite**: Graceful degradation testing against noisy sensors, corrupted GPS, sparse grid samples, and serial timeouts.
5. **Demonstration & UI Tests**: Verification of single-file offline HTML/SVG visual dashboard rendering.

---

### 2. Test Execution Baseline Summary

```text
============================== test session starts ==============================
platform win32 -- Python 3.14.0a4, pytest-8.3.4, pluggy-1.5.0
rootdir: C:\Users\lovsh\Desktop\FieldSense
collected 178 items

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

============================= 178 passed in 0.70s ==============================
```

---

### 3. Formal Test Evidence Register

#### Test ID: `TST-001` — Canonical FieldSample Immutability
- **Objective**: Verify that `FieldSample` instances are strictly immutable and reject attribute mutation attempts.
- **Setup**: Instantiate a `FieldSample` object with standard parameter values.
- **Procedure**: Attempt to assign a new value to `sample.nitrogen` at runtime.
- **Expected Result**: Python raises `FrozenInstanceError`.
- **Actual Result**: `FrozenInstanceError` raised as expected.
- **Status**: PASSED
- **Notes**: Core architectural requirement enforcing raw observational data integrity (`D-001`).

---

#### Test ID: `TST-002` — Validation Engine Gatekeeper & Sample Rejection
- **Objective**: Verify that out-of-bounds physical metrics (e.g. $\text{pH} = 15.2$, $\text{Moisture} = -5\%$) are tagged `REJECTED` and `pipeline_eligible = False`.
- **Setup**: Create synthetic `FieldSample` containing out-of-bounds pH reading ($15.2$).
- **Procedure**: Process sample through `ValidationEngine.validate_sample()`.
- **Expected Result**: Validation state returns `ValidationState.REJECTED`, `pipeline_eligible` set to `False`, and rejection reason code logged.
- **Actual Result**: Sample marked `REJECTED`, `pipeline_eligible = False`, reason `OUT_OF_BOUNDS`.
- **Status**: PASSED
- **Notes**: Rejected samples remain preserved in `FieldSession.samples` for complete auditability.

---

#### Test ID: `TST-003` — Carbon Readiness Proxy Safety Boundary
- **Objective**: Confirm that `CarbonReadinessResult` enforces `decision_support_only = True`, `evidence_level = "LIMITED"`, and outputs explicit missing indicators.
- **Setup**: Execute `IntelligenceEngine.compute_intelligence()` on valid field samples.
- **Procedure**: Inspect returned `carbon_readiness` result object.
- **Expected Result**: `decision_support_only` is `True`, `evidence_level` is `"LIMITED"`, and `missing_indicators` contains `["soil_organic_carbon", "bulk_density", "management_history"]`.
- **Actual Result**: All safety indicators match expected contracts exactly.
- **Status**: PASSED
- **Notes**: Prevents scientific misrepresentation or uncertified carbon credit claims (`D-005`).

---

#### Test ID: `TST-004` — Spatial Engine Support Distance Threshold ($100\text{m}$)
- **Objective**: Confirm that grid nodes located $> 100\text{m}$ from the nearest valid sample point return `value = None` (unsupported).
- **Setup**: Generate sample dataset with point cluster centered at $(0,0)$ and grid node at $(150,150)$ meters.
- **Procedure**: Execute `SpatialEngine.interpolate_grid()`.
- **Expected Result**: Grid node at $(150,150)$ returns `value = None` (unsupported).
- **Actual Result**: Distance exceeds $100\text{m}$; node value set to `None`.
- **Status**: PASSED
- **Notes**: Eliminates arbitrary spatial extrapolation artifacts across unmonitored field areas.

---

#### Test ID: `TST-005` — Sparse Grid Handling ($N < 3$)
- **Objective**: Verify that spatial interpolation aborts safely when provided fewer than 3 valid samples.
- **Setup**: Pass a session containing only 2 valid samples to `SpatialEngine`.
- **Procedure**: Execute `SpatialEngine.interpolate_grid()`.
- **Expected Result**: Engine returns `SpatialFieldResult` with `is_valid = False` without throwing unhandled exceptions.
- **Actual Result**: Returns `is_valid = False` as expected.
- **Status**: PASSED
- **Notes**: Fault injection verification for sparse data edge cases.

---

#### Test ID: `TST-006` — 4-Neighbor BFS Zone Clustering & Small Region Merging
- **Objective**: Confirm that small contiguous component clusters $< 2$ grid cells ($< 200\text{m}^2$) are merged into neighboring dominant zones.
- **Setup**: Construct a spatial grid containing a single isolated outlier cell surrounded by healthy cells.
- **Procedure**: Process grid through `ZoneEngine.detect_zones()`.
- **Expected Result**: Single isolated cell is merged into adjacent zone; total zone count simplified.
- **Actual Result**: Outlier cell merged into neighboring zone seamlessly.
- **Status**: PASSED
- **Notes**: Verifies BFS graph merging algorithm (`D-007`).

---

#### Test ID: `TST-007` — Recommendation Engine Prescription Prohibition
- **Objective**: Verify that generated recommendations contain qualitative directional advice and **zero** quantitative fertilizer/chemical dosages.
- **Setup**: Run `RecommendationEngine` against a poor nitrogen zone.
- **Procedure**: Inspect recommendation text strings for chemical units (`kg/acre`, `liters`, `kg/ha`, `urea`).
- **Expected Result**: Guidance provides directional actions (e.g. *"Review nitrogen availability"*); contains zero quantitative chemical numbers or units.
- **Actual Result**: Clean qualitative text emitted; zero dosage figures found.
- **Status**: PASSED
- **Notes**: Agronomic safety boundary compliance (`D-006`).

---

#### Test ID: `TST-008` — Offline Passive UI Renderer Validation
- **Objective**: Confirm that `LocalUIRenderer` compiles a single-file HTML document with zero external HTTP/HTTPS network dependencies.
- **Setup**: Execute `python -m fieldsense.demo` to produce `artifacts/fieldsense_competition_demo.html`.
- **Procedure**: Scan HTML output for external network resource calls (`http://`, `https://`, `src=`, CDN scripts, external fonts).
- **Expected Result**: Output file contains zero external URL references; all SVG graphics and CSS styling embedded inline.
- **Actual Result**: 100% self-contained HTML output verified.
- **Status**: PASSED
- **Notes**: Operational requirement for network-isolated edge deployment (`D-008`).

---

#### Test ID: `TST-009` — Hardware Adapter Isolation & Mock Transport
- **Objective**: Confirm that `HardwareSensorAdapter` converts raw serial bytes into canonical `FieldSample` instances identically to `VirtualSensorAdapter`.
- **Setup**: Configure `HardwareSensorAdapter` with `MockHardwareTransport` and `MockGPSAdapter`.
- **Procedure**: Execute `acquire_sample(lat, lon)` and pass result to downstream `ValidationEngine`.
- **Expected Result**: Emits valid `FieldSample` tagged `source = SampleSource.HARDWARE`; downstream pipeline processes sample without error.
- **Actual Result**: Emits canonical sample; pipeline completes flawlessly.
- **Status**: PASSED
- **Notes**: Proves hardware transparency abstraction (`D-002`).

---

#### Test ID: `TST-010` — Physical Hardware Serial Modbus & UART Communication
- **Objective**: Validate RS485 Modbus RTU communication with physical JXBS 7-in-1 sensor probe and UART serial connection to NEO-M8N GPS module.
- **Setup**: Physical connection of JXBS 7-in-1 sensor to 12.24V DC supply and FTDI USB-RS485 adapter (COM8, 9600 8N1).
- **Procedure**: Execute `hardware_test/soil sensor/jxbs_test.py` Modbus RTU query sequence across air/foam baseline and physical soil positions.
- **Expected Result**: Serial Modbus frames read without CRC error; all 7 parameters ($N, P, K, \text{pH}, \text{EC}, \text{Moisture}, \text{Temp}$) parsed correctly.
- **Actual Result**: 100% Modbus response length match (7 bytes), 0 CRC failures observed, distinct physical parameter responses for air/foam vs. soil positions.
- **Status**: PASSED (BENCH VERIFIED)
- **Notes**: Empirically verified JXBS 7-in-1 hardware component; Arduino UNO Q onboard MPU integration pending final board assembly.

---

#### Test ID: `TST-011` (`NEO-M8N-GPS-001`) — GPS Hardware and NMEA Functional Verification
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

#### Test ID: `TST-012` (`MAX485-001`) — RS485 Physical Layer and Direction Control Verification
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

#### Test ID: `TST-013` (`TFT-TOUCH-001`) — ST7789V Display and XPT2046 Touch Verification
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

#### Test ID: `TST-014` (`UNO-Q-001`) — Arduino UNO Q Platform and Physical UART Verification
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
  - Component Verification Phase officially closed (`COMPLETE`).
  - UNO Q platform itself is verified; complete FieldSense hardware system peripheral integration (JXBS, GPS, TFT) remains Phase 2 V1 Hardware Integration (`PENDING HARDWARE`).

---

### 4. Golden Scenarios Summary Table

| Scenario Name | Description | Key Metric Pattern | Primary Zone Status | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| `HEALTHY_FIELD` | Uniform high-fertility soil | All metric scores $> 0.80$ | `HEALTHY` (Score 0.88) | PASSED |
| `NUTRIENT_DEFICIENT` | Severely depressed N & P | $N < 20\,\text{ppm}$, $P < 10\,\text{ppm}$ | `POOR` (Issue: Nitrogen) | PASSED |
| `MOISTURE_DEFICIENT` | Extreme soil drought | $\text{Moisture} < 10\%$ VWC | `POOR` (Issue: Moisture)| PASSED |
| `MIXED_STRESS` | Salinity & pH imbalance | $\text{EC} > 4000\,\mu\text{S/cm}$, $\text{pH} = 4.8$ | `POOR` (Issue: Salinity)| PASSED |
| `SPATIAL_GRADIENT` | Continuous N transition across plot | Linear slope $(0.20 \rightarrow 0.90)$ | `POOR` $\rightarrow$ `MOD` $\rightarrow$ `HEALTHY` | PASSED |

---

### 5. Performance & Execution Latency Benchmarks

- **Test Machine Host**: Windows 11 Dev Workstation (AMD/Intel 64-bit Architecture).
- **Full Pipeline Execution Time (25 samples, $10\text{m}$ grid)**: $42.5\text{ms}$ (`MEASURED (Host Windows)`).
- **Peak RAM Footprint**: $< 22\text{MB}$ (`MEASURED (Host Windows)`).
- **Physical Edge Latency (Arduino UNO Q QRB2210 Debian Linux)**: `PENDING HARDWARE` (`UNO_Q_PHYSICAL_BENCHMARK = PENDING_HARDWARE`).
