# SLM V1 — Validation & Evidence Report

**Date:** 2026-08-25
**Scope:** the onboard small-language-model explanation layer (`fieldsense/ai/`) only.
**Purpose:** close out the V1 SLM investigation against measured evidence, and state
precisely what is proven, what is not, and what the shipped system claims.

This report records only what was measured. Where a figure was estimated,
illustrative, or never taken, it says so rather than filling the gap.

---

## 1. Summary

| Question | Answer | Evidence |
| :--- | :--- | :--- |
| Does a real GGUF execute on the UNO Q? | **Yes** | §3 |
| Is the model's text usable for the zone narrative? | **Yes** — it passes guard and fidelity | §5 |
| Is the model's text usable for the field summary? | **No** — rejected, 0/5 accepted | §5 |
| Does the system ever show rejected model text? | **No** — deterministic template is substituted and labelled | §8 |
| Does a larger model fix the field summary? | **No** — TinyLlama-1.1B is measurably worse | §6 |
| Is the full hardware → dashboard → TFT pipeline working? | **Yes** | §8 |

**SLM V1 status: COMPLETE** — see §10 for the exact reason and its boundary.

---

## 2. Deployment

### 2.1 Hardware

| | |
| :--- | :--- |
| Board | Arduino UNO Q — Qualcomm QRB2210 Linux MPU + STM32U585 MCU |
| Cores used for inference | 4 × Cortex-A53 (`FIELDSENSE_AI_THREADS=4`) |
| Access | `arduino@uno` over SSH; repo at `~/FieldSense/FieldSense` |
| Board state during measurement | idle, with the App Lab GPS gateway running |

### 2.2 llama.cpp

Verified on the board on 2026-08-25, **before any weights were downloaded** —
which is the only reason the flag fault below was found cheaply.

| | Measured |
| :--- | :--- |
| Version | `0.2.0-dev` |
| Build | `10615` |
| Commit | `f280b2698` |
| Architecture | **aarch64** (ARM64) — confirmed by the binary's own `--version` output on the QRB2210 |
| Binary | `~/llama.cpp/build/bin/llama-cli`, built from source with `cmake -B build && cmake --build build --config Release -j4` |

Recorded in `docs/STATUS.md` `AI-01` and `docs/AI_DEPLOYMENT.md` §7; commit `3a8315e`.

### 2.3 Model

| | Measured |
| :--- | :--- |
| Model | Qwen2.5-0.5B-Instruct |
| Quantisation | `Q4_K_M` |
| Weights on disk | **469 MB** (measured; the pre-hardware sizing table estimated ~0.40 GB) |
| Integrity check | first four bytes read `GGUF` |
| Location | `~/FieldSense/FieldSense/models/qwen2.5-0.5b-instruct-q4_k_m.gguf` (gitignored) |

### 2.4 Memory and disk

| | Measured | Source |
| :--- | :--- | :--- |
| Available RAM | **2.8 GB**, idle board with the GPS gateway running | `tools/slm_probe.py` gate 0, commit `93e8e7e` |
| Headroom vs Qwen 469 MB | ~7× | derived from the above |
| Headroom vs TinyLlama 638 MB | ~4× | derived from the above |
| Headroom vs Phi-3-mini 2.3 GB | ~1.2× — on the probe's WARN threshold; would load and then page | derived from the above |
| Disk | gated at **≥ 2 GB free** on the home filesystem via `df -h ~` before download; the check passed | `docs/evidence/SLM_VALIDATION.md` §2 |

**Not measured:** an exact free-disk figure was not captured as a numbered
result. The gate was pass/fail and it passed.

---

## 3. Real inference proof

The claim being established is narrow: **a language model executed on this board
and produced the text**. Passing tests do not show that, and a narrative
appearing does not either — `AIAdapterFactory` resolves `AUTO` to templates when
assets are missing, and `LlamaCppAdapter` falls back to templates when generation
fails. Both paths produce a complete narrative and a green run.

### 3.1 The evidence that the GGUF genuinely ran

