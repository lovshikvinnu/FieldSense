# FieldSense AI — Runtime Deployment

Two optional runtime integrations, both depending on external system assets that
are absent by default.

| Part | Subsystem | Module | Status |
| :--- | :--- | :--- | :--- |
| **I** | Local SLM explanation layer | `fieldsense/ai/` | `IMPLEMENTED` / on-target benchmark `PENDING_HARDWARE` |
| **II** | Display bridge to the 2.8" SPI panel | `fieldsense/hardware/display_bridge.py` | `IMPLEMENTED` / panel wiring `PENDING_HARDWARE` |

---

# Part I — Explanation Layer

**Module:** `fieldsense/ai/`

---

## 1. Default State: No Model Required

The explanation layer ships with **no model weights**. `AIAdapterFactory` resolves
to `MockAIAdapter`, which generates deterministic template narratives instantly.
This is the state of every development machine and of the competition demo:

```bash
python -m fieldsense.demo
# Explanation Layer:  MOCK_TEMPLATE_v1 [FALLBACK_TEMPLATE] | Guard Blocks: 0
```

Nothing needs installing for the dashboard to show a plain-language summary.

---

## 2. Enabling a Local Model

Two optional system assets. Neither is a Python dependency; `pyproject.toml`
`dependencies` remains `[]`.

### 2.1 Build llama.cpp

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp && cmake -B build && cmake --build build --config Release -j4
```

Place the resulting `llama-cli` on `PATH`, or set `AIConfig.binary_path`.

### 2.2 Obtain quantized GGUF weights

`Q4_K_M` is the recommended quantization. Size the model to available RAM;
generation streams every weight per token, so the model must fit in free memory
or throughput collapses to eMMC paging speed.

| Model | Q4_K_M size | Est. tokens/sec on QRB2210 | 150-token summary |
| :--- | :--- | :--- | :--- |
| Qwen2.5-0.5B-Instruct | ~0.40 GB | ~10 | ~15 s |
| TinyLlama-1.1B-Chat | ~0.67 GB | ~6 | ~25 s |
| Phi-3-mini-4k-instruct | ~2.30 GB | ~1.7 | ~90 s |
| Llama-3-8B | ~4.90 GB | will not load | — |

Estimates derive from the memory-bandwidth bound
(`tokens/sec ~= usable bandwidth / model bytes`) at an assumed ~4 GB/s achieved.
`UNO_Q_PHYSICAL_BENCHMARK = PENDING_HARDWARE`; measure on the target board.

**Measured 2026-08-25 on the UNO Q** (`tools/slm_probe.py`, idle board with the
App Lab GPS gateway running): **2.8 GB available**. That makes Qwen2.5-0.5B a
7x headroom choice and TinyLlama-1.1B a 4x one, while Phi-3-mini at 2.3 GB has
only 1.2x - it would load and then page, so its throughput estimate above is
optimistic for this board. Tokens/sec remains unmeasured.

### 2.3 Point the configuration at them

```python
from fieldsense.ai import AIConfig, AIAdapterFactory

