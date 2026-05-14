# ADR-0003 Python and JS sibling implementations of URL builders and consumption indicator must stay in sync

Status: accepted
Date: 2026-05-14
Owners: 2355287-davecthomas
Must read: true
Supersedes: 
Superseded by: 

Purpose: Python and JS sibling implementations of URL builders and consumption indicator must stay in sync
Derived from: [2026-05-14T17-40-17Z--2355287-davecthomas--thread_bootstrap--turn_3](../daily/2026-05-14/events/2026-05-14T17-40-17Z--2355287-davecthomas--thread_bootstrap--turn_3.md)

## Context

- The engine intentionally implements the same algorithm twice: once in Python (for unit tests, for offline CLI use, and for build-side computation) and once in inlined runtime JS (for in-browser interactivity). This is a deliberate trade — duplication for testability and offline reach — but it is also the most fragile invariant in the codebase, because any drift between the two implementations produces silently-incorrect Maps URLs or silently-incorrect SoC indicators with no test failure. The decision to record is that **the Python and JS sibling implementations are a contract; they MUST be edited together, and the dedup rule, encoding rules, and trigger rules are part of that contract.**

## Decision

- `src/trip_planner/maps.py` defines `dirUrl`, `placeUrl`, `buildFullTripMapsUrl`, `buildDayMapsUrl` with the address-match-or-coord-proximity dedup (`|Δlat| < 0.001` AND `|Δlng| < 0.001`) and the `%20`→`+`, `%2C` left as `,` encoding. `templates/runtime.js` carries the JS implementation of the same four builders with identical semantics.
- `src/trip_planner/consumption.py` defines `evaluate_indicator(...)` for the §3.4 AC conservation indicator; `templates/runtime.js` mirrors it line-for-line with the same trigger rule (AC-on arrival SoC < 25% AND AC-off improves by ≥ 3 percentage points).
- The v14 refactor of the maps URL builders (per `samples/sd_austin_spec.md` §12.2) extracted a shared `encodeStopsAsMapsPath(stops)` helper inside the JS so the full-trip and per-day builders can not drift apart inside JS — the same shape applies on the Python side via `maps.py`.

## Consequences

- Promote to ADR. This is the rule most likely to be silently violated by a future contributor (or a future agent), and an ADR makes it discoverable from the index.

## Source memory events

- [2026-05-14T17-40-17Z--2355287-davecthomas--thread_bootstrap--turn_3](../daily/2026-05-14/events/2026-05-14T17-40-17Z--2355287-davecthomas--thread_bootstrap--turn_3.md)

## Related code paths

- docs/trip-planner.md
- src/trip_planner/maps.py
- src/trip_planner/templates/runtime.js
- tests/test_maps.py
