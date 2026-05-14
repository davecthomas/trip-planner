---
timestamp: "2026-05-14T17:40:19Z"
bootstrapped_at: "2026-05-14T20:53:00Z"
author: "2355287-davecthomas"
branch: "main"
thread_id: "bootstrap"
turn_id: "5"
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
  - "src/trip_planner/templates/runtime.js"
  - "trips/sd_austin.yaml"
verification:
  - "docs/trip-planner.md §3.2 vehicle block lists every consumption parameter (baseline_wh_per_mi, ac_penalty_wh_per_mi, AC window, climb_kwh_per_1000ft, regen_recovery, indicator thresholds)."
  - "docs/trip-planner.md §3.2 final paragraph: 'no hard-coded EV constants live in the JS or CSS.'"
  - "docs/trip-planner.md §6.5: per-leg envelope reads from vehicle block + per-stop elevation_ft + per-stop socOut/legMiles/depart."
---

## Why

- The engine is intentionally portable across electric vehicles. The decision recorded here is that **all consumption-envelope constants live in the YAML `vehicle` block; no EV-specific values may be hard-coded in `runtime.js`, `consumption.py`, or `styles.css`**. To use a different EV the user replaces the `vehicle` block (and the per-stop `elevation_ft` values) and the engine produces correct behavior with no code change. This rule keeps the engine from accidentally becoming a Tesla-Model-Y-Performance renderer and is the basis on which the §3.4 AC indicator and the §3.3 effective-range envelope can claim to be data-driven rather than coincidental.

## What changed

- `docs/trip-planner.md` §3.2 makes the vehicle block the carrier of every consumption parameter the runtime reads: `usable_pack_kwh`, `reserve_soc_pct`, `baseline_wh_per_mi`, `ac_penalty_wh_per_mi`, `ac_window_start`, `ac_window_end`, `climb_kwh_per_1000ft`, `regen_recovery`, plus the §3.4 indicator thresholds (`ac_indicator_arrival_threshold_pct`, `ac_indicator_min_improvement_pp`).
- The per-leg projection function (Python `consumption.py`, JS `runtime.js`) reads these constants from the embedded JSON, never from inlined literals.

## Evidence

- `docs/trip-planner.md` §3.2 paragraph after the vehicle YAML block: "The runtime reads every consumption parameter from this block — no hard-coded EV constants live in the JS or CSS. To use a different EV, replace this block (and the per-stop `elevation_ft` values) and the engine produces the right behavior for the new vehicle."
- `docs/trip-planner.md` §6.5 enumerates the three inputs to the consumption envelope as (1) the `vehicle` block, (2) per-stop `elevation_ft`, (3) per-stop `socOut`/`legMiles`/`depart` — all data, no constants.
- `trips/sd_austin.yaml` instantiates the rule for a Tesla Model Y Performance: 75 kWh usable, 20% reserve, 330 Wh/mi baseline, 30 Wh/mi AC penalty, AC window 10:00–18:00, 2.35 kWh per 1,000 ft climb, 0.65 regen recovery, 25% / 3pp indicator thresholds.

## Next

- Promote to ADR. This rule is what permits future trips for non-Tesla EVs without forking the engine, and it should be visible in the index so contributors do not silently inline EV-specific constants while extending the runtime.
