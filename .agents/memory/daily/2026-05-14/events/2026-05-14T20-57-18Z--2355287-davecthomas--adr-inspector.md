---
timestamp: "2026-05-14T20:57:18Z"
author: "2355287-davecthomas"
branch: "main"
thread_id: "adr-inspector"
turn_id: "1"
decision_candidate: true
ai_generated: true
ai_model: "claude-sonnet-4.5"
ai_tool: "claude"
ai_surface: "claude-code"
ai_executor: "local-agent"
related_adrs: []
files_touched:
  - "docs/trip-planner.md"
verification:
  - "docs/trip-planner.md §4 'State' table lists state.plan, state.day, state.mode each with dual persistence to localStorage[<prefix>-...] AND URL fragment."
  - "docs/trip-planner.md §4 final paragraph: 'Fragment values take precedence over localStorage on initial load. Out-of-range values fall back to defaults silently — no broken bookmarks.'"
  - "docs/trip-planner.md §3.1 declares meta.storage_prefix as the localStorage key prefix, namespacing per-trip state so multiple trips can coexist in different tabs."
  - "docs/trip-planner.md §10 'A different storage prefix' confirms the prefix is the per-trip namespace boundary: 'Multiple distinct trips can be open in different tabs without state collision.'"
---

## Why

- The render engine emits a static HTML file with no backend, so the only state surfaces available to the runtime are the URL and the browser's localStorage. The spec deliberately uses **both**, with a precedence rule: URL fragment wins on load, localStorage holds the personal continuity between visits. This is the decision to record — that the engine treats URL fragments as the canonical shareable state and localStorage as a per-device fallback, with silent degradation on out-of-range values so stale bookmarks never break the page. The alternative (localStorage-only) would have killed shareability of a specific day/plan view; the alternative (fragment-only) would have lost per-device continuity. The two-tier model with fragment-precedence is the deliberate compromise.
- The `meta.storage_prefix` field exists specifically so multiple distinct trip files can coexist in different tabs without colliding in localStorage. This is what makes the engine multi-trip-friendly without any backend coordination — every trip carries its own state namespace as data, not as code.

## What changed

- `docs/trip-planner.md` §4 codifies the state model: three keys (`state.plan`, `state.day`, `state.mode`), each persisted to **both** `localStorage[<prefix>-<key>]` and the URL fragment. Fragment example: `#plan=Baseline&day=2&mode=day`.
- `docs/trip-planner.md` §4 codifies the precedence and degradation rule: "Fragment values take precedence over localStorage on initial load. Out-of-range values fall back to defaults silently — no broken bookmarks."
- `docs/trip-planner.md` §3.1 codifies the per-trip namespace mechanism: `meta.storage_prefix` (e.g. `"sd-austin"`) is the localStorage key prefix, declared in YAML alongside the trip's other metadata.
- `docs/trip-planner.md` §10 reinforces this as a customization point: changing `meta.storage_prefix` lets multiple trips run in parallel tabs.

## Evidence

- `docs/trip-planner.md` §4 'State' table:
  ```
  state.plan | the `key` of one of the plans | localStorage[<prefix>-plan], URL fragment
  state.day  | 1-based day index             | localStorage[<prefix>-day],  URL fragment
  state.mode | day or agenda                 | localStorage[<prefix>-mode], URL fragment
  ```
- `docs/trip-planner.md` §4 explicit precedence + degradation rule: "Fragment values take precedence over localStorage on initial load. Out-of-range values fall back to defaults silently — no broken bookmarks."
- `docs/trip-planner.md` §3.1 schema: `storage_prefix: "sd-austin"   # Used as the localStorage key prefix` is a required string in every `meta` block.
- `docs/trip-planner.md` §10: "Change `meta.storage_prefix` in YAML. Multiple distinct trips can be open in different tabs without state collision."

## Next

- Promote to ADR. The URL-fragment-over-localStorage precedence rule is the kind of decision that is silently reversed by a "convenience" refactor (e.g. switching to fragment-only or localStorage-only) — an ADR makes the bookmark-portability and tab-isolation guarantees discoverable from the index so future contributors understand why both layers exist together.