config = AIConfig(
    backend="AUTO",                             # AUTO | MOCK | LLAMA_CPP
    model_path="models/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    binary_path="/opt/llama.cpp/build/bin/llama-cli",
    threads=4,                                  # QRB2210 exposes 4 Cortex-A53 cores
    timeout_seconds=120.0,
)
adapter = AIAdapterFactory.create_adapter(config)
```

`AUTO` selects `LlamaCppAdapter` only when both assets exist, and
`MockAIAdapter` otherwise. No code change is needed to switch.

---

## 3. Timing Boundary (Important)

The deterministic pipeline meets a `< 500 ms` budget. Real model inference costs
**15-90 seconds**, i.e. 30x to 180x that budget. The explanation layer therefore
runs **after** the deterministic pipeline (stage 7b in `fieldsense/demo.py`) and
is always optional and always discardable. It must never be placed inside the
deterministic stages, and `tests/test_benchmark.py` must continue to exercise
`MockAIAdapter` only.

---

## 4. Degradation Ladder

Every failure mode is a normal condition reported through
`AINarrative.generation_status`. None raises, and all produce a complete,
renderable narrative.

| Condition | Status | Result |
| :--- | :--- | :--- |
| No weights / no binary | `MODEL_UNAVAILABLE` | Full deterministic template |
| Guard rejects every section | `GUARD_REJECTED` | Full deterministic template |
| Guard rejects some sections | `FALLBACK_TEMPLATE` | Rejected sections templated, rest kept |
| Binary times out | `TIMEOUT` | Full deterministic template |
| Binary exits non-zero | `FALLBACK_TEMPLATE` | Template, `GENERATION_FAILED` recorded |
| All sections clean | `OK` | Model text displayed, badged `AI GENERATED` |

Generation is **per section** (one field summary, one per zone), so a single bad
paragraph degrades one paragraph rather than the whole narrative. Each rejection
is retried once with a corrective prompt before falling back.

---

## 5. Safety Boundary

`NarrativeGuard` inspects every generated string before display and rejects:

1. **Dose units** — `kg`, `ha`, `acre`, `litres`, `ppm`, `tonnes`, ...
2. **Agrochemicals** — `urea`, `DAP`, `MOP`, `gypsum`, `lime`, ...
3. **Out-of-boundary claims** — carbon credits, offsets, sequestration, guaranteed yield
4. **Unsupported numbers** — any number absent from the `ExplanationContext`

Check 4 is the strongest: a narrative may only restate quantities the
deterministic engines actually produced. `%` and `m²` are permitted units
because the dashboard presents scores as percentages and zone area in m², and
their numbers are still constrained by check 4.

Violations are recorded on `AINarrative.guard_violations` and surfaced in the
dashboard footnote, so a block is auditable rather than silent.

Narrative strings are rendered with `innerText`, never `innerHTML`, so model
output cannot inject markup into the offline dashboard.

---

## 6. Determinism

`AINarrative` is **non-normative presentation text** and is excluded from the
bit-exact guarantee of `docs/archive/03_ARCHITECTURE.md` section 25 when produced by a
model backend. `MockAIAdapter` is bit-exact and reports
`generation_time_ms = 0.0` rather than a measured value, so all golden scenario,
determinism, and benchmark tests remain valid. See
`docs/CCR-001_UIFieldView_Narrative.md`.

---

## 7. Unresolved Specifications

| ID | Description | Current Assumption | Required Decision | Status |
| :--- | :--- | :--- | :--- | :--- |
| `AI-01` | `llama-cli` flag compatibility | `--no-display-prompt`, `--single-turn` | `VERIFIED 2026-08-25` against llama.cpp 0.2.0-dev build 10615 (f280b2698) on the UNO Q. That build has no `-no-cnv`. | `RESOLVED` |
| `AI-02` | Model selection for 4 GB UNO Q | Qwen2.5-0.5B / TinyLlama-1.1B class | Benchmark on QRB2210 Debian | `PENDING_HARDWARE` |
| `AI-03` | On-target tokens/sec | Estimated from bandwidth bound | Measure physically | `UNO_Q_PHYSICAL_BENCHMARK` |
| `AI-04` | Prompt phrasing per model family | Generic instruct-style prompt | Tune per selected model chat template | `PROTOTYPE_ONLY` |

---

# Part II — Display Bridge: dashboard onto the 2.8" SPI panel

> This section covers the **display** pipeline, not the SLM. It lives here because
> both are optional runtime integrations that depend on external system assets.
> If the document grows further, split this into `docs/DISPLAY_DEPLOYMENT.md`.

## D1. What this does

`LocalUIRenderer` produces a self-contained HTML document. The panel is a
240×320 ST7789V SPI display. The bridge joins them on the Linux (QRB2210) side:

```text
  artifacts/fieldsense_competition_demo.html
        │
        │  headless browser, exact 240×320 CSS viewport
        ▼
    PNG bytes
        │
        │  stdlib PNG decode (zlib) → optional rotation
        ▼
  RGB888 buffer
        │
        │  pack to RGB565
        ▼
    /dev/fb1        ← fbtft exposes the SPI panel as a framebuffer
```

Everything above is implemented in `fieldsense/hardware/display_bridge.py` using
the standard library only. `dependencies = []` is unchanged. The browser and the
`fbtft` kernel driver are **external system assets**, discovered at runtime and
absent by default — the same discipline used for `llama.cpp`.

## D2. Prerequisite you cannot skip

> [!IMPORTANT]
> **The panel must be wired to the QRB2210 (Linux) SPI bus.**
> Bench verification to date drove it from the **STM32 MCU** with Arduino
> firmware (`hardware_test/TFT/display_test_*.ino`). Linux cannot expose a
> framebuffer for a display it has no SPI connection to. Exact pin assignment is
> `HW-04` / `PENDING HARDWARE`.

Everything except the final `/dev/fb1` write can be developed and tested today
on any laptop — see [D7](#d7-develop-without-the-panel).

## D3. Install a browser

```bash
sudo apt update && sudo apt install -y chromium
```

Confirm the bridge can see it:

```bash
python3 -m fieldsense.hardware.display_bridge --target probe
```

```text
FieldSense display bridge - environment probe

  platform        : linux
  browser         : /usr/bin/chromium
  display server  : none
  dashboard       : artifacts/fieldsense_competition_demo.html
  framebuffer     : none (fbtft driver not loaded)

  would use target: png
