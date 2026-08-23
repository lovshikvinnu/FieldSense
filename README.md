# FieldSense AI

**Offline, portable edge-intelligence platform for multi-point soil assessment and Carbon Readiness.**

Walk a field taking GPS-tagged soil readings at ~25 points. FieldSense builds a colour-coded field map, splits the field into contiguous management zones, and tells the farmer which zones need attention — all computed locally on an embedded Linux board, with **no internet and no cloud**.

It is an *instrument*, not a web app.

---

## Status

| Layer | State |
| :--- | :--- |
| Deterministic software pipeline (8 stages) | ✅ Complete — 178 tests passing |
| AI explanation layer (`fieldsense/ai/`) | ✅ Complete — runs on templates; model weights optional |
| Offline dashboard UI (240×320 + desktop) | ✅ Complete |
| Component hardware bench tests | ✅ JXBS · MAX485 · NEO-M8N · TFT+touch · UNO Q all verified |
| Soil sensor → MAX485 → UNO Q integration | ✅ Verified end-to-end |
| GPS / TFT wired to UNO Q | ⚠️ `PENDING HARDWARE` — pin assignment not yet fixed |
| TFT showing the dashboard | ❌ **Not yet possible — see [Known Gaps](#known-gaps)** |

---

## Quick Start

Python 3.10+. The core package has **zero runtime dependencies** — standard library only.

```bash
python3 -m pip install -e ".[dev]"
```

Run the full pipeline and generate the offline dashboard:

```bash
python3 -m fieldsense.demo
```

Open `artifacts/fieldsense_competition_demo.html` in any browser.

Run the test suite:

```bash
python3 -m pytest -q
```

Hardware bench scripts need one extra package (not required for anything above):

```bash
python3 -m pip install pyserial
```

---

## How It Works

A **linear 8-stage pipeline**. Data enters at stage 1 and flows one way to stage 8. No feedback, no shared mutable state.

```
 STAGE 1        STAGE 2         STAGE 3          STAGE 4
┌─────────┐   ┌──────────┐   ┌─────────────┐   ┌──────────────┐
│ Sensor  │──>│Validation│──>│Intelligence │──>│   Spatial    │
│ Adapter │   │  Engine  │   │   Engine    │   │    Engine    │
│ acquire │   │physically│   │normalise +  │   │lat/lon → x,y │
│ samples │   │plausible?│   │MCDA scoring │   │IDW raster    │
└─────────┘   └────┬─────┘   └─────────────┘   └──────┬───────┘
                   │                                   │
             rejected samples                          ▼
             kept for audit,               ┌──────────────────────┐
             excluded from maps            │  STAGE 5: Zones      │
                                           │  4-neighbour BFS     │
                                           └──────────┬───────────┘
                    STAGE 8         STAGE 7           ▼
              ┌───────────────┐  ┌─────────────┐  ┌──────────────────┐
              │LocalUIRenderer│<─│UIViewAdapter│<─│STAGE 6:          │
              │ HTML+CSS+SVG  │  │passive view │  │Recommendations   │
              └───────────────┘  └─────────────┘  └──────────────────┘
                        ▲
                        │  optional, out of band
              ┌─────────┴──────────┐
              │ fieldsense/ai/     │  narrates results in plain language;
              │ guarded narrative  │  cannot change a single number
              └────────────────────┘
```

### If you come from electronics rather than software

| ECE concept | FieldSense equivalent |
| :--- | :--- |
| Sensor front-end | JXBS 7-in-1 probe over RS485 / Modbus RTU |
| GPS receiver, NMEA parsing | NEO-M8N over UART |
| Signal conditioning / sanity limits | `ValidationEngine` — rejects impossible readings |
| Calibration curve | `Normalizer` — raw units → 0.0–1.0 optimality |
| Weighted sensor fusion | MCDA scoring → Soil Health index |
| 2-D field reconstruction from sparse probes | IDW spatial interpolation |
| Connected-component labelling | Zone detection via 4-neighbour BFS |
| HMI / front panel | Offline HTML + SVG dashboard |
| Hardware abstraction layer | `SensorAdapter` — virtual and physical are interchangeable |

---

## Directory Map

### Repository root

| Path | Responsibility |
| :--- | :--- |
| `fieldsense/` | The product. Pure-Python package, standard library only. |
| `tests/` | 147 automated tests. Pure software; no hardware required. |
| `hardware_test/` | Bench-test scripts and empirical test records for each physical component. Requires hardware. |
| `docs/` | Specifications, decision log, and test evidence. See [Documentation](#documentation). |
| `scripts/` | Operator entry points. `launch_display.sh` pushes the dashboard to the 2.8" panel. |
| `artifacts/` | Build output — generated dashboard and panel frames. Git-ignored; rebuild with `python3 -m fieldsense.demo`. |
| `pyproject.toml` | Packaging and pytest configuration. `dependencies = []` is deliberate. |

### `fieldsense/` — the pipeline, one package per stage

| Package | Responsibility | Stage |
| :--- | :--- | :--- |
| `domain/` | Pure data contracts: `FieldSample`, `FieldSession`, enums, `SensorAdapter` ABC. Depends on nothing. | — |
| `input/` | `VirtualSensorAdapter` — deterministic synthetic soil field for testing without hardware. | 1 |
| `hardware/` | `HardwareSensorAdapter`, `transport/` (RS485 ABC + mock), `gps/` (ABC + virtual/stub), `HardwareConfig`, adapter factory, and `display_bridge.py` for the 2.8" panel. | 1 |
| `intelligence/` | `validation/` (sanity gatekeeper), `normalization/` (raw → 0–1), `scoring/` (MCDA weights, Soil Health, N, Moisture, Carbon Readiness). | 2–3 |
| `spatial/` | lat/lon → local Cartesian metres, field bounds, grid generation, IDW interpolation (p = 2.0, 100 m max support). | 4 |
| `zones/` | 4-neighbour BFS connected components, small-region merging, primary-issue selection. | 5 |
| `recommendations/` | Rule engine plus six rule classes: nutrient, moisture, salinity, soil condition, carbon, monitoring. | 6 |
| `presentation/` | `UIViewAdapter` → `UIFieldView` → `LocalUIRenderer`. Compact-first HTML/CSS/SVG for the 240×320 panel, scaling up for desktop. Performs **zero** calculation. | 7–8 |
| `ai/` | Optional explanation layer. `LocalLLMAdapter` ABC, `MockAIAdapter` (templates), `LlamaCppAdapter` (GGUF via `llama.cpp`), `NarrativeGuard` safety filter, `AIAdapterFactory`. | out of band |
| `testing/` | Golden scenario datasets and the benchmark harness. Product code, not tests. | — |
| `storage/` | Persistence layer. 🚧 **Stub** — docstring only. Serialization currently lives on the models as `to_dict`/`from_dict`. | — |
| `application/` | Service orchestration. 🚧 **Stub** — docstring only. `demo.py` does this job today. | — |
| `demo.py` | End-to-end runner wiring all 8 stages plus the optional narrative. The best single map of the system. | — |

### `hardware_test/` — one folder per physical component

| Path | Component | Status |
| :--- | :--- | :--- |
| `soil sensor/` | JXBS-3001-TR 7-in-1 probe, standalone over USB-RS485 | ✅ Verified |
| `RS485/` | MAX485 transceiver module, transmit and receive paths | ✅ Verified |
| `GPS/` | u-blox NEO-M8N (`GY-GPSV3-NEO`) NMEA output | ✅ Verified |
| `TFT/` | 2.8" ST7789V display + XPT2046 resistive touch | ✅ Verified (on ESP32 bench host) |
| `arduino uno q/` | UNO Q boot, Linux MPU, STM32 MCU, RouterBridge IPC, UART loopback | ✅ Verified |
| `soil sensor with Max485-RS485/` | Full chain: JXBS → RS485 → MAX485 → STM32 → RouterBridge → Linux → Python | ✅ Verified |

Step-by-step instructions for all of these are in **[TESTING_GUIDE.md](TESTING_GUIDE.md)**.

---

## Hardware

| Component | Part | Role |
| :--- | :--- | :--- |
| Compute | Arduino UNO Q 4 GB (`ABX00173`) | QRB2210 MPU (Debian Linux) + STM32U585 MCU |
| Soil probe | JXBS-3001-TR 7-in-1 | N, P, K, pH, EC, moisture, temperature over Modbus RTU |
| Bus transceiver | MAX485 module (`HW-097`) | TTL ↔ RS485 differential. **No auto-direction — MCU drives DE/RE.** |
| GPS | u-blox NEO-M8N (`GY-GPSV3-NEO`) | Position fix over UART NMEA 0183 |
| Display | 2.8" SPI TFT, ST7789V + XPT2046 | 240×320 panel with resistive touch. **3.3 V logic only.** |
| Power | 3S 18650 pack + BMS → LM2596S buck | 12 V rail for the probe, 5 V for the board |
| Bench tools | FT232 USB-RS485, CH340 USB-TTL | Laptop-side testing without the UNO Q |

**Power rails:** probe 12 V (external), MAX485 5 V (UNO Q rail), GPS 3.3 V, TFT 3.3 V logic. All grounds common.

---

## Design Boundaries

These are deliberate and load-bearing. Do not "fix" them without a Contract Change Request ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) Part IV).

