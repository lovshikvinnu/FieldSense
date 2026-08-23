# FieldSense AI — Documentation & Testing Audit

**Date:** 2026-08-23
**Scope:** `README.md`, `docs/**`, `PROPOSAL_ALIGNMENT.md`, `SPECIFICATION_REGISTER.md`, `DEMO_GUIDE.md`, `hardware_test/**`, cross-checked against the code and a live test run.
**Baseline at audit time:** 147 tests passing.

---

## Summary

The hardware documentation is genuinely good — empirical, source-classified (`MEASURED` / `CONFIRMED` / `ASSUMED` / `PENDING`), and honest about its boundaries. The problems are **structural**: a merge reverted the README, two generations of documentation now coexist with no statement of which is authoritative, and the software docs have not caught up with the AI layer or the current test count.

One finding is not a documentation problem at all but a real architectural gap that documentation was hiding (**C-1**).

Severity: 🔴 blocking · 🟠 misleading · 🟡 tidy-up

---

## A. Critical

### 🔴 A-1 · `README.md` was reverted by merge `7c4e2af`

At commit `97f0f30` the README was 112 lines with Overview, Key Capabilities, Architecture, a documentation index, and Quick Start. After the merge it is 24 lines titled *"Sprint 1 Foundation"*, describing seven fully-implemented modules as `(future)` and containing no way to install, run, or test anything.

**Status:** ✅ **Fixed** — README rewritten with a complete directory map.

### 🔴 A-2 · Stale regression baseline in five documents

`105 tests` is claimed in `docs/01_SOFTWARE_WORKPLAN.md` (×3), `docs/02_PROJECT_HANDBOOK.md` (×4), `docs/TEST_AND_VALIDATION.md` (×2), and `docs/CCR-001`. Actual: **147**.

`docs/TEST_AND_VALIDATION.md` reproduces a pytest transcript reading `collected 105 items`, which now misrepresents the suite.

**Action:** update `TEST_AND_VALIDATION.md` §2 to 147 and regenerate the transcript. The `CCR-001` reference is historically correct (it recorded the pre-change baseline) and should stay.

### 🔴 A-3 · No setup instructions existed anywhere

No document stated `pip install -e ".[dev]"`, and `pyserial` — imported by all four hardware scripts — is declared nowhere, including `pyproject.toml`.

**Status:** ✅ **Fixed** in `README.md` and `TESTING_GUIDE.md`. **Still open:** whether `pyserial` should become an optional extra, e.g. `[project.optional-dependencies] hardware = ["pyserial>=3.5"]`. Deliberately not added — it touches the "zero dependencies" claim and is the architect's call.

---

## B. Structure

### 🟠 B-1 · `docs/` contains duplicate and diverged copies

Six file pairs are byte-identical across `docs/` and `docs/archive/`:

```
docs/01_SOFTWARE_WORKPLAN.md              == docs/archive/01_SOFTWARE_WORKPLAN.md
docs/03_ARCHITECTURE.md                   == docs/archive/03_ARCHITECTURE.md
docs/validation_and_limitations.md        == docs/archive/validation_and_limitations.md
docs/FieldSense_AI_..._Handoff.md         == docs/archive/FieldSense_AI_..._Handoff.md
DEMO_GUIDE.md                             == docs/archive/DEMO_GUIDE.md
SPECIFICATION_REGISTER.md                 == docs/archive/SPECIFICATION_REGISTER.md
```

Two pairs have **diverged**, which is worse than duplication because there is no longer a single truth:

```
docs/02_PROJECT_HANDBOOK.md   ≠  docs/archive/02_PROJECT_HANDBOOK.md
PROPOSAL_ALIGNMENT.md         ≠  docs/archive/PROPOSAL_ALIGNMENT.md
```

Cause: `97f0f30` moved the Phase 1 docs into `archive/`; the merge restored the originals alongside them; later edits landed on the top-level copies only.

**Action:** delete the top-level duplicates of archived files, keeping `archive/` as the single historical copy — but first port the AI-layer edits out of `docs/02_PROJECT_HANDBOOK.md` §24 and `PROPOSAL_ALIGNMENT.md` into the current `docs/PROJECT_HANDBOOK.md`, or those edits are lost.

### 🟠 B-2 · Two documentation generations, no stated precedence

| Old (Phase 1) | New (hardware-verified) |
| :--- | :--- |
| `01_SOFTWARE_WORKPLAN.md` | — |
| `02_PROJECT_HANDBOOK.md` | `PROJECT_HANDBOOK.md` |
| `03_ARCHITECTURE.md` | `SYSTEM_ARCHITECTURE.md` |
| `validation_and_limitations.md` | `TEST_AND_VALIDATION.md` |
| `FieldSense_AI_..._Handoff.md` | `SOFTWARE_SPEC.md` + `HARDWARE_SPEC.md` + `DECISION_LOG.md` |

