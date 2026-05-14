# Trip Planner — Render Engine Specification

**Version:** 1.0
**Status:** Initial design

This document specifies a small render engine that takes a YAML trip specification and emits a single, self-contained HTML file that displays the trip as an interactive day-by-day itinerary, with plan switching, an agenda view, and one-tap link-outs to Google Maps.

The engine is intentionally focused on EV road trips — the schema knows about charging stops, hotel bookings with pet policies, and Google Place IDs — but the schema is general enough that any multi-day, multi-stop trip with the same shape (origin → stops → destination, optionally grouped into days, optionally grouped into plan variants) fits without modification.

---

## 1 — Design goals

1. **One file out.** The render is a single HTML file with CSS and JS inlined. Open it in any modern mobile browser without a build step, backend, or API key.
2. **YAML in.** The trip spec is a human-readable YAML file that a non-engineer can edit. The Python loader validates structure and surfaces errors clearly.
3. **Browser does interaction.** Python's job is to bake the trip data into the page and inline a fixed runtime. Plan/day switching, URL building, state persistence all run client-side after the file is opened.
4. **Sample fidelity.** The bundled SD → Austin sample (a real EV trip with three plan variants) must render to a page that is functionally equivalent to the hand-written `samples/sd_austin_v14.html`.
5. **Testable.** Every piece of logic with branching behavior — Pydantic validation, the YAML loader, the Google Maps URL builders — has unit tests. The renderer has a smoke test that asserts the embedded JSON, CSS, and JS appear in the output.

## 2 — Render pipeline

```
spec.yaml
    │
    ▼
┌───────────────┐
│ loader.py     │  reads YAML; parses into a dict
└───────┬───────┘
        ▼
┌───────────────┐
│ models.py     │  Pydantic v2 validation; raises ValidationError on bad input
└───────┬───────┘
        ▼
┌───────────────┐
│ renderer.py   │  reads CSS + JS from templates/; renders Jinja2 with trip data
└───────┬───────┘
        ▼
   one .html file
```

Failures at any stage raise a typed exception (`SpecLoadError`, `SpecValidationError`, `RenderError`) that the CLI surfaces with a non-zero exit code and a human-readable message.

## 3 — YAML schema

A trip spec is a YAML document with three top-level sections: `meta`, `vehicle`, and `plans`. The shapes below are the authoritative source — they map 1:1 to the Pydantic models in `src/trip_planner/models.py`.

### 3.1 — `meta`

```yaml
meta:
  title: "San Diego → Austin"           # Brand line in the sticky header
  version_label: "v14 · Tesla MYP · 69 mph"   # Right-side meta string
  agenda_label: "Full Trip Agenda · v14"      # Eyebrow on the agenda cover
  default_plan: "Baseline"              # Which plan loads on first visit
  storage_prefix: "sd-austin"           # Used as the localStorage key prefix
```

All `meta` fields are required strings.

### 3.2 — `vehicle` (drives the consumption envelope and §3.4 indicator)

```yaml
vehicle:
  # Identity
  name: "Tesla Model Y Performance"
  make: "Tesla"
  model: "Model Y Performance"
  year: 2024
  wheels: '21" Überturbine'
  notes: "Stock aero, no roof box. 69 mph cruise. ~605 lb payload."

  # Pack + budget
  usable_pack_kwh: 75            # usable capacity in kWh
  reserve_soc_pct: 20             # SoC reserve on arrival to every charge

  # Consumption (per §3.3 of the trip spec)
  baseline_wh_per_mi: 330         # at cruise + payload, no AC, no climb
  ac_penalty_wh_per_mi: 30        # added when AC is on
  ac_window_start: "10:00"        # local time AC window opens
  ac_window_end: "18:00"          # local time AC window closes
  climb_kwh_per_1000ft: 2.35      # kWh to lift loaded car 1,000 ft
  regen_recovery: 0.65            # fraction of climb energy recovered on descent

  # §3.4 AC conservation indicator thresholds
  ac_indicator_arrival_threshold_pct: 25   # fire below this projected SoC
  ac_indicator_min_improvement_pp: 3       # AC-off must improve by ≥ this much
```

The runtime reads every consumption parameter from this block — no
hard-coded EV constants live in the JS or CSS. To use a different EV,
replace this block (and the per-stop `elevation_ft` values) and the
engine produces the right behavior for the new vehicle.

