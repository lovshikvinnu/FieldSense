# FieldSense — TFT + XPT2046 + Arduino UNO Q Integration Documentation

## ROLE

Act as the repository documentation engineer for FieldSense.

The 2.8-inch ST7789 TFT and XPT2046 resistive touch panel have now been integrated with the Arduino UNO Q and tested using the UNO Q's native hardware SPI.

Create a technical Markdown document describing the actual integration testing performed.

This is an actual FieldSense V1 hardware integration record, NOT a generic TFT tutorial.

---

# EXISTING FOLDER

The integration folder already exists:

```text
hardware/
└── TFT UNO Q/
    └── sketch.ino
```

The existing:

```text
sketch.ino
```

must NOT be modified.

---

# DOCUMENT TO CREATE

Create:

```text
hardware/tft UNO Q/TFT_UNOQ_INTEGRATION.md
```

If a suitable documentation file already exists in the folder, update it instead of creating a duplicate.

ONLY create/update the documentation file.

---

# 1. HARDWARE ARCHITECTURE

Document the actual FieldSense TFT integration architecture:

```text
Arduino UNO Q
      │
      │ Hardware SPI
      ▼
┌───────────────────────┐
│ 2.8" TFT Display      │
│ ST7789                │
└───────────────────────┘
      │
      │ Touch SPI
      ▼
┌───────────────────────┐
│ XPT2046 Touch         │
│ Resistive Controller  │
└───────────────────────┘
```

### Main display

* 2.8-inch TFT LCD
* ST7789 controller
* 240 × 320 native resolution
* Tested in 320 × 240 landscape orientation (`tft.setRotation(1)`)

### Touch

* XPT2046 resistive touch controller
* Analog 12-bit coordinate system
* Touch input mapped to the display coordinate system

### Interface

The integration uses hardware SPI.

The architecture uses:

* Shared clock (SCK)
* Shared MOSI
* Dedicated MISO return paths where required (XPT2046 Touch controller returns touch data over MISO)
* Separate Chip Select lines (`TFT_CS` and `TOUCH_CS`)

### Pin Assignments (Derived from `sketch.ino`)

| Component | Pin Function | Arduino UNO Q Pin | Description |
| --------- | ------------ | ----------------- | ----------- |
| ST7789 TFT | `TFT_CS` | Pin 10 | Display Chip Select |
| ST7789 TFT | `TFT_DC` | Pin 9 | Data / Command Control |
| ST7789 TFT | `TFT_RST` | Pin 8 | Hardware Reset |
| ST7789 TFT | `TFT_LED` | Pin 7 | Backlight Power / PWM Control |
| XPT2046 Touch | `TOUCH_CS` | Pin 4 | Touch Controller Chip Select |
| XPT2046 Touch | `TOUCH_IRQ` | Pin 2 | Touch Interrupt Request Line |
| Shared SPI Bus | `&SPI` | Native SPI Pins | Shared Hardware SPI (SCK, MOSI, MISO) |

---

# 2. TESTING STRATEGY

Document that testing was performed in multiple phases to distinguish:

```text
Software problems
        vs
Electrical / wiring problems
        vs
Physical hardware defects
```

The integration was not treated as a single "upload and hope" test.

Instead, individual failure modes were isolated experimentally.

---

# 3. TOOLCHAIN VALIDATION

Document the compiler/library issue encountered during integration.

The UNO Q environment produced compatibility/compiler collisions involving:

* UNO Q core
* Legacy Adafruit libraries

The issue was resolved at the board's Linux filesystem level using Linux `sed` commands to rewrite the relevant library headers (e.g. undefining colliding macros such as `MOSI`, `MISO`, `SCK` prior to importing core graphics libraries).

The important engineering record is:

```text
Library compatibility issue
        ↓
Identified at compile stage
        ↓
Library headers patched directly
        ↓
Build/integration continued
```

Clearly mark this as a development-environment workaround rather than a hardware modification.

## 3a. Frame receiver build — verified 2026-08-24

`frame_receiver/frame_receiver.ino` builds clean for `arduino:zephyr:unoq` at
platform 0.90.0:

```text
Sketch uses 97424 bytes (12%) of program storage space. Maximum is 786432 bytes.
Global variables use 40968 bytes (15%) of dynamic memory, leaving 221176 bytes
for local variables. Maximum is 262144 bytes.
```

Three environment facts had to be settled first. All three are environment
setup, not sketch bugs, and all three will recur on a fresh board image.

