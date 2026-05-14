# ADR-0006 URL fragment overrides localStorage on load; out-of-range state silently falls back to defaults

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

Purpose: URL fragment overrides localStorage on load; out-of-range state silently falls back to defaults
Derived from: [2026-05-14T20-57-18Z--2355287-davecthomas--adr-inspector](../daily/2026-05-14/events/2026-05-14T20-57-18Z--2355287-davecthomas--adr-inspector.md)

## Context

- The render engine emits a static HTML file with no backend, so the only state surfaces available to the runtime are the URL and the browser's localStorage. The spec deliberately uses **both**, with a precedence rule: URL fragment wins on load, localStorage holds the personal continuity between visits. This is the decision to record — that the engine treats URL fragments as the canonical shareable state and localStorage as a per-device fallback, with silent degradation on out-of-range values so stale bookmarks never break the page. The alternative (localStorage-only) would have killed shareability of a specific day/plan view; the alternative (fragment-only) would have lost per-device continuity. The two-tier model with fragment-precedence is the deliberate compromise.
- The `meta.storage_prefix` field exists specifically so multiple distinct trip files can coexist in different tabs without colliding in localStorage. This is what makes the engine multi-trip-friendly without any backend coordination — every trip carries its own state namespace as data, not as code.

## Decision

- `docs/trip-planner.md` §4 codifies the state model: three keys (`state.plan`, `state.day`, `state.mode`), each persisted to **both** `localStorage[<prefix>-<key>]` and the URL fragment. Fragment example: `#plan=Baseline&day=2&mode=day`.
- `docs/trip-planner.md` §4 codifies the precedence and degradation rule: "Fragment values take precedence over localStorage on initial load. Out-of-range values fall back to defaults silently — no broken bookmarks."
- `docs/trip-planner.md` §3.1 codifies the per-trip namespace mechanism: `meta.storage_prefix` (e.g. `"sd-austin"`) is the localStorage key prefix, declared in YAML alongside the trip's other metadata.
- `docs/trip-planner.md` §10 reinforces this as a customization point: changing `meta.storage_prefix` lets multiple trips run in parallel tabs.

## Consequences

- Promote to ADR. The URL-fragment-over-localStorage precedence rule is the kind of decision that is silently reversed by a "convenience" refactor (e.g. switching to fragment-only or localStorage-only) — an ADR makes the bookmark-portability and tab-isolation guarantees discoverable from the index so future contributors understand why both layers exist together.

## Source memory events

- [2026-05-14T20-57-18Z--2355287-davecthomas--adr-inspector](../daily/2026-05-14/events/2026-05-14T20-57-18Z--2355287-davecthomas--adr-inspector.md)

## Related code paths

- docs/trip-planner.md
