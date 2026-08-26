# 2.8" SPI TFT Display & XPT2046 Touch Panel Hardware Test Methodology Documentation

## 1. Role & Document Purpose

**Role:** Repository Documentation Engineer for FieldSense  
**Document Purpose:** This document explains **HOW THE TFT WAS ACTUALLY TESTED** during bench verification. It is an empirical engineering test record, not a generic ST7789/XPT2046 datasheet.

---

## 2. Component Identification & Status

* **Component:** 2.8" SPI TFT Display + XPT2046 Resistive Touch Panel Breakout
* **PCB Marking:** `2.8" TFT 240xRGBx320 V1.1`
* **Display Controller:** **ST7789V**
* **Touch Controller:** **XPT2046 / HR2046**
* **Status:** **VERIFIED — Display & Resistive Touch Subsystems Fully Operational**

---

## 3. Evidence & Information Classification

To maintain technical integrity, information in this document is categorized according to source:

* **DATASHEET INFORMATION:** 240 × 320 native matrix resolution, ST7789V command registers, XPT2046 12-bit SAR ADC architecture.
* **PHYSICALLY VERIFIED:** PCB text `2.8" TFT 240xRGBx320 V1.1`, onboard 3.3 V LDO (`U2`), lack of logic level shifters, full-size SD slot (`SD1`), touch IC `U1` marked `HR2046`, 14-pin single row header, resistive touch overlay.
* **MEASURED:** Active-low `T_IRQ` line state transition (`1` idle, `0` pressed), raw touch ADC range (~500 to ~3500 across X and Y axes).
* **SOFTWARE VERIFIED:** ST7789V initialization via `Adafruit_ST7789`, `setRotation(1)` 320 × 240 landscape frame rendering, zero edge clipping, bit-banged SPI response for `0x90` (X) and `0xD0` (Y) touch channels.
* **ASSUMED:** Final FieldSense pin assignments on host microcontrollers (e.g. Arduino UNO Q / ESP32 production board).
* **PENDING:** Screen coordinate calibration matrix (mapping raw 12-bit ADC values to pixel coordinates) and full-system GUI integration.

---

## 4. Test Architecture

Bench characterization was performed using an **ESP32 DevKit** host because it natively provides 3.3 V CMOS logic levels matching the display and touch controller requirements.

```text
ESP32 DevKit
      │
      ├──────── SPI (4-Wire) ────────→ ST7789V TFT
      │
      └──────── SPI (Dedicated) ────→ XPT2046
```

### Power Architecture

```text
ESP32 3V3 Rail
   │
   ├── TFT VCC
   └── TFT LED / Backlight

ESP32 GND Rail
   │
   └── TFT GND
```

> **Note:** The TFT display subsystem and LED backlight were powered directly from the ESP32 3.3 V power rail during bench testing.

---

## 5. Physical Inspection

Physical inspection of the `2.8" TFT 240xRGBx320 V1.1` breakout board established the following hardware features:

* **Breakout Subsystem:** Red PCB with single-row 14-pin header.
* **Board Marking:** `2.8" TFT 240xRGBx320 V1.1`
* **Onboard Power Regulator:** Onboard 3.3 V LDO linear regulator designated `U2`.
* **Logic Level Shifting:** **No 5 V logic-level shifter ICs present on board.**
* **SD Card Subsystem:** Onboard full-size SD card slot (`SD1`).
* **Touch Controller:** Integrated IC designated `U1` with surface marking `HR2046` (pin-compatible clone/variant of XPT2046).
* **Touch Panel:** 4-wire resistive touch panel laminated onto display glass.

> **CRITICAL WARNING:** Despite the presence of onboard LDO regulator `U2`, the display and touch signal interface lines MUST be treated as **3.3 V logic ONLY**. Do NOT drive interface pins directly with 5 V microcontroller signals without external level shifting.

---

## 6. Display Interface & Bench Wiring

The ST7789V display subsystem uses a 4-wire hardware SPI interface (`CS`, `DC`, `MOSI`, `SCK`, `RST`).

### Tested ESP32 Display Pinout

