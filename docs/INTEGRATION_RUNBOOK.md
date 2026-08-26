# FieldSense AI — Integration Runbook

Bringing the assembled instrument up on the Arduino UNO Q, from a bare board to
a dashboard on the 2.8" panel. Four steps, each with a pass criterion. Do not
advance until the current step passes.

**Architecture rule this runbook follows:** the hardware side (STM32 firmware,
RouterBridge, JXBS Modbus) and the software side (Phase 1 engine, spatial IDW,
AI, UI) are **frozen**. Everything below exercises the *adapter layer* between
them. `FieldSample` is the sole boundary contract.

```
  STEP 1              STEP 2                STEP 3              STEP 4
  acquisition   ->    contract        ->    pipeline      ->    display
  GPS + soil          FieldSample           engine + AI         RGB565 panel
```

---

## Prerequisites

```bash
cd ~/FieldSense
python3 -m pip install -e ".[dev]"
python3 -m pytest -q          # expect: 294 passed
```

A green suite before touching hardware means every later failure is electrical
or configuration, not code. Skipping this makes debugging much harder.

Serial permissions, once:

```bash
sudo usermod -aG dialout $USER    # then log out and back in
ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyS*
```

| Component | Expected device | Status |
| :--- | :--- | :--- |
| JXBS probe via USB-RS485 | `/dev/ttyUSB0` | verified |
| JXBS probe via MAX485 on STM32 | RouterBridge `get_soil_data` | verified |
| NEO-M8N GPS | `/dev/ttyS0` or `/dev/ttyAMA0` | `HW-03` unconfirmed |
| 2.8" TFT | QRB2210 SPI | `DSP-01` unassigned |

---

## STEP 1 — Hardware acquisition

Prove each sensor answers, independently of the software stack.

### 1a. Soil probe

Power the probe from **12 V** (brown +, black −), RS485 yellow → A, blue → B,
and tie the 12 V supply ground to the board ground.

```bash
python3 "hardware/soil-probe/jxbs_test.py" --port /dev/ttyUSB0
```

Expected:

```
  ph           0x0006  raw=680        6.80 pH
  moisture     0x0012  raw=312       31.20 %
  temperature  0x0013  raw=243       24.30 degC
  ec           0x0015  raw=210      210.00 uS/cm
  nitrogen     0x001E  raw=42        42.00 mg/kg
  phosphorus   0x001F  raw=18        18.00 mg/kg
  potassium    0x0020  raw=95        95.00 mg/kg
  ec [conv]      0.2100 dS/m   (converted from 210.0 uS/cm for the software contract)
  parameters read: 7/7
```

**Pass:** all 7 parameters read, CRC clean, and **moisture changes** when you
move the probe between air and wet soil. A constant plausible number is not
proof of measurement — only a responding value is.

### 1b. GPS

```bash
python3 hardware/gps/test_gps.py --port /dev/ttyUSB0 --samples 5
```

Expected:

```
fix 1/5  lat=12.971600  lon=77.594600  sats=9  hdop=0.8  alt=545.4m
```

**Pass:** decimal-degree coordinates matching your actual location, `sats >= 5`,
`hdop <= 2`. Sentences streaming with no fix means the receiver is healthy and
cannot see satellites — go outdoors. Cold start takes minutes.

**If GPS is not yet wired to the UNO Q** (`HW-03` open), run this on a laptop
with the CH340 adapter and continue; step 2 tolerates a missing fix.

---

## STEP 1b — Choose the acquisition path

Three physical soil wirings are supported, and all three produce the same
`FieldSample`. Pick the one that matches your harness and set it once:

| `FIELDSENSE_SOURCE` | Probe wiring | Dependencies |
| :--- | :--- | :--- |
| `HARDWARE` | JXBS → MAX485 → USB-RS485 dongle → **Linux** `/dev/ttyUSB0` | Standard library only |
| `BRIDGE` | JXBS → MAX485 → **STM32** `Serial1` → RouterBridge `get_soil_data` | Standard library only; needs the MCU sketch flashed |
| `USB_PYSERIAL` | Same wiring as `HARDWARE` | Requires `pip install pyserial` |

GPS always arrives over the RouterBridge (`get_gps_data`), which the NEO-M8N
sketch provides.

```bash
export FIELDSENSE_SOURCE=HARDWARE          # or BRIDGE
export FIELDSENSE_SENSOR_PORT=/dev/ttyUSB0
export FIELDSENSE_REQUIRE_GPS_FIX=0        # cold start degrades, does not abort

python3 -c "
from fieldsense.hardware.factory import DataSourceConfig, SensorAdapterFactory
cfg = DataSourceConfig.from_env()
print(SensorAdapterFactory.describe_source(cfg))
"
```

