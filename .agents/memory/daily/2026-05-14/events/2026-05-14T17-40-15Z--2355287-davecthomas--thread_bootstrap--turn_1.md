---
timestamp: "2026-05-14T17:40:15Z"
bootstrapped_at: "2026-05-14T20:53:00Z"
author: "2355287-davecthomas"
branch: "main"
thread_id: "bootstrap"
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
  - "README.md"
  - "src/trip_planner/renderer.py"
  - "src/trip_planner/templates/trip.html.j2"
  - "src/trip_planner/templates/styles.css"
  - "src/trip_planner/templates/runtime.js"
verification:
  - "docs/trip-planner.md §1 Design goals item 1 (one HTML file) and item 2 (YAML in)."
  - "docs/trip-planner.md §11 dependency policy: only Google Fonts CDN; no backends, no API keys."
  - "trip.html.j2 inlines CSS via <style> and JS via <script>; renderer.py reads templates verbatim."
---

## Why

- The render engine is intentionally constrained to "YAML in, one self-contained HTML file out" so that a non-engineer can edit a trip and a recipient can open it on any modern mobile browser without a build step, backend, or API key. This boundary is the foundation of every other engine choice (template structure, dependency policy, runtime architecture, even why the Mapbox widget was removed in v13 of the sample plan).

## What changed

- Initial commit `9ac2d7d` introduced the engine with the single-file output contract baked in: `src/trip_planner/renderer.py` reads `templates/trip.html.j2`, `templates/styles.css`, and `templates/runtime.js` and emits one HTML document with CSS inlined in `<style>`, runtime JS inlined in `<script>`, and trip data embedded as a `const TRIPS = ...` JSON literal.
- Dependency policy is enforced by the template itself: only Google Fonts is loaded from a CDN; no Mapbox, no API keys, no app-specific backend.

## Evidence

- `docs/trip-planner.md` §1 Design goals (items 1–3): "One file out", "YAML in", "Browser does interaction".
- `docs/trip-planner.md` §11 (in samples spec) and §4 of engine doc: render must function fully offline once loaded except for font files.
- `samples/sd_austin_spec.md` §13 (v13 revision): Mapbox removed precisely because it added a CDN payload, a token dependency, and an at-render auth point of failure — concrete demonstration of the dependency-policy invariant.
- Initial commit message: "Loads a YAML trip spec, validates it with Pydantic, and renders a single self-contained HTML file (inline CSS, inline runtime JS, embedded JSON trip data)."

## Next

- Promote to ADR as the foundational engine boundary decision; subsequent ADRs (data-shape contract, dual-implementation rule, exception hierarchy, vehicle-envelope rule) all depend on this boundary holding.
