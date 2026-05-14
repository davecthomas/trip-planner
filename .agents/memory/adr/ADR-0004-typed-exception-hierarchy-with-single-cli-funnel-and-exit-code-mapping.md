# ADR-0004 Typed exception hierarchy with single CLI funnel and exit-code mapping

Status: accepted
Date: 2026-05-14
Owners: 2355287-davecthomas
Must read: true
Supersedes: 
Superseded by: 

Purpose: Typed exception hierarchy with single CLI funnel and exit-code mapping
Derived from: [2026-05-14T17-40-18Z--2355287-davecthomas--thread_bootstrap--turn_4](../daily/2026-05-14/events/2026-05-14T17-40-18Z--2355287-davecthomas--thread_bootstrap--turn_4.md)

## Context

- The CLI is the only externally-observable error surface for this engine, and the choice of how internal failures map to CLI behavior is a contract that downstream callers (CI scripts, automation, humans) will rely on. The decision is to **funnel all internal failures through a single typed exception hierarchy rooted at `TripPlannerError`, with three named subclasses that map to specific CLI exit codes and a single `except TripPlannerError` wrapper in the CLI**. Raw tracebacks are reserved for `--verbose`. This is the engine's error contract.

## Decision

- `src/trip_planner/errors.py` defines `TripPlannerError` as the root and three subclasses with distinct semantics:
  - `SpecLoadError` — YAML cannot be parsed (file missing, malformed YAML)
  - `SpecValidationError` — YAML parses but fails the Pydantic schema
  - `RenderError` — template/runtime missing, write failure, etc.
- `src/trip_planner/cli.py` wraps the entire `render`/`validate`/`full-trip-url` flow in a single `except TripPlannerError as exc` block, emits a clean human-readable message, and sets exit code 1 (load/validation failures) or 2 (render failures) accordingly. `--verbose` flips logging to DEBUG and emits the full traceback.

## Consequences

- Promote to ADR so any future CLI subcommand, library extension, or alternate template skin honors the same error funnel and exit-code mapping rather than introducing a new ad-hoc surface.

## Source memory events

- [2026-05-14T17-40-18Z--2355287-davecthomas--thread_bootstrap--turn_4](../daily/2026-05-14/events/2026-05-14T17-40-18Z--2355287-davecthomas--thread_bootstrap--turn_4.md)

## Related code paths

- docs/trip-planner.md
- src/trip_planner/errors.py
- src/trip_planner/cli.py
- src/trip_planner/loader.py
- src/trip_planner/renderer.py
