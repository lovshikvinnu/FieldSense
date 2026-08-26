# docs/evidence/

Validation reports and the data behind them. When a claim elsewhere in the
documentation says something was measured, this is where the measurement is.

| File | What it evidences |
| :--- | :--- |
| [`TEST_AND_VALIDATION.md`](TEST_AND_VALIDATION.md) | The test and validation evidence record for the deterministic pipeline: what each test covers and what it demonstrates. |
| [`SLM_VALIDATION.md`](SLM_VALIDATION.md) | The gate-by-gate procedure for proving a language model actually executed on the UNO Q — not that the tests passed, not that a narrative appeared, but that the model ran on the board. |
| [`SLM_V1_VALIDATION_REPORT.md`](SLM_V1_VALIDATION_REPORT.md) | The dated report of that run: available RAM, measured throughput, the Qwen-versus-TinyLlama head-to-head, and the acceptance and fidelity results. |
| `field_test_simulated.json` | A five-point run stamped `VIRTUAL`, produced by the simulated sensor path. Retained as the reference for what a simulated dataset looks like. It is **not** field data and nothing at runtime reads it. |

## Reading these honestly

Every dataset in this project carries its own provenance stamp, and the reports
above distinguish `LIVE_HARDWARE` from `VIRTUAL` from `UNSTAMPED` rather than
presenting them together. A run that proves the transport works is not a run
that proves the soil advice is correct — see [`../STATUS.md`](../STATUS.md) for
where that line currently falls.
