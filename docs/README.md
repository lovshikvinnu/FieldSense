# FieldSense documentation

Start with the row that matches why you are here.

| I want to… | Read |
| :--- | :--- |
| Understand what the product is | [`../README.md`](../README.md) |
| Walk a field with the unit | [`FIELD_SESSION.md`](FIELD_SESSION.md) |
| Bring a bare board up to a working instrument | [`INTEGRATION_RUNBOOK.md`](INTEGRATION_RUNBOOK.md) → [`FIELD_RUN.md`](FIELD_RUN.md) |
| Wire it correctly | [`HARDWARE.md`](HARDWARE.md) |
| Understand how the software is built | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Set up the onboard language model | [`AI_DEPLOYMENT.md`](AI_DEPLOYMENT.md) |
| Test something | [`TESTING_GUIDE.md`](TESTING_GUIDE.md) |
| Know what is proven and what is not | [`STATUS.md`](STATUS.md) |
| Demonstrate it to someone | [`DEMO_GUIDE.md`](DEMO_GUIDE.md) |

## Active documents

| Document | Audience | Covers |
| :--- | :--- | :--- |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Developer | The authoritative architecture reference. Module contracts, algorithms, the decision log, and the frozen contracts with their change-control protocol. |
| [`HARDWARE.md`](HARDWARE.md) | Hardware | Component specifications, electrical requirements, register maps, wiring, and the verification status of each claim. |
| [`FIELD_SESSION.md`](FIELD_SESSION.md) | Operator | The field procedure. Power on, walk, sample, read the result off the glass — no laptop, no SSH, no typed commands. |
| [`FIELD_RUN.md`](FIELD_RUN.md) | Engineer | A single engineer-driven run from probe to dashboard, including flashing and gateway checks. |
| [`INTEGRATION_RUNBOOK.md`](INTEGRATION_RUNBOOK.md) | Engineer | Four-step bring-up — acquisition, contract, pipeline, display — each with a pass criterion. |
| [`AI_DEPLOYMENT.md`](AI_DEPLOYMENT.md) | Deployment | Local SLM setup, `NarrativeGuard`, the display bridge, and the standalone boot service. |
| [`TESTING_GUIDE.md`](TESTING_GUIDE.md) | Developer / Hardware | How to test every component, from pure software up to the assembled instrument, plus the test evidence register. |
| [`STATUS.md`](STATUS.md) | Everyone | The honest register: requirements alignment, open hardware items, and what is `VERIFIED` versus `PENDING_HARDWARE`. |
| [`OFFICIAL_PROJECT_REPORT.md`](OFFICIAL_PROJECT_REPORT.md) | Evaluator | The submission report — scope, evidence, and results in one document. |
| [`PROJECT_HANDBOOK.md`](PROJECT_HANDBOOK.md) | Everyone | Project purpose, roles, conventions, and working agreements. |
| [`DEMO_GUIDE.md`](DEMO_GUIDE.md) | Presenter | Walkthrough for judging and presentations. |

## Supporting directories

| Directory | What is in it |
| :--- | :--- |
| [`evidence/`](evidence/) | Validation reports and the datasets behind them. Claims made elsewhere in the documentation are sourced here. |
| [`archive/`](archive/) | Superseded and historical documents, kept because they record how decisions were reached. Not current. |
| [`images/`](images/) | Diagrams and UI captures used by the README and these documents. |

Hardware bench records live outside `docs/`, next to the scripts that produced
them, in [`../hardware/`](../hardware/).