Nothing told a reader which to trust. A new engineer would reasonably open `03_ARCHITECTURE.md` first and get a pre-hardware view.

**Status:** ✅ **Partly fixed** — `README.md` now names the authoritative set and marks `docs/archive/` superseded. Physical de-duplication (B-1) still pending.

---

## C. Content vs. implementation

### 🔴 C-1 · The 2.8" TFT cannot display the dashboard — and no document says so

The most important finding in this audit.

- `LocalUIRenderer` emits a **self-contained HTML document**, which requires a browser.
- The panel is an **SPI ST7789V driven by Arduino firmware on the STM32 MCU** (`display_test_*.ino` uses `Adafruit_ST7789`).
- There is **no bridge between the two**, and no document acknowledges the gap.

`HARDWARE_SPEC.md` §7 marks the display `VERIFIED / READY FOR V1 INTEGRATION`, and `SYSTEM_ARCHITECTURE.md` shows `LocalUIRenderer` feeding the output layer. Both are individually true; together they imply an integration that does not exist.

Two routes, neither implemented:

| Route | Wire TFT to | Mechanism | UI changes |
| :--- | :--- | :--- | :--- |
| **A** — Linux framebuffer | QRB2210 SPI | `fbtft` → `/dev/fb1` → kiosk browser | **None** — layout is already 240×320 |
| **B** — MCU renders | STM32 SPI | Second renderer pushing draw commands over RouterBridge | New renderer required |

Route A preserves all existing UI work.

**Status:** ✅ **Resolved in software.** Route A implemented as `fieldsense/hardware/display_bridge.py` + `scripts/launch_display.sh`, documented in `docs/AI_LAYER_DEPLOYMENT.md` Part II, covered by 31 tests. Remaining work is physical: rewire the panel to the QRB2210 SPI bus (`HW-04`) and confirm `fbtft` is in the shipped kernel (`DSP-02`).

### 🟠 C-2 · `SOFTWARE_SPEC.md` §1 omits implemented packages

The repository tree claims "11 strictly decoupled modules" and lists neither `fieldsense/ai/` (10 files, fully implemented, 42 tests) nor `fieldsense/transport/`.

### 🟠 C-3 · AI layer described as future in three documents

`SOFTWARE_SPEC.md` §13, `SYSTEM_ARCHITECTURE.md` §8 ("The **future** AI Explanation Layer"), and `DECISION_LOG.md` D-004 all predate the implementation. None mentions `LocalLLMAdapter`, `MockAIAdapter`, `LlamaCppAdapter`, `NarrativeGuard`, or `AIAdapterFactory`.

`NarrativeGuard` in particular is an unlisted safety control: it deterministically blocks generated text containing dose units, agrochemical names, carbon claims, or numbers absent from the deterministic context. That belongs in `DECISION_LOG.md` as a decision in its own right.

### 🟠 C-4 · `SPECIFICATION_REGISTER.md` is stale

`HW-01` (JXBS register map) and `HW-02` (RS485 serial parameters) are still marked `PENDING_HARDWARE`, but `HARDWARE_SPEC.md` §4 and the bench tests have both **confirmed** them. `HW-04` (UNO Q pin ownership) is partly resolved — the STM32 owns RS485 via `Serial1` and GPIO 7.

Conversely, four AI-layer items (`AI-01`…`AI-04`) from `docs/AI_LAYER_DEPLOYMENT.md` are absent from the register.

### 🟡 C-5 · `UNO_Q_HARDWARE_TEST.md` names files that do not exist

Refers throughout to `test_q.py` and `test_q.ino`. Actual files: `main.py` and `sketch.ino`. The only broken file reference in the entire repository — everything else resolves.

### 🟡 C-6 · Hardware scripts are Windows-only, undocumented

All four hardcode `COM8` / `COM10`. They cannot run on the UNO Q's Debian target without edits, and no document mentioned this.

**Status:** ✅ **Documented** in `TESTING_GUIDE.md` §1 with a port-mapping table. A `--port` argument would be the better long-term fix.

### 🟡 C-7 · Windows-local absolute paths leak into six documents

`file:///C:/Users/lovsh/Desktop/FieldSense/...` appears in `docs/PROJECT_HANDBOOK.md` and all five `hardware_test/*/*.md` files. These are dead links for everyone else. Replace with repository-relative paths.

### 🟡 C-8 · Inconsistent component naming

The soil sensor appears as `JXBS-3001-TR` (10 occurrences) and `JXBS-3001-NPKPH-RS` (1, in the `HARDWARE_SPEC.md` inventory). The purchase record says `JXBS-3001-TR`. Pick one.