The full vehicle name surfaces in the sticky header's meta string when
the YAML's `meta.version_label` references it; otherwise the vehicle
block is consumed only by the §3.4 indicator and is not directly
visible. `notes` is surfaced in verification copy when present.

### 3.3 — `plans`

A list of plan variants. Each variant is rendered as one tab in the plan toggle.

```yaml
plans:
  - key: "A"                              # Internal key — used in state.plan, URL fragment, localStorage
    label: "Plan A · 3D · 2N"             # Title-bar label (agenda cover, sticky-header main button text)
    tagline: "Sat 5/23 AM departure"      # Short human-readable hint shown as the plan-button sub-label
    summary: "Sat 5/23 – Mon 5/25 · ~1,340 mi · 14 charges"
    days: [ ... ]                         # See §3.4
    verification: { ... }                 # See §3.5
```

`key` must be unique across plans, ≤16 characters, alphanumeric (and `-` / `_`).

`tagline` is optional. When present it replaces the days·nights segment as
the plan-button sub-label so users can scan plans by their human-readable
descriptor ("Sat 5/23 AM departure") rather than memorize what each letter
means. When absent the sub-label falls back to whatever follows the first
`·` in `label`.

### 3.4 — `days`

Each plan carries an ordered list of days. Day order in YAML is render order.

```yaml
days:
  - title: "San Diego → Tucson"          # Visible title on the day-head and agenda
    date: "Sat 5/23"                     # Visible date string
    stats:
      miles: 433
      drive: "6h 35m"
      charges: 5
    stops: [ ... ]                       # See §3.5
```

`stats.miles` and `stats.charges` are integers; `stats.drive` is a free-text string.

### 3.5 — `stops`

Each day carries an ordered list of stops. Stop order is render order.

Every stop has a `type` and a small set of fields keyed by that type. The full schema is in `src/trip_planner/models.py` (`Stop` model); the table below is the authoritative human-readable summary.

| Field | Type | Applies to | Notes |
| --- | --- | --- | --- |
| `type` | enum | all | `origin` / `charge` / `meal` / `hotel` / `dest` |
| `name` | string | all | Display name |
| `address` | string | all | Precise street address; Directions target |
| `city_hint` | string | businesses | Disambiguation suffix for `Open in Maps` name queries (e.g. "Tucson AZ") |
| `place_id` | string | all (optional) | Google Place ID — definitive resolver in Maps URLs when present |
| `lat`, `lng` | number | all | Coordinates; retained for the URL-builder coord-proximity dedup |
| `elevation_ft` | number | all (optional) | Elevation above sea level; when present at both ends of a leg the §3.4 AC indicator uses the climb delta to compute the per-leg energy penalty |
| `leg_miles` | number | non-origin | Road-routed miles from prior stop |
| `leg_drive` | string | non-origin | Drive time from prior stop |
| `arrive` | string | non-origin | Local arrival time |
| `depart` | string | non-dest | Local departure time |
| `soc_in`, `soc_out` | string | `charge` | Inbound and outbound SoC, e.g. "52%" |
| `charger_type` | string | `charge` | e.g. "V3 · 250 kW" |
| `meal` | string | `charge` | `breakfast` / `lunch` / `dinner` / `coffee` / `no meal` |
| `restaurants` | array | `charge` | Objects with `name`, `cuisine` |
| `rating` | object | `hotel` | `{stars: int, user: float}` |
| `rate` | string | `hotel` | Illustrative nightly rate, e.g. "~$155" |
| `phone` | string | `hotel` | Property phone; renders a `Call` button |
| `booking_status` | enum | `hotel` | `BOOKED` / `PENDING` / `TO BOOK` |
| `conf_number` | string | `hotel` (optional) | Confirmation # when `BOOKED` |
| `plan_label` | string | `hotel` | Plan affiliation, used in the booking pill |
| `check_in`, `check_out` | string | `hotel` (optional) | Local check-in / check-out times |
| `cancel_by` | string | `hotel` | Free-cancel deadline or verification note |
| `pet_policy` | string | `hotel` | Exact policy text |
| `charger_prox` | string | `hotel` | Drive time to the nearest SC from the property |
| `notes` | string | all (optional) | Free-text rendered in the dashed footer of the card |

