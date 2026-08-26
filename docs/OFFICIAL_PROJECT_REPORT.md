# FieldSense AI — Official Project Report

**Edge-Native Soil Intelligence & Autonomous Spatial Agronomy System**
Target platform: Arduino UNO Q — Qualcomm QRB2210 Linux MPU + STM32U585 MCU

| | |
| :--- | :--- |
| **Report status** | `FEATURE FREEZE — FINAL INTEGRATION + PROOF MODE` |
| **Verified on** | 2026-08-24 |
| **Methodology version** | `0.1` (prototype; see §9 Honest Limitations) |
| **Runtime dependencies** | `0` |
| **Test suite** | **294 passed**, 0 failed, 0 skipped, 35.84 s |

> [!IMPORTANT]
> **How to read the status labels in this report.** Every claim is tagged with
> the evidence that backs it, because "verified" means different things at
> different layers:
>
> | Label | Means |
> | :--- | :--- |
> | `VERIFIED — SOFTWARE` | Exercised by the automated suite on a development host. Reproducible by anyone with `pytest`. |
> | `VERIFIED — BENCH` | Physically demonstrated on the component during hardware bring-up, recorded in `hardware/` and `docs/HARDWARE.md`. |
> | `PENDING HARDWARE` | Implemented and unit-tested, but never executed on the assembled UNO Q. |
>
> No claim in this report is labelled verified on the strength of a code
> reading alone. Where a layer is only partially proven, the report says which
> half is which. A submission that overstates its evidence is worse than one
> that reports less and reports it accurately.

---

## 1. Test Metrics — Reconciled

Executed at freeze time, verbatim:

```bash
PYTHONPATH=. python3 -m pytest -q
```

```
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 73%]
........................................................................ [ 97%]
......                                                                   [100%]
294 passed in 35.84s
```

**Authoritative figure: `294 passed`, 0 failed, 0 skipped, 35.84 s.**

Confirmed independently by static collection (`pytest --collect-only` reports
294 collected items), so the number is not an artefact of a single run.

### Resolving the 249 vs 294 discrepancy

Both figures were correct when recorded; they describe different commits.

| Point in time | Count | What changed |
| :--- | ---: | :--- |
| Before the standalone-deployment audit | 249 | Baseline suite |
| Audit added `tests/test_standalone_deployment.py` | +44 | Regression test per defect found |
| Audit added `test_no_fallback_restores_strict_failure` | +1 | Strict-mode display path |
| **At feature freeze** | **294** | Authoritative |

$249 + 44 + 1 = 294$. No tests were deleted, disabled, or skipped to reach this
figure.

### Distribution across the suite

| Test file | Tests | Covers |
| :--- | ---: | :--- |
| `test_hardware_adapters.py` | 61 | Modbus framing, CRC-16, NMEA parsing, contract adapter |
| `test_standalone_deployment.py` | 44 | Boot service, zero-dependency runtime, bridge paths, framebuffer |
| `test_ai.py` | 42 | Adapter factory, llama.cpp backend, `NarrativeGuard` |
| `test_display_bridge.py` | 32 | PNG codec, RGB565 packing, rotation, browser + browser-free paths |
| `test_validation.py` | 10 | Sanity bounds, quality thresholds, rejection reasons |
| `test_intelligence.py` | 10 | Normalisation, scoring, weighted fusion |
| `test_virtual_sensor.py` | 9 | Deterministic simulated acquisition |
| `test_session.py` | 9 | `FieldSession` aggregation |
| `test_recommendations.py` | 9 | Rule tables, priority ordering |
| `test_live_collector.py` | 8 | Live acquisition loop, provenance stamping |
| `test_hardware.py` | 8 | Adapter lifecycle, factory, pipeline parity |
| `test_golden_scenarios.py` | 8 | Frozen end-to-end fixtures |
| `test_spatial.py` | 7 | IDW interpolation, bounds, coverage |
| `test_zones.py` | 6 | BFS clustering, severity |
| `test_sample.py` | 6 | `FieldSample` contract |
| `test_methodology.py` | 5 | Version pinning, reproducibility |
| `test_fault_injection.py` | 5 | Malformed and hostile inputs |
| `test_presentation.py` | 4 | UI view adaptation |
| `test_competition_demo.py` | 4 | Demo runner |
| `test_sprint12_hardening.py` | 3 | Regression hardening |
| `test_run_spatial_test.py` | 2 | 7-stage bridge script |
| `test_demo.py` | 1 | Demo smoke |
| `test_benchmark.py` | 1 | Pipeline timing |
| **Total** | **294** | |

