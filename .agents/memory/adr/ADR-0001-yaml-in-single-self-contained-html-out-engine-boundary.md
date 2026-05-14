# ADR-0001 YAML-in, single self-contained HTML-out engine boundary

Status: accepted
Date: 2026-05-14
Owners: 2355287-davecthomas
Must read: true
Supersedes: 
Superseded by: 

Purpose: YAML-in, single self-contained HTML-out engine boundary
Derived from: [2026-05-14T17-40-15Z--2355287-davecthomas--thread_bootstrap--turn_1](../daily/2026-05-14/events/2026-05-14T17-40-15Z--2355287-davecthomas--thread_bootstrap--turn_1.md)

## Context

- The render engine is intentionally constrained to "YAML in, one self-contained HTML file out" so that a non-engineer can edit a trip and a recipient can open it on any modern mobile browser without a build step, backend, or API key. This boundary is the foundation of every other engine choice (template structure, dependency policy, runtime architecture, even why the Mapbox widget was removed in v13 of the sample plan).

## Decision

- Initial commit `9ac2d7d` introduced the engine with the single-file output contract baked in: `src/trip_planner/renderer.py` reads `templates/trip.html.j2`, `templates/styles.css`, and `templates/runtime.js` and emits one HTML document with CSS inlined in `<style>`, runtime JS inlined in `<script>`, and trip data embedded as a `const TRIPS = ...` JSON literal.
- Dependency policy is enforced by the template itself: only Google Fonts is loaded from a CDN; no Mapbox, no API keys, no app-specific backend.

## Consequences

- Promote to ADR as the foundational engine boundary decision; subsequent ADRs (data-shape contract, dual-implementation rule, exception hierarchy, vehicle-envelope rule) all depend on this boundary holding.

## Source memory events

- [2026-05-14T17-40-15Z--2355287-davecthomas--thread_bootstrap--turn_1](../daily/2026-05-14/events/2026-05-14T17-40-15Z--2355287-davecthomas--thread_bootstrap--turn_1.md)

## Related code paths

- docs/trip-planner.md
- README.md
- src/trip_planner/renderer.py
- src/trip_planner/templates/trip.html.j2
- src/trip_planner/templates/styles.css
- src/trip_planner/templates/runtime.js
