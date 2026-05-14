---
timestamp: "2026-05-14T17:40:17Z"
bootstrapped_at: "2026-05-14T20:53:00Z"
author: "2355287-davecthomas"
branch: "main"
thread_id: "bootstrap"
turn_id: "3"
decision_candidate: true
ai_generated: true
ai_model: "claude-sonnet-4.5"
ai_tool: "claude"
ai_surface: "claude-code"
ai_executor: "local-agent"
related_adrs: []
files_touched:
  - "docs/trip-planner.md"
  - "src/trip_planner/maps.py"
  - "src/trip_planner/templates/runtime.js"
  - "tests/test_maps.py"
verification:
  - "docs/trip-planner.md §5: 'Python equivalents of all four live in src/trip_planner/maps.py so the algorithm is unit-tested on the Python side. The runtime JS uses the same algorithm — the same dedup, the same encoding.'"
  - "docs/trip-planner.md §6.5: consumption indicator runs in src/trip_planner/consumption.py and is mirrored line-for-line in templates/runtime.js; 'the two MUST be edited together.'"
  - "tests/test_maps.py covers the dedup rule explicitly using the SD-Austin sample as canonical fixture."
---

## Why

- The engine intentionally implements the same algorithm twice: once in Python (for unit tests, for offline CLI use, and for build-side computation) and once in inlined runtime JS (for in-browser interactivity). This is a deliberate trade — duplication for testability and offline reach — but it is also the most fragile invariant in the codebase, because any drift between the two implementations produces silently-incorrect Maps URLs or silently-incorrect SoC indicators with no test failure. The decision to record is that **the Python and JS sibling implementations are a contract; they MUST be edited together, and the dedup rule, encoding rules, and trigger rules are part of that contract.**

## What changed

- `src/trip_planner/maps.py` defines `dirUrl`, `placeUrl`, `buildFullTripMapsUrl`, `buildDayMapsUrl` with the address-match-or-coord-proximity dedup (`|Δlat| < 0.001` AND `|Δlng| < 0.001`) and the `%20`→`+`, `%2C` left as `,` encoding. `templates/runtime.js` carries the JS implementation of the same four builders with identical semantics.
- `src/trip_planner/consumption.py` defines `evaluate_indicator(...)` for the §3.4 AC conservation indicator; `templates/runtime.js` mirrors it line-for-line with the same trigger rule (AC-on arrival SoC < 25% AND AC-off improves by ≥ 3 percentage points).
- The v14 refactor of the maps URL builders (per `samples/sd_austin_spec.md` §12.2) extracted a shared `encodeStopsAsMapsPath(stops)` helper inside the JS so the full-trip and per-day builders can not drift apart inside JS — the same shape applies on the Python side via `maps.py`.

## Evidence

- `docs/trip-planner.md` §5 final paragraph: "Python equivalents of all four live in `src/trip_planner/maps.py` so the algorithm is unit-tested on the Python side. The runtime JS uses the same algorithm — the same dedup, the same encoding."
- `docs/trip-planner.md` §6.5 final paragraph: "The JS implementation in `templates/runtime.js` mirrors it line-for-line; the two MUST be edited together."
- `samples/sd_austin_spec.md` §12.2 implementation note: "v14 refactored §12.1 to share the segment-encoding and dedup logic with §12.2 via a single `encodeStopsAsMapsPath(stops)` helper ... This guarantees the two builders cannot drift apart on encoding, dedup, or output format."
- `tests/test_maps.py` is named in the spec as the gate that pins the dedup rule using the SD-Austin sample as the canonical fixture.

## Next

- Promote to ADR. This is the rule most likely to be silently violated by a future contributor (or a future agent), and an ADR makes it discoverable from the index.
