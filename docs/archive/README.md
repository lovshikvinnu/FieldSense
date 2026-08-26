# docs/archive/

Superseded and historical documents. **Nothing here is current.** They are kept
because they record how decisions were reached and what the evidence looked like
at the time — deleting them would remove the trail behind claims made elsewhere.

## Superseded by `ARCHITECTURE.md`

[`../ARCHITECTURE.md`](../ARCHITECTURE.md) was assembled from these three and
states so in its own header. They stayed in place afterwards and were a standing
source of "which one is authoritative?".

| File | Became |
| :--- | :--- |
| [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) | Part I — system design, MCU/MPU split, data flow |
| [`SOFTWARE_SPEC.md`](SOFTWARE_SPEC.md) | Part II — module contracts, algorithms, configuration |
| [`DECISION_LOG.md`](DECISION_LOG.md) | Part III — why each architectural decision was made |

> **One caveat, stated rather than hidden.** `DECISION_LOG.md` is fully contained
> in `ARCHITECTURE.md`. The other two are not quite: their *Verified Hardware
> Paths* sections were added after the consolidation and have not been folded in.
> If you need the verified GPS, JXBS, TFT or touch boundary paths as those two
> documents record them, read them here. Everything else in both is duplicated
> upstream.

## Audits

| File | What it was |
| :--- | :--- |
| [`MASTER_AUDIT_REPORT.md`](MASTER_AUDIT_REPORT.md) | Repository and architecture audit, 2026-08-23. Describes an earlier tree (105 tests, the pre-`firmware/` layout) and is accurate for that date only. |
| [`DOCUMENTATION_AUDIT.md`](DOCUMENTATION_AUDIT.md) | Documentation and testing audit, 2026-08-23. The consolidation of `docs/` from 21 files down to 8 plus an archive was carried out from this document's findings. |
| [`CCR-001_UIFieldView_Narrative.md`](CCR-001_UIFieldView_Narrative.md) | Contract change request for adding the AI narrative to `UIFieldView`. Kept as the record of the change-control process; the change itself has shipped. |

## Earlier planning material

Written 2026-08-09, before implementation, and superseded by the active
documents above.

| File | Superseded by |
| :--- | :--- |
| [`01_SOFTWARE_WORKPLAN.md`](01_SOFTWARE_WORKPLAN.md) | `SOFTWARE_SPEC.md`, then `ARCHITECTURE.md` |
| [`02_PROJECT_HANDBOOK.md`](02_PROJECT_HANDBOOK.md) | [`../PROJECT_HANDBOOK.md`](../PROJECT_HANDBOOK.md) |
| [`03_ARCHITECTURE.md`](03_ARCHITECTURE.md) | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| [`FieldSense_AI_Software_Workplan_AI_Agent_Handoff.md`](FieldSense_AI_Software_Workplan_AI_Agent_Handoff.md) | The three documents above, collectively |
| [`PROPOSAL_ALIGNMENT.md`](PROPOSAL_ALIGNMENT.md) | [`../STATUS.md`](../STATUS.md) §1 |
| [`SPECIFICATION_REGISTER.md`](SPECIFICATION_REGISTER.md) | [`../STATUS.md`](../STATUS.md) §2–6 |
| [`validation_and_limitations.md`](validation_and_limitations.md) | [`../evidence/TEST_AND_VALIDATION.md`](../evidence/TEST_AND_VALIDATION.md) |
