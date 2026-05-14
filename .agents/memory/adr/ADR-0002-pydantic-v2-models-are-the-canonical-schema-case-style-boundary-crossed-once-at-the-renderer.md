# ADR-0002 Pydantic v2 models are the canonical schema; case-style boundary crossed once at the renderer

Status: accepted
Date: 2026-05-14
Owners: 2355287-davecthomas
Must read: true
Supersedes: 
Superseded by: 

Purpose: Pydantic v2 models are the canonical schema; case-style boundary crossed once at the renderer
Derived from: [2026-05-14T17-40-16Z--2355287-davecthomas--thread_bootstrap--turn_2](../daily/2026-05-14/events/2026-05-14T17-40-16Z--2355287-davecthomas--thread_bootstrap--turn_2.md)

## Context

- A central question for any data-driven render engine is "where is the schema authoritative?" The decision here is that **Pydantic v2 models in `src/trip_planner/models.py` are the canonical schema**, the YAML loader's only job is to feed those models, and the case-style boundary (snake_case in YAML/Python, camelCase at the JS runtime) is crossed exactly once — in the renderer's `to_runtime_dict()`. Without this rule there are three plausible places to validate (loader, renderer, runtime JS), three plausible places to define field names, and the engine drifts. With it, every other piece of the system has one trustworthy data shape to consume.

## Decision

- `loader.py` parses YAML to a plain dict with no transformation; `models.py` takes that dict through Pydantic validation and surfaces typed errors via `SpecValidationError`; `renderer.py.to_runtime_dict()` converts the validated model to camelCase JSON only at the moment of embedding into the HTML.
- The §3 YAML schema in `docs/trip-planner.md` is explicit that "the shapes below are the authoritative source — they map 1:1 to the Pydantic models in `src/trip_planner/models.py`."

## Consequences

- Promote to ADR. Future ADRs about adding stop types, additional validation, or an alternate skin must reference this boundary and not validate elsewhere or rename fields off-boundary.

## Source memory events

- [2026-05-14T17-40-16Z--2355287-davecthomas--thread_bootstrap--turn_2](../daily/2026-05-14/events/2026-05-14T17-40-16Z--2355287-davecthomas--thread_bootstrap--turn_2.md)

## Related code paths

- docs/trip-planner.md
- src/trip_planner/models.py
- src/trip_planner/loader.py
- src/trip_planner/renderer.py