- **Deterministic core.** Same inputs → bit-identical outputs. Every number traces to an explicit formula and config constant.
- **No dosages, ever.** Recommendations are directional ("review nitrogen management"), never `kg/ha` or litres. Rule tables cannot emit a quantity.
- **Carbon Readiness is a proxy**, tagged `decision_support_only = True`, `evidence_level = "LIMITED"`, publishing its own missing inputs. FieldSense does not measure soil organic carbon or certify credits.
- **AI cannot compute.** The explanation layer only narrates. `NarrativeGuard` deterministically blocks any generated sentence containing a dose unit, an agrochemical name, a carbon claim, or a number absent from the deterministic context.
- **Zero dependencies.** `dependencies = []`. `llama.cpp` is invoked as an external binary via stdlib `subprocess`, never as a Python extension.

---

## Documentation

Eight documents, each with one job.

| Document | Contents |
| :--- | :--- |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | **How to test every component**, standalone and integrated, plus the test evidence register |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture · software specification · decision log · frozen contracts |
| [docs/HARDWARE.md](docs/HARDWARE.md) | Component specs, register maps, wiring, verification status |
| [docs/AI_DEPLOYMENT.md](docs/AI_DEPLOYMENT.md) | Part I: local SLM. Part II: display bridge to the 2.8" panel |
| [docs/PROJECT_HANDBOOK.md](docs/PROJECT_HANDBOOK.md) | Problem statement, users, value proposition, phases |
| [docs/STATUS.md](docs/STATUS.md) | Requirements matrix and every open specification item |
| [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) | Presentation walkthrough |
| [docs/DOCUMENTATION_AUDIT.md](docs/DOCUMENTATION_AUDIT.md) | Record of the documentation audit and cleanup |

