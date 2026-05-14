# ADR-0008 AC conservation indicator fires only on a two-gate AND-composed trigger; silent on well-buffered legs

Status: accepted
Date: 2026-05-14
Owners: 2355287-davecthomas
Must read: true
Supersedes: 
Superseded by: 
ai-generated: True
ai-model: claude-sonnet-4.5
ai-tool: claude
ai-surface: claude-code
ai-executor: local-agent

Purpose: AC conservation indicator fires only on a two-gate AND-composed trigger; silent on well-buffered legs
Derived from: [2026-05-14T21-08-26Z--2355287-davecthomas--adr-inspector](../daily/2026-05-14/events/2026-05-14T21-08-26Z--2355287-davecthomas--adr-inspector.md)

## Context

- The §3.4 AC conservation indicator is a behavioral signal whose value depends entirely on its signal-to-noise ratio. A naive design would fire any time AC adds meaningful energy demand — but on well-buffered legs (arrival SoC comfortably above reserve) the alert would be noise, and on legs where the AC-off scenario is only marginally better than AC-on the user has no meaningful action to take. The decision to record is the **two-gate silent-by-default trigger**: the indicator fires only when **both** (a) the AC-on projected arrival SoC falls below `vehicle.ac_indicator_arrival_threshold_pct` AND (b) the AC-off projection improves the AC-on figure by at least `vehicle.ac_indicator_min_improvement_pp` percentage points. Either gate alone would be misleading: the threshold gate alone would fire on legs where AC contributes negligibly (e.g. flat, short, AC window doesn't apply), giving the user no actionable lever; the improvement gate alone would fire on legs with massive AC penalty even when arrival SoC is still comfortable (e.g. 50% AC-on vs 60% AC-off — fine either way). Both gates together is the deliberate choice — the indicator only surfaces when AC is materially driving you toward a tight margin AND switching it off is a real lever.
- The thresholds themselves are exposed in the YAML `vehicle` block (per ADR-0005's data-drivenness rule), so different vehicles can tune the gates without code changes — but the **trigger shape** (two gates, AND-composed, silent on either-gate-misses) is an architectural property that is independent of the numbers and must survive future tuning.
- The decision is at risk of dilution under future refactors: someone trying to make the indicator "more helpful" might lower the improvement gate to 1pp, or remove it entirely so the threshold gate fires alone, or invert the silent-by-default behavior into an always-on display. Each of those changes would defeat the indicator's purpose as a focused signal and degrade it into noise that users learn to ignore. The ADR captures this risk explicitly.

## Decision

- `docs/trip-planner.md` gains a new §6.5 "Consumption envelope and the §3.4 AC indicator" that formalizes the per-leg evaluation:
  - For every `charge` stop, two projected arrival SoCs are computed at the next stop: AC-on (baseline + AC penalty if `depart` falls in the AC window + elevation penalty) and AC-off (baseline + elevation penalty only).
  - The trigger fires when **both** conditions hold: AC-on projection < `vehicle.ac_indicator_arrival_threshold_pct` **and** AC-off improves the AC-on figure by ≥ `vehicle.ac_indicator_min_improvement_pp`.
  - When the trigger fires, an amber row appears inside the departure-side charge stop card with both projections surfaced numerically; otherwise the indicator stays silent.
- `docs/trip-planner.md` §3.2 declares both gate thresholds as YAML fields on the `vehicle` block — `ac_indicator_arrival_threshold_pct` and `ac_indicator_min_improvement_pp` — so the gate values are data-driven per ADR-0005.
- `docs/trip-planner.md` §6.5 declares `src/trip_planner/consumption.py::evaluate_indicator(...)` as the Python implementation and `templates/runtime.js` as its line-for-line JS mirror (per ADR-0003).

## Consequences

- Promote to ADR. The two-gate silent-by-default trigger is the kind of behavioral invariant that future contributors are most likely to erode unintentionally — someone trying to make the indicator "more visible" or "more helpful" might lower the improvement gate, remove it, or invert the default to always-on. An ADR captures the deliberate signal-to-noise rationale and the AND-composition of the two gates so that future changes to the thresholds (allowed) are kept distinct from changes to the trigger shape (requires an ADR supersede).

## Source memory events

- [2026-05-14T21-08-26Z--2355287-davecthomas--adr-inspector](../daily/2026-05-14/events/2026-05-14T21-08-26Z--2355287-davecthomas--adr-inspector.md)

## Related code paths

- docs/trip-planner.md
