---
timestamp: "2026-05-14T17:40:18Z"
bootstrapped_at: "2026-05-14T20:53:00Z"
author: "2355287-davecthomas"
branch: "main"
thread_id: "bootstrap"
turn_id: "4"
decision_candidate: true
ai_generated: true
ai_model: "claude-sonnet-4.5"
ai_tool: "claude"
ai_surface: "claude-code"
ai_executor: "local-agent"
related_adrs: []
files_touched:
  - "docs/trip-planner.md"
  - "src/trip_planner/errors.py"
  - "src/trip_planner/cli.py"
  - "src/trip_planner/loader.py"
  - "src/trip_planner/renderer.py"
verification:
  - "docs/trip-planner.md §8 error table maps each typed exception to a CLI exit code."
  - "errors.py defines TripPlannerError as the root with three subclasses: SpecLoadError, SpecValidationError, RenderError."
  - "cli.py wraps the entire flow in a single `except TripPlannerError` so internal exceptions surface as clean messages, never raw tracebacks (unless --verbose)."
---

## Why

- The CLI is the only externally-observable error surface for this engine, and the choice of how internal failures map to CLI behavior is a contract that downstream callers (CI scripts, automation, humans) will rely on. The decision is to **funnel all internal failures through a single typed exception hierarchy rooted at `TripPlannerError`, with three named subclasses that map to specific CLI exit codes and a single `except TripPlannerError` wrapper in the CLI**. Raw tracebacks are reserved for `--verbose`. This is the engine's error contract.

## What changed

- `src/trip_planner/errors.py` defines `TripPlannerError` as the root and three subclasses with distinct semantics:
  - `SpecLoadError` — YAML cannot be parsed (file missing, malformed YAML)
  - `SpecValidationError` — YAML parses but fails the Pydantic schema
  - `RenderError` — template/runtime missing, write failure, etc.
- `src/trip_planner/cli.py` wraps the entire `render`/`validate`/`full-trip-url` flow in a single `except TripPlannerError as exc` block, emits a clean human-readable message, and sets exit code 1 (load/validation failures) or 2 (render failures) accordingly. `--verbose` flips logging to DEBUG and emits the full traceback.

## Evidence

- `docs/trip-planner.md` §8 table:

  | Exception | When raised | CLI behavior |
  | --- | --- | --- |
  | `SpecLoadError` | YAML cannot be parsed | Exit 1, print path and parse error |
  | `SpecValidationError` | YAML parses but does not match the schema | Exit 1, print Pydantic-style errors |
  | `RenderError` | Template/runtime missing, write failure, etc. | Exit 2, print exception |

- `docs/trip-planner.md` §8 final paragraph: "All three inherit from `TripPlannerError`. The CLI wraps the entire flow in a single `except TripPlannerError` so internal exceptions surface as clean messages, never raw tracebacks (unless `--verbose` is passed)."
- Logging convention: `TripPlanner.<module>` namespace, INFO by default, DEBUG with `--verbose`.

## Next

- Promote to ADR so any future CLI subcommand, library extension, or alternate template skin honors the same error funnel and exit-code mapping rather than introducing a new ad-hoc surface.