| Signal | ESP32 GPIO | Description |
| :--- | :--- | :--- |
| **MOSI** | `GPIO 23` | Master Out Slave In (Data) |
| **SCK** | `GPIO 18` | Serial Clock |
| **CS** | `GPIO 15` | Chip Select (Active LOW) |
| **DC** | `GPIO 2` | Data / Command Select |
| **RST** | `GPIO 4` | Hardware Reset (Active LOW) |
| **VCC** | `3V3` | Power Input |
| **GND** | `GND` | Common Ground |
| **LED** | `3V3` | Backlight Anode |

> **Note:** These GPIO mappings represent the actual bench-test setup on the ESP32 DevKit and are NOT mandatory pinouts for final FieldSense production integration.

---

## 7. Test 1 — Display Subsystem Verification

### Test Sketch
[`hardware/tft/display_test_notouch.ino`](display_test_notouch.ino)

### Objective
Verify ST7789V display initialization, SPI communication, landscape rotation, geometry rendering, boundary alignment, and color rendering independently of the touch controller.

### Test Procedure
1. Connect TFT display pins to ESP32 hardware SPI controller (`GPIO 23`, `18`, `15`, `2`, `4`).
2. Connect VCC and LED backlight pins to ESP32 3.3 V output rail; connect GND to common ground.
3. Flash and execute [`display_test_notouch.ino`](display_test_notouch.ino).
4. Verify ST7789V controller initialization via standard `Adafruit_ST7789` driver.
5. Apply landscape rotation (`setRotation(1)`).
6. Perform full-screen refresh to solid black (`ST77XX_BLACK`).
7. Render 320 × 240 perimeter white boundary rectangle (`tft.drawRect(0, 0, 320, 240, ST77XX_WHITE)`).
8. Render primary color blocks (Red, Green, Blue, Yellow).
9. Render text strings (`FIELDSENSE AI`, `2.8in TFT Display`, `Driver: ST7789V / 320x240 Native`).
10. Inspect display for pixel noise, offset shifts, memory alignment errors, or edge clipping.

### Initial Driver Troubleshooting & Diagnosis
During initial bench setup, a generic ILI9341 driver library was evaluated:
* **Observed Symptom:** Display produced visible graphical output, but image rotation was shifted and static pixel noise appeared along the bottom memory region.
* **Diagnosis:** Investigation confirmed the controller RAM structure matched native 240 × 320 **ST7789V** addressing rather than ILI9341 RAM mapping.
* **Resolution:** Switching to `Adafruit_ST7789(TFT_CS, TFT_DC, TFT_RST)` with initialization `tft.init(240, 320)` and `tft.setRotation(1)` completely resolved alignment issues.

### ST7789V Test Results

#### Full-Screen Color Test
* **Colors Rendered:** Solid Black, Red, Green, Blue, Yellow.
* **Result:** PASS — Active matrix rendered all primary colors cleanly with uniform backlight distribution.

#### Edge Boundary & Alignment Test
* **Boundary:** 320 × 240 outer border test.
* **Result:** PASS — Perimeter line visible along all four glass boundaries with no GRAM offsets or clipping.

#### Graphics & Text Test
* **Elements:** Color blocks, multi-size text fonts, status text.
* **Result:** PASS — Crisp typography and geometry with full edge-to-edge frame integrity.

---

## 8. Test 2 — Touch Controller Subsystem Verification

### Test Sketch
[`hardware/tft/display_test_touch.ino`](display_test_touch.ino)

### Objective
Verify XPT2046 / HR2046 resistive touch controller operation, SPI command execution, raw 12-bit ADC measurement, dynamic coordinate tracking, and active-low interrupt line (`T_IRQ`) response.

### Touch Controller Pinout (Bench Test)

| Signal | ESP32 GPIO | Description |
| :--- | :--- | :--- |
| **T_CLK** | `GPIO 14` | Touch SPI Serial Clock |
| **T_CS** | `GPIO 27` | Touch Chip Select |
| **T_DIN** | `GPIO 26` | Touch Serial Data In (MOSI) |
| **T_DO** | `GPIO 25` | Touch Serial Data Out (MISO) |
| **T_IRQ** | `GPIO 33` | Touch Pen Interrupt (Active LOW) |

### Touch Bus Troubleshooting History
During initial bench integration, an attempt was made to share SPI bus lines between the ST7789V display and XPT2046 touch controller.
* **Observed Symptom:** Touch readouts saturated at static maximum invalid values (`Z = 4095`, `X = 0`, `Y = 0`).
* **Root Cause Analysis:** SPI MISO bus loading / tri-state bus conflict introduced by the display/touch combo breakout board when sharing lines without dedicated isolation buffers.
* **Resolution:** Touch interface signals were isolated onto dedicated GPIO pins (`GPIO 14, 27, 26, 25`). Following signal isolation, valid dynamic readings were immediately obtained.

