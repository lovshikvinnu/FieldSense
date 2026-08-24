# SLM Validation — proving the model runs on the board

The goal is one specific claim: **a language model executed on the UNO Q and
produced the narrative**. Not that the tests pass. Not that a narrative
appeared. Those are already true and prove nothing about the model.

This matters because the system is built to degrade quietly. `AIAdapterFactory`
resolves `AUTO` to the template backend whenever the weights or binary are
missing, and `LlamaCppAdapter` falls back to templates when a generation fails.
Both paths produce a complete narrative, a valid status, and a green run.
Nothing errors. The pipeline has been doing exactly this all along — every
dashboard so far has been badged `MOCK_TEMPLATE_v1`.

So every gate below is checked with `tools/slm_probe.py`, which ignores status
lines and reports what actually produced the text.

| | |
| :--- | :--- |
| Board | `arduino@uno` over SSH |
| Repo | `~/FieldSense/FieldSense` |
| Time | ~1 hour, most of it compiling llama.cpp |
| Reference | `docs/AI_DEPLOYMENT.md` section 2 |

---

## Gate 0 — what is already installed

Takes seconds. Run it before doing anything else; the answer may be "more than
you thought".

```bash
cd ~/FieldSense/FieldSense && git pull --ff-only origin main
python3 tools/slm_probe.py --no-inference
```

The probe prints the resolved configuration and checks each asset. Read the
`VERDICT` line at the bottom.

- **Assets missing** — expected on a fresh board. Continue to step 1.
- **Assets present** — skip to gate 2 and prove inference actually happens.

The probe is self-checking. If you ever doubt it, `python3 tools/slm_probe.py
--selftest` forces the template backend and confirms the probe correctly refuses
to call that a real inference.

---

## 1. Build llama.cpp

This is the slow part — a `cmake` build on four Cortex-A53 cores. Expect tens of
minutes. Run it in `screen` or `tmux` so an SSH drop does not kill it.

```bash
cd ~ && git clone https://github.com/ggml-org/llama.cpp
```

```bash
cd ~/llama.cpp && cmake -B build && cmake --build build --config Release -j4
```

The binary lands at `~/llama.cpp/build/bin/llama-cli`. Confirm it runs before
going further:

```bash
~/llama.cpp/build/bin/llama-cli --version
```

### Check one flag while you are here

`AIConfig.extra_args` defaults to `("-no-cnv",)`, and that flag name has changed
across llama.cpp releases. If this build does not accept it, every generation
fails and silently degrades to templates — which looks like "the model does not
work" when the real problem is one argument.

```bash
~/llama.cpp/build/bin/llama-cli --help | grep -i "no-cnv\|conversation"
```

If `-no-cnv` is absent, report what the help does show. It is a one-line
configuration change, not a code change.

## 2. Get the weights

**Qwen2.5-0.5B-Instruct, Q4_K_M, ~0.40 GB.** Start here rather than something
larger. Generation streams every weight for every token, so throughput is bound
by memory bandwidth: 0.5B gives roughly 10 tokens/sec and a ~15 s summary, while
Phi-3-mini at 2.3 GB drops to ~1.7 tokens/sec and ~90 s. Prove the path works at
the fast end first, then size up if you want better text.

### Check disk before downloading

The weights are ~0.40 GB and the llama.cpp build tree is larger again. A
half-finished download leaves a file that passes a casual glance and fails at
load time, so confirm the room exists first.

```bash
df -h ~ && du -sh ~/llama.cpp 2>/dev/null
```

Want at least 2 GB free on the home filesystem.

### Download

```bash
mkdir -p ~/FieldSense/FieldSense/models
```