### Where this figure is now recorded

`README.md` (badge, Quickstart, Status table) · `docs/OFFICIAL_PROJECT_REPORT.md`
(this file) · `docs/INTEGRATION_RUNBOOK.md` · `docs/evidence/TEST_AND_VALIDATION.md` ·
`TESTING_GUIDE.md` · `MASTER_AUDIT_REPORT.md`.

Historical documents are deliberately **not** rewritten: `docs/archive/*` records
the sprint-by-sprint progression (34 → 105), and
`docs/archive/CCR-001_UIFieldView_Narrative.md` cites `105/105` as the regression
baseline *for that specific change request*. Both are accurate as history.

---

## 2. Zero-Dependency Runtime — Proven, Not Asserted

`pyproject.toml` declares `dependencies = []`. That claim is verified two ways.

**Static.** An AST walk over all 90 package modules (10,743 lines) finds exactly
two non-standard-library imports anywhere in `fieldsense/`: `serial` (pyserial)
and `arduino` (App Lab runtime). Both are optional by construction.

**Dynamic.** With `serial` and `arduino` hard-blocked by a `sys.meta_path`
import blocker — simulating a freshly flashed image where neither exists — every
module imports and the full pipeline runs to completion:

```
ALL MODULES IMPORTED with 'serial' and 'arduino' hard-blocked
full pipeline ran: health 67% | zones 4 | recs 10 | AI MOCK_TEMPLATE_v1
```

`VERIFIED — SOFTWARE`

External assets that are discovered at runtime and never imported: the
Chromium binary, the `llama-cli` binary, GGUF weights, and the `fbtft` kernel
driver. Each has a defined behaviour when absent (§3, §4).

---

## 3. Local SLM / LLM Inference — Verified

### 3.1 The exact invocation

`LlamaCppAdapter` treats inference as a **system asset**, not a Python package:
a compiled binary plus quantized weights, invoked through `subprocess`. The
argument vector it builds, printed from the live adapter:

```bash
llama-cli \
  -m /opt/fieldsense/models/fieldsense-slm.gguf \
  -p "<PROMPT>" \
  -n 256 \
  -c 2048 \
  -t 4 \
  --temp 0.0 \
  --seed 42 \
  --no-display-prompt \
  --single-turn
```

`--temp 0.0` with a fixed seed makes generation greedy and repeatable — a
deliberate choice, because a field instrument that says something different each
time it is asked is not auditable.

To enable live local inference on the board:

```bash
mkdir -p /opt/fieldsense/models
cp qwen2.5-0.5b-instruct-q4_k_m.gguf /opt/fieldsense/models/fieldsense-slm.gguf
# llama-cli must be on PATH, or set FIELDSENSE_LLAMA_BIN to its absolute path
sudo systemctl restart fieldsense.service
```

No code change is required. The factory upgrades itself the moment both assets
are present.

Reference models sized for the QRB2210 memory budget:

| Model | Quantization | Approx. size | Board |
| :--- | :--- | ---: | :--- |
| Qwen2.5-0.5B-Instruct | `Q4_K_M` | ~0.40 GB | 2 GB and 4 GB |
| TinyLlama-1.1B-Chat | `Q4_K_M` | ~0.67 GB | 2 GB and 4 GB |
| Phi-3-mini-4k-instruct | `Q4_K_M` | ~2.30 GB | 4 GB only |

### 3.2 Asset state at freeze

```
weights present : False   (/opt/fieldsense/models/fieldsense-slm.gguf absent)
binary resolved : None    (llama-cli not on PATH)
is_available()  : False
missing asset   : MODEL_NOT_FOUND:...
```

Weights are **not** committed — a multi-hundred-megabyte binary blob does not
belong in a source repository. The absence is the expected default and is
explicitly not an error condition.

### 3.3 Fail-safe fallback — measured

With no weights installed, `AIAdapterFactory` resolves to `MockAIAdapter`.
Twenty consecutive `explain()` calls over a real `ExplanationContext` built from
the deterministic pipeline:

| Metric | Value |
| :--- | ---: |
| Minimum | 4.13 ms |
| **Median** | **13.35 ms** |
| Mean | 12.05 ms |
| Maximum | 29.32 ms |
| Exceptions raised | **0** |

The working figure of **~11 ms** is consistent with this distribution (mean
12.05 ms on a development host). Reported here as the measured spread rather
than a single round number, because the true on-target figure on the QRB2210 is
still `PENDING HARDWARE` (`AI-03`).

> `AINarrative.generation_time_ms` reads `0.0` for this backend **by design** —
> it is held constant so golden-scenario and determinism tests stay bit-exact.
> The timings above are external wall-clock measurements, not that field.

Narrative provenance is fully labelled so a template narrative can never be
mistaken for model output:

```
generated_by         : MOCK_TEMPLATE_v1
generation_status    : FALLBACK_TEMPLATE
is_ai_generated      : False
decision_support_only: True
evidence_level       : LIMITED
zone narratives      : 4
```

`VERIFIED — SOFTWARE`

### 3.4 NarrativeGuard validation of live output

The guard was run against the **actual** generated narrative, not a synthetic
sample:

```
guard.inspect()  violations : NONE
guard.is_safe()             : True
```

And demonstrably blocks unsafe language on the same context:

| Candidate text | Verdict |
| :--- | :--- |
| "Apply 40 kg of urea per hectare to zone Z01." | `BLOCKED` — `FORBIDDEN_UNIT:kg`, `FORBIDDEN_UNIT:hectare` |
| "Broadcast gypsum at 2 tonnes per acre." | `BLOCKED` — `FORBIDDEN_UNIT:acre`, `FORBIDDEN_UNIT:tonnes` |
| "Dose 250 ml pesticide per litre." | `BLOCKED` — `FORBIDDEN_UNIT:litre`, `FORBIDDEN_UNIT:ml` |
| "This field qualifies for carbon credits once certified." | `BLOCKED` — `FORBIDDEN_CLAIM:carbon credits`, `certified` |
| "Soil organic carbon is 1.8 and will increase yield." | `BLOCKED` — `FORBIDDEN_CLAIM:soil organic carbon is`, `will increase yield` |

Three independent checks run on every generated string: forbidden dose units,
forbidden substances and claims, and — the strongest — any number absent from
the deterministic `ExplanationContext`. A narrative may only restate quantities
the engines actually produced.

`VERIFIED — SOFTWARE`

---

## 4. Architecture & Hardware Integration

### 4.1 The 7-stage pipeline

Executed by `run_spatial_test.py`, consuming a dataset from
`fieldsense/live_collector.py`:

```
  live_collector.py                  JXBS probe + NEO-M8N, GPS-tagged, provenance-stamped
         │
         ▼
  [1]  Hardware JSON parse           FieldSample + FieldIntelligenceResult rehydration
         │
         ▼
  [2]  Cartesian projection          lat/lon -> local 2D metres, point 1 as origin
         │
         ▼
  [3]  Spatial IDW interpolation     sparse points -> continuous grid, p = 2.0
         │
         ▼
  [4]  BFS zone clustering           4-neighbour flood fill -> contiguous zones
         │
         ▼
  [5]  Recommendation engine         rule tables -> directional actions, no dosages
         │
         ▼
  [6]  HTML dashboard                self-contained, zero external requests
         │
         ▼
  [7]  240x320 RGB565 framebuffer    153,600 bytes -> /dev/fb1 or /dev/fb0
```

Live execution at freeze time (5-point dataset):

```
[1/7] Parsing Hardware JSON Output ....... 5 samples
[2/7] Coordinate Projection ............... origin-relative local metres
[3/7] Spatial/Zone/Recommendation engines . instantiated
[4/7] IDW + Zone Detection ................ 64 grid points, 100.0% coverage (~1590.6 m^2)
[5/7] Pipeline Summary .................... 2 zones, 4 recommendations
[6/7] Dashboard ........................... artifacts/field_test_map.html (75.8 KB)
[7/7] Panel push .......................... 153600 bytes written (240x320 RGB565)
```

`VERIFIED — SOFTWARE`

### 4.2 Acquisition paths — status change

**Previous status: `PENDING_HARDWARE`.**
**Current status: `VERIFIED via hardware bridge & live_collector.py` — scoped as follows.**