```

`probe` changes nothing. Run it first, always.

## D4. Expose the panel as a framebuffer (`fbtft`)

### D4.1 Check the driver exists

```bash
ls /lib/modules/$(uname -r)/kernel/drivers/staging/fbtft/ 2>/dev/null
modinfo fb_st7789v 2>/dev/null | head -3
```

> [!WARNING]
> `fbtft` lives in kernel *staging*. It is **not guaranteed** to be built into
> the Arduino/Qualcomm Debian image. If both commands come back empty, the panel
> cannot become a framebuffer without building the module or rebuilding the
> kernel. Establish this **before** committing to this route — it is the single
> biggest schedule risk in the display path.

### D4.2 Enable SPI and load the driver

Newer kernels are device-tree driven. Add an overlay describing the panel on the
SPI bus:

```dts
/* st7789v-fieldsense.dts — pin numbers are PENDING HARDWARE (HW-04) */
&spi0 {
    status = "okay";

    st7789v: display@0 {
        compatible = "sitronix,st7789v";
        reg = <0>;                       /* CS 0 */
        spi-max-frequency = <32000000>;  /* start at 16 MHz if unstable */
        rotate = <0>;
        width  = <240>;
        height = <320>;
        bgr;
        fps = <30>;
        buswidth = <8>;
        dc-gpios    = <&gpio  DC_PIN 0>;
        reset-gpios = <&gpio RST_PIN 0>;
        led-gpios   = <&gpio  BL_PIN 0>;   /* backlight */
    };
};
```

Build and install it:

```bash
dtc -@ -I dts -O dtb -o st7789v-fieldsense.dtbo st7789v-fieldsense.dts
sudo cp st7789v-fieldsense.dtbo /boot/overlays/
# then enable the overlay per the board's boot configuration, and reboot
```

Older kernels that still ship `fbtft_device` can skip the overlay:

```bash
sudo modprobe fbtft_device name=flexfb busnum=0 cs=0 gpios=reset:RST,dc:DC,led:BL      speed=32000000 rotate=0 bgr=1 custom=1 height=320 width=240
sudo modprobe flexfb width=240 height=320 init=-1,0x11,-2,120,-1,0x36,0x00,-1,0x3A,0x05,-1,0x29,-3
```

### D4.3 Verify the framebuffer appeared

```bash
ls -l /dev/fb*
cat /sys/class/graphics/fb1/virtual_size      # expect: 240,320
cat /sys/class/graphics/fb1/bits_per_pixel    # expect: 16
dmesg | grep -i -E 'fbtft|st7789|spi'
```

Prove the panel is alive before involving any application code:

```bash
cat /dev/urandom > /dev/fb1      # screen fills with noise
cat /dev/zero    > /dev/fb1      # screen goes black
```

If noise appears, the electrical path and driver are good and every remaining
problem is software.

### D4.4 Permissions

```bash
sudo usermod -aG video $USER     # then log out and back in
```

## D5. Display the dashboard

One command:

```bash
./scripts/launch_display.sh
```

It regenerates the dashboard, auto-detects the best target, and pushes a frame.

Explicit targets:

```bash
./scripts/launch_display.sh probe    # report environment, change nothing
./scripts/launch_display.sh fb       # push one frame to /dev/fb1
./scripts/launch_display.sh png      # save artifacts/panel_frame.png preview
./scripts/launch_display.sh kiosk    # full-screen browser (needs a display server)
./scripts/launch_display.sh watch    # re-render every REFRESH_SEC
```

Environment overrides:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `FB_DEVICE` | `/dev/fb1` | Framebuffer device |
| `ROTATE` | `0` | `0`, `90`, `180`, `270` clockwise |
| `WIDTH` / `HEIGHT` | `240` / `320` | Panel geometry |
| `BYTEORDER` | `little` | `little` for `/dev/fbN`, `big` for a raw SPI stream |
| `BROWSER` | auto | Explicit browser binary |
| `REGENERATE` | `1` | Re-run the pipeline before displaying |
| `REFRESH_SEC` | `30` | Watch-mode interval |

Example — landscape panel on `/dev/fb0`:

```bash
FB_DEVICE=/dev/fb0 ROTATE=90 ./scripts/launch_display.sh fb
```

The module is also callable directly:

```bash
python3 -m fieldsense.hardware.display_bridge --target fb --device /dev/fb1 --rotate 90
```

## D6. Kiosk route (only if a display server exists)

If the panel is already backed by X or Wayland, skip the pixel pipeline and let
the browser paint it:

```bash
chromium   --kiosk --incognito --noerrdialogs --disable-infobars   --disable-session-crashed-bubble --disable-translate --disable-pinch   --overscroll-history-navigation=0 --hide-scrollbars   --force-device-scale-factor=1 --check-for-update-interval=31536000   --window-position=0,0 --window-size=240,320   --app=file:///home/USER/FieldSense/artifacts/fieldsense_competition_demo.html
```

`./scripts/launch_display.sh kiosk` builds this command for you.

> [!NOTE]
> A bare `fbtft` framebuffer is **not** a display server. Chromium cannot draw to
> `/dev/fb1` directly. Either run X against the framebuffer (`xserver-xorg-video-fbdev`
> with `FRAMEBUFFER=/dev/fb1`), or use the `fb` target, which needs no display
> server at all. **On a 240×320 panel the `fb` target is the better choice** —
> it costs about 60 MB instead of a full X session.

## D7. Develop without the panel

Everything except the final device write works on any laptop:

```bash
python3 -m fieldsense.demo                                    # build the dashboard
python3 -m fieldsense.hardware.display_bridge --target png    # exact 240×320 frame
open artifacts/panel_frame.png
```

`artifacts/panel_frame.png` is pixel-for-pixel what the panel will show.

> [!TIP]
> **Why the bridge renders inside an iframe.** Chromium clamps a headless window
> to a minimum width (500 px observed). A naive `--window-size=240,320` therefore
> renders the **≥480 px tablet layout** and crops it to 240×320 — the output has
> the right dimensions and the wrong layout, which is easy to ship by accident.
> The bridge hosts the dashboard in an exactly-sized iframe, which gets its own
> viewport so the compact media queries evaluate against 240 px, then crops back.
> `tests/test_display_bridge.py` guards this.

## D8. Start on boot

The service is a **file in this repository**, not a snippet to retype:
`deploy/fieldsense.service`. Install it with the bundled installer:

```bash
sudo ./scripts/install_boot_service.sh
```

It creates the `fieldsense` system account, adds it to `video` (to write
`/dev/fbN`) and `dialout` (to open the RS485 tty), copies the tree to
`/opt/fieldsense`, installs the unit, and enables it. Preview without changing
anything:

```bash
./scripts/install_boot_service.sh --dry-run
```

For a panel that keeps refreshing rather than showing one frame from boot:

```bash
sudo ./scripts/install_boot_service.sh --refresh
```

Then:

```bash
sudo systemctl start fieldsense.service
journalctl -u fieldsense -f
```

### What the unit runs

`ExecStart` points at `scripts/boot_fieldsense.sh`, which:

1. Verifies `fieldsense` imports and reports whether any third-party package is
   present — the runtime is standard library only, and this proves it on the
   board instead of discovering a missing wheel with no network to install it.
2. Optionally acquires live samples (when `FIELDSENSE_SOURCE` names a hardware
   source) with `--no-interactive`, which is mandatory: systemd gives the unit no
   TTY and `live_collector`'s operator prompt would otherwise block the boot.
3. Regenerates the dashboard and `artifacts/panel_summary.json`.
4. Pushes a frame to the panel, auto-detecting `/dev/fb1` then `/dev/fb0`.

Each stage logs and continues. A partly failed boot still lights the screen,
because a dark panel in a field is indistinguishable from a dead board.

### Configuration without a code change

Every knob is an `Environment=` line in the unit:

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `FIELDSENSE_SOURCE` | `VIRTUAL` | `VIRTUAL`, `HARDWARE` (USB-RS485 on Linux), `BRIDGE` (probe on the STM32), `USB_PYSERIAL` |
| `FIELDSENSE_SENSOR_PORT` | `/dev/ttyUSB0` | Probe tty for the `HARDWARE` source |
| `FIELDSENSE_SENSOR_BAUD` | `9600` | JXBS factory default, 8N1 |
| `FIELDSENSE_REQUIRE_GPS_FIX` | `0` | `1` aborts a sample with no fix; `0` degrades its quality instead |
| `FIELDSENSE_POINTS` | `5` | Live points per acquisition cycle |
| `FB_DEVICE` | `auto` | `auto`, `/dev/fb0`, `/dev/fb1` |
| `ROTATE` | `0` | `0`, `90`, `180`, `270` |
| `REFRESH_SEC` | `300` | Loop interval for the refresh unit |
| `FIELDSENSE_AI_BACKEND` | `AUTO` | `AUTO`, `MOCK`, `LLAMA_CPP` |
| `FIELDSENSE_MODEL_PATH` | `models/fieldsense-slm.gguf` | GGUF weights. **Use an absolute path in a unit** — the default is repo-relative and a service's working directory is not the repository unless the unit says so. |
| `FIELDSENSE_LLAMA_BIN` | `llama-cli` | Inference binary, on `PATH` or absolute |

After editing:

```bash
sudo systemctl daemon-reload && sudo systemctl restart fieldsense.service
```

### The board has no browser

The `fb` and `png` targets rasterise the HTML dashboard with headless Chromium.
Chromium is a **system asset, not a dependency**, and a stock UNO Q image does
not carry one. The bridge therefore falls back to a browser-free renderer
(`fieldsense/hardware/panel_renderer.py`) that draws the health score, sample
counts, zones, actions, and provenance straight into a 240×320 RGB565 buffer
using nothing but the standard library. It reads the numbers from
`artifacts/panel_summary.json` rather than recomputing them, so the panel can
never disagree with the dashboard.

```bash
python3 -m fieldsense.hardware.display_bridge --target panel   # force it
python3 -m fieldsense.hardware.display_bridge --target fb --no-fallback  # require the real UI
```

Install Chromium (`sudo apt install chromium`) to get the full dashboard on the
panel. Without it the unit still boots to a legible screen instead of a dark one.

## D9. Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `no Chromium-family browser found` | Not installed | `sudo apt install chromium` for the full dashboard; without it the bridge draws the browser-free status panel |
| `renderer=panel` in the log, plain text on the screen | No browser, fallback active | Expected. Install chromium for the graphical dashboard |
| `no framebuffer device found` | Driver not loaded | `dmesg \| grep fbtft`; re-check D4. `FB_DEVICE=auto` already tries fb1 then fb0 |
| `geometry mismatch: ... would display transposed` | `--rotate` disagrees with the panel's `virtual_size` | Byte counts match after a 90° rotation, so only the geometry check catches it. Set `ROTATE` to match the panel |

| `permission denied writing /dev/fb1` | Not in `video` group | `sudo usermod -aG video $USER`, re-login |
| `size mismatch: expects 240x320 ... got N bytes` | Rotation vs panel geometry | Match `--rotate` / `--width` / `--height` to `virtual_size` |
| Panel stays black, no errors | Backlight off | Drive the `LED`/`BL` pin; check `led-gpios` |
| Colours inverted (red ↔ blue) | BGR vs RGB | Toggle `bgr` in the overlay |
| Image torn or noisy | SPI too fast | Lower `spi-max-frequency` to 16 MHz |
| Image mirrored or 90° out | Rotation mismatch | Set `ROTATE=90` (or `180`/`270`) |
| Rendered frame shows the wide layout | Iframe wrapper bypassed | Use the bridge, not a raw `--window-size` screenshot |
| Blank white frame | Page did not finish painting | Raise `--settle-ms` (default 800) |

## D10. Unresolved specifications

| ID | Description | Status |
| :--- | :--- | :--- |
| `DSP-01` | TFT SPI pins on the QRB2210 (bus, CS, DC, RST, backlight) | `PENDING HARDWARE` |
| `DSP-02` | `fbtft` / `fb_st7789v` present in the shipped kernel | `UNVERIFIED` — check first |
| `DSP-03` | Maximum stable SPI clock for this panel and cable | `PENDING HARDWARE` |
| `DSP-04` | Final orientation (portrait 240×320 vs landscape 320×240) | `DECISION REQUIRED` |
| `DSP-05` | Touch input reaching the UI (XPT2046 → events) | `NOT STARTED` — calibration matrix also pending |
| `DSP-06` | Frame refresh cadence and power cost | `PENDING HARDWARE` |

> [!NOTE]
> `DSP-05` matters for the demo: the dashboard's **Read More** control expects a
> tap. Until touch events reach the UI, the panel is display-only and the AI
> insights drawer cannot be opened on the device. The `watch` target is the
> interim workaround — or demonstrate the drawer on a laptop.