`docs/archive/` holds the superseded Phase 1 documentation. History only — do not treat as current.

---

## Known Gaps

Tracked honestly rather than hidden. Full analysis in `docs/DOCUMENTATION_AUDIT.md`.

1. **TFT display bridge — software done, wiring pending.** The framebuffer route is implemented (`fieldsense/hardware/display_bridge.py`, `scripts/launch_display.sh`) and renders a verified pixel-exact 240×320 frame today. It cannot reach the panel until the display is moved from the STM32 to the **QRB2210 SPI bus** (`HW-04`), and until `fbtft` is confirmed present in the shipped kernel (`DSP-02`). See `docs/AI_LAYER_DEPLOYMENT.md` Part II.
2. **GPS and TFT are not yet wired to the UNO Q.** Both are verified standalone, on a CH340 adapter and an ESP32 respectively. UNO Q pin assignment is `PENDING HARDWARE`.
3. **Touch calibration matrix is not derived.** Raw ADC range ~500–3500 measured; the mapping to pixel coordinates is not yet computed.
4. **Hardware scripts are Windows-only.** They hardcode `COM8` / `COM10`. Running on the UNO Q needs `/dev/ttyUSB*` or `/dev/ttyS*`.
5. **Model weights are absent by default.** The AI layer runs on deterministic templates until a `.gguf` is installed. This is intended, not a defect.
