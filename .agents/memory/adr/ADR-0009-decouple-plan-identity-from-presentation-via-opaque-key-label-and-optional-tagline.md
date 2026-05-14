# ADR-0009 Decouple plan identity from presentation via opaque key, label, and optional tagline

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

Purpose: Decouple plan identity from presentation via opaque key, label, and optional tagline
Derived from: [2026-05-14T22-34-58Z--2355287-davecthomas--adr-inspector](../daily/2026-05-14/events/2026-05-14T22-34-58Z--2355287-davecthomas--adr-inspector.md)

## Context

- The render engine persists plan selection to both `localStorage` and the URL fragment (per ADR-0006), which means the plan `key` is a durable contract: changing it breaks bookmarks and stored user state. At the same time, the YAML author wants the visible plan button to read like English ("Plan A · 3D · 2N", subtitled "Sat 5/23 AM departure"), not like a stable identifier. The decision recorded here resolves that tension by splitting plan identity into three tiers: an opaque machine identifier (`key`), a presentation title (`label`), and an optional human-readable discriminator (`tagline`). Each tier has one job and one consumer.
- The original schema conflated all three roles into `key` (e.g. `key: "Baseline"` doubled as the URL fragment value, the localStorage suffix, AND the button text). That coupling meant any rename for presentation reasons silently invalidated every bookmark and every device's stored state. The new model breaks the coupling: `key` can stay `"A"` forever while `label` and `tagline` evolve freely as the plan's human description sharpens. The fallback rule for tagline absence is deliberate too — it preserves legibility for legacy YAML that has only `label`, so the new field is genuinely optional rather than a soft migration trap.
- This is the same shape of decision as ADR-0006 (URL-fragment-over-localStorage precedence): a small invariant that is silently reversed by a "make it nicer" refactor unless the constraint is visible from the ADR index. Without an ADR, a future contributor would reasonably propose "let's just use the label as the key and skip the indirection" and not realize they'd be breaking the bookmark/state-persistence contract.

## Decision

- `docs/trip-planner.md` §3.3 now defines three plan fields with non-overlapping responsibilities:
  - `key` — internal, opaque, ≤16 chars alphanumeric (+`-`/`_`), unique. Used in `state.plan`, URL fragment, localStorage. Never shown verbatim to users.
  - `label` — title-bar text rendered on the agenda cover and as the sticky-header main button text.
  - `tagline` — optional human-readable sub-label on the plan button.
- `docs/trip-planner.md` §3.3 changes the canonical example from `key: "Baseline"` (which previously doubled as both identifier and visible label) to `key: "A"` paired with `label: "Plan A · 3D · 2N"` and `tagline: "Sat 5/23 AM departure"`. This makes the three-tier model concrete in the bundled spec, not just in the field table.
- `docs/trip-planner.md` §3.3 codifies the deterministic tagline-fallback rule: when `tagline` is absent the sub-label falls back to whatever follows the first `·` in `label`. This is what makes `tagline` genuinely optional — pre-tagline YAMLs continue to render sensibly.

## Consequences

- Promote to ADR. The three-tier plan-identity model is exactly the kind of contract that is silently broken by a "simplify the schema" refactor unless the rationale is discoverable from the ADR index. An ADR makes the bookmark-portability and stored-state-stability guarantees explicit for future contributors deciding whether to rename keys, fold `tagline` back into `label`, or relax the `key` constraints.

## Source memory events

- [2026-05-14T22-34-58Z--2355287-davecthomas--adr-inspector](../daily/2026-05-14/events/2026-05-14T22-34-58Z--2355287-davecthomas--adr-inspector.md)

## Related code paths

- docs/trip-planner.md
