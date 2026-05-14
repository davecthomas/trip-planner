---
timestamp: "2026-05-14T22:34:58Z"
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
  - "docs/trip-planner.md §3.3 defines three plan fields with distinct roles: `key` (internal, used in state.plan / URL fragment / localStorage), `label` (title-bar text on agenda cover and sticky-header main button), `tagline` (optional plan-button sub-label)."
  - "docs/trip-planner.md §3.3 example deliberately uses an opaque key: `key: \"A\"` paired with `label: \"Plan A · 3D · 2N\"` and `tagline: \"Sat 5/23 AM departure\"` — distinct from the prior schema where `key: \"Baseline\"` carried both identity and presentation."
  - "docs/trip-planner.md §3.3 constrains keys to ≤16 chars, alphanumeric (plus `-` / `_`), and unique across plans — i.e. opaque-identifier semantics, not free-form presentation."
  - "docs/trip-planner.md §3.3 codifies the deterministic fallback rule: 'When [tagline is] absent the sub-label falls back to whatever follows the first `·` in `label`.' The rationale is stated explicitly: 'so users can scan plans by their human-readable descriptor (\"Sat 5/23 AM departure\") rather than memorize what each letter means.'"
  - "docs/trip-planner.md §4 'State' table confirms `state.plan` is keyed by `the key of one of the plans` and persisted to both `localStorage[<prefix>-plan]` and the URL fragment — i.e. the key is the durable contract for state persistence and shareable URLs, which is what forces it to stay opaque and stable."
---

## Why

- The render engine persists plan selection to both `localStorage` and the URL fragment (per ADR-0006), which means the plan `key` is a durable contract: changing it breaks bookmarks and stored user state. At the same time, the YAML author wants the visible plan button to read like English ("Plan A · 3D · 2N", subtitled "Sat 5/23 AM departure"), not like a stable identifier. The decision recorded here resolves that tension by splitting plan identity into three tiers: an opaque machine identifier (`key`), a presentation title (`label`), and an optional human-readable discriminator (`tagline`). Each tier has one job and one consumer.
- The original schema conflated all three roles into `key` (e.g. `key: "Baseline"` doubled as the URL fragment value, the localStorage suffix, AND the button text). That coupling meant any rename for presentation reasons silently invalidated every bookmark and every device's stored state. The new model breaks the coupling: `key` can stay `"A"` forever while `label` and `tagline` evolve freely as the plan's human description sharpens. The fallback rule for tagline absence is deliberate too — it preserves legibility for legacy YAML that has only `label`, so the new field is genuinely optional rather than a soft migration trap.
- This is the same shape of decision as ADR-0006 (URL-fragment-over-localStorage precedence): a small invariant that is silently reversed by a "make it nicer" refactor unless the constraint is visible from the ADR index. Without an ADR, a future contributor would reasonably propose "let's just use the label as the key and skip the indirection" and not realize they'd be breaking the bookmark/state-persistence contract.

## What changed

- `docs/trip-planner.md` §3.3 now defines three plan fields with non-overlapping responsibilities:
  - `key` — internal, opaque, ≤16 chars alphanumeric (+`-`/`_`), unique. Used in `state.plan`, URL fragment, localStorage. Never shown verbatim to users.
  - `label` — title-bar text rendered on the agenda cover and as the sticky-header main button text.
  - `tagline` — optional human-readable sub-label on the plan button.
- `docs/trip-planner.md` §3.3 changes the canonical example from `key: "Baseline"` (which previously doubled as both identifier and visible label) to `key: "A"` paired with `label: "Plan A · 3D · 2N"` and `tagline: "Sat 5/23 AM departure"`. This makes the three-tier model concrete in the bundled spec, not just in the field table.
- `docs/trip-planner.md` §3.3 codifies the deterministic tagline-fallback rule: when `tagline` is absent the sub-label falls back to whatever follows the first `·` in `label`. This is what makes `tagline` genuinely optional — pre-tagline YAMLs continue to render sensibly.

## Evidence

- `docs/trip-planner.md` §3.3 plan example:
  ```yaml
  plans:
    - key: "A"                              # Internal key — used in state.plan, URL fragment, localStorage
      label: "Plan A · 3D · 2N"             # Title-bar label (agenda cover, sticky-header main button text)
      tagline: "Sat 5/23 AM departure"      # Short human-readable hint shown as the plan-button sub-label
  ```
- `docs/trip-planner.md` §3.3 key constraint: "`key` must be unique across plans, ≤16 characters, alphanumeric (and `-` / `_`)." — i.e. identifier semantics, not presentation.
- `docs/trip-planner.md` §3.3 tagline rationale and fallback rule: "`tagline` is optional. When present it replaces the days·nights segment as the plan-button sub-label so users can scan plans by their human-readable descriptor (\"Sat 5/23 AM departure\") rather than memorize what each letter means. When absent the sub-label falls back to whatever follows the first `·` in `label`."
- `docs/trip-planner.md` §4 'State' table: `state.plan` persisted to `localStorage[<prefix>-plan]` and URL fragment — i.e. `key` is the value that round-trips through bookmarks and stored device state.
- ADR-0006 establishes that URL fragments and localStorage are both first-class state surfaces with fragment-over-localStorage precedence on load. That ADR is what makes plan `key` a stable contract rather than throwaway scaffolding.

## Next

- Promote to ADR. The three-tier plan-identity model is exactly the kind of contract that is silently broken by a "simplify the schema" refactor unless the rationale is discoverable from the ADR index. An ADR makes the bookmark-portability and stored-state-stability guarantees explicit for future contributors deciding whether to rename keys, fold `tagline` back into `label`, or relax the `key` constraints.