### 🟡 C-9 · TFT manufacturer field is misleading

`HARDWARE_SPEC.md` §2 lists the display vendor as `Generic / ILI` while §7 correctly identifies the controller as **ST7789V**. ILI9341 is a *different* controller commonly confused with this board — anyone sourcing a driver library from the inventory table would pick the wrong one.

### 🟡 C-10 · `fieldsense/transport/` is broken

`import fieldsense.transport` raises `ModuleNotFoundError: No module named 'fieldsense.transport.base'`. It is a stale duplicate of `fieldsense/hardware/transport/`; nothing imports it, so tests are unaffected. Flagged in an earlier review and still present.

**Action:** delete the directory.

### 🟠 C-11 · 181 compiled `.pyc` files are tracked, and there is no `.gitignore`

`git ls-files` returns **181** `__pycache__/*.pyc` entries. The repository has no `.gitignore`, so build artifacts and `.DS_Store` are committed alongside source.

This is not cosmetic. Compiled bytecode changes on every run and conflicts on every merge, which is precisely the class of noise that lets a real regression slip through unnoticed — and this repository has already lost its `README.md` to a merge (**A-1**). Removing the noise makes the next merge legible.

**Action:**

```
# .gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.DS_Store
*.egg-info/
artifacts/*.html
```

then `git rm -r --cached` the tracked `__pycache__` directories. Not performed here — it rewrites the index, which is the maintainer's call, and `artifacts/*.html` in particular is a judgement call since the demo dashboard may be wanted in-tree for the competition.

---

## D. What is in good shape

Worth recording, so the next audit does not re-litigate it.

- **Evidence classification.** `hardware_test/*` documents separate `DATASHEET` / `PHYSICALLY VERIFIED` / `MEASURED` / `SOFTWARE VERIFIED` / `ASSUMED` / `PENDING`. This is unusually disciplined and should be preserved.
- **File references.** Exactly one broken reference (C-5) across every document checked.
- **Negative-case testing.** The UNO Q UART test verifies *disconnect detection*, not just loopback success.
- **Honest boundary language.** `PROTOTYPE_ONLY`, `PENDING_HARDWARE`, `HARDWARE_SPEC_REQUIRED`, `decision_support_only` are used consistently across code and documentation.
- **Failure modes captured.** The SPI contention signature (`Z=4095, X=0, Y=0`) and the DE/RE truncation hazard are both written down. That is exactly the knowledge that is normally lost.

---

## E. Recommended order of work

| # | Action | Effort | Severity |
| :--- | :--- | :--- | :--- |
| 1 | Decide TFT Route A vs B (**C-1**) | Decision | 🔴 |
| 2 | Update test baseline 105 → 147 (**A-2**) | Minutes | 🔴 |
| 3 | Port AI edits into `PROJECT_HANDBOOK.md`, then de-duplicate `docs/` (**B-1**) | ~1 hour | 🟠 |
| 4 | Add `ai/` to `SOFTWARE_SPEC.md` §1; update §13 and `SYSTEM_ARCHITECTURE.md` §8 (**C-2**, **C-3**) | ~1 hour | 🟠 |
| 5 | Add `NarrativeGuard` as `D-011` in `DECISION_LOG.md` (**C-3**) | ~30 min | 🟠 |
| 6 | Refresh `SPECIFICATION_REGISTER.md`; add `AI-01`…`AI-04` (**C-4**) | ~30 min | 🟠 |
| 7 | Fix `test_q.*` → `main.py`/`sketch.ino` (**C-5**) | Minutes | 🟡 |
| 8 | Strip Windows absolute paths (**C-7**) | Minutes | 🟡 |
| 9 | Delete `fieldsense/transport/` (**C-10**) | Minutes | 🟡 |
| 10 | Canonicalise sensor name; fix TFT vendor field (**C-8**, **C-9**) | Minutes | 🟡 |
| 11 | Add `.gitignore`, untrack `__pycache__` (**C-11**) | Minutes | 🟠 |

Items 2 and 7–10 are mechanical and safe. Items 3–6 change meaning and deserve review. Item 1 is an engineering decision, not a documentation task.

---

## F. Delivered by this audit

| Artifact | Change |
| :--- | :--- |
| `README.md` | Rewritten. Directory map covering every directory, quick start, architecture, hardware BOM, documentation index, known gaps. |
| `TESTING_GUIDE.md` | New. Four-level test ladder, per-component standalone procedures with wiring and pass criteria, integration procedures, troubleshooting table, explicit not-yet-testable list. |
| `docs/DOCUMENTATION_AUDIT.md` | This document. |

No source code was modified. Test baseline unchanged at 147 passing.