| Signal | Observed on the UNO Q |
| :--- | :--- |
| `AINarrative.generated_by` | names the GGUF filename, not `MOCK_TEMPLATE_v1` |
| llama.cpp's own timing line | `[ Prompt: 15.9 t/s ]`, `[ Generation: 8.3 t/s ]` — produced by the binary itself while generating |
| Reported generation rate, other runs | **9.4 tokens/sec** (commit `6a07ae4`), **8.2 tokens/sec** (commit `024b7ba`) |
| Piped output volume | **1055 bytes on stdout** under `start_new_session=True`, against 0 bytes with an inherited tty — see §4.1 |
| Text content | recognisable prose about the field, distinct from the deterministic template |

The decisive point is that these came from a binary that had to be argued into
producing output at all (§4.1). A template backend cannot emit llama.cpp timing
lines, and the tty investigation only makes sense because generation was
demonstrably happening — at 9.4 tokens/sec — while the pipes were empty.

### 3.2 Generation speed

| Metric | Measured |
| :--- | :--- |
| llama.cpp-reported generation rate | 8.2 – 9.4 tokens/sec across observed runs |
| llama.cpp-reported prompt rate | 15.9 tokens/sec (single observation) |

**Not measured:** a controlled tokens/sec benchmark. These are the binary's own
per-run reports, taken opportunistically during debugging, not a repeated
measurement under fixed conditions. `AI-03` in `docs/STATUS.md` remains open and
is correctly marked so.

### 3.3 Wall-clock timing and peak RSS

From `tools/slm_bench.py`, five repeats on the `field_summary` section,
2026-08-25 on the UNO Q:

| Metric | Qwen2.5-0.5B Q4_K_M |
| :--- | :--- |
| Generation time, mean | **28.2 s** |
| Peak child RSS | **584 MB** |

Peak child RSS is read from `getrusage(RUSAGE_CHILDREN).ru_maxrss`, scaled by
platform — kilobytes on Linux, bytes on macOS. That scaling is deliberate: the
first version of the bench reported a ~500 MB model as using 7.8 GB (commit
`f21f322`).

**A caution on one figure:** the `wall clock: 18342.7 ms` block in
`docs/evidence/SLM_VALIDATION.md` gate 2 is an **illustrative example**, written on
2026-08-24 in commit `6723394` before any model existed on the board. It is not a
measurement and must not be quoted as one. The measured wall-clock figure for
Qwen is the 28.2 s mean above.

---

## 4. Output pipeline fixes

Four separate faults sat between "the model generated text" and "the guard judged
the model". Until all four were fixed, every measurement of model quality was
measuring something else.

### 4.1 The binary produced nothing — `--single-turn` and the controlling terminal

Two independent faults, both silent.

**Flag compatibility.** `AIConfig.extra_args` defaulted to `-no-cnv`, which build
10615 does not have. Without conversation mode suppressed, `llama-cli` waits for
interactive turns, a subprocess with no tty returns nothing, the adapter records
`GENERATION_FAILED`, and the run still reports a complete narrative. The
board's binary offers `-st` / `--single-turn`; the long form is now the default.
Commit `3a8315e`.

**Controlling terminal.** `llama-cli` opens `/dev/tty` directly and renders its
chat UI there. With a terminal present it exits 0 having written nothing to
either pipe — so the adapter received an empty string and the guard correctly
reported `EMPTY_NARRATIVE` for text the model had generated perfectly well at
9.4 tokens/sec. Two theories were falsified on hardware before the right one:
reading stderr would have changed nothing (stderr was empty too), and
`stdin=DEVNULL` changed nothing (stdin is not what `llama-cli` consults).

The measured matrix, same command four ways on the board:

| Variant | stdout | stderr |
| :--- | :--- | :--- |
| inherited stdin | 0 bytes | 0 bytes |
| `stdin=DEVNULL` | 0 bytes | 0 bytes |
| `start_new_session=True` | **1055 bytes** | — |

`setsid()` removes the controlling terminal, the `/dev/tty` open fails, and
generation falls back to the pipe. Commits `5549874`, `1ea1ff6`, `6a07ae4`.

### 4.2 llama.cpp output furniture reached the guard

`_clean_output` passed the tool's own output straight through, so the guard was
reading llama.cpp and attributing it to the model.