> [!IMPORTANT]
> `HARDWARE` is the default physical path and needs **no third-party package**.
> `USB_PYSERIAL` exists only for the bench dongle setup that was verified with
> pyserial; it will fail on a freshly flashed image, where `dependencies = []`
> means pyserial was never installed.

### Verifying the STM32 soil bridge on its own

```bash
python3 -c "
from fieldsense.hardware import BridgeSoilAdapter
soil = BridgeSoilAdapter().read()
print('parameters read :', soil.parameters_read, 'of 7')
print('pH', soil.ph, '| moisture', soil.moisture, '%')
print('EC', soil.ec, 'dS/m  (raw', soil.ec_raw_us_cm, 'uS/cm)')
print('errors:', soil.read_errors or 'none')
"
```

The sketch reports its own Modbus failure in band as
`{"error":"MODBUS_READ_FAILED"}`. That becomes a fully degraded reading with
`parameters_read == 0`, not an exception, so the campaign continues and
`ValidationEngine` rejects the sample on its zeroed pH.

---

## STEP 2 — Contract adapter verification

Prove that telemetry becomes a `FieldSample` the frozen validator accepts. This
is the boundary crossing, and the step most likely to surface a unit mismatch.

```bash
python3 - <<'PY'
from fieldsense.hardware import (JXBSSoilAdapter, NMEAGPSAdapter,
                                 HardwareSampleAdapter)
from fieldsense.intelligence import ValidationEngine

soil_adapter = JXBSSoilAdapter.from_serial("/dev/ttyUSB0")
soil_adapter.initialize()
soil = soil_adapter.read()

# Swap for NMEAGPSAdapter.from_bridge() once GPS runs through the STM32.
gps_adapter = NMEAGPSAdapter.from_serial("/dev/ttyUSB1")
gps = gps_adapter.acquire_gps_data()

builder = HardwareSampleAdapter()
sample = builder.build_sample(gps, soil)

for key, value in builder.acquisition_report(gps, soil).items():
    print(f"  {key}: {value}")

result = ValidationEngine().validate(sample)
print(f"\n  sample_id  {sample.sample_id}")
print(f"  source     {sample.source.value}")
print(f"  quality    {sample.measurement_quality}")
print(f"  VALIDATION {result.state.value}  eligible={result.pipeline_eligible}")
PY
```

**Pass:** `source HARDWARE`, `measurement_quality >= 0.70`, and
`VALIDATION VALID  eligible=True`.

### If validation rejects the sample

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `REJECTED`, reason `MEASUREMENT_OUT_OF_RANGE`, EC in the hundreds | EC forwarded as µS/cm instead of dS/m | Every soil path divides by 1000, unconditionally. If you bypassed the adapters you skipped the conversion — do not hand-roll it, and never gate it on the magnitude of the reading |
| `quality` around 0.35 | No GPS fix | Antenna needs sky view |
| `quality` scaled to a fraction like 5/7 | Some registers failed | Check RS485 wiring and the 12 V rail |
| `quality` 0.0 | No soil data at all | Step 1a did not really pass |

> The adapter never pre-judges a sample. It reports quality; `ValidationEngine`
> alone decides `VALID` / `REJECTED`. Keep it that way — two gatekeepers means
> two answers.

---

## STEP 3 — Pipeline execution

Feed hardware samples through the unmodified Phase 1 engine, AI layer, and UI
renderer. Nothing downstream knows or cares that the data came from a probe.

Collect at least **3** samples (`SpatialEngine` needs 3 to interpolate); 20–25
spread across the field is realistic.