YAML uses `snake_case`. Python models match. The runtime JS expects `camelCase` (the JS in the template assumes the data shape that JS naturally uses), so the renderer converts at the boundary — `loader.py` keeps snake_case for Python, and the renderer's `to_runtime_dict()` rewrites keys to camelCase before JSON serialization.

### 3.6 — `verification`

Each plan carries a verification block with three lists. These are rendered into the green/blue/accent panel at the bottom of every day view, plus an amber audit group that the renderer computes itself from the stop data.

```yaml
verification:
  confirmed: [ "Origin: …", "Vehicle: …" ]
  estimates: [ "Drive times computed at 69 mph + 5% allowance", … ]
  tradeoffs: [ "El Paso stop selected to keep next leg ≤125 mi cap.", … ]
```

The fourth panel group ("Open in Maps · Quality Audit") is computed at runtime from each stop's `place_id` and is not declared in YAML.

## 4 — Runtime architecture

The emitted HTML is a single `<html>` document with:

1. A `<head>` containing the title, viewport meta, Google Fonts preconnect/stylesheet, and all CSS inline.
2. A `<body>` containing the sticky header (brand, plan toggle, day toggle, trip-toggles row) and a `<main>` with two `<section>`s — `#day-view` and `#agenda-view`.
3. One `<script>` tag at the bottom that:
   a. Defines `const TRIPS = …` from the embedded JSON.
   b. Inlines the runtime JS (URL builders, state management, render functions, event wiring).

State:

| Key | Values | Persistence |
| --- | --- | --- |
| `state.plan` | the `key` of one of the plans | `localStorage[<prefix>-plan]`, URL fragment |
| `state.day` | 1-based day index within the active plan | `localStorage[<prefix>-day]`, URL fragment |
| `state.mode` | `day` or `agenda` | `localStorage[<prefix>-mode]`, URL fragment |

URL fragment example: `#plan=Baseline&day=2&mode=day`. Fragment values take precedence over localStorage on initial load. Out-of-range values fall back to defaults silently — no broken bookmarks.

## 5 — Google Maps URL builders

The runtime exposes four URL-builder functions. All are pure functions of the stop data.

| Builder | Purpose | URL shape |
| --- | --- | --- |
| `dirUrl(stop)` | Routable Directions to a single stop | `/maps/dir/?api=1&destination=<addr>&destination_place_id=<id?>` |
| `placeUrl(stop)` | Open a single stop on its Place page | `/maps/search/?api=1&query=<name+cityHint>&query_place_id=<id?>` |
| `buildFullTripMapsUrl(planKey)` | Open the entire active plan's route | `/maps/dir/<seg1>/<seg2>/…/<segN>` |
| `buildDayMapsUrl(planKey, dayIdx)` | Open just the active day's route | Same path format as above |

For multi-stop URLs each segment is `"<Name>, <Address>"` for businesses and `"<Address>"` for personal endpoints. Consecutive stops collapse on address-match (case-insensitive, trimmed) or coordinate proximity (`|Δlat| < 0.001` AND `|Δlng| < 0.001`) — catches hotel-as-end-of-day-N / origin-of-day-N+1 pairs and on-site-charger / hotel pairs.

Python equivalents of all four live in `src/trip_planner/maps.py` so the algorithm is unit-tested on the Python side. The runtime JS uses the same algorithm — the same dedup, the same encoding (`%20`→`+`, `%2C` left as `,`).

## 6 — Place quality audit

A runtime function `placeQuality(stop)` returns one of:

- `verified` — business stop with a `place_id` (deterministic Google Place landing)
- `fallback` — business stop without a `place_id` (Google falls back to name+city search)
- `n/a` — personal endpoint (origin/dest); Place semantics don't apply

The day-view verification panel computes the counts per plan and surfaces:

- The number of business stops resolving to a Place page
- The enumerated list of every fallback stop by name (or "0 stops on name-query fallback")

The same function powers the inline ✓ / ⚠ badge next to every "Open in Maps" button on stop cards. A `console.warn` is also emitted on every render when fallbacks exist, naming the affected plan and stops — useful in DevTools as a live progress signal as missing Place IDs get captured over time.

## 6.5 — Consumption envelope and the §3.4 AC indicator

The runtime computes a per-leg consumption envelope from three inputs:

1. The `vehicle` block (baseline Wh/mi, AC penalty, AC window, climb cost,
   pack size, indicator thresholds).