Measured contamination on the UNO Q:

| Violation observed | Actual cause |
| :--- | :--- |
| `UNSUPPORTED_NUMBER[field_summary]:15.9` | llama.cpp's **prompt** token rate |
| `UNSUPPORTED_NUMBER[field_summary]:8.3` | llama.cpp's **generation** token rate |
| `LENGTH_EXCEEDED` inflation | **470–1055 characters** of spinner and timing furniture counted against 900- and 500-character limits |

Attributed by running identical model text with and without the furniture: alone
it draws no violations at all; with the spinner and timing line it draws exactly
the pair observed on the board. Of the three violation types seen at that point,
`UNSUPPORTED_NUMBER` was **entirely** llama.cpp, `LENGTH_EXCEEDED` was
substantially inflated by it, and only `FORBIDDEN_CLAIM` was genuinely the model.
Commits `f5d09f7` (failure pinned first, three `xfail(strict)` tests), `3f33850`
(fix).

A second round was needed. Gate 2 then reported `status: OK` with llama.cpp's
**ASCII-art logo** as the field summary — not empty, no forbidden claim, and
inside the length limit once the sentence trim had shortened it. A visible
rejection had become a silent acceptance, which is worse. The build prints a
whole chat session on stdout: logo, a build/model/ftype block, a command menu,
the prompt echoed after a `>` marker and elided as `... (truncated)` when long,
then the answer, then timings. Two rounds of blacklisting furniture had already
missed pieces of it, so the fix stopped guessing at the noise: **every line of
the prompt we sent is dropped from the output**, along with the fixed chrome
around it, and what survives is what the model added. When furniture is
recognised but nothing follows it, the result is empty and is rejected as empty,
rather than falling back to raw text — returning raw is precisely how the banner
reached the guard. Commit `b48a06c`.

### 4.3 Length was the harness, not the model

Gate 2 left one violation class: `LENGTH_EXCEEDED` at 1354 and 1420 characters
against a 900 limit, and 1296 and 1274 against 500. Four generations within 11%
of each other on two unrelated sections is the `-n 256` ceiling being hit every
time, not the model choosing a length — which is also why adding a word budget to
the prompt changed nothing.

Every section had shared one global `max_output_tokens`, so a 500-character zone
note and a 900-character summary both asked for 256 tokens. The budget is now
derived per section from the limit the guard will apply — **144 tokens and 80** —
using 5.6 characters per token, above the 5.55 measured maximum so the estimate
errs toward a shorter answer rather than a rejected one. Output is additionally
trimmed to the last complete sentence inside the limit, falling back to a word
boundary and then to leaving the text alone, so text is only ever removed, never
invented. Verified end to end against a stub that overruns as Qwen does: status
`OK`, `is_ai_generated` true, no violations, 866 characters, ending on a full
stop. Commit `0e9ef82`.

### 4.4 The prompt primed the claims it forbade

The rules said *"Never mention carbon credits, carbon offsets, or carbon
sequestration"*. Qwen2.5-0.5B produced all three phrases verbatim, in both
sections, on every attempt including the retry — a 0.5B model reads an enumerated
term as a topic, not a prohibition. The replacement is a positive scope rule:
write only about the values in DATA, introduce no other subject. The retry suffix
was also wrong — it mentioned only quantities and numbers, so a rejection for
*length* was answered with advice about *units*, which is why a 1523-character
answer was retried into a 1493-character one. Commit `7a31c97`.

### 4.5 Why the original measurements were contaminated

Before §4.1–§4.4, every apparent statement about model quality was actually a
statement about the harness:

| What it looked like | What it was |
| :--- | :--- |
| "The model produces nothing" | `-no-cnv` rejected; then `/dev/tty` swallowing output |
| "The model invents measurements (15.9, 8.3)" | llama.cpp's token-rate line |
| "The model is far too verbose" | the `-n 256` ceiling, plus 470–1055 chars of furniture |
| "The model passes cleanly" | llama.cpp's ASCII logo accepted as the field summary |
| "The narrative is fine — zero guard blocks" | the guard has no rule that binds a number to its field (§5.2) |

