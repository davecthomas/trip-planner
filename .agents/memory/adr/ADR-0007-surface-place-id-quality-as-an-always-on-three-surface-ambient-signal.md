# ADR-0007 Surface place_id quality as an always-on three-surface ambient signal

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

Purpose: Surface place_id quality as an always-on three-surface ambient signal
Derived from: [2026-05-14T20-57-19Z--2355287-davecthomas--adr-inspector](../daily/2026-05-14/events/2026-05-14T20-57-19Z--2355287-davecthomas--adr-inspector.md)

## Context

- The engine accepts that `place_id` capture is an **incremental, ongoing data-quality task** — the YAML can be authored without place IDs and still render usefully (Google falls back to a name+city search). The decision to record is that the engine surfaces this gap **everywhere, always, in three concurrent registers** rather than as a one-time audit. A single classifier (`placeQuality(stop)` → `verified` / `fallback` / `n/a`) drives an inline badge per stop card, a per-plan enumerated panel, **and** a `console.warn` on every render. This is a deliberate "data-quality-as-ambient-signal" pattern: the gap is impossible to ignore in the UI, impossible to ignore during dev, and the verification panel surfaces the exact stop names that still need `place_id` so each pass of editing chips away at the list. The alternative (a one-off audit script) would have been less intrusive but would have let `place_id` gaps quietly accumulate; the alternative (no audit at all) would have hidden the silent UX degradation of name+city fallback from the user. The always-on three-surface design is the deliberate choice.
- The three-state classifier (`verified` / `fallback` / `n/a`) is intentional too — `n/a` for personal endpoints means the audit does not falsely flag origin/destination stops where Place semantics don't apply, so the badge and the count both stay honest.

## Decision

- `docs/trip-planner.md` §6 defines `placeQuality(stop)` as a single runtime function returning one of three states:
  - `verified` — business stop with a `place_id` (deterministic Google Place landing)
  - `fallback` — business stop without a `place_id` (Google falls back to name+city search)
  - `n/a` — personal endpoint (origin/dest); Place semantics don't apply
- `docs/trip-planner.md` §6 names the three surfaces driven by the same classifier:
  1. The day-view verification panel computes per-plan counts and lists every fallback stop by name (or shows "0 stops on name-query fallback").
  2. Inline ✓ / ⚠ badge next to every "Open in Maps" button on every stop card.
  3. A `console.warn` is emitted on every render whenever any fallbacks exist, naming the affected plan and stops.
- `docs/trip-planner.md` §3.5 declares `place_id` as an optional field on every stop type, making the audit work without forcing authors to capture place IDs up-front.

## Consequences

- Promote to ADR. The "data-quality-as-ambient-signal" pattern is easy to dilute under a future refactor ("the console.warn is noisy, let's gate it behind a debug flag" — which would defeat its purpose as a progress signal). An ADR captures the deliberate three-surface design and the rationale that ties it to the incremental `place_id` capture workflow.

## Source memory events

- [2026-05-14T20-57-19Z--2355287-davecthomas--adr-inspector](../daily/2026-05-14/events/2026-05-14T20-57-19Z--2355287-davecthomas--adr-inspector.md)

## Related code paths

- docs/trip-planner.md