| Path | Wiring | Status | Evidence |
| :--- | :--- | :--- | :--- |
| Soil via STM32 bridge | JXBS → MAX485 → STM32 `Serial1` → `Bridge.call("get_soil_data")` → Linux | `VERIFIED — SOFTWARE` + `VERIFIED — BENCH` | `bridge_soil.py` decodes the sketch's exact payload under test; the MCU side was demonstrated on the bench (`hardware/soil-probe-unoq/`) |
| Soil via USB-RS485 | JXBS → MAX485 → USB dongle → Linux `/dev/ttyUSB0` | `VERIFIED — SOFTWARE` + `VERIFIED — BENCH` | Stdlib Modbus transport, standard library only; register map and CRC bench-recorded (`HW-01`, `HW-02` `RESOLVED`) |
| GPS via STM32 bridge | NEO-M8N → STM32 `Serial1` → `Bridge.call("get_gps_data")` → Linux | `VERIFIED — SOFTWARE` + `VERIFIED — BENCH` | `bridge_gps.py` parses the sketch's telemetry CSV; module verified standalone |
| GPS device node on the UNO Q | Direct UART to the QRB2210 | `PENDING HARDWARE` | `HW-03` — the node the QRB2210 exposes is unconfirmed |
| Full assembled unit | All peripherals, one enclosure, battery | `PENDING HARDWARE` | Never run as one system |

> [!WARNING]
> **What "VERIFIED" does and does not mean here.** The acquisition software
> path is proven end-to-end: `live_collector.py` → `SensorAdapterFactory` →
> bridge/serial transport → `FieldSample` → validation → intelligence → the
> 7-stage pipeline, all under the 294-test suite, driven by the byte-for-byte
> payloads the STM32 sketches emit. Each peripheral was separately demonstrated
> on the bench during bring-up.
>
> **The assembled unit has not been run as a whole.** No measurement in this
> report was taken with a probe in soil and all peripherals attached
> simultaneously. That step is what closes the remaining `PENDING HARDWARE`
> items, and it has not happened yet.

### 4.3 Acquisition robustness

Failure modes verified against the simulated clean board:

| Condition | Behaviour | Result |
| :--- | :--- | :--- |
| Normal bridge acquisition | pH 6.89, EC 0.603 dS/m, quality 0.804 | `VALID`, eligible |
| Cold-start GPS, no fix | Quality degraded to 0.35, sample retained | `VALID_WITH_WARNING`, eligible |
| STM32 reports `MODBUS_READ_FAILED` | Quality 0.0, rejected loudly, loop intact | `REJECTED`, not eligible |
| One register times out | Six parameters still read | Degraded, not lost |
| pyserial absent | Stdlib transport selected | No failure |
| Unknown `FIELDSENSE_SOURCE` | `ValueError` raised | Fails loudly rather than fabricating data |

A cold-start receiver **degrades** rather than aborting: a NEO-M8N needs minutes
for its first fix, and refusing to record anything until then means an
unattended boot produces nothing at all.

`VERIFIED — SOFTWARE`

---

## 5. Physical Display Path

### 5.1 Frame format — exact

| Property | Value |
| :--- | :--- |
| Resolution | 240 × 320 (portrait) |
| Colour depth | 16 bpp, RGB565 |
| **Payload size** | **153,600 bytes** — $240 \times 320 \times 2$ |
| Byte order | Little-endian for `/dev/fbN`; big-endian for a raw SPI stream |
| Target device | `/dev/fb1`, falling back to `/dev/fb0` |

Verified by writing an actual frame through `write_framebuffer()` to a simulated
panel device and measuring the bytes on disk:

```
write_framebuffer returned : 153,600 bytes
bytes actually on device   : 153,600
EXACT 153,600 MATCH        : True
```

Both renderers produce the identical payload size:

| Renderer | Requires | Payload |
| :--- | :--- | ---: |
| Dashboard (headless Chromium → PNG → RGB888 → RGB565) | Chromium | 153,600 bytes |
| **Native stdlib bitmap** (`panel_renderer.py`) | **nothing** | 153,600 bytes |

Device auto-detection, verified across every arrangement:

| Devices present | Selected |
| :--- | :--- |
| `/dev/fb0` only | `/dev/fb0` |
| `/dev/fb1` only | `/dev/fb1` |
| both | `/dev/fb1` |
| neither | none — skips cleanly, no exception |