Model quality could not be honestly assessed until all five were removed. That is
the reason this investigation took the shape it did.

---

## 5. Probe taxonomy — execution vs acceptance

The probe originally reported one boolean, and it was wrong in both directions.

**First failure — conflation.** It reported `real model inference: NO` for a run
where Qwen demonstrably executed (`generated_by` named the GGUF, llama.cpp
reported 8.2 tokens/sec) and the text was rejected downstream. That verdict hid
the most useful thing the run established and would have sent someone to
reinstall a working model.

**Second failure — "any section" optimism.** `is_ai_generated` is true when *any*
section came from the model, so a run with one section accepted and one templated
reported as cleanly accepted. On the board, gate 3 rejected `field_summary` for
three contradictions and accepted `ZONE-01`, and the probe called it *"output
accepted: yes — real inference confirmed"*.

The probe now separates three facts and reports all of them
(`tools/slm_probe.py`, commits `024b7ba`, `1ce8614`):

| Fact | How it is determined |
| :--- | :--- |
| **executed** | the LlamaCpp path was taken (`generated_by` carries the GGUF name) **and** the process did not record `GENERATION_FAILED` / `TIMEOUT` |
| **accepted** | sections are compared against what the deterministic backend would have written for the same context; an exact match means the model was rejected and this is the fallback |
| **ratio** | how many sections came from the model, and which ones fell back, by name |

Four verdicts follow, and partial acceptance returns non-zero:

| Verdict | Meaning |
| :--- | :--- |
| real on-board inference confirmed | executed **and** every section accepted |
| the model RAN and was PARTLY accepted | executed; named sections accepted, named sections templated |
| the model RAN, but its output was rejected | executed; nothing survived the guard/fidelity layer |
| NO real inference | templates — the model did not run |

Verified against stubs reproducing each case: a binary exiting 0 with empty
stdout gives *executed yes, accepted no* plus the exact four `EMPTY_NARRATIVE`
violations observed on the board; a binary exiting non-zero gives *executed no*.

### 5.1 The guard (unchanged throughout)

`NarrativeGuard` rejects dose units, agrochemicals, out-of-boundary claims, and
any number absent from the `ExplanationContext`. **It was not modified at any
point in this investigation and was never at fault** — it was reading llama.cpp's
output and judging it correctly.

### 5.2 Why fidelity is a separate layer

A physical run on the UNO Q reported `OK` with **zero guard blocks** for a
narrative that got four things wrong. The guard could not have caught it and
should not try: its strongest rule is that every number appears in the context,
and *five* does — as `valid_samples`. Binding a number to the field it is
attached to is a different question, so `FidelityChecker` is a separate layer.
`guard.py` is untouched. Commit `a23c502`.