> **INTEGRATION LESSON:** The XPT2046 touch interface should use an electrically clean or dedicated SPI arrangement unless verified MISO tri-state bus isolation hardware is implemented.

### Protocol Verification & Direct Bit-Bang Diagnostic
Direct 8-bit SPI control bytes were issued to the XPT2046 controller via bit-banging in [`display_test_touch.ino`](display_test_touch.ino):
* `0x90` — X-Axis differential position conversion command frame
* `0xD0` — Y-Axis differential position conversion command frame

#### Measured ADC Range
* **Observed Raw Values:** `~500` (lower boundary) to `~3500` (upper boundary) across full active surface.
* **Linearity & Dynamic Response:** Dynamic conversion values responded smoothly to pen drag and multi-point stylus pressure across both X and Y axes.

### Touch Interrupt (`T_IRQ`) Response
The `T_IRQ` line was physically tested under tactile stylus pressure:
* **No Touch (Idle):** `T_IRQ = 1` (Pulled HIGH via internal/external pullup)
* **Touch Active (Pen Down):** `T_IRQ = 0` (Driven LOW upon physical contact)
* **Result:** PASS — Active-low interrupt line reliably signals contact events.

---

## 9. Verification Summary

| Subsystem | Controller IC | Physical Interface | Test Sketch | Result |
| :--- | :--- | :--- | :--- | :--- |
| **Display** | ST7789V | 4-Wire Hardware SPI | [`display_test_notouch.ino`](display_test_notouch.ino) | **PASS** |
| **Touch** | XPT2046 / HR2046 | Dedicated SPI + Active-LOW IRQ | [`display_test_touch.ino`](display_test_touch.ino) | **PASS** |

---

## 10. Verified Hardware & Software Configuration

### Display Subsystem Configuration
```text
Controller:          ST7789V
Native Resolution:   240 × 320
Bench Orientation:   320 × 240 Landscape (setRotation(1))
Interface:           4-Wire Hardware SPI (MOSI, SCK, CS, DC, RST)
Logic Level:         3.3 V CMOS
Driver Library:      Adafruit_ST7789
```

### Touch Subsystem Configuration
```text
Controller:          XPT2046 / HR2046
Resolution:          12-bit SAR ADC
Interface:           Dedicated SPI (T_CLK, T_CS, T_DIN, T_DO)
Interrupt:           T_IRQ (Active LOW on touch contact)
Raw ADC Dynamic Range: ~500 to ~3500
```

---

## 11. System Integration Warnings & Mandates

1. **Strict 3.3 V Logic Requirement:** Treat all TFT display and touch signal lines as **3.3 V logic**. Do not connect directly to 5 V microcontrollers without bidirectional logic level shifters.
2. **Do Not Rely on ESP32 Bench Pinout:** The GPIO pins used in [`display_test_notouch.ino`](display_test_notouch.ino) and [`display_test_touch.ino`](display_test_touch.ino) were selected for ESP32 bench testing only. Production mapping for FieldSense hardware must be explicitly assigned.
3. **SPI Bus Isolation Required:** Do NOT share the XPT2046 touch SPI lines directly on the main display SPI bus without verifying MISO bus isolation, as bus contention will saturate touch output (`Z=4095`, `X=0`, `Y=0`).
4. **ADC Calibration Matrix Needed:** The raw 12-bit ADC values (`~500–3500`) must be mapped through a 2-point or 3-point calibration matrix before being passed as screen coordinates (`0..319`, `0..239`).
5. **Controller Distinction:** The display driver MUST be instantiated as **ST7789V**, NOT ILI9341.
6. **Native Resolution Shift:** The ST7789V native GRAM is 240 × 320; landscape mode (320 wide × 240 high) is achieved in software via `setRotation(1)`.

---

## 12. Final Status

```text
Component:
2.8" SPI TFT Display + XPT2046 Resistive Touch Panel

Display:
ST7789V

Touch:
XPT2046 / HR2046

Status:
VERIFIED — Bench Verification Complete

Display:
PASS

Touch:
PASS
```