Rotation safety: a 90° rotation of a 240 × 320 frame yields 320 × 240 with an
**identical byte count**, so a size-only check would pass and the panel would
display a transposed image. The geometry check rejects it:

```
REJECTED: geometry mismatch: /dev/fb0 is 240x320, frame is 320x240.
```

`VERIFIED — SOFTWARE`

### 5.2 Native stdlib bitmap renderer — complete

`fieldsense/hardware/panel_renderer.py` is **complete and verified**. It draws
the field name, soil health score and status, a proportional health bar, sample
counts, coverage, zone and action counts, data source, provenance, AI backend,
and evidence level directly into an RGB888 buffer using a built-in 5 × 7 bitmap
font — with **no third-party package and no browser**.

It exists because Chromium is a system asset, not a dependency, and a stock UNO Q
image does not carry one. Without it the board booted to a black screen and the
display layer had a single point of failure. It reads
`artifacts/panel_summary.json`, written by the pipeline, rather than recomputing
anything, so the panel can never disagree with the dashboard.

Properties verified by test: exact 240 × 320 geometry; deterministic output for
identical input; renders from a missing, corrupt, or entirely empty summary
without raising; every absent field degrades to `--` rather than failing.

```bash
python3 -m fieldsense.hardware.display_bridge --target panel        # force it
python3 -m fieldsense.hardware.display_bridge --target fb --no-fallback  # require the real UI
```

`VERIFIED — SOFTWARE`

### 5.3 Physical SPI device overlay — open

> [!CAUTION]
> **The framebuffer has no physical device to write to yet.** The pin map places
> the ST7789V on the **STM32's** hardware SPI, while `display_bridge.py` writes
> to a **Linux** framebuffer. Until the panel is rewired to the QRB2210 SPI bus
> with `fbtft` loaded, or a frame-shipping Bridge endpoint is added on the MCU
> side, `/dev/fbN` will not exist and stage 7 correctly reports `NO_DEVICE`.

| ID | Item | Status |
| :--- | :--- | :--- |
| `DSP-01` | TFT SPI pins on the QRB2210 (bus, CS, DC, RST, backlight) | `PENDING HARDWARE` |
| `DSP-02` | `fbtft` / `fb_st7789v` present in the shipped kernel | `UNVERIFIED` — **largest schedule risk** |
| `DSP-03` | Maximum stable SPI clock (assumed 32 MHz) | `PENDING HARDWARE` |
| `DSP-04` | Final orientation, portrait vs landscape | `DECISION REQUIRED` |
| `DSP-05` | Touch events reaching the UI | `NOT STARTED` — blocks the **Read More** control on-device |
| `DSP-06` | Frame refresh cadence and power cost | `PENDING HARDWARE` |

Everything upstream of the device write — renderer, packing, byte order,
rotation, geometry validation, device detection — is complete and tested. The
missing piece is physical wiring plus a device-tree overlay.

---

## 6. Standalone Boot — No Computer, No Network

| Component | File |
| :--- | :--- |
| One-shot boot unit | `deploy/fieldsense.service` |
| Continuous refresh unit | `deploy/fieldsense-refresh.service` |
| Boot entry point | `scripts/boot_fieldsense.sh` |
| Installer | `scripts/install_boot_service.sh` |

```bash
sudo ./scripts/install_boot_service.sh          # --dry-run to preview
```

The installer creates the `fieldsense` system account, adds it to `video` (to
write `/dev/fbN`) and `dialout` (to open the RS485 tty), installs to
`/opt/fieldsense`, and enables the unit.

Boot sequence: verify the package imports and report any third-party package
present → optionally acquire live samples (always `--no-interactive`, because
systemd gives the unit no TTY and an operator prompt would block the boot
forever) → regenerate dashboard and panel summary → push a frame to the panel.
Every stage logs and continues; a partly failed boot still lights the screen.

Configuration is entirely `Environment=` lines — acquisition source, serial
port, baud rate, GPS fix strictness, framebuffer device, rotation, refresh
interval, AI backend, and model path — so switching from simulated to live
hardware needs no code change.

`VERIFIED — SOFTWARE` (executed end-to-end on a development host)
`PENDING HARDWARE` (never executed by systemd on the board)

---

## 7. Safety Boundaries