**One sketch per directory.** `arduino-cli` merges every `.ino` in a sketch
folder into a single translation unit, and requires the folder name to match
the main file. `sketch.ino` and `sketch_frame_receiver.ino` as siblings could
therefore never build: the frame receiver compile pulled in the touch demo's
`XPT2046_Touchscreen.h` include and its duplicate `setup()`/`loop()`. Hence
`frame_receiver/` and `touch_demo/`.

**Arduino_RouterBridge is required, not optional.** On the UNO Q the STM32's
`Serial` is not a UART — it is an RPC transport to the QRB2210 Linux side. The
platform ships a stub `Arduino_RouterBridge.h` that hard-`#error`s until the
real library is installed:

```bash
arduino-cli lib install "Arduino_RouterBridge"
```

This pulls Arduino_RPClite, MsgPack, ArxContainer, ArxTypeTraits and DebugLog.
A "Multiple libraries were found for Arduino_RouterBridge.h" note in the build
output is expected and harmless — it means the real library won over the stub.

**Pin the display library to 1.10.4.** Version 1.11.0 added
`Adafruit_ST7796S.{h,cpp}`, which names constructor parameters `MOSI`, `SCLK`
and `RST`. The UNO Q variant header does `#define MOSI 0`, so those parameters
expand to `int8_t 0` and the file will not parse. The frame receiver never uses
ST7796S, but `arduino-cli` compiles every `.cpp` in a library regardless of what
the sketch includes, so it breaks the build anyway:

```bash
arduino-cli lib install "Adafruit ST7735 and ST7789 Library"@1.10.4
```

Note that the `#undef MOSI/MISO/SCK` guard at the top of `touch_demo.ino`
does **not** help here, and section 3 above should not be read as implying it
does. That guard only fixes collisions inside the sketch's own translation
unit. `Adafruit_ST7796S.cpp` is compiled separately and never sees it — the
only fixes are removing the file or not installing the version that ships it.

Re-check after any `lib install`, which can silently pull 1.11.0 back in as a
dependency. This must print nothing:

```bash
ls ~/Arduino/libraries/Adafruit_ST7735_and_ST7789_Library/ | grep -i 7796
```

---

# 4. PHYSICAL LAYER AUDIT

Document the persistent white-screen failure.

Initial condition:

```text
TFT powered
+
software attempting initialization
=
white screen
```

Instead of assuming a software driver failure, a physical wire-by-wire continuity test was performed.

The test isolated a faulty jumper cable.

The defective jumper was replaced.

After replacement, the display communication could proceed.

Emphasize this as an important debugging result:

> The white-screen problem was caused by a physical connection fault rather than the TFT controller itself.

---

# 5. SPI DATA INTEGRITY

Document the transition from Software SPI to native Hardware SPI.

Initial approach:

```text
Software SPI / bit-banging
```

This produced data-integrity problems associated with:

* Breadboard wiring
* Crosstalk
* Timing
* Software-generated clocking

The integration was moved to:

```text
Arduino UNO Q native Hardware SPI
```

using the hardware SPI transaction mechanism (`SPI.begin()` and passing `&SPI` to `Adafruit_ST7789`).

Document the engineering reason:

> Use the UNO Q's native hardware SPI instead of relying on software bit-banging for the final integration path.

---

# 6. DISPLAY VERIFICATION

Document that the ST7789 display was successfully brought up after resolving:

* Library/compiler compatibility
* Physical wiring fault
* SPI implementation issues

Verify/document:

* Display initialization (`tft.init(240, 320)`)
* 240 × 320 native resolution
* 320 × 240 landscape operation (`tft.setRotation(1)`)
* Pixel rendering
* Color output
* UI rendering (`fillScreen(ST77XX_BLACK)`, title `"Touch Diagnostics"`, horizontal divider line `drawFastHLine`)

---

# 7. COLOR MATRIX CORRECTION

Document the observed color-order problem.

The ST7789 display initially exhibited an inverted/incorrect color matrix.

The display configuration was corrected (`tft.invertDisplay(false)`) to produce the intended FieldSense dark-mode UI.

Final result:

```text
ST7789
   ↓
Correct color interpretation
   ↓
FieldSense dark-mode UI
```

---

# 8. XPT2046 TOUCH INTEGRATION

Document the touch subsystem:

```text
XPT2046
   ↓
Resistive touch ADC
   ↓
UNO Q SPI
   ↓
Touch coordinates
   ↓
320 × 240 UI coordinates
```

The touch controller provides analog 12-bit coordinate values which were mapped to the display's:

```text
320 × 240
```

coordinate system.

Coordinate remapping and noise filtering implemented in `sketch.ino`:

* **Raw ADC Mapping Range:** `map(p.x, 200, 3700, 320, 0)` and `map(p.y, 200, 3700, 240, 0)`
* **Boundary Constraining:** `constrain(mapped_x, 0, 320)` and `constrain(mapped_y, 0, 240)`
* **Z-Axis Pressure Filtering:** Noise/floating threshold filtering (`if (p.z < 400 || p.z > 4000)`) to ignore floating noise or lifted finger artifacts.
* **Rotation Alignment:** `ts.setRotation(1)` matched with `tft.setRotation(1)`.

Document that coordinate remapping/calibration was required to align physical touch positions with the UI.

---

# 9. TOUCH HARDWARE DEFECT / PHYSICAL OBSERVATION

Document the discovered mechanical issue:

> A mechanical lamination pinch in the display's outer bezel was identified as causing phantom Z-axis touch inputs near the center of the screen.

This is a physical observation from the integration test.

Document its effect:

```text
Physical bezel/lamination issue
        ↓
Phantom touch / Z-axis behavior
```

Resolution/status:

```text
Phase 1 prototype:
ACCEPTED

Final field hardware:
REQUIRES HARDWARE REVISION
```

Recommended future direction:

> Evaluate capacitive-touch displays for final FieldSense units.

Do NOT describe this as a software bug.

---

# 10. QUALITY CONTROL / RISK ASSESSMENT

Create a section documenting the following risks:

| Issue                      | Cause                                | Resolution             | Final Status               |
| -------------------------- | ------------------------------------ | ---------------------- | -------------------------- |
| White screen               | Faulty jumper                        | Replaced jumper        | Resolved                   |
| Library/compiler collision | UNO Q / legacy library compatibility | Header workaround      | Resolved for prototype     |
| SPI data integrity         | Software SPI / breadboard effects    | Native hardware SPI    | Resolved                   |
| Color inversion            | ST7789 color configuration           | Corrected              | Resolved                   |
| Touch coordinate mismatch  | Coordinate orientation/scaling       | Remapped               | Resolved                   |
| Phantom Z input            | Mechanical lamination pinch          | Accepted for prototype | Hardware revision required |

---

# 11. FINAL DATA PATH

Include:

```text
┌───────────────────────┐
│ Arduino UNO Q         │
│ Hardware SPI          │
└──────────┬────────────┘
           │
           ├──────────────→ ST7789
           │                 Display
           │
           └──────────────→ XPT2046
                             Touch
```

Then:

```text
Touch
  ↓
Raw ADC coordinates
  ↓
Coordinate remapping
  ↓
320 × 240 UI coordinates
  ↓
FieldSense interface
```

---

# 12. VERIFIED RESULT

Create a clear final result section:

```text
Component:
2.8" ST7789 TFT + XPT2046 Touch

Host:
Arduino UNO Q

Display:
🟢 VERIFIED

Touch:
🟢 VERIFIED

Hardware SPI:
🟢 VERIFIED

UI rendering:
🟢 VERIFIED

Touch coordinate mapping:
🟢 VERIFIED

Prototype mechanical issue:
🟡 ACCEPTED — hardware revision recommended
```

---

# 13. WHAT THIS TEST PROVES

This integration verifies:

* UNO Q can communicate with the ST7789 through hardware SPI
* TFT display can render the FieldSense interface
* Correct display orientation can be achieved
* Color rendering can be configured correctly
* XPT2046 touch input can be read
* Touch coordinates can be mapped to the UI
* Native hardware SPI provides the required integration path
* Physical wiring faults can be isolated and resolved
* The TFT/touch subsystem can operate on the UNO Q

---

# 14. WHAT THIS TEST DOES NOT PROVE

Do NOT claim this test proves:

* Long-term TFT reliability
* Outdoor sunlight readability
* Final enclosure durability
* Waterproofing
* Final touch accuracy certification
* Final production display selection
* Full FieldSense system integration

The bezel/lamination issue must remain documented as a prototype hardware risk.

---

# 15. FINAL STATUS

End with:

```text
2.8" ST7789 + XPT2046 + Arduino UNO Q

Integration:
🟢 VERIFIED

Display:
🟢 PASS

Touch:
🟢 PASS

Hardware SPI:
🟢 PASS

FieldSense UI:
🟢 PASS

Mechanical touch issue:
🟡 Prototype limitation
```

State clearly:

> The TFT subsystem is functionally integrated with the Arduino UNO Q for FieldSense V1 prototyping. A capacitive-touch display should be evaluated for the final hardware revision because of the observed mechanical lamination/phantom-touch issue.
