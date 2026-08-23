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

Full procedure: `docs/AI_LAYER_DEPLOYMENT.md` Part II.

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
| Local SLM narrative on hardware | ⚠️ Pending | No `.gguf` installed; see `docs/AI_LAYER_DEPLOYMENT.md` |

The last one deserves emphasis: the scoring curves and MCDA weights are **unvalidated prototype values** at `methodology_version = "0.1"`. Every hardware test above can pass perfectly while the agronomic interpretation remains unproven. Those are different claims — keep them separate when presenting.
