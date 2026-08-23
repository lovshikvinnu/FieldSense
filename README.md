<div align="center">

# FieldSense AI

### Edge-Native Soil Intelligence & Autonomous Spatial Agronomy System

**Built by Lovshik Vinnu & Neha Priya**
*Electronics & Communication Engineering*

![Tests](https://img.shields.io/badge/tests-231%20passing-10b981?style=flat-square)
![Dependencies](https://img.shields.io/badge/runtime%20dependencies-0-3b82f6?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-f59e0b?style=flat-square)
![Offline](https://img.shields.io/badge/network-not%20required-8b5cf6?style=flat-square)
![Platform](https://img.shields.io/badge/target-Arduino%20UNO%20Q%20%C2%B7%20QRB2210-64748b?style=flat-square)

*A portable instrument that reads soil at many points across a field, works out which patches need attention, and explains it in plain language — entirely offline, on a battery-powered board you can carry.*

</div>

---

## The Problem

A farmer treats a field as one uniform thing. Fertiliser goes on at a single rate, everywhere.

Fields are not uniform. One corner is nitrogen-starved while another is already saturated. Spreading a single rate across all of it means **half the field is underfed and half is over-fertilised**. The over-fertilised half is the expensive part: surplus nitrogen leaches into groundwater, salts accumulate, soil structure degrades, and next season needs *more* input to get the same yield. It is a loop that gets worse each cycle.

Laboratory soil testing would resolve it, but the economics do not work. Samples go to a lab, results come back in one to two weeks, and the cost per sample means a farmer takes two or three for an entire field — far too coarse to see the variation that matters.

## The Solution

**Measure many points, map the variation, and act on patches instead of the whole field.**

FieldSense is a handheld probe plus a small Linux board. You walk the field taking GPS-tagged readings — roughly 25 points across a plot. At every point it captures **nitrogen, phosphorus, potassium, pH, electrical conductivity, moisture and temperature** in seconds.

The board then does the work a lab would do, on the spot:

| Step | What happens |
| :--- | :--- |
| **Reject bad readings** | A physically impossible value never reaches the map |
| **Reconstruct the field** | Inverse-distance interpolation turns ~25 sparse points into a continuous surface |
| **Find the patches** | Connected-component clustering groups neighbouring cells into management zones |
| **Say what to do** | Deterministic rules produce directional guidance per zone |
| **Explain it** | An optional on-device language model puts it in plain sentences |

Results appear on a 2.8-inch screen **before you leave the field**. No signal, no subscription, no cloud.

> **What it deliberately does not do.** FieldSense never prescribes a dosage. No *"apply 25 kg/acre urea."* It says *"review nitrogen management in this zone."* A wrong number here damages real soil and real livelihoods, so quantities are structurally impossible to emit — the rule tables cannot produce one, and a safety filter blocks the language model from inventing one. See [Design Boundaries](#design-boundaries).

---

## Hardware

![FieldSense Hardware Circuit Diagram](docs/hardware_circuit_diagram.png)

### Power — two isolated domains

The single most important wiring rule in this build.

| Domain | Source | Feeds |
| :--- | :--- | :--- |
| **A — 5 V** | USB power bank → UNO Q USB-C | The board, GPS, display |
| **B — 12 V** | 3S 18650 pack (3 × Li-ion + BMS) | **JXBS soil probe only** |

> ⚠️ **Never connect +12 V to any UNO Q pin.** The rails stay separate.
> **Grounds must be tied together** — RS485 is differential and needs a shared reference. Without that link you get silence or nonsense.

### Soil probe — JXBS-3001-TR (Modbus RTU / RS485)

```
JXBS probe ──> USB-RS485 adapter ──> UNO Q USB host  ──>  /dev/ttyUSB0
```

| Wire | Signal | Connects to |
| :--- | :--- | :--- |
| Brown | VCC | **+12 V** from the 18650 pack |
| Black | GND | Pack ground, tied to UNO Q ground |
| Yellow | RS485 **A** (D+) | Adapter terminal A |
| Blue / Green | RS485 **B** (D−) | Adapter terminal B |

`9600 8-N-1` · slave `0x01` · function `0x03` · seven holding registers.

### GPS — NEO-M8N (UART / NMEA 0183)

| Module pin | UNO Q |
| :--- | :--- |
| VCC | 5 V or 3.3 V |
| GND | GND |
| **TX** | **RX — Pin 0** (Serial1) |
| **RX** | **TX — Pin 1** (Serial1) |

> TX and RX **cross over**. Wiring them straight through is the most common reason a GPS looks dead.

### Display — 2.8" SPI TFT, ST7789V + XPT2046 touch

| Display pin | UNO Q |
| :--- | :--- |
| VCC | 3.3 V |
| GND | GND |
| CS | **D10** |
| RESET | **D8** |
| DC / RS | **D9** |
| SDI / MOSI | **D11** |
| SCK | **D13** |
| LED / BLK | 3.3 V |
| SDO / MISO | **D12** |

> ⚠️ **3.3 V logic only.** The power pin tolerates 5 V because of an onboard LDO — the **signal** lines do not, and no level shifters are fitted.
> ⚠️ The controller is **ST7789V**, not ILI9341. These boards are widely mislabelled and an ILI9341 driver will not initialise this panel.

Full electrical specifications, verified register maps and datasheet references: **[docs/HARDWARE.md](docs/HARDWARE.md)**

---

## The Interface

Compact-first. One HTML document serves the 240 × 320 panel and a laptop.

<div align="center">

| Field panel — 240 × 320 | AI insights drawer |
| :---: | :---: |
| <img src="docs/images/ui_panel_240x320.png" width="240" alt="FieldSense on the 2.8 inch panel"> | <img src="docs/images/ui_panel_ai_drawer.png" width="240" alt="Plain-language summary drawer"> |
| Score, colour-coded zone bar, field map, and a one-line teaser — all above the fold | Tapping **Read More** slides the explanation up **without covering the map** |

</div>

![FieldSense desktop dashboard](docs/images/ui_dashboard_desktop.png)

Run `python3 -m fieldsense.demo` and open `artifacts/fieldsense_competition_demo.html` in any browser — it is a single self-contained file with no external requests. The panel images above are generated straight from that same renderer, so what you see here is exactly what the hardware shows.

---

## Architecture

![FieldSense signal chain](docs/images/pipeline_architecture.png)

The hardware side and the software side are both **frozen**. An adapter layer is the only crossing point, and `FieldSample` is the only contract that crosses it.

```
   PHYSICAL TELEMETRY                                          FROZEN
   ┌──────────────────┬──────────────────┬──────────────────┐
   │ JXBS probe       │ NEO-M8N GPS      │ STM32 Bridge     │
   │ Modbus RTU       │ NMEA 0183        │ RouterBridge IPC │
   └────────┬─────────┴────────┬─────────┴────────┬─────────┘
            │                  │                  │
            ▼                  ▼                  ▼
   ┌─────────────────────────────────────────────────────────┐
   │  ADAPTER & CONTRACT LAYER      fieldsense/hardware/     │
   │                                                         │
   │  soil_adapter.py      CRC-16, registers, µS/cm → dS/m   │
   │  gps_adapter.py       checksum, DDMM.MMMM → decimal °   │
   │  hardware_sample_adapter.py    compose + quality score  │
   └───────────────────────────┬─────────────────────────────┘
                               ▼
                     ┌───────────────────┐
                     │   FieldSample     │   the sole boundary contract
                     └─────────┬─────────┘
                               ▼
   ┌─────────────────────────────────────────────────────────┐
   │  DETERMINISTIC INTELLIGENCE ENGINE    bit-exact <500 ms  │
   │  Validation → Intelligence → Spatial → Zones → Rules    │
   └──────────────┬───────────────────────────┬──────────────┘
                  ▼                           ▼
   ┌──────────────────────────┐   ┌──────────────────────────┐
   │  AI EXPLANATION          │   │  PRESENTATION            │
   │  local SLM / templates   │   │  UIViewAdapter           │
   │       ↓                  │   │       ↓                  │
   │  NarrativeGuard  ⛔      │   │  LocalUIRenderer         │
   │  blocks dosages,         │   │  offline HTML + SVG      │
   │  agrochemicals, carbon   │   │       ↓                  │
   │  claims, invented numbers│   │  display_bridge.py       │
   └──────────────────────────┘   └────────────┬─────────────┘
                                               ▼
                                   ┌───────────────────────┐
                                   │  RGB565 → /dev/fb1    │
                                   │  2.8" ST7789V panel   │
                                   └───────────────────────┘
```

### Documentation

| Document | What it covers |
| :--- | :--- |
| **[System Architecture](docs/ARCHITECTURE.md)** | Module contracts, algorithms, decision log, frozen contracts |
| **[Hardware Specs & Datasheets](docs/HARDWARE.md)** | Component specs, register maps, wiring, vendor references |
| **[Integration Runbook](docs/INTEGRATION_RUNBOOK.md)** | Four-step board bring-up: acquisition → contract → pipeline → display |
| **[Testing Guide](TESTING_GUIDE.md)** | How to test every component, plus the test evidence register |
| **[AI Deployment](docs/AI_DEPLOYMENT.md)** | Local SLM setup and the 2.8" display bridge |
| [Project Handbook](docs/PROJECT_HANDBOOK.md) | Purpose, users, development phases |
| [Status & Open Items](docs/STATUS.md) | Requirements matrix and every unresolved specification |
| [Demo Guide](docs/DEMO_GUIDE.md) | Presentation walkthrough |

---

## Quickstart

Python 3.10+. **No runtime dependencies** — standard library only.

```bash
python3 -m pip install -e ".[dev]"
```

**Run the tests** — 231 should pass:

```bash
python3 -m pytest -q
```

**Run the full pipeline** and generate the offline dashboard:

```bash
python3 -m fieldsense.demo
```

```
Samples:            25 Total | 24 Valid | 1 Rejected
Overall Health:     67% [MODERATE]
Zones Detected:     4 Spatially Connected Management Zones
Explanation Layer:  MOCK_TEMPLATE_v1 [FALLBACK_TEMPLATE] | Guard Blocks: 0
Dashboard Artifact: artifacts/fieldsense_competition_demo.html
```

The `1 Rejected` is deliberate — the dataset plants one unstable sample so you can watch the validation gatekeeper work.

**Push it to the 2.8" panel:**

```bash
./scripts/launch_display.sh
```

```bash
./scripts/launch_display.sh probe
```

`probe` reports what your machine can do and changes nothing. Run it first. On a laptop without the panel, `./scripts/launch_display.sh png` writes the exact 240 × 320 frame instead.

Hardware bench scripts need one extra package:

```bash
python3 -m pip install pyserial
```

---

## Repository Layout

| Path | Responsibility |
| :--- | :--- |
| `fieldsense/` | The product. Pure Python, standard library only. |
| `tests/` | 231 automated tests. No hardware required. |
| `hardware_test/` | Bench scripts and empirical test records per component. |
| `docs/` | Specifications, runbook, decision log, images. |
| `scripts/` | Operator entry points — `launch_display.sh`. |
| `artifacts/` | Generated dashboard output. Git-ignored; rebuild with `python3 -m fieldsense.demo`. |

### Inside `fieldsense/`

| Package | Responsibility | Stage |
| :--- | :--- | :--- |
| `domain/` | Pure data contracts: `FieldSample`, `FieldSession`, enums, `SensorAdapter` ABC. | — |
| `input/` | `VirtualSensorAdapter` — deterministic synthetic field for hardware-free testing. | 1 |
| `hardware/` | **Adapter & contract layer**: `gps_adapter.py`, `soil_adapter.py`, `hardware_sample_adapter.py`, `transport/`, `gps/`, `display_bridge.py`. | 1 |
| `intelligence/` | `validation/` gatekeeper, `normalization/`, `scoring/` MCDA indices. | 2–3 |
| `spatial/` | lat/lon → local metres, grid, IDW interpolation (p = 2.0, 100 m cap). | 4 |
| `zones/` | 4-neighbour BFS clustering, small-region merging, primary-issue selection. | 5 |
| `recommendations/` | Rule engine and six agronomic rule classes. | 6 |
| `presentation/` | `UIViewAdapter` → `UIFieldView` → `LocalUIRenderer`. Performs **zero** calculation. | 7–8 |
| `ai/` | `LocalLLMAdapter`, `MockAIAdapter`, `LlamaCppAdapter`, `NarrativeGuard`, factory. | out of band |
| `testing/` | Golden scenario datasets and the benchmark harness. | — |
| `storage/`, `application/` | 🚧 Planned. Docstring stubs only today. | — |

---

## Design Boundaries

Deliberate and load-bearing. Changing one requires a Contract Change Request — [ARCHITECTURE.md](docs/ARCHITECTURE.md) Part IV.

- **Deterministic core.** Identical inputs give bit-identical outputs. Every number traces to an explicit formula and a config constant.
- **No dosages, ever.** Recommendations are directional. The rule tables cannot emit `kg/ha` or litres.
- **Carbon Readiness is a proxy**, tagged `decision_support_only = True`, `evidence_level = "LIMITED"`, and it publishes its own missing inputs. FieldSense does not measure soil organic carbon or certify credits.
- **AI cannot compute.** The explanation layer only narrates. `NarrativeGuard` deterministically blocks any sentence containing a dose unit, an agrochemical name, a carbon claim, or a number absent from the deterministic context.
- **One adapter boundary.** Unit conversion happens once, in `fieldsense/hardware/`. The adapters never validate, score, or interpret.
- **Zero dependencies.** `dependencies = []`. `llama.cpp`, the browser and `pyserial` are optional *system assets*, shelled out to or imported lazily — never module-level. Serial I/O uses stdlib `termios`.

---

## Status

| Layer | State |
| :--- | :--- |
| Deterministic pipeline (8 stages) | ✅ Complete — 231 tests |
| Hardware → `FieldSample` adapter layer | ✅ Complete |
| AI explanation layer + safety guard | ✅ Complete — runs on templates; weights optional |
| Offline dashboard (240 × 320 + desktop) | ✅ Complete |
| Display bridge → RGB565 framebuffer | ✅ Complete |
| Component bench verification | ✅ JXBS · MAX485 · NEO-M8N · TFT+touch · UNO Q |
| Probe → MAX485 → UNO Q acquisition | ✅ Verified end-to-end |
| GPS wired to UNO Q | ⚠️ `HW-03` — UART node unconfirmed |
| Display wired to QRB2210 SPI | ⚠️ `DSP-01` / `DSP-02` — pins unassigned, `fbtft` unverified |
| Touch events reaching the UI | ⚠️ `DSP-05` — calibration matrix not derived |

### Honest limitations

The scoring curves and MCDA weights are **unvalidated prototype values** at `methodology_version = "0.1"`. Every hardware test above can pass while the agronomic interpretation remains unproven — *"the sensor chain works"* and *"the soil advice is correct"* are different claims, and only the first is currently evidenced.

Full register of open items: **[docs/STATUS.md](docs/STATUS.md)**

---

<div align="center">

**FieldSense AI** · Built for farmers who need answers in the field, not in two weeks.

</div>