```bash
python3 - <<'PY'
from datetime import datetime, timezone
from fieldsense.domain.models import FieldSession
from fieldsense.hardware import JXBSSoilAdapter, NMEAGPSAdapter, HardwareSampleAdapter
from fieldsense.intelligence import ValidationEngine, FieldIntelligenceEngine
from fieldsense.spatial import SpatialEngine, SpatialConfig
from fieldsense.zones import ZoneDetectionEngine
from fieldsense.recommendations import RecommendationEngine
from fieldsense.presentation import UIViewAdapter, LocalUIRenderer
from fieldsense.ai import AIAdapterFactory, build_explanation_context
from dataclasses import replace
import os

soil_adapter = JXBSSoilAdapter.from_serial("/dev/ttyUSB0"); soil_adapter.initialize()
gps_adapter = NMEAGPSAdapter.from_serial("/dev/ttyUSB1")
builder = HardwareSampleAdapter()

session = FieldSession(session_id="FIELD-001",
                       created_at=datetime.now(timezone.utc),
                       field_name="Field 001")
TARGET = 25
while len(session.samples) < TARGET:
    input(f"Insert probe at point {len(session.samples)+1}/{TARGET}, press Enter...")
    sample = builder.build_sample(gps_adapter.acquire_gps_data(), soil_adapter.read())
    session.add_sample(sample)
    print(f"  captured {sample.sample_id}  quality={sample.measurement_quality}")

eligible = ValidationEngine().get_session_eligible_samples(session)
print(f"\n{len(eligible)}/{len(session.samples)} samples eligible")

intel   = FieldIntelligenceEngine().process_many(eligible)
spatial = SpatialEngine(config=SpatialConfig(grid_spacing_meters=10.0)).process(intel, eligible)
zones   = ZoneDetectionEngine().process(spatial)
recs    = RecommendationEngine().process(zones)
view    = UIViewAdapter().adapt(session, spatial, zones, recs)

ai = AIAdapterFactory.create_adapter()
view = replace(view, narrative=ai.explain(build_explanation_context(session, spatial, zones, recs)))
ai.shutdown()

os.makedirs("artifacts", exist_ok=True)
with open("artifacts/fieldsense_competition_demo.html", "w", encoding="utf-8") as fh:
    fh.write(LocalUIRenderer().render_html(view))

print(f"zones={len(zones.zones)}  recommendations={len(recs.recommendations)}")
print(f"coverage={spatial.coverage.coverage_ratio:.0%}")
print("dashboard -> artifacts/fieldsense_competition_demo.html")
PY
```

**Pass:** at least one zone detected, coverage above 0, and the HTML file
written. 
> **Timing.** The deterministic stages must stay under ~500 ms. The AI layer is
> deliberately out of band and may take tens of seconds with a real model; with
> no `.gguf` installed it uses instant deterministic templates. Both are
> correct — check `narrative_status` if unsure.

---

## STEP 4 — Display output

Push the rendered dashboard to the 2.8" panel.

```bash
./scripts/launch_display.sh probe      # report what is available, change nothing
```

Then:

```bash
./scripts/launch_display.sh fb
```

**Pass:** the dashboard appears on the panel — 67%-style score, zone status bar,
field map, and the pinned teaser with **Read More**.

Prerequisites specific to this step, both still open:

- **`DSP-01`** — the panel must be wired to the **QRB2210 SPI bus**, not the
  STM32. Linux cannot expose a framebuffer for a display it cannot reach.
- **`DSP-02`** — `fbtft` / `fb_st7789v` must exist in the shipped kernel.
  **Check this first**, it is the largest schedule risk:

  ```bash
  modinfo fb_st7789v && ls /lib/modules/$(uname -r)/kernel/drivers/staging/fbtft/
  ```

Full driver setup, device-tree overlay, rotation, byte order, systemd autostart
and troubleshooting: [AI_DEPLOYMENT.md](AI_DEPLOYMENT.md) Part II.

Without the panel, verify the exact frame on any machine:

```bash
python3 -m fieldsense.hardware.display_bridge --target png
# artifacts/panel_frame.png is pixel-for-pixel what the panel will show
```

> Touch input does not reach the UI yet (`DSP-05` — no calibration matrix). The
> **Read More** drawer cannot be opened on the device. Demonstrate that on a
> laptop for now.

---

## Quick reference

| Step | Command | Pass criterion |
| :--- | :--- | :--- |
| 0 | `PYTHONPATH=. python3 -m pytest -q` | 294 passed |
| 1a | `python3 "hardware/soil-probe/jxbs_test.py" --port /dev/ttyUSB0` | 7/7 parameters, moisture responds |
| 1b | `python3 hardware/gps/test_gps.py --port /dev/ttyUSB0` | decimal fix, sats ≥ 5, hdop ≤ 2 |
| 2 | contract snippet above | `VALID`, quality ≥ 0.70 |
| 3 | pipeline snippet above | zones ≥ 1, dashboard written |
| 4 | `./scripts/launch_display.sh fb` | dashboard visible on the panel |

## Known blockers

| ID | Blocks | Status |
| :--- | :--- | :--- |
| `HW-03` | GPS on the UNO Q — UART node unconfirmed | `PENDING_HARDWARE` |
| `HW-04` | GPS and display pin assignment | `PARTIALLY RESOLVED` |
| `DSP-01` | Panel wired to QRB2210 SPI | `PENDING_HARDWARE` |
| `DSP-02` | `fbtft` in the shipped kernel | `UNVERIFIED` |
| `DSP-05` | Touch events reaching the UI | `NOT STARTED` |
| `PF-01` | On-target timing benchmark | `PENDING_HARDWARE` |

Full register: [STATUS.md](STATUS.md).