```bash
curl -L --fail --progress-bar -o ~/FieldSense/FieldSense/models/qwen2.5-0.5b-instruct-q4_k_m.gguf https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

`--fail` matters: without it curl happily writes an HTML error page to the
`.gguf` filename, which then fails the magic-byte check below for a confusing
reason. If it 404s, the quantisation filename has changed — list what the repo
actually offers at
<https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/main> and use the
`q4_k_m` entry.

The `models/` folder is gitignored, so weights never enter the repo.

Sanity-check the download — a truncated file still looks plausible until
llama.cpp rejects it:

```bash
ls -lh ~/FieldSense/FieldSense/models/ && head -c 4 ~/FieldSense/FieldSense/models/*.gguf
```

The first four bytes must read `GGUF`.

## 3. Point the configuration at them

Environment variables, not a code edit — `AIConfig.from_env()` reads these, so a
boot service can use the same values later.

```bash
export FIELDSENSE_AI_BACKEND=AUTO
export FIELDSENSE_MODEL_PATH=$HOME/FieldSense/FieldSense/models/qwen2.5-0.5b-instruct-q4_k_m.gguf
export FIELDSENSE_LLAMA_BIN=$HOME/llama.cpp/build/bin/llama-cli
export FIELDSENSE_AI_THREADS=4
export FIELDSENSE_AI_TIMEOUT=120
```

---

## Gate 1 — assets resolve

```bash
python3 tools/slm_probe.py --no-inference
```

Every line should read `PASS`: weights found, `GGUF` magic correct, binary
found, executable, `--version` runs, and memory headroom above the weight size.

A `WARN` on memory headroom means the model is close to available RAM. It will
still run, but it will page and be very slow. Use a smaller model rather than
waiting it out.

## Gate 2 — real inference, the one that counts

```bash
python3 tools/slm_probe.py
```

The first run is slow — the model loads from eMMC before the first token. Expect
15–30 seconds for the summary on the 0.5B model.

**The pass condition:**

```
[PASS] real model inference          yes

VERDICT: real on-board inference confirmed.
  model     : qwen2.5-0.5b-instruct-q4_k_m.gguf
  status    : OK
  wall clock: 18342.7 ms
```

`model` naming the GGUF file rather than `MOCK_TEMPLATE_v1` is the proof. The
probe also prints the first 200 characters of the generated summary — read them.
Template output is recognisably formulaic; model output is not.

**Record that entire block.** It is the evidence for SLM validation, and it is
the thing that has never existed for this project.

---

## If gate 2 fails with assets present

The installation is fine and generation is failing. `generation_status` says
which:

**Read the `guard violations` line, not just the status.** `GUARD_REJECTED`
covers two completely different faults, and the status alone cannot tell them
apart — a binary that never ran records `GENERATION_FAILED` entries, which count
as violations, so a broken install reports the same status as unsafe model text.
Verified by inducing both.

| Status | Violations show | Meaning | Do this |
| :--- | :--- | :--- | :--- |
| `TIMEOUT` | — | Model slower than `FIELDSENSE_AI_TIMEOUT`. | Raise the timeout, or use a smaller model. On a 0.5B model a timeout means something else is wrong — check for paging. |
| `GUARD_REJECTED` | `GENERATION_FAILED[...]:SubprocessError` | **The binary failed. No text was ever produced.** Nothing to do with the guard. | Almost always the `-no-cnv` flag. Run the `--help` check from step 1, then try the binary by hand. |
| `GUARD_REJECTED` | named content rules | The model produced text the safety guard refused. | See `fieldsense/ai/guard.py`. Report the violations the probe prints. |
| `FALLBACK_TEMPLATE` | — | Some sections generated, others did not. | A partial failure — usually one slow section hitting the timeout. Check the reported generation time. |

## Once it passes

Run the whole pipeline with the model live and confirm the dashboard changes:

```bash
PYTHONPATH=. python3 run_spatial_test.py field_test_live_hardware.json --display bridge
```

Step 6 of the output previously read `Narrative: MOCK_TEMPLATE_v1
[FALLBACK_TEMPLATE]`. With the model installed it should name the GGUF and read
`OK`. That single line changing is the difference between a template pipeline
and an AI pipeline, and it is worth a screenshot.

---

## What not to claim

Until gate 2 passes, the project has **no** onboard SLM validation, regardless
of how many AI tests pass. The 42 tests in `tests/test_ai.py` exercise the
adapter against a fake binary; they prove the plumbing, not that a model ran on
this board.

The same discipline that found the GPS fault applies: instrument first, read
what the instrument says, do not infer success from the absence of errors.
