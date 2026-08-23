# FieldSense AI — Status & Open Items

What is built, what is verified, and what is still undecided. Consolidates the
former `PROPOSAL_ALIGNMENT.md` and `SPECIFICATION_REGISTER.md`.

**Regression baseline:** 178 tests passing.

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
| **Display Bridge** | HTML dashboard → RGB565 → framebuffer | `IMPLEMENTED` | `fieldsense/hardware/display_bridge.py` |
| **Hardware Boundary** | `HardwareSensorAdapter`, `SensorTransport`, `GPSAdapter` | `IMPLEMENTED` | `fieldsense/hardware/` |
| **Physical Acquisition** | JXBS → MAX485 → UNO Q → RouterBridge → Python | `VERIFIED` | `hardware_test/soil sensor with Max485-RS485/` |
| **GPS on UNO Q** | NEO-M8N wired to the board | `PENDING_HARDWARE` | verified standalone only |
| **Display on UNO Q** | Panel wired to QRB2210 SPI | `PENDING_HARDWARE` | verified standalone on ESP32 |

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
| `HW-04` | UNO Q pin ownership (QRB2210 vs STM32U585) | STM32 owns RS485 via `Serial1` + GPIO 7 (verified). GPS and display pins unassigned | Assign GPS UART and display SPI pins | Embedded Eng | `PARTIALLY RESOLVED` |

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
| `AI-01` | `llama-cli` flag compatibility | `--no-display-prompt`, `-no-cnv` | Verify against the installed llama.cpp release | `HARDWARE_SPEC_REQUIRED` |
| `AI-02` | Model selection for the 4 GB UNO Q | Qwen2.5-0.5B / TinyLlama-1.1B class | Benchmark on QRB2210 | `PENDING_HARDWARE` |
| `AI-03` | On-target tokens per second | Estimated from the memory-bandwidth bound | Measure physically | `PENDING_HARDWARE` |
| `AI-04` | Prompt phrasing per model family | Generic instruct-style prompt | Tune to the selected model's chat template | `PROTOTYPE_ONLY` |

---

## 6. Display Bridge

| ID | Description | Current Position | Required Decision | Status |
| :--- | :--- | :--- | :--- | :--- |
| `DSP-01` | TFT SPI pins on the QRB2210 | Unassigned | Assign bus, CS, DC, RST, backlight | `PENDING_HARDWARE` |
| `DSP-02` | `fbtft` / `fb_st7789v` in the shipped kernel | Unverified | **Check first — biggest schedule risk** | `UNVERIFIED` |
| `DSP-03` | Maximum stable SPI clock | Assumed 32 MHz, fall back to 16 MHz | Measure with the production cable | `PENDING_HARDWARE` |
| `DSP-04` | Final orientation | Portrait 240×320 implemented | Portrait vs landscape 320×240 | `DECISION REQUIRED` |
| `DSP-05` | Touch input reaching the UI | Raw ADC range measured; no calibration matrix | Derive matrix, route events to the page | `NOT STARTED` |
| `DSP-06` | Frame refresh cadence & power cost | `watch` mode default 30 s | Measure | `PENDING_HARDWARE` |

> `DSP-05` blocks the dashboard's **Read More** control on the device. Until touch
> events reach the page the panel is display-only.