2. Each stop's `elevation_ft` — net climb on a leg drives the elevation
   penalty.
3. Each stop's `socOut`, `legMiles`, and `depart` time — these compose the
   per-leg energy demand and whether the AC window applies.

For every `charge` stop in the day view, the runtime evaluates the
projected arrival SoC at the next stop under two scenarios:

- **AC on:** baseline + AC penalty (if `depart` falls in the AC window)
  + elevation penalty (if both stops carry `elevation_ft`).
- **AC off:** baseline + elevation penalty only.

The trigger fires when **both** conditions hold:

- AC-on projected arrival SoC is below
  `vehicle.ac_indicator_arrival_threshold_pct`.
- AC-off projection improves the AC-on figure by at least
  `vehicle.ac_indicator_min_improvement_pp` percentage points.

When the trigger fires, an amber row appears inside the departure-side
charge stop card with both projections surfaced numerically so the user
can evaluate the actual margin. The indicator stays silent when arrival
SoC is comfortable — no noise on well-buffered legs.

The same algorithm runs in `src/trip_planner/consumption.py` as
`evaluate_indicator(...)` so the build side can compute the indicator
without a browser (useful for tests, the CLI, and offline reports).
The JS implementation in `templates/runtime.js` mirrors it line-for-line;
the two MUST be edited together.

## 7 — Customization points

The renderer reads three template files from `src/trip_planner/templates/`:

| File | Purpose |
| --- | --- |
| `trip.html.j2` | The full HTML shell, including Jinja2 placeholders for inlined CSS/JS and the embedded trip JSON |
| `styles.css` | All CSS rules; copied verbatim into a `<style>` block |
| `runtime.js` | All runtime JS; copied verbatim into a `<script>` block, after the JSON-encoded trip data |

To tweak the look or behavior, edit the static files. The template structure is intentionally split so a CSS-only or JS-only change does not require touching the HTML scaffold.

A `Renderer` instance accepts an optional `templates_dir` override for tests and downstream callers that want a different look while keeping the schema.

## 8 — Error handling and logging

| Exception | When raised | CLI behavior |
| --- | --- | --- |
| `SpecLoadError` | YAML cannot be parsed (file missing, malformed YAML) | Exit 1, print path and parse error |
| `SpecValidationError` | YAML parses but does not match the schema | Exit 1, print Pydantic-style errors |
| `RenderError` | Template/runtime missing, write failure, etc. | Exit 2, print exception |

All three inherit from `TripPlannerError`. The CLI wraps the entire flow in a single `except TripPlannerError` so internal exceptions surface as clean messages, never raw tracebacks (unless `--verbose` is passed, in which case the full traceback is logged at DEBUG).

Logging uses the stdlib `logging` module with a `TripPlanner.<module>` namespace. Default level is `INFO`; `--verbose` flips it to `DEBUG`. Boundary modules (`loader`, `renderer`, `cli`) log at INFO on success and ERROR on failure. Inner modules (`models`, `maps`) log only on DEBUG.

## 9 — Testing

Unit tests live in `tests/` and cover:

- `test_models.py` — schema validation, including error cases (bad type enum, missing required fields)
- `test_loader.py` — round-trip YAML → model → dict, fixture-driven
- `test_maps.py` — every URL builder, with the SD-Austin sample as the canonical fixture; covers the dedup rule explicitly
- `test_renderer.py` — smoke test on the sample (renders without errors, output contains embedded JSON for all three plans, all four CSS sentinel selectors, and the expected runtime function names)

Coverage target: ≥85% on the package code.

Run with `poetry run pytest` or `poetry run pytest --cov` for coverage.

## 10 — Extending the engine

Common extensions:

- **A new stop type.** Add the enum value to `StopType` in `models.py`, add a `card-num.<type>` color rule to `styles.css`, add a render branch to `renderStopCard()` in `runtime.js`. The `dirUrl` / `placeUrl` semantics treat anything not in `{origin, dest}` as a business, so a new type gets sensible defaults for free.
- **A second template skin.** Pass `templates_dir=Path("path/to/alt")` to `Renderer`. The CLI accepts `--templates-dir` for the same reason.
- **A different storage prefix.** Change `meta.storage_prefix` in YAML. Multiple distinct trips can be open in different tabs without state collision.
