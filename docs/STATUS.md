# FieldSense AI — Status & Open Items

What is built, what is verified, and what is still undecided. Consolidates the
former `PROPOSAL_ALIGNMENT.md` and `SPECIFICATION_REGISTER.md`.

**Regression baseline:** 552 tests passing (2026-08-26).

> **Sections 4-6 predate the field-session work.** The `DSP-0x` entries below
> were written on 2026-08-25, before the panel moved to 320x240 landscape,
> before the touch controller was moved onto the pins the board's SPI actually
> reads, and before the operator-driven session existed. Where this register
> and [FIELD_SESSION.md](FIELD_SESSION.md) disagree about the panel or the
> START control, `FIELD_SESSION.md` is the later document. These entries are
> left as written rather than silently re-graded; re-verifying each one on the
> assembled unit is an open task in its own right.

---

## 1. Requirements Alignment

| Module | Requirement | Status | Evidence |
| :--- | :--- | :--- | :--- |
| **Domain** | Canonical `FieldSample` & `FieldSession` contracts | `IMPLEMENTED` | `fieldsense/domain/` |
| **Sensor** | `SensorAdapter` ABC & `VirtualSensorAdapter` | `IMPLEMENTED` | `fieldsense/input/` |
| **Validation** | Sanity gatekeeper (`VALID`, `VALID_WITH_WARNING`, `REJECTED`) | `IMPLEMENTED` | `fieldsense/intelligence/validation/` |
| **Intelligence** | Deterministic MCDA scoring on $[0,1]$ | `IMPLEMENTED` | `fieldsense/intelligence/scoring/` |
| **Carbon Readiness** | Decision-support signal, `decision_support_only = True` | `IMPLEMENTED` | `fieldsense/intelligence/scoring/models.py` |
| **Spatial Engine** | IDW ($p=2.0$), local metres projection, coverage | `IMPLEMENTED` | `fieldsense/spatial/` |
| **Zone Engine** | 4-neighbour BFS connectivity, primary issue selection | `IMPLEMENTED` | `fieldsense/zones/` |
| **Recommendations** | Traceable rule-based decision support, zero dosages | `IMPLEMENTED` | `fieldsense/recommendations/` |
| **Presentation** | Passive `UIFieldView` + offline HTML/CSS/SVG dashboard | `IMPLEMENTED` | `fieldsense/presentation/` |
| **Compact UI** | 240×320 panel layout scaling up to desktop | `IMPLEMENTED` | `fieldsense/presentation/renderer.py` |
| **AI Explanation** | Passive downstream narrative layer (`LocalLLMAdapter`) | `IMPLEMENTED` | `fieldsense/ai/` |
| **AI Safety Gate** | `NarrativeGuard` blocks dosages, agrochemicals, carbon claims, invented numbers | `IMPLEMENTED` | `fieldsense/ai/guard.py` |
| **Display Bridge** | HTML dashboard → RGB565 → PNG / framebuffer | `IMPLEMENTED` | `fieldsense/hardware/display_bridge.py` |
| **Panel Value Link** | Summary → `FS\|` record → router → MCU → `renderValues()` | `VERIFIED` | see §6a |
| **Hardware Boundary** | `HardwareSensorAdapter`, `SensorTransport`, `GPSAdapter` | `IMPLEMENTED` | `fieldsense/hardware/` |
| **Physical Acquisition** | JXBS → MAX485 → UNO Q → RouterBridge → Python | `VERIFIED` | `hardware/soil-probe-unoq/` |
| **GPS on UNO Q** | NEO-M8N wired to the board | `PENDING_HARDWARE` | verified standalone only |
| **Display on UNO Q** | Panel driven by the STM32, not the QRB2210 | `VERIFIED` | 2026-08-24 on hardware; see §6a |

### Boundary discipline

1. **Hardware independence** — `VirtualSensorAdapter` and `HardwareSensorAdapter` both emit canonical `FieldSample` objects. Downstream code cannot tell them apart.
2. **Offline operation** — all UI assets are embedded. No HTTP, no CDN, no map tiles.
3. **Agronomic boundary** — Carbon Readiness enforces `decision_support_only = True` and `evidence_level = "LIMITED"`. Fertilizer and irrigation quantities are prohibited in recommendations.
4. **AI boundary** — the explanation layer cannot alter a score, raster, zone, or recommendation. Generated language passes `NarrativeGuard` before display; any dose unit, agrochemical name, carbon claim, or number absent from the deterministic context is rejected and replaced by a deterministic template. Violations are recorded on `AINarrative.guard_violations` for audit rather than silently discarded.

---

## 2. Hardware Specifications

| ID | Description | Current Position | Required Decision | Owner | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `HW-01` | JXBS Modbus RTU register map | Empirically mapped: pH `0x0006`, moisture `0x0012`, temp `0x0013`, EC `0x0015`, NPK `0x001E`–`0x0020` | — | Hardware Eng | `RESOLVED` |
| `HW-02` | JXBS RS485 serial parameters | `9600` 8N1, slave `0x01`, function `0x03` | — | Hardware Eng | `RESOLVED` |
| `HW-03` | NEO-M8N UART device node on UNO Q | Assumed `/dev/ttyS0` or `/dev/ttyAMA0` | Confirm the node the QRB2210 exposes | Hardware Eng | `PENDING_HARDWARE` |
| `HW-04` | UNO Q pin ownership (QRB2210 vs STM32U585) | STM32 owns the display (CS 10, DC 9, RST 8, backlight 6) and the GPS (`Serial1`). RS485 `RE/DE` stays on D7 and nothing else may claim it. `Serial` is the RouterBridge Monitor, not a UART | — | `RESOLVED` |

---

## 3. Agronomic & Methodological Boundaries