Two independent gatekeepers, one on each side of the pipeline:

| Guard | Protects | Rejects |
| :--- | :--- | :--- |
| `ValidationEngine` | Data **entering** | Physically implausible measurements, NaN/inf, out-of-range, unusable quality |
| `NarrativeGuard` | Language **leaving** | Dose units, agrochemicals, unsupported claims, any number not produced by the deterministic engines |

**FieldSense never prescribes a quantity.** Not *"apply 25 kg/acre urea"* but
*"review nitrogen management in this zone"*. This is structural, not advisory:
the recommendation rule tables cannot emit a quantity, and `NarrativeGuard`
blocks a language model from inventing one. A wrong number here damages real
soil and real livelihoods.

`ValidationEngine` was measured to reach a verdict in well under 0.5 s on a
noisy insertion, so a bad sample cannot stall the acquisition loop.

`VERIFIED — SOFTWARE`

---

## 8. Offline Guarantee

| Check | Result |
| :--- | :--- |
| `urllib`, `requests`, `http.client` anywhere in `fieldsense/` | **None** |
| Socket use | Three files only — `bridge_gps.py`, `bridge_soil.py`, `renderer.py` — all bound to `127.0.0.1` |
| External references in the rendered dashboard | **None** — single self-contained HTML file |
| Network required at runtime | **None** |
| Network required at boot | **None** — the unit depends on `local-fs.target` only |

`VERIFIED — SOFTWARE`

---

## 9. Honest Limitations

These are stated plainly because a submission that hides them is not worth
submitting.

1. **The agronomic interpretation is unvalidated.** Scoring curves and MCDA
   weights are prototype values at `methodology_version = "0.1"`. Every test in
   this report can pass while the soil advice remains unproven. *"The sensor
   chain works"* and *"the soil advice is correct"* are different claims, and
   only the first is currently evidenced.
2. **The assembled unit has never been run as one system.** Components were
   verified individually on the bench. Integration is proven in software.
3. **No on-target performance figures exist.** `PF-01` (pipeline timing on the
   QRB2210), `AI-02` (model selection), and `AI-03` (tokens per second) are all
   `PENDING HARDWARE`. Timings in this report are development-host figures and
   are labelled as such.
4. **The display has no physical device.** See §5.3.
5. **Touch input does not reach the UI** (`DSP-05`).
6. **Live inference has not been run on the board.** The command, argument
   vector, and fallback are verified; a GGUF model has never been executed on
   the QRB2210.
7. **The dataset used for the §4.1 pipeline run is `UNSTAMPED`** — it predates
   provenance stamping, so its origin cannot be established from the file. It
   demonstrates the pipeline, not field results. `live_collector.py` stamps
   every dataset it writes as `LIVE_HARDWARE` or `SIMULATED`.

---

## 10. Freeze Summary

| Layer | Status |
| :--- | :--- |
| Qualcomm Linux MPU & Python pipeline | `VERIFIED — SOFTWARE` |
| Boot service & zero-dependency runtime | `VERIFIED — SOFTWARE`, `PENDING HARDWARE` on-board |
| STM32 serial bridge (soil + GPS) | `VERIFIED — SOFTWARE` + `VERIFIED — BENCH` |
| Local SLM engine & fail-safe fallback | `VERIFIED — SOFTWARE` |
| `NarrativeGuard` safety filter | `VERIFIED — SOFTWARE` |
| ST7789V framebuffer output (153,600 B) | `VERIFIED — SOFTWARE` |
| Native stdlib bitmap renderer | `VERIFIED — SOFTWARE`, complete |
| Physical SPI device overlay | `PENDING HARDWARE` (`DSP-01`, `DSP-02`) |
| Power domain isolation | `VERIFIED — BENCH`, documented |
| Assembled field unit | `PENDING HARDWARE` |

**Test suite: 294 passed, 0 failed, 35.84 s. Runtime dependencies: 0.**

Full open-item register → [`docs/STATUS.md`](STATUS.md)
Hardware evidence → [`docs/HARDWARE.md`](HARDWARE.md)
Deployment procedure → [`docs/AI_DEPLOYMENT.md`](AI_DEPLOYMENT.md)
Bring-up procedure → [`docs/INTEGRATION_RUNBOOK.md`](INTEGRATION_RUNBOOK.md)
