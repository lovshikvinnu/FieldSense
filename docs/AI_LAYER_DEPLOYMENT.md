# FieldSense AI — Explanation Layer Deployment

**Module:** `fieldsense/ai/`
**Status:** `IMPLEMENTED` (software) / `PENDING_HARDWARE` (on-target benchmark)

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
bit-exact guarantee of `docs/03_ARCHITECTURE.md` section 25 when produced by a
model backend. `MockAIAdapter` is bit-exact and reports
`generation_time_ms = 0.0` rather than a measured value, so all golden scenario,
determinism, and benchmark tests remain valid. See
`docs/CCR-001_UIFieldView_Narrative.md`.

---

## 7. Unresolved Specifications

| ID | Description | Current Assumption | Required Decision | Status |
| :--- | :--- | :--- | :--- | :--- |
| `AI-01` | `llama-cli` flag compatibility | `--no-display-prompt`, `-no-cnv` | Verify against installed llama.cpp release | `HARDWARE_SPEC_REQUIRED` |
| `AI-02` | Model selection for 4 GB UNO Q | Qwen2.5-0.5B / TinyLlama-1.1B class | Benchmark on QRB2210 Debian | `PENDING_HARDWARE` |
| `AI-03` | On-target tokens/sec | Estimated from bandwidth bound | Measure physically | `UNO_Q_PHYSICAL_BENCHMARK` |
| `AI-04` | Prompt phrasing per model family | Generic instruct-style prompt | Tune per selected model chat template | `PROTOTYPE_ONLY` |
