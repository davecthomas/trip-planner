---
timestamp: "2026-05-14T21:08:26Z"
author: "2355287-davecthomas"
branch: "main"
thread_id: "adr-inspector"
turn_id: "3"
decision_candidate: true
ai_generated: true
ai_model: "claude-sonnet-4.5"
ai_tool: "claude"
ai_surface: "claude-code"
ai_executor: "local-agent"
related_adrs:
  - "ADR-0003"
  - "ADR-0005"
files_touched:
  - "docs/trip-planner.md"
verification:
  - "docs/trip-planner.md §6.5 defines the AC indicator as a per-leg evaluation that compares two scenarios (AC on vs AC off) and fires only when BOTH a threshold gate AND an improvement gate are satisfied."
  - "docs/trip-planner.md §6.5 names both gates as data-driven constants in the YAML vehicle block: `vehicle.ac_indicator_arrival_threshold_pct` and `vehicle.ac_indicator_min_improvement_pp` — neither is hard-coded in JS or Python."
  - "docs/trip-planner.md §6.5 makes the silent-by-default behavior explicit: 'The indicator stays silent when arrival SoC is comfortable — no noise on well-buffered legs.'"
  - "docs/trip-planner.md §6.5 declares the build-side mirror: `evaluate_indicator(...)` in `src/trip_planner/consumption.py` is the canonical Python implementation that the JS in `templates/runtime.js` mirrors line-for-line."
---

## Why

- The §3.4 AC conservation indicator is a behavioral signal whose value depends entirely on its signal-to-noise ratio. A naive design would fire any time AC adds meaningful energy demand — but on well-buffered legs (arrival SoC comfortably above reserve) the alert would be noise, and on legs where the AC-off scenario is only marginally better than AC-on the user has no meaningful action to take. The decision to record is the **two-gate silent-by-default trigger**: the indicator fires only when **both** (a) the AC-on projected arrival SoC falls below `vehicle.ac_indicator_arrival_threshold_pct` AND (b) the AC-off projection improves the AC-on figure by at least `vehicle.ac_indicator_min_improvement_pp` percentage points. Either gate alone would be misleading: the threshold gate alone would fire on legs where AC contributes negligibly (e.g. flat, short, AC window doesn't apply), giving the user no actionable lever; the improvement gate alone would fire on legs with massive AC penalty even when arrival SoC is still comfortable (e.g. 50% AC-on vs 60% AC-off — fine either way). Both gates together is the deliberate choice — the indicator only surfaces when AC is materially driving you toward a tight margin AND switching it off is a real lever.
- The thresholds themselves are exposed in the YAML `vehicle` block (per ADR-0005's data-drivenness rule), so different vehicles can tune the gates without code changes — but the **trigger shape** (two gates, AND-composed, silent on either-gate-misses) is an architectural property that is independent of the numbers and must survive future tuning.
- The decision is at risk of dilution under future refactors: someone trying to make the indicator "more helpful" might lower the improvement gate to 1pp, or remove it entirely so the threshold gate fires alone, or invert the silent-by-default behavior into an always-on display. Each of those changes would defeat the indicator's purpose as a focused signal and degrade it into noise that users learn to ignore. The ADR captures this risk explicitly.

## What changed

- `docs/trip-planner.md` gains a new §6.5 "Consumption envelope and the §3.4 AC indicator" that formalizes the per-leg evaluation:
  - For every `charge` stop, two projected arrival SoCs are computed at the next stop: AC-on (baseline + AC penalty if `depart` falls in the AC window + elevation penalty) and AC-off (baseline + elevation penalty only).
  - The trigger fires when **both** conditions hold: AC-on projection < `vehicle.ac_indicator_arrival_threshold_pct` **and** AC-off improves the AC-on figure by ≥ `vehicle.ac_indicator_min_improvement_pp`.
  - When the trigger fires, an amber row appears inside the departure-side charge stop card with both projections surfaced numerically; otherwise the indicator stays silent.
- `docs/trip-planner.md` §3.2 declares both gate thresholds as YAML fields on the `vehicle` block — `ac_indicator_arrival_threshold_pct` and `ac_indicator_min_improvement_pp` — so the gate values are data-driven per ADR-0005.
- `docs/trip-planner.md` §6.5 declares `src/trip_planner/consumption.py::evaluate_indicator(...)` as the Python implementation and `templates/runtime.js` as its line-for-line JS mirror (per ADR-0003).

## Evidence

- `docs/trip-planner.md` §6.5 (trigger composition): "The trigger fires when **both** conditions hold: AC-on projected arrival SoC is below `vehicle.ac_indicator_arrival_threshold_pct`. AC-off projection improves the AC-on figure by at least `vehicle.ac_indicator_min_improvement_pp` percentage points."
- `docs/trip-planner.md` §6.5 (silent-by-default property): "When the trigger fires, an amber row appears inside the departure-side charge stop card with both projections surfaced numerically so the user can evaluate the actual margin. The indicator stays silent when arrival SoC is comfortable — no noise on well-buffered legs."
- `docs/trip-planner.md` §6.5 (two-scenario projection model): "For every `charge` stop in the day view, the runtime evaluates the projected arrival SoC at the next stop under two scenarios: **AC on:** baseline + AC penalty (if `depart` falls in the AC window) + elevation penalty (if both stops carry `elevation_ft`). **AC off:** baseline + elevation penalty only."
- `docs/trip-planner.md` §3.2 schema (gate constants are YAML, not code): "`ac_indicator_arrival_threshold_pct: 25   # fire below this projected SoC` / `ac_indicator_min_improvement_pp: 3       # AC-off must improve by ≥ this much`"
- `docs/trip-planner.md` §6.5 (Python/JS sibling): "The same algorithm runs in `src/trip_planner/consumption.py` as `evaluate_indicator(...)` so the build side can compute the indicator without a browser (useful for tests, the CLI, and offline reports). The JS implementation in `templates/runtime.js` mirrors it line-for-line; the two MUST be edited together."

## Next

- Promote to ADR. The two-gate silent-by-default trigger is the kind of behavioral invariant that future contributors are most likely to erode unintentionally — someone trying to make the indicator "more visible" or "more helpful" might lower the improvement gate, remove it, or invert the default to always-on. An ADR captures the deliberate signal-to-noise rationale and the AND-composition of the two gates so that future changes to the thresholds (allowed) are kept distinct from changes to the trigger shape (requires an ADR supersede).
