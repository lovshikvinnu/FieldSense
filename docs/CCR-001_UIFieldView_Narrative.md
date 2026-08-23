# Contract Change Request CCR-001

**Status:** `PENDING_ARCHITECT_SIGNOFF`
**Raised:** 2026-08-23
**Protocol:** `docs/archive/03_ARCHITECTURE.md` section 30

---

## 1. Change ID & Title

`CCR-001` — Add optional `narrative` field to `UIFieldView` for the AI explanation layer.

## 2. Target Frozen Contract

Frozen contract #10: `UIFieldView` (`fieldsense.presentation.models`).

## 3. Current Behavior & Signature

```python
@dataclass(frozen=True)
class UIFieldView:
    field: FieldSummary
    gps_status: GPSStatus
    sampling_status: SamplingStatus
    health_summary: HealthSummary
    map: MapView
    zones: List[UIZone]
    recommendations: List[UIRecommendation]
    system_status: SystemStatus
```

## 4. Proposed Modification

Append one optional, defaulted field:

```python
    narrative: Optional[AINarrative] = None
```

`to_dict()` emits `"narrative": null` when absent. `from_dict()` tolerates a
missing or null key. No existing field is renamed, reordered, retyped, or removed.

## 5. Rationale & Architectural Necessity

`docs/03_ARCHITECTURE.md` section 22 and `docs/PROJECT_HANDBOOK.md` section 7b
specify a downstream AI explanation layer whose output is displayed on the
dashboard. The presentation layer is strictly passive (principle 4), so it cannot
generate the text itself, and `LocalUIRenderer` consumes `UIFieldView` exclusively
(section 19). The view model is therefore the only correct carrier.

The alternative — passing the narrative as a second argument to `render_html()` —
was rejected because it changes a public method signature, bypasses the single
UI data contract, and would exclude the narrative from `UIFieldView` serialization.

## 6. Backward Compatibility & Migration Impact

**Fully backward compatible. No migration required.**

- Field is defaulted, so every existing constructor call remains valid.
- `UIViewAdapter.adapt()` signature is unchanged and still returns `narrative=None`.
- `LocalUIRenderer.render_html()` signature is unchanged.
- Previously serialized payloads deserialize unchanged.
- The dashboard renders completely when `narrative` is `None`; the summary card
  is simply not displayed.
- Regression baseline: 105/105 pre-existing tests pass unmodified.

## 7. Affected Code Modules & Test Files

| File | Change |
| :--- | :--- |
| `fieldsense/presentation/models.py` | Field added; `to_dict`/`from_dict` updated |
| `fieldsense/presentation/renderer.py` | Conditional summary card, CSS, `renderNarrative()` |
| `fieldsense/demo.py` | Optional stage 7b, `enable_narrative` flag, summary keys |
| `tests/test_ai.py` | New: 29 tests covering the field, round-trip, and rendering |

## 8. Determinism Impact

`docs/archive/03_ARCHITECTURE.md` section 25 requires bit-exact reproducible output.
`AINarrative` is declared **non-normative presentation text** and is excluded
from that guarantee when produced by a model backend.

Mitigations already in place:

- `MockAIAdapter` is bit-exact and reports `generation_time_ms = 0.0` rather than
  a measured wall-clock value, so it introduces no run-to-run variance.
- All golden scenario, determinism, and benchmark tests use `MockAIAdapter`.
- The deterministic core (validation, scoring, spatial, zones, recommendations)
  is untouched and remains bit-exact.

## 9. Boundary Preservation

- The AI layer cannot alter any deterministic value; it receives a read-only
  `ExplanationContext` and returns text only.
- `NarrativeGuard` deterministically rejects dosages, agrochemical names,
  carbon claims, and any number absent from the context before display.
- The dashboard labels the panel as template- or AI-generated and states
  `decision_support_only`.
- No new runtime dependency: `pyproject.toml` `dependencies` remains `[]`.

## 10. Human Architect Sign-off & Approval

| Role | Name | Decision | Date |
| :--- | :--- | :--- | :--- |
| System Architect | _pending_ | _pending_ | _pending_ |
