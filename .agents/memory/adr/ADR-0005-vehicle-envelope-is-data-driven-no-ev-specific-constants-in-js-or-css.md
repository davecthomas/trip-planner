# ADR-0005 Vehicle envelope is data-driven; no EV-specific constants in JS or CSS

Status: accepted
Date: 2026-05-14
Owners: 2355287-davecthomas
Must read: true
Supersedes: 
Superseded by: 

Purpose: Vehicle envelope is data-driven; no EV-specific constants in JS or CSS
Derived from: [2026-05-14T17-40-19Z--2355287-davecthomas--thread_bootstrap--turn_5](../daily/2026-05-14/events/2026-05-14T17-40-19Z--2355287-davecthomas--thread_bootstrap--turn_5.md)

## Context

- The engine is intentionally portable across electric vehicles. The decision recorded here is that **all consumption-envelope constants live in the YAML `vehicle` block; no EV-specific values may be hard-coded in `runtime.js`, `consumption.py`, or `styles.css`**. To use a different EV the user replaces the `vehicle` block (and the per-stop `elevation_ft` values) and the engine produces correct behavior with no code change. This rule keeps the engine from accidentally becoming a Tesla-Model-Y-Performance renderer and is the basis on which the §3.4 AC indicator and the §3.3 effective-range envelope can claim to be data-driven rather than coincidental.

## Decision

- `docs/trip-planner.md` §3.2 makes the vehicle block the carrier of every consumption parameter the runtime reads: `usable_pack_kwh`, `reserve_soc_pct`, `baseline_wh_per_mi`, `ac_penalty_wh_per_mi`, `ac_window_start`, `ac_window_end`, `climb_kwh_per_1000ft`, `regen_recovery`, plus the §3.4 indicator thresholds (`ac_indicator_arrival_threshold_pct`, `ac_indicator_min_improvement_pp`).
- The per-leg projection function (Python `consumption.py`, JS `runtime.js`) reads these constants from the embedded JSON, never from inlined literals.

## Consequences

- Promote to ADR. This rule is what permits future trips for non-Tesla EVs without forking the engine, and it should be visible in the index so contributors do not silently inline EV-specific constants while extending the runtime.

## Source memory events

- [2026-05-14T17-40-19Z--2355287-davecthomas--thread_bootstrap--turn_5](../daily/2026-05-14/events/2026-05-14T17-40-19Z--2355287-davecthomas--thread_bootstrap--turn_5.md)

## Related code paths

- docs/trip-planner.md
- src/trip_planner/models.py
- src/trip_planner/templates/runtime.js
- trips/sd_austin.yaml