| ID | Description | Current Position | Required Decision | Owner | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `AG-01` | Parameter scoring curves & optimum bands | JXBS verified ranges + prototype curves | Validate against field trial datasets | Lead Agronomist | `PROTOTYPE_ONLY` |
| `AG-02` | Soil health weighting vector ($\sum = 1.00$) | $0.20N + 0.15P + 0.15K + 0.20\text{pH} + 0.10\text{EC} + 0.20\text{Moisture}$ | Adjust for regional soil types | Lead Agronomist | `PROTOTYPE_ONLY` |
| `AG-03` | Carbon Readiness proxy weightings | Proxy index from pH, moisture, EC | Maintain `decision_support_only = True` | Lead Agronomist | `PROTOTYPE_ONLY` |

> Every hardware test can pass while the agronomic interpretation remains unproven.
> "The sensor chain works" and "the soil advice is correct" are different claims.

---

## 4. Platform Performance

| ID | Description | Current Position | Required Decision | Status |
| :--- | :--- | :--- | :--- | :--- |
| `PF-01` | Pipeline execution time | Host benchmark $< 80\text{ms}$ for 500 samples (development machine) | Benchmark on QRB2210 Debian | `PENDING_HARDWARE` |
| `PF-02` | Total system power draw & battery life | Never measured | Measure on the assembled instrument | `UNKNOWN` |

---

## 5. AI Explanation Layer

| ID | Description | Current Position | Required Decision | Status |
| :--- | :--- | :--- | :--- | :--- |
| `AI-01` | `llama-cli` flag compatibility | `--no-display-prompt`, `--single-turn` | `VERIFIED 2026-08-25` against llama.cpp 0.2.0-dev build 10615 (f280b2698) on the UNO Q. That build has no `-no-cnv`. | `RESOLVED` |
| `AI-02` | Model selection for the 4 GB UNO Q | Qwen2.5-0.5B / TinyLlama-1.1B class | Benchmark on QRB2210 | `PENDING_HARDWARE` |
| `AI-03` | On-target tokens per second | Estimated from the memory-bandwidth bound | Measure physically | `PENDING_HARDWARE` |
| `AI-04` | Prompt phrasing per model family | Generic instruct-style prompt | Tune to the selected model's chat template | `PROTOTYPE_ONLY` |

---

## 6. Display Bridge

| ID | Description | Current Position | Required Decision | Status |
| :--- | :--- | :--- | :--- | :--- |
| `DSP-01` | TFT SPI pins on the QRB2210 | Moot — the QRB2210 routes no SPI to the headers, so the panel is driven by the STM32 (CS 10, DC 9, RST 8, backlight 6; D7 stays MAX485_RE_DE) | — | `RESOLVED` |
| `DSP-02` | `fbtft` / `fb_st7789v` in the shipped kernel | Not applicable — no `/dev/fbN` for this panel can exist on the UNO Q, since no SPI reaches the QRB2210 headers | — | `RESOLVED` |
| `DSP-03` | Maximum stable SPI clock | Assumed 32 MHz, fall back to 16 MHz | Measure with the production cable | `PENDING_HARDWARE` |
| `DSP-04` | Final orientation | Portrait 240×320 implemented | Portrait vs landscape 320×240 | `DECISION REQUIRED` |
| `DSP-05` | Touch input reaching the UI | Raw ADC range measured; no calibration matrix | Derive matrix, route events to the page | `NOT STARTED` |
| `DSP-06` | Frame refresh cadence & power cost | `watch` mode default 30 s | Measure | `PENDING_HARDWARE` |

> `DSP-05` blocks the dashboard's **Read More** control on the device. Until touch
> events reach the page the panel is display-only.

---

## 6a. TFT Panel — Verification Status

Three separate claims. Only the first is verified, and conflating them would
overstate what the hardware has actually shown.

| Claim | Status | Evidence |
| :--- | :--- | :--- |
| TFT end-to-end pipeline (transport, MCU parser, `renderValues()`) | `VERIFIED` | 2026-08-24, UNO Q. `run_spatial_test.py --display bridge` pushed a record and the panel rendered it |
| TFT driven by real `LIVE_HARDWARE` pipeline data | `NOT YET VERIFIED` | the verifying run used a mock dataset — see below |
| Multi-location spatial mapping | `NOT YET VERIFIED` | every run so far is single-location or synthetic |

**The run that verified the transport did NOT use field measurements.** It read
`field_test_20260823_171931.json`, whose own output reports `PROVENANCE:
UNSTAMPED` and `Narrative: MOCK_TEMPLATE_v1 [FALLBACK_TEMPLATE]`, and whose
coordinates form a synthetic ~20 m grid. The numbers currently on the glass are
test values. They prove the wire, the parser and the renderer work. They are
**not** hardware evidence and must not be presented as field results.

Next validation, in order: re-run the same path against the `LIVE_HARDWARE`
dataset, then a 5-point multi-location field run so interpolation has distinct
positions to work with.

### What the panel path actually is

Pixel streaming to this panel is not viable and the measurement, not a hunch,
says so. `Serial` on the UNO Q is Arduino_RouterBridge's `Monitor`: one
`available()` costs ~595 ms — 1.68 calls/second measured over 247 seconds — so a
153,600-byte RGB565 frame would take about three minutes. The MCU therefore
draws the dashboard itself and the host sends it a ~76-byte `FS|` record.

Two properties of that link are worth keeping in mind when reading a failure:

- **The MCU pulls; it is never pushed to.** A record is collected only while a
  client is still connected, and the firmware polls roughly once a second. Both
  senders hold the socket open for `PANEL_HOLD_SECONDS` after writing.
- **A successful send is not a successful delivery.** TCP accepting the bytes
  says nothing about whether the MCU read them. Confirm on the glass.