Each rule reads one deterministic field and looks for an explicit assertion of
its opposite: health status, sample counts, moisture polarity, zone severity,
spatial confidence, and the direction of a water recommendation. Claims are
scoped to the sentence carrying their subject — a character window was tried
first and produced a false positive on correct text (*"Map coverage is high.
Spatial data support is low."* read backwards across the full stop), caught by a
conservative test before it shipped.

**This layer catches contradictions, not falsehoods. A plausible invention still
passes.**

---

## 6. Qwen benchmark — 5 runs

`tools/slm_bench.py`, 2026-08-25 on the UNO Q. Section: `field_summary` — the one
that fails. Shipped prompt, shipped guard, shipped fidelity checker; only the
model path is a parameter, so the deployment stayed frozen while the candidate
was measured beside it.

| Metric | Qwen2.5-0.5B-Instruct Q4_K_M |
| :--- | :--- |
| Repeats | 5 |
| Weights | 469 MB |
| **Acceptance** | **0/5** |
| Generation time, mean | 28.2 s |
| Peak child RSS | 584 MB |
| Determinism | **yes** — 1 distinct text across 5 runs |

The bench judges **the model's own text**, not `_generate_section`'s return
value. That return value is the *template* when a section is rejected, so
comparing it across runs would report every failing model as perfectly
deterministic — by comparing the fallback with itself.

### 6.1 The exact field-summary failure

Two contradictions against the DATA block, identical in all five runs:

| Deterministic fact | What Qwen wrote |
| :--- | :--- |
| `overall_soil_health = 0.36`, status `POOR` | described the 36% score as **high** |
| `valid_samples = 5`, `rejected_samples = 0` | **"five rejected"** |

The earlier gate-3 pipeline run on the board produced three contradictions in the
field summary; the original pre-fidelity run produced four, pinned verbatim in
`tests/test_fidelity.py`:

1. *"indicating good overall soil health"* — status was `POOR`
2. *"five were rejected as implausible"* — `rejected_samples = 0`
3. *"high moisture levels"* — `moisture_score = 0.0`, a **deficiency**
4. *"spatial data support is high"* — `confidence = LOW`

Contradiction 3 is the one that matters most: the run inverted a deficiency into
an excess **directly above a recommendation to review irrigation**, and a farmer
following the sentence rather than the recommendation would withhold water.

### 6.2 Zone narrative success

The `ZONE-01` narrative **passes** guard and fidelity and is displayed as model
output. Gate 3 accepted it on the board, every time, while rejecting the field
summary — which is why the per-section design matters: generation is per section,
so a bad paragraph degrades one paragraph rather than the whole narrative.

---

## 7. TinyLlama comparison

Same `field_summary` context, same prompt, same guard, same fidelity checker,
five repeats, same board, same day.

| | Qwen2.5-0.5B Q4_K_M | TinyLlama-1.1B-Chat Q4_K_M |
| :--- | :--- | :--- |
| Weights | 469 MB | 638 MB |
| **Acceptance** | **0/5** | **0/5** |
| Generation, mean | **28.2 s** | **75.1 s** (2.7×) |
| Peak child RSS | **584 MB** | **745 MB** (1.3×) |
| Deterministic | yes, 1 distinct text in 5 | yes, 1 distinct text in 5 |

### 7.1 Output behaviour

Qwen writes fluent prose and gets two facts wrong. TinyLlama **does not write a
summary at all** — it echoes the DATA block back as a key-value list, then quotes
the TASK instruction including its own word budget, and is cut off mid-sentence.
That earns a `UNSUPPORTED_NUMBER:120` from the guard, 120 being the word budget
from the prompt rather than any field value.

### 7.2 Why we rejected switching

- **No acceptance gain.** 0/5 either way.
- **2.7× the generation cost** and 1.3× the resident memory, for a regression in
  output *shape* — from imperfect prose to a non-summary.
- **Deterministic on both sides.** 1 distinct text in 5 runs each, so neither
  result is a sampling accident.

**Decision: keep Qwen2.5-0.5B, keep the fidelity fallback.** Recorded because a
larger model is the obvious suggestion, and this is the measured evidence that it
does not help here.

---

## 8. Validator correction — the `rejected_samples` association bug

The TinyLlama comparison exposed a **false positive** in `FidelityChecker`.

**The bug.** TinyLlama's list-formatted answer contained:

```
Sampled: 5 Sampled: 5 Rejected as Implusable: 0
```

That rejected count is **correct** — `rejected_samples = 0`. The checker called
it a contradiction, because the pattern was written for prose (*"five were
rejected"*, count **before** the keyword) and matched the `5` from the preceding
`Sampled:` field.

**Prose vs labelled-list forms.** The two shapes put the count on opposite sides
of the keyword:

| Form | Example | Count position |
| :--- | :--- | :--- |
| Prose | "five were rejected as implausible" | **before** the keyword |
| Labelled list | "Rejected as Implausible: 0" | **after** the label |

The labelled form is now checked first and wins, because a colon binds a value to
its label in a way adjacency does not. Prose is still read when no label is
present, so Qwen's genuine contradiction is unaffected. `_REJECTED_LABELLED` and
`_PASSED_LABELLED` were added alongside the existing prose patterns; the guard
was not touched and no threshold was loosened. Commit `1ea924f`.

**Why this direction of error is the expensive one.** A missed contradiction is
one bad sentence. A false positive rejects *correct* model output into a
template, makes a working model look unusable, and nothing reports that it
happened.

**The TinyLlama recommendation is unaffected** — it failed on a guard violation
(`UNSUPPORTED_NUMBER:120`) as well, and remains the wrong choice.

### 8.1 Regression coverage

Four tests carry the fix, **three of which fail against the old logic** —
checked, not assumed:

| Test | Guards against |
| :--- | :--- |
| `test_a_labelled_zero_rejected_count_is_accepted` | the false positive itself, on TinyLlama's verbatim board output |
| `test_a_labelled_count_that_is_wrong_is_still_rejected` | the rule silently stopping firing |
| `test_prose_counts_still_bind_the_old_way` | Qwen's genuine contradiction surviving the fix |
| `test_a_labelled_form_wins_over_an_adjacent_number` | precedence where both readings are possible |

One further test is load-bearing for the whole design:
`test_the_template_fallback_passes_fidelity` proves the deterministic narrative
passes fidelity across healthy, moderate and poor fields. Without it, a rejected
model section could fall back to text that fails the same validator, and the loop
would be silent.

### 8.2 Test counts (measured 2026-08-25)

| Suite | Tests | Result |
| :--- | :--- | :--- |
| `tests/test_ai.py` | 62 | pass |
| `tests/test_fidelity.py` | 19 | pass |
| AI layer subtotal | **81** | pass |
| **Full repository suite** | **422** | **pass** |

These exercise the adapter against fake binaries and stubs. **They prove the
plumbing, not that a model ran on the board** — that claim rests on §3 alone.

---

## 9. Final V1 architecture and status

### 9.1 What is true

1. **Qwen2.5-0.5B-Instruct Q4_K_M is genuinely running onboard the UNO Q**, via
   llama.cpp 0.2.0-dev build 10615 (`f280b2698`), aarch64. Evidence in §3.
2. **Zone-level model output can and does pass the contract** — guard and
   fidelity both — and is displayed as model text.
3. **The field summary currently falls back to the deterministic template**,
   which is accurate by construction. Measured acceptance for that section is
   0/5.
4. **The system does not claim the failed model output as accepted.** Rejected
   sections are replaced by the template, `generation_status` reports
   `FALLBACK_TEMPLATE`, the violations are recorded on
   `AINarrative.guard_violations`, and the dashboard footnote surfaces both —
   including which model produced the rejected text.
5. **The full pipeline works**: hardware acquisition → spatial analysis → AI
   explanation layer → dashboard → TFT panel. The TFT transport, MCU parser and
   `renderValues()` path were verified on the UNO Q on 2026-08-24.

### 9.2 The degradation contract

| Condition | Status reported | What the user sees |
| :--- | :--- | :--- |
| No weights / no binary | `MODEL_UNAVAILABLE` | full deterministic template |
| Guard rejects every section | `GUARD_REJECTED` | full deterministic template |
| Guard rejects some sections | `FALLBACK_TEMPLATE` | rejected sections templated, rest kept |
| Binary times out | `TIMEOUT` | full deterministic template |
| Binary exits non-zero | `FALLBACK_TEMPLATE` | template, `GENERATION_FAILED` recorded |
| All sections clean | `OK` | model text, badged `AI GENERATED` |

**A fallback is not a failure of the system.** It is the system declining to show
a farmer something untrue, and naming the model that produced the rejected text.

### 9.3 Timing boundary

The deterministic pipeline meets its `< 500 ms` budget. Measured model inference
costs **28.2 s** for the field summary — roughly 56× that budget. The explanation
layer therefore runs **after** the deterministic pipeline, is always optional and
always discardable, and must never be placed inside the deterministic stages.
`tests/test_benchmark.py` continues to exercise `MockAIAdapter` only.

---

## 10. Known limitations and deferred work

### 10.1 Measured limitations

| # | Limitation |
| :--- | :--- |
| 1 | **Field summary acceptance is 0/5.** That section is template-served in V1. |
| 2 | **Fidelity catches contradictions, not falsehoods.** A plausible invention with no contradicted field still passes. |
| 3 | **Tokens/sec is not benchmarked.** Only llama.cpp's own opportunistic per-run reports (8.2–9.4 t/s) exist. `AI-03` remains open. |
| 4 | **`AINarrative` is non-normative** and is excluded from the bit-exact determinism guarantee when produced by a model backend. |
| 5 | **The bench covers one section and one context.** Determinism and acceptance are established for `field_summary` on the probe's sample context, not across the input space. |

### 10.2 Deferred — explicitly future work

- **Prompt-shape experiments.** The failing section is a structured-summary task
  and the current prompt is generic instruct-style. `AI-04` (prompt phrasing per
  model family / chat template) is `PROTOTYPE_ONLY` and untouched. Reshaping the
  field-summary prompt is the cheapest untried lever and costs nothing at
  runtime.
- **Model-quality experiments** beyond the two measured candidates.
- **A controlled tokens/sec benchmark** on the QRB2210, closing `AI-03`.
- **Documentation consistency:** `docs/STATUS.md` and `docs/AI_DEPLOYMENT.md`
  still carry `AI-02` (model selection) as `PENDING_HARDWARE`, though the
  head-to-head in §7 is the benchmark it was waiting for. Left as-is by this
  report; flagged rather than silently edited.

### 10.3 Explicitly not proposed

**No model switch is proposed.** §7 is the measured evidence against the obvious
next step, and it was recorded precisely so this does not get relitigated. No
change to GPS, soil, TFT, spatial, acquisition, or hardware code is part of this
close-out. **The guard was not weakened at any point and must not be** — the
guard and the fidelity layer are the only things standing between a small model's
confident invention and a field decision.

---

## 11. Evidence trail

| Commit | What it establishes |
| :--- | :--- |
| `6723394` | The SLM validation procedure, gated on what actually generated the text |
| `93e8e7e` | 2.8 GB available RAM measured on the UNO Q |
| `3a8315e` | llama.cpp 0.2.0-dev build 10615 `f280b2698` aarch64; `--single-turn` verified, `-no-cnv` absent |
| `bf24665` | `-no-cnv` references retired from the runbook, report and status tables |
| `024b7ba` | Probe separates model execution from output acceptance |
| `5549874` | Stream dump reproducing FieldSense's own subprocess conditions |
| `1ea1ff6` | tty matrix, after `stdin=DEVNULL` failed to explain the board |
| `6a07ae4` | `start_new_session` recovers 1055 bytes on stdout; 9.4 tokens/sec confirmed |
| `f5d09f7` | llama.cpp furniture failure mode pinned (3 `xfail(strict)` tests) before any behaviour change |
| `3f33850` | Furniture stripped so the guard judges the model, not the tool |
| `7a31c97` | Prompt stops priming the claims it forbids; word budget added |
| `0e9ef82` | Per-section token budget (144 / 80) and sentence-boundary trim |
| `b48a06c` | Chat banner and echoed prompt dropped before judging; ASCII-logo acceptance closed |
| `a23c502` | `FidelityChecker` added; four hardware contradictions pinned verbatim |
| `c1df649` | Gate 3 added; gate 2 stops reading as the finish line |
| `1ce8614` | Probe counts sections instead of calling any model text a clean pass |
| `f21f322` | `tools/slm_bench.py` — controlled bench for the section that actually fails |
| `55203af` | Measured Qwen vs TinyLlama head-to-head recorded |
| `1ea924f` | `rejected_samples` association bug fixed; 4 regression tests |

**Reproduce:**

```bash
python3 tools/slm_probe.py --no-inference    # gate 0/1: assets
python3 tools/slm_probe.py                   # gate 2/3: execution, acceptance, fidelity
python3 tools/slm_bench.py --repeats 5       # the head-to-head
```

---

## 12. Verdict

**SLM V1: COMPLETE.**

The V1 objective was to establish whether a language model can run on the UNO Q
and whether its output can be trusted in front of a farmer. Both questions are
answered with measurements: the model runs, one section of its output meets the
contract and is displayed, the other does not and is safely and visibly replaced.
The 0/5 field-summary acceptance is a **recorded model-quality finding with a
correct, honest fallback**, not an open defect — and the obvious remedy was
measured and rejected on evidence.

Improving field-summary acceptance is V2 work, and §10.2 says where to start.
