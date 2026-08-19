# FieldSense AI

Offline portable edge-intelligence platform for multi-point soil assessment and Carbon Readiness.

## Sprint 1 Foundation

This sprint implements the frozen core domain models:
- `FieldSample`
- `FieldSession`
- Standard enums: `SampleSource`, `ValidationState`, `SessionStatus`

## Package Structure

- `fieldsense/domain`: Core domain models and enums
- `fieldsense/input`: Sensor adapter interfaces (future)
- `fieldsense/intelligence`: Deterministic processing pipeline (future)
- `fieldsense/spatial`: Interpolation engine (future)
- `fieldsense/zones`: Zone detection engine (future)
- `fieldsense/recommendations`: Action recommendation engine (future)
- `fieldsense/storage`: Session storage layer (future)
- `fieldsense/application`: Application service orchestration (future)
- `fieldsense/presentation`: UI / CLI interfaces (future)
- `fieldsense/ai`: LLM / AI explanation modules (future)
- `tests`: Unit tests for domain models
