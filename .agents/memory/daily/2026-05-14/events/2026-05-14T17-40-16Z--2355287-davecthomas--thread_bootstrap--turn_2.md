---
timestamp: "2026-05-14T17:40:16Z"
bootstrapped_at: "2026-05-14T20:53:00Z"
author: "2355287-davecthomas"
branch: "main"
thread_id: "bootstrap"
turn_id: "2"
decision_candidate: true
ai_generated: true
ai_model: "claude-sonnet-4.5"
ai_tool: "claude"
ai_surface: "claude-code"
ai_executor: "local-agent"
related_adrs: []
files_touched:
  - "docs/trip-planner.md"
  - "src/trip_planner/models.py"
  - "src/trip_planner/loader.py"
  - "src/trip_planner/renderer.py"
verification:
  - "docs/trip-planner.md §3 — schemas in YAML map 1:1 to Pydantic models in src/trip_planner/models.py."
  - "docs/trip-planner.md §3.5 final paragraph: snake_case in YAML/Python, camelCase at the JS boundary; renderer's to_runtime_dict() converts."
  - "tests/test_models.py and tests/test_loader.py pin the validation contract."
---

## Why

- A central question for any data-driven render engine is "where is the schema authoritative?" The decision here is that **Pydantic v2 models in `src/trip_planner/models.py` are the canonical schema**, the YAML loader's only job is to feed those models, and the case-style boundary (snake_case in YAML/Python, camelCase at the JS runtime) is crossed exactly once — in the renderer's `to_runtime_dict()`. Without this rule there are three plausible places to validate (loader, renderer, runtime JS), three plausible places to define field names, and the engine drifts. With it, every other piece of the system has one trustworthy data shape to consume.

## What changed

- `loader.py` parses YAML to a plain dict with no transformation; `models.py` takes that dict through Pydantic validation and surfaces typed errors via `SpecValidationError`; `renderer.py.to_runtime_dict()` converts the validated model to camelCase JSON only at the moment of embedding into the HTML.
- The §3 YAML schema in `docs/trip-planner.md` is explicit that "the shapes below are the authoritative source — they map 1:1 to the Pydantic models in `src/trip_planner/models.py`."

## Evidence

- `docs/trip-planner.md` §3 ("YAML schema") opening: shapes map 1:1 to Pydantic models.
- `docs/trip-planner.md` §3.5 final paragraph: "YAML uses `snake_case`. Python models match. The runtime JS expects `camelCase` ... so the renderer converts at the boundary."
- `docs/trip-planner.md` §8 error table ties `SpecValidationError` to the validation step specifically.
- `samples/sd_austin_spec.md` §9 per-stop schema uses camelCase exactly because that is what the runtime sees, after `to_runtime_dict()` has run — confirms the conversion-at-renderer rule, not at loader.

## Next

- Promote to ADR. Future ADRs about adding stop types, additional validation, or an alternate skin must reference this boundary and not validate elsewhere or rename fields off-boundary.
