# trip-planner

> Render a single-page, fully self-contained HTML itinerary from a YAML trip specification.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)
[![Built with Poetry](https://img.shields.io/badge/built%20with-poetry-60A5FA.svg)](https://python-poetry.org/)

**trip-planner** takes a human-readable YAML description of a multi-day, multi-stop trip and bakes it into one HTML file that you can drop in iCloud, email to yourself, or open straight from disk on any modern mobile browser. No build step, no backend, no API key, no JavaScript framework — the page is interactive (plan switching, agenda view, Google Maps deep-links) because everything it needs is inlined at render time.

The schema is opinionated toward **EV road trips**: it understands plan variants, charge stops with state-of-charge in/out, hotels with booking metadata and pet policies, and a per-leg consumption envelope that drives an AC-conservation indicator. The same engine renders any trip shaped as `origin → stops → destination`, optionally grouped into days and plan variants.

The bundled sample (`trips/sd_austin.yaml`) is a real San Diego → Austin EV plan with three plan variants, hotel bookings, and a full Supercharger sequence — open `trips/sd_austin.yaml` to see the full shape of a non-trivial spec.

---

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [From trip notes to YAML — the LLM-assisted workflow](#from-trip-notes-to-yaml--the-llm-assisted-workflow)
  - [Writing good trip notes](#writing-good-trip-notes)
- [CLI reference](#cli-reference)
- [YAML schema](#yaml-schema)
  - [`meta`](#meta)
  - [`vehicle`](#vehicle)
  - [`plans`](#plans)
  - [`days`](#days)
  - [`stops`](#stops)
  - [`verification`](#verification)
  - [YAML anchors — reusable places](#yaml-anchors--reusable-places)
- [The rendered page — runtime tour](#the-rendered-page--runtime-tour)
- [Tips and recipes](#tips-and-recipes)
- [Customization](#customization)
- [Using trip-planner as a library](#using-trip-planner-as-a-library)
- [Troubleshooting](#troubleshooting)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Versioning and stability](#versioning-and-stability)
- [License](#license)

---

## Features

- **One file out.** A complete HTML document with CSS and JS inlined — no asset folder to ship alongside it.
- **Plan variants.** Bundle multiple itineraries (`Plan A`, `Plan B`, `Conservative`) into one render; the user toggles between them in the sticky header.
- **Day-by-day, full-trip, or cross-plan merged view.** Each plan has a per-day view and a full-trip agenda. A fourth `All Plans · Merged` toggle unions every supercharger and hotel across plans into one west-to-east sequence — dedup'd by `place_id` or address, ordered by projection onto the origin→destination vector — so a driver can see every possible stop in one continuous list.
- **Deep-link state.** Plan / day / mode are mirrored into the URL fragment and `localStorage`. Send someone `#plan=A&day=2&mode=day` and they land exactly where you did.
- **Google Maps integration.** One-tap **Directions** and **Open in Maps** buttons for every stop; one-tap full-trip and per-day multi-stop routes. URL builders dedupe consecutive same-location stops (hotel-end-of-day-N / hotel-origin-of-day-N+1) automatically.
- **Place-quality audit.** Every business stop is classified `verified` (has a Google Place ID), `fallback` (name+city search), or `n/a` (personal endpoint). The day view surfaces counts and named fallbacks, and a `console.warn` fires per render so DevTools doubles as a progress bar while you capture missing Place IDs.
- **EV-aware consumption envelope.** The `vehicle` block defines a per-leg energy model — baseline Wh/mi, AC penalty, AC window, climb cost — and the runtime fires a `§3.4 AC conservation indicator` when an upcoming leg's projected arrival SoC dips below your threshold and turning AC off would meaningfully widen the margin. Same algorithm is exposed in Python (`trip_planner.consumption.evaluate_indicator`) for tests and offline reports.
- **Strict, friendly validation.** Pydantic v2 models with `extra="forbid"` catch every typo before render; the CLI surfaces clean, non-traceback error messages by default and full tracebacks under `--verbose`.
- **Hand-edit-friendly.** Templates and runtime JS live as static files in `src/trip_planner/templates/`; tweak CSS or JS without touching Python.
- **Tested.** Pydantic models, YAML loader, every Maps URL builder, and the AC indicator algorithm all have unit tests. The renderer has a smoke test against the bundled sample.

---

## Requirements

- **Python 3.11+**
- [Poetry](https://python-poetry.org/) (recommended) — handles the virtualenv, lockfile, and CLI entry point in one command.
- A modern browser to open the output. Tested on iOS Safari, Android Chrome, desktop Chrome, Firefox, Safari.

Runtime dependencies (installed by Poetry):

| Package | Purpose |
| --- | --- |
| `pydantic ^2.7` | Schema validation for the YAML spec |
| `pyyaml ^6.0` | YAML parsing |
| `jinja2 ^3.1` | HTML template rendering |
| `click ^8.1` | CLI framework |

Dev dependencies: `pytest ^8.2`, `pytest-cov ^5.0`.

---

## Installation

Clone the repo and install via Poetry:

```bash
git clone https://github.com/davecthomas/trip-planner.git
cd trip-planner
poetry install
```

That creates a virtualenv, installs all dependencies, and registers a `trip-planner` console script you can invoke through `poetry run`.

Don't want to use Poetry? You can install into any virtualenv you manage yourself:

```bash
python -m venv .venv
source .venv/bin/activate
pip install pydantic pyyaml jinja2 click
pip install -e .
```

---

## Quick start

### Render the bundled sample

```bash
poetry run trip-planner render trips/sd_austin.yaml --output renders/sd_austin.html
open renders/sd_austin.html        # macOS
# xdg-open renders/sd_austin.html  # Linux
# start renders/sd_austin.html     # Windows
```

You'll get a single self-contained HTML file under `renders/sd_austin.html`. Open it in any browser; everything you need to make it interactive is already inside the file.

### Render your own trip

You don't have to hand-write YAML. Write your trip notes in markdown (or any prose) — then either:

- **In Claude Code:** run `/yamlify path/to/your_notes.md`. The slash command produces validated YAML at `trips/private/<slug>.yaml`. See [From trip notes to YAML](#from-trip-notes-to-yaml--the-llm-assisted-workflow).
- **In any other LLM** (Claude.ai, ChatGPT, Cursor, etc.): paste the contents of [`prompts/markdown_to_yaml.md`](prompts/markdown_to_yaml.md) along with your notes. Save the output under `trips/private/`.

Then render exactly like the sample:

```bash
poetry run trip-planner validate trips/private/your-trip.yaml
poetry run trip-planner render trips/private/your-trip.yaml -o renders/your-trip.html
open renders/your-trip.html
```

Tips on writing notes that produce high-quality YAML are in [Writing good trip notes](#writing-good-trip-notes).

### Other handy commands

Validate a spec without rendering (fast — useful as a pre-commit / CI check):

```bash
poetry run trip-planner validate trips/sd_austin.yaml
# ok: trips/sd_austin.yaml — 3 plan(s), 10 day(s), 61 stop(s)
```

Print the Google Maps URL for an entire plan (handy for pasting into the Maps app):

```bash
poetry run trip-planner full-trip-url trips/sd_austin.yaml --plan A
```

Run the test suite:

```bash
poetry run pytest
poetry run pytest --cov                 # with coverage
poetry run pytest -k consumption -v     # focused subset
```

---

## From trip notes to YAML — the LLM-assisted workflow

You don't have to hand-write YAML. trip-planner ships with a portable conversion prompt and a Claude Code slash command that turn freeform trip notes into a validated YAML spec for you.

### What's in the box

| File | Role |
| --- | --- |
| [`prompts/markdown_to_yaml.md`](prompts/markdown_to_yaml.md) | **Universal LLM prompt.** Self-contained instructions covering the schema, hard validation rules, the YAML-anchor idiom for reusable places, a worked example, and PII guardrails. Paste it into Claude, ChatGPT, Cursor — anywhere — alongside your notes. |
| [`schema/trip.schema.json`](schema/trip.schema.json) | **JSON Schema** generated from the Pydantic models. Editors (VS Code with the YAML extension, JetBrains, Neovim with `yaml-language-server`) use this for autocomplete and live validation. LLMs use it as the machine-readable contract. |
| [`.claude/commands/yamlify.md`](.claude/commands/yamlify.md) | **`/yamlify` slash command** for Claude Code. Locates your notes, runs the conversion, validates the output, saves to `trips/private/`, and prints the render command. |
| [`CLAUDE.md`](CLAUDE.md) | Repo-level agent guide. Any LLM running in this directory picks up the PII rules and file-routing conventions. |

### Workflow A — inside Claude Code (one command)

```text
/yamlify samples/my_trip_notes.md
```

The slash command:

1. Reads your markdown notes (or asks you to provide them).
2. Loads `prompts/markdown_to_yaml.md` and `schema/trip.schema.json`.
3. Produces YAML following the schema.
4. Validates via `trip-planner validate`. Self-corrects on errors (up to 5 retries).
5. Saves to `trips/private/<slug>.yaml` (gitignored — your real addresses never leave your machine).
6. Prints the next-step render command.

You can also invoke it with no arguments — the command will look for a recently-modified markdown file under `samples/`.

### Workflow B — any other LLM (portable prompt)

For Claude.ai, ChatGPT, Cursor, or any other LLM:

1. Copy the entire contents of [`prompts/markdown_to_yaml.md`](prompts/markdown_to_yaml.md) into your chat.
2. Paste your trip notes after it.
3. Take the YAML output and save it under `trips/private/` (e.g. `trips/private/my-trip.yaml`).
4. Validate locally:

   ```bash
   poetry run trip-planner validate trips/private/my-trip.yaml
   ```

5. Render when clean:

   ```bash
   poetry run trip-planner render trips/private/my-trip.yaml -o renders/my-trip.html
   open renders/my-trip.html
   ```

### Editor support — autocomplete and lint your YAML

Add a one-line header to any trip YAML to wire up [yaml-language-server](https://github.com/redhat-developer/yaml-language-server) (used by VS Code's YAML extension, plus most LSP-aware editors):

```yaml
# yaml-language-server: $schema=../../schema/trip.schema.json
```

Adjust the relative path to point at `schema/trip.schema.json` from wherever your YAML lives. With that line, your editor warns on unknown fields, autocompletes valid keys, and shows inline type errors as you type.

### Keeping the schema in sync

The committed `schema/trip.schema.json` is generated from `src/trip_planner/models.py`. If you change a model, regenerate the schema:

```bash
poetry run trip-planner schema -o schema/trip.schema.json
```

The test suite includes a drift check (`tests/test_schema.py::test_committed_schema_matches_generated`) so CI catches a forgotten regen. You can also wire `trip-planner schema --check -o schema/trip.schema.json` into a pre-commit hook — it exits non-zero (code 3) if the on-disk schema is stale.

### Where trip files live

| Directory | Tracked in git? | What goes here |
| --- | --- | --- |
| `trips/sd_austin.yaml` | **Yes** | The public sanitized sample (City Hall endpoints, fake conf numbers). |
| `trips/private/` | **No** (gitignored, but `.gitkeep` is committed so the directory exists on fresh clones) | Your personal trip specs — real addresses, real hotel bookings. **Default output of `/yamlify`.** |
| `trips/<anything else>.yaml` | **No** (gitignored via `trips/*`) | Other personal specs you want kept out of git. |
| `samples/` | **No** (gitignored) | Your personal planning docs — markdown specs, drafts, scratch notes. |

This layout means you can't accidentally commit a real home address: by default, every personal artifact lands in a gitignored location.

### Writing good trip notes

The `/yamlify` workflow is only as good as the notes you feed it. You don't need a specific format — bullet lists, tables, and prose all work — but the more of the following you include, the less the LLM has to guess (and the fewer `# TODO:` comments end up in the output).

**Always include:**

- **Origin and destination.** Full street addresses if you want them in the YAML. The LLM won't fabricate them — it'll leave a `TODO` placeholder.
- **Dates.** Trip start date at minimum; per-day dates if multi-day. Use unambiguous formats (`Sat 5/23`, not "this Saturday").
- **Vehicle.** Make / model / year. Mention if you want the AC consumption indicator wired up (then include `kWh`, `Wh/mi`, AC window, climb cost — see the `vehicle` section of the schema for the full list).

**For each stop, ideally:**

- Stop type (charge / meal / hotel / endpoint).
- Name + full address.
- Arrival and departure times (`HH:MM`, 24-hour preferred).
- Miles and drive time from the prior stop.
- For **charge stops**: SoC in / out (e.g. `52% → 85%`), charger type (`V3 250 kW`), meal taken (or "no meal"), nearby restaurants if you have favorites.
- For **hotels**: nightly rate, booking status (`BOOKED` / `PENDING` / `TO BOOK`), confirmation number if booked, check-in/out times, cancellation policy, pet policy, drive time to nearest charger.
- Google **Place IDs** if you've captured them (one-tap "Open in Maps" lands on the right Place page instead of falling back to a name search).

**Plan variants:**

If you're maintaining multiple options (e.g. Baseline / Plan A / Plan B), name them clearly and group their stops separately. Note which is the **default** plan (loads first) and which are contingencies.

**What you can skip:**

- Lat/lng coordinates — the LLM can derive these from addresses (and will mark them `# TODO: confirm` if uncertain).
- Editorial copy for the verification panel — the LLM will infer reasonable "confirmed / estimates / tradeoffs" entries from your notes, and you can edit afterward.
- Formatting consistency. Markdown tables, plain bullets, and free-form prose all parse.

**One thing to watch:**

Don't put real home addresses, hotel confirmation numbers, or personal phone numbers in notes that live in a tracked location. Default home for personal notes is `samples/` (gitignored) and default output of `/yamlify` is `trips/private/` (also gitignored).

For a worked example, see [`prompts/markdown_to_yaml.md`](prompts/markdown_to_yaml.md) §9 (a short Vegas-weekend notes blob and its corresponding YAML).

### Editor support — turn your YAML editor into an autocomplete machine

Add this one-line header to any trip YAML to wire it up to [yaml-language-server](https://github.com/redhat-developer/yaml-language-server):

```yaml
# yaml-language-server: $schema=../../schema/trip.schema.json
```

Adjust the relative path to point at `schema/trip.schema.json` from wherever your YAML lives. With that line:

- **VS Code** (with the [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.yaml)) — autocomplete on every field, inline error squiggles on typos, hover docs on each property.
- **JetBrains IDEs** (PyCharm, IntelliJ) — same; built-in YAML support reads the header.
- **Neovim / Helix** — any editor with `yaml-language-server` configured.

This is the single highest-leverage tweak you can make. Schema-aware editing catches `confimed` vs `confirmed` and `placeId` vs `place_id` before you even save.

---

## CLI reference

```text
trip-planner [GLOBAL OPTIONS] COMMAND [ARGS]...
```

### Global options

| Flag | Description |
| --- | --- |
| `-v`, `--verbose` | Enable DEBUG-level logging and full tracebacks on unexpected errors. Default is INFO + one-line error messages. |
| `--version` | Print the package version and exit. |
| `-h`, `--help` | Show usage for the command (works on the group and each subcommand). |

Logs go to **stderr**; command output goes to **stdout**, so you can pipe `full-trip-url` cleanly into clipboards or scripts without log noise contaminating the output.

### `render` — generate HTML

```bash
trip-planner render <SPEC.yaml> [--output FILE] [--templates-dir DIR]
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `SPEC` (positional) | _required_ | Path to a YAML trip spec. |
| `-o`, `--output FILE` | `renders/trip.html` | Where to write the rendered HTML. Parent directories are created automatically. |
| `--templates-dir DIR` | bundled `src/trip_planner/templates/` | Override the template set (must contain `trip.html.j2`, `styles.css`, `runtime.js`). See [Customization](#customization). |

On success: prints `wrote /abs/path/to/output.html` and exits **0**.

### `validate` — schema check only

```bash
trip-planner validate <SPEC.yaml>
```

Loads and validates the spec without rendering. Prints a one-line summary: number of plans, days, and stops. Useful in CI or as a fast iteration loop while editing YAML.

### `schema` — emit the JSON Schema

```bash
trip-planner schema [-o FILE] [--check]
```

Generates a JSON Schema describing the YAML input shape (snake_case field names) from the Pydantic models. Useful for IDE validation and for LLM-assisted YAML generation.

| Option | Default | Description |
| --- | --- | --- |
| `-o`, `--output FILE` | stdout | Write the schema to a file (parent dirs created). |
| `--check` | off | Compare against an existing file (requires `--output`). Exits **3** if the file is missing or stale. Useful in pre-commit hooks and CI. |

Regenerate after model changes:

```bash
poetry run trip-planner schema -o schema/trip.schema.json
```

Drift-check in CI:

```bash
poetry run trip-planner schema --check -o schema/trip.schema.json
```

### `full-trip-url` — print a Maps URL

```bash
trip-planner full-trip-url <SPEC.yaml> --plan <PLAN-KEY>
```

| Argument / option | Description |
| --- | --- |
| `SPEC` (positional) | Path to a YAML trip spec. |
| `--plan PLAN-KEY` | The `key` of the plan to encode (e.g. `A`, `Baseline`). Required. |

Outputs a single Google Maps URL covering every stop in the plan (with consecutive-duplicate dedup), one line, no trailing newline noise. Pipe straight to your clipboard:

```bash
poetry run trip-planner full-trip-url trips/sd_austin.yaml --plan A | pbcopy
```

### Exit codes

| Code | When |
| --- | --- |
| `0` | Success |
| `1` | A typed error from the trip-planner pipeline — bad path, malformed YAML, schema violation, unknown plan key. Message printed to stderr; no traceback unless `--verbose`. |
| `2` | An unexpected exception (anything not a `TripPlannerError`). Stderr gets `unexpected: <ExceptionClass>: <message>`. Pass `-v` to see the traceback. |
| `3` | `schema --check` detected drift — the committed schema file is missing or out of sync with the Pydantic models. Regenerate with `trip-planner schema -o <path>`. |

---

## YAML schema

A trip spec is a YAML document with three top-level sections — `meta`, `vehicle` (optional), and `plans` — plus any number of convention `_*` keys that exist only to hold YAML anchors. The shapes below are authoritative; they map 1:1 to the Pydantic models in `src/trip_planner/models.py`.

Validation is **strict**: unknown keys raise an error (`extra="forbid"`), so a typo in `confimed:` doesn't silently swallow your verification copy.

### `meta`

```yaml
meta:
  title: "San Diego → Austin"               # Brand line in the sticky header
  version_label: "v15 · Tesla MYP · 69 mph" # Right-aligned meta string
  agenda_label: "Full Trip Agenda · v15"    # Eyebrow on the agenda cover
  default_plan: "A"                         # Which plan loads on first visit
  storage_prefix: "sd-austin"               # localStorage key prefix
```

| Field | Constraints |
| --- | --- |
| `title` | Required string. |
| `version_label` | Required string. Appears top-right in the sticky header. |
| `agenda_label` | Required string. |
| `default_plan` | Required string. **Must match the `key` of one of the plans** (the validator enforces this). |
| `storage_prefix` | Required. Lowercase ASCII; `^[a-z][a-z0-9-]{0,31}$`. Used to namespace `localStorage`, so two trips opened in different tabs don't collide. |

### `vehicle`

Optional, but **required if you want the AC conservation indicator to fire**. The runtime reads every consumption constant from this block — no EV-specific math is hard-coded in the JS.

```yaml
vehicle:
  # Identity
  name: "Tesla Model Y Performance"
  make: "Tesla"
  model: "Model Y Performance"
  year: 2024
  wheels: '21" Überturbine'
  notes: >-
    Stock aero, no roof box. ~605 lb payload. 69 mph cruise.

  # Pack + budget
  usable_pack_kwh: 75              # Usable capacity in kWh (Tesla MYP ≈ 75)
  reserve_soc_pct: 20              # % SoC to keep on arrival to every charge

  # Consumption envelope
  baseline_wh_per_mi: 330          # At cruise + payload, no AC, no climb
  ac_penalty_wh_per_mi: 30         # Added when AC is on
  ac_window_start: "10:00"         # Local time AC window opens
  ac_window_end: "18:00"           # Local time AC window closes
  climb_kwh_per_1000ft: 2.35       # kWh to lift loaded car 1,000 ft
  regen_recovery: 0.65             # Fraction of climb energy recovered on descent

  # §3.4 AC indicator thresholds
  ac_indicator_arrival_threshold_pct: 25   # Fire below this projected SoC
  ac_indicator_min_improvement_pp: 3       # AC-off must improve by ≥ this many pp
```

| Field | Range | Default | Purpose |
| --- | --- | --- | --- |
| `name` | _required_ | — | Display name in headers and verification copy. |
| `make` / `model` / `year` / `wheels` / `notes` | optional | — | Free-form identity fields surfaced in verification copy. `year` must be 1990–2100. |
| `usable_pack_kwh` | `0 < x ≤ 300` | _required_ | Usable pack capacity in kWh. |
| `reserve_soc_pct` | `0–80` | `20` | Reserve SoC target on arrival. |
| `baseline_wh_per_mi` | `0 < x ≤ 1000` | _required_ | Cruise consumption excluding AC and climb. |
| `ac_penalty_wh_per_mi` | `0–200` | _required_ | Added Wh/mi when AC is on. |
| `ac_window_start` / `ac_window_end` | `HH:MM` | `"10:00"` / `"18:00"` | AC window. Does not wrap past midnight. |
| `climb_kwh_per_1000ft` | `0 < x ≤ 10` | _required_ | Energy to lift the loaded car 1,000 ft. |
| `regen_recovery` | `0.0–1.0` | `0.65` | Fraction of climb energy recovered on descent. |
| `ac_indicator_arrival_threshold_pct` | `0–100` | `25` | Trigger threshold for the §3.4 indicator. |
| `ac_indicator_min_improvement_pp` | `0–100` | `3` | Minimum AC-off improvement (pp) before the indicator fires. |

> **To use a different EV:** swap the entire `vehicle` block and the per-stop `elevation_ft` values. Nothing else needs to change.

### `plans`

A list of plan variants. Each becomes a tab in the plan toggle.

```yaml
plans:
  - key: "A"                                  # Unique key — used in URL fragment & localStorage
    label: "Plan A · 3D · 2N"                 # Tab label, agenda cover title
    tagline: "Sat 5/23 AM departure"          # Sub-label on the plan button
    summary: "Sat 5/23 – Mon 5/25 · ~1,340 mi · 14 charges"
    days: [ ... ]                             # See below
    verification: { ... }                     # Optional, see below
```

| Field | Constraints |
| --- | --- |
| `key` | Required. `^[A-Za-z0-9_-]{1,16}$`. Must be unique across plans. |
| `label` | Required. Appears in the plan toggle and on the agenda cover. |
| `summary` | Required. Free-form one-liner. |
| `tagline` | Optional. When present, replaces the days·nights sub-label so users can scan plans by their human-readable hint instead of memorizing letter codes. |
| `days` | Required, min length 1. Order is render order. |
| `verification` | Optional. Defaults to all-empty groups. |

### `days`

```yaml
days:
  - title: "San Diego → Tucson"
    date: "Sat 5/23"
    stats: { miles: 433, drive: "6h 35m", charges: 5 }
    stops: [ ... ]
```

| Field | Type | Notes |
| --- | --- | --- |
| `title` | string | Visible day-head title and agenda entry. |
| `date` | string | Free-form date string. Surfaced as the day sub-label and used by the day-toggle pre-computed map. |
| `stats.miles` | int ≥ 0 | Total miles for the day. |
| `stats.drive` | string | Free-form drive time ("6h 35m"). |
| `stats.charges` | int ≥ 0 | Number of charge stops. |
| `stops` | list | Required, min length 1. Order is render order. |

### `stops`

Each day carries an ordered list of stops. Every stop has a `type` and a set of fields keyed by that type.

| Field | Type | Applies to | Notes |
| --- | --- | --- | --- |
| `type` | enum | all | `origin` / `charge` / `meal` / `hotel` / `dest` |
| `name` | string | all | Display name. |
| `address` | string | all | Precise street address. Used as the Directions target. |
| `lat`, `lng` | number | all | Coordinates. Used by the coordinate-proximity dedup in multi-stop URLs. |
| `city_hint` | string | businesses | Disambiguation suffix for `Open in Maps` name queries (e.g. `"Tucson AZ"`). |
| `place_id` | string | optional | Google Place ID — the definitive resolver in Maps URLs when present. Without it, business stops fall back to a name+city search. |
| `elevation_ft` | number (-1000 to 15000) | optional | Elevation above sea level. When present at both ends of a leg, the AC indicator uses the climb delta to compute the per-leg energy penalty. |
| `notes` | string | optional | Free-text rendered in the dashed footer of the stop card. |
| `leg_miles` | number ≥ 0 | non-origin | Road-routed miles from the prior stop. |
| `leg_drive` | string | non-origin | Drive time from the prior stop. |
| `arrive` | string (`HH:MM`) | non-origin | Local arrival time. |
| `depart` | string (`HH:MM`) | non-dest | Local departure time. |
| `soc_in`, `soc_out` | `"NN%"` | `charge` | Inbound / outbound state of charge. |
| `charger_type` | string | `charge` | e.g. `"V3 · 250 kW"`. |
| `meal` | string | `charge` | `breakfast` / `lunch` / `dinner` / `coffee` / `no meal`. |
| `restaurants` | list of `{name, cuisine}` | `charge` | Optional recommendations. |
| `rating` | `{stars: 1–5, user: 0.0–5.0}` | `hotel` | |
| `rate` | string | `hotel` | Illustrative nightly rate (`"~$155"`). |
| `phone` | string | `hotel` | Property phone — renders a `Call` button. |
| `booking_status` | enum | `hotel` | `BOOKED` / `PENDING` / `TO BOOK`. Defaults to `PENDING` with a warning log if omitted. |
| `conf_number` | string | `hotel` (optional) | Confirmation # when `BOOKED`. |
| `plan_label` | string | `hotel` | Plan affiliation, used in the booking pill. |
| `check_in`, `check_out` | string | `hotel` (optional) | Local check-in / check-out times. |
| `cancel_by` | string | `hotel` | Free-cancel deadline or verification note. |
| `pet_policy` | string | `hotel` | Exact policy text. |
| `charger_prox` | string | `hotel` | Drive time to the nearest Supercharger from the property. |

> **Naming:** YAML uses `snake_case`. Python models accept either snake_case or camelCase on input. When the renderer serializes the trip into the embedded JSON for the browser, every key is rewritten to camelCase via the model's alias generator.

### `verification`

Each plan can carry a `verification` block with three editorial groups rendered into the colored panel at the bottom of every day view:

```yaml
verification:
  confirmed: ["Origin: San Diego City Hall", "Vehicle: Tesla MYP"]
  estimates: ["Drive times computed at 69 mph + 5% allowance"]
  tradeoffs: ["El Paso stop selected to keep next leg ≤ 125 mi."]
```

A fourth group, **Open in Maps · Quality Audit**, is computed at runtime from each stop's `place_id` and surfaces:

- the count of business stops resolving to a Place page (`verified`),
- the enumerated list of every fallback stop by name (or "0 stops on name-query fallback" when clean).

### YAML anchors — reusable places

Top-level keys whose name starts with `_` (e.g. `_aliases`) are dropped by the loader before validation. This lets you collect reusable place definitions once and reference them across plans and days using standard YAML anchors:

```yaml
_aliases:
  - &sc_elcentro
    name: "El Centro Supercharger"
    address: "3551 S Dogwood Rd, El Centro CA 92243"
    city_hint: "El Centro CA"
    place_id: "ChIJ7e8kLs1n14ARXaJ4irX08UY"
    lat: 32.7608
    lng: -115.5325
    elevation_ft: 50

plans:
  - key: "A"
    label: "Plan A"
    summary: "Sat 5/23 …"
    days:
      - title: "San Diego → Tucson"
        date: "Sat 5/23"
        stats: { miles: 433, drive: "6h 35m", charges: 5 }
        stops:
          - <<: *sc_elcentro       # Merges anchor into this stop
            type: charge
            leg_miles: 118
            leg_drive: "1h 47m"
            arrive: "08:32"
            depart: "09:00"
            soc_in: "52%"
            soc_out: "85%"
            charger_type: "V3 · 250 kW"
            meal: "breakfast"
```

PyYAML resolves anchors at parse time, so by the time the loader hands the dict to Pydantic each stop is a fully-expanded mapping. The `_aliases` carrier key is then dropped — invisible to the schema validator.

See `trips/sd_austin.yaml` for the full pattern in use across endpoints, Superchargers, and hotels.

---

## The rendered page — runtime tour

Open a render in a browser and here's what's wired up.

### Sticky header

- **Brand line** (`meta.title`) and **version chip** (`meta.version_label`).
- **Plan toggle**: one button per plan. Each shows the plan's `label` plus a sub-label derived from `tagline` (or the segment after the first `·` in `label`).
- **Day toggle**: one button per day, pre-labeled with `Day N` and the day's `date`.
- **Mode toggle**: three views — **Day view** (cards for each stop in the active day), **Full Trip Agenda** (the active plan as a printable-feeling agenda cover plus all days), and **All Plans · Merged** (every unique charger and hotel across all plans, ordered along the road). In merged mode the plan and day toggles deselect to signal that the view is cross-plan; selection restores on exit.

### State and deep links

The runtime keeps three pieces of state:

| Key | Values | Persisted as |
| --- | --- | --- |
| `state.plan` | a plan `key` | `localStorage[<prefix>-plan]`, URL fragment `plan=` |
| `state.day` | 1-based day index | `localStorage[<prefix>-day]`, URL fragment `day=` |
| `state.mode` | `day`, `agenda`, or `merged` | `localStorage[<prefix>-mode]`, URL fragment `mode=` |

URL fragment example: `#plan=A&day=2&mode=day`. Fragment values **take precedence over `localStorage` on load**. Out-of-range values fall back to defaults silently — no broken bookmarks if you delete a plan or shorten a day list.

### Stop cards

Each stop renders a card with:

- A type-colored numeric badge (charge / meal / hotel / endpoint).
- Arrive / depart times, leg miles, drive time, SoC in/out (for charges), rating + booking pill + pet policy (for hotels), restaurants list, free-form notes.
- **Two Maps buttons**: `Directions` (routable URL targeting the stop's address) and `Open in Maps` (lands on the business Place page when a `place_id` is present, else a name+city search). Each button is suffixed with a `✓` or `⚠` indicating the place-quality classification.
- For `charge` stops, an amber **§3.4 AC indicator row** when the runtime projects an at-risk arrival SoC for the upcoming leg and AC-off would meaningfully improve it (see [the consumption model](#yaml-schema) above).

### Multi-stop maps

A **Map the day** button and a **Map full trip** button build a single `/maps/dir/seg1/seg2/.../segN` URL covering every stop in scope. The URL builder:

1. Walks the stops in order.
2. Collapses consecutive duplicates by **address-match (case-insensitive, trimmed)** or **coordinate proximity** (`|Δlat| < 0.001` AND `|Δlng| < 0.001` ≈ 110 m at the equator). This is what fuses the on-site-Supercharger / hotel pair and the hotel-end-of-day-N / hotel-origin-of-day-N+1 reprise into a single waypoint.
3. Emits `"<Name>, <Address>"` for businesses and `"<Address>"` for personal endpoints, with spaces as `+` and commas left as `,`.

The same algorithm is implemented in Python (`trip_planner.maps`) and exercised by unit tests, so the CLI's `full-trip-url` command and the in-browser button produce byte-identical URLs.

### Verification panel

At the bottom of every day view, four groups:

- **Confirmed** — `verification.confirmed[]`.
- **Estimates** — `verification.estimates[]`.
- **Tradeoffs** — `verification.tradeoffs[]`.
- **Open in Maps · Quality Audit** — computed at runtime; lists every business stop on name-query fallback. A `console.warn` also fires per render naming the affected plan and stops — open DevTools while you capture missing Place IDs and watch the warning shrink.

### All Plans · Merged view

A flat continuous list of every unique charger and hotel across every plan, ordered along the road from trip origin to destination. Useful for drivers who want to scan all options without first committing to a plan — skip any stop and keep driving.

- **Deduplication.** Each stop's identity is `type + (placeId | address | coord)`. Two superchargers with the same `place_id` collapse to one entry. A Supercharger and a hotel at the same `place_id` (e.g. on-site charging at a hotel campus) stay distinct because `type` is part of the key.
- **Ordering.** Each entry is projected onto the vector from the trip origin to the trip destination (`(stop − origin) · (dest − origin)`) and sorted by the scalar projection. Works for any trip direction. Ties (a charger and a hotel at the same coordinates) tie-break with `charge` before `hotel`.
- **Plan chips.** Under each stop, a chip per plan that visits it (`A`, `B`, `C`). Hotel chips are color-coded by booking status — green when `BOOKED` somewhere, gray when `TO BOOK`.
- **Inline reservation detail.** Under each hotel, one row per plan that holds a reservation: plan-key prefix + a green `BOOKED · Conf #<n>` pill + check-in → check-out times. The pill is the same `.booking-pill.booked` element used in the day and agenda views, so the green BOOKED treatment reads identically in all three.
- **No day boundaries.** The view is a single sequence with no per-day grouping. Plan and day toggles deselect while you're in merged mode and restore when you leave.

---

## Tips and recipes

### Open on your phone

The cleanest path: render locally, drop the file in iCloud Drive / Google Drive / Dropbox, open the file on your phone, and tap "Open in Safari/Chrome." Because everything is inlined, the page works fully offline once loaded.

### Share a specific plan/day

Append the URL fragment when you share a link or screenshot the address bar:

```
file:///…/sd_austin.html#plan=B&day=2&mode=day
```

Fragment values override `localStorage`, so the recipient lands exactly where you intended.

### Reset state

If the page seems "stuck" on an old plan/day after you've edited the YAML and re-rendered, the recipient's `localStorage` is likely still pinning a now-invalid plan key. Two fixes:

- Bump `meta.storage_prefix` (e.g. `sd-austin` → `sd-austin-v2`) — new prefix, fresh state.
- Or in DevTools: `localStorage.clear()` and reload.

### Pipe the full-trip URL to your clipboard

```bash
poetry run trip-planner full-trip-url trips/sd_austin.yaml --plan A | pbcopy   # macOS
poetry run trip-planner full-trip-url trips/sd_austin.yaml --plan A | xclip    # Linux (xclip)
```

### Check a plan without rendering

`validate` is much faster than `render` and is what you want in a Git pre-commit hook or CI step:

```bash
poetry run trip-planner validate trips/my_trip.yaml
```

### Watch for missing Place IDs

After rendering, open the file in a browser, open DevTools → Console, and look for the `place-quality` warning. It lists every business stop currently relying on a name-query fallback. Capture a Place ID from Google Maps (`Share → Embed map → look at the `place_id=` parameter in the URL`) and paste it onto the matching stop or anchor.

---

## Customization

### Tweak the look

The renderer reads three files from `src/trip_planner/templates/`:

| File | Purpose |
| --- | --- |
| `trip.html.j2` | HTML shell with Jinja2 placeholders for the inlined CSS, runtime JS, and trip JSON. |
| `styles.css` | All CSS; copied verbatim into a `<style>` block. |
| `runtime.js` | All runtime JS; copied verbatim into a `<script>` block, **after** the JSON-encoded trip data. |

Edit the files directly and re-render. The template structure is split intentionally so a CSS-only or JS-only change does not require touching the HTML scaffold.

### Use an alternate template set

Point the renderer at a different directory:

```bash
poetry run trip-planner render trips/sd_austin.yaml \
  --templates-dir ./my-templates \
  --output renders/sd_austin.html
```

The directory must contain all three files (`trip.html.j2`, `styles.css`, `runtime.js`). Programmatic equivalent:

```python
from pathlib import Path
from trip_planner.loader import load_trip
from trip_planner.renderer import Renderer

trip = load_trip("trips/sd_austin.yaml")
renderer = Renderer(templates_dir=Path("./my-templates"))
renderer.render_to_file(trip, "renders/sd_austin.html")
```

### Add a new stop type

1. Add the enum value to `StopType` in `src/trip_planner/models.py`.
2. Add a `card-num.<type>` color rule to `templates/styles.css`.
3. Add a render branch to `renderStopCard()` in `templates/runtime.js`.

`dir_url` and `place_url` treat anything outside `{origin, dest}` as a business, so a new type inherits sensible Maps defaults for free.

### Use a different vehicle

Swap the entire `vehicle` block in your YAML to your EV's actual numbers and update per-stop `elevation_ft`. Nothing else needs to change — the runtime pulls every consumption constant from this block.

If you don't care about the AC indicator at all, omit the `vehicle` block: the renderer continues to work, the indicator just never fires.

### Multiple trips, one device

Each rendered file is isolated by `meta.storage_prefix`. Use a distinct prefix per trip and you can have several trips open in separate tabs without their state colliding.

---

## Using trip-planner as a library

The CLI is a thin wrapper over a small Python API. You can import the same building blocks:

```python
from pathlib import Path

from trip_planner.loader import load_trip
from trip_planner.renderer import Renderer
from trip_planner.maps import full_trip_url, day_url, audit_plan_place_quality
from trip_planner.consumption import evaluate_indicator

trip = load_trip("trips/sd_austin.yaml")   # → Trip (validated)

# Render
Renderer().render_to_file(trip, "out.html")

# Inspect plans / stops as Pydantic models
for plan in trip.plans:
    print(plan.key, plan.label, len(plan.days), "days")

# Build Maps URLs without a browser
plan_a = next(p for p in trip.plans if p.key == "A")
print(full_trip_url(plan_a))
print(day_url(plan_a.days[0]))

# Audit a plan's Place-ID coverage
print(audit_plan_place_quality(plan_a))
# {"verified": ["…"], "fallback": ["…"]}

# Evaluate the §3.4 AC indicator for a specific charge → next-stop hop
result = evaluate_indicator(plan_a.days[0].stops[1], plan_a.days[0].stops[2], trip.vehicle)
if result and result.fires:
    print(f"AC-off advised: {result.ac_on_arrival_soc_pct:.0f}% → {result.ac_off_arrival_soc_pct:.0f}%")
```

All public exceptions live on `trip_planner`:

```python
from trip_planner import TripPlannerError, SpecLoadError, SpecValidationError, RenderError
```

Logging follows the `TripPlanner.*` namespace (`TripPlanner.loader`, `TripPlanner.renderer`, etc.) so library users can attach their own handler:

```python
import logging
logging.getLogger("TripPlanner").setLevel(logging.DEBUG)
```

---

## Troubleshooting

### `error: schema validation failed for …`

A Pydantic validation error. The message will tell you which field failed and how — `extra="forbid"` means an unrecognized key (typo) raises just as loudly as a missing required field.

```
error: schema validation failed for trips/my_trip.yaml:
1 validation error for Trip
plans.0.days.0.stops.2.soc_in
  Extra inputs are not permitted [type=extra_forbidden, input_value='52%', input_type=str]
```

Common causes:

- A typo'd field name (`soc-in` instead of `soc_in`, `confimed` instead of `confirmed`).
- `meta.default_plan` doesn't match any plan's `key`.
- Duplicate plan keys across `plans[]`.
- A hotel stop with `booking_status` missing — this _doesn't_ fail, but emits a warning log and defaults the status to `PENDING`. Set it explicitly to silence the warning.

Re-run with `--verbose` to see the full traceback if you need it.

### `error: YAML parse error in …`

The file isn't valid YAML — usually an indentation mistake or a stray tab character. The wrapped message includes the line and column from PyYAML. Open the file at that location and check the indentation level matches the surrounding block.

### `error: could not read …`

The path doesn't exist or isn't readable. Check the path; remember relative paths resolve from the directory you ran the command in, not the repo root.

### `error: missing template asset: …`

You passed `--templates-dir` to a directory that doesn't contain `trip.html.j2`, `styles.css`, or `runtime.js`. All three are required.

### `error: plan 'X' not found in spec (have: A, B, C)`

`full-trip-url --plan X` references a key that's not in the spec. The error lists the available keys — pick one.

### The page renders but the plan/day toggle starts on the wrong tab

Your browser's `localStorage` is pinning an old value. See [Reset state](#reset-state).

### The AC indicator never fires (or fires too eagerly)

The indicator is a function of six knobs in `vehicle`: `usable_pack_kwh`, `baseline_wh_per_mi`, `ac_penalty_wh_per_mi`, `ac_window_start/end`, `climb_kwh_per_1000ft`, `ac_indicator_arrival_threshold_pct`, `ac_indicator_min_improvement_pp`. Walk a leg through the algorithm by hand (or in a Python REPL with `trip_planner.consumption.evaluate_indicator`) and tune the threshold or improvement floor until it matches your taste.

Two situations where the indicator returns `None` (silently doesn't fire) regardless of math:

- `current.soc_out` is missing or unparseable.
- `next_stop.leg_miles` is missing or `<= 0`.

---

## Testing

```bash
poetry run pytest               # full suite
poetry run pytest --cov         # with coverage report
poetry run pytest -k maps -v    # focused subset
```

Coverage target: **≥ 85%** on package code (`tool.coverage.run.source = ["trip_planner"]` in `pyproject.toml`).

Suites:

| File | Covers |
| --- | --- |
| `tests/test_models.py` | Schema validation, type-specific requirements, error cases (bad enum, missing required fields, duplicate plan keys, default_plan mismatch). |
| `tests/test_loader.py` | YAML → model round-trip, anchor expansion, `_*`-key dropping, error mapping. |
| `tests/test_maps.py` | Every URL builder (`dir_url`, `place_url`, `full_trip_url`, `day_url`), the dedup rule (address-match and coord proximity), Place-quality classification. |
| `tests/test_renderer.py` | Smoke test on the sample: renders without errors, output contains the embedded JSON for every plan, all four CSS sentinel selectors, and the expected runtime function names. |
| `tests/test_consumption.py` | The §3.4 indicator algorithm — fires/doesn't fire under each branch (below threshold + meets improvement, below threshold but improvement floor not met, above threshold, missing inputs returning `None`). |
| `tests/test_schema.py` | JSON Schema export: valid JSON, top-level shape, drift check (`schema/trip.schema.json` must match the live Pydantic models). |

---

## Project layout

```
trip-planner/
├── README.md                     This file
├── CLAUDE.md                     Agent guide — file routing, PII rules, common workflows
├── pyproject.toml                Poetry config + script entry point
├── docs/
│   └── trip-planner.md           Engine spec — deeper rationale for §3.4, runtime architecture, design rules
├── prompts/
│   └── markdown_to_yaml.md       Universal LLM prompt: trip notes → YAML
├── schema/
│   └── trip.schema.json          JSON Schema generated from the Pydantic models (regenerated by `trip-planner schema`)
├── trips/
│   ├── sd_austin.yaml            Public sanitized sample (SD → Austin, 3 plan variants)
│   └── private/                  Gitignored — your personal trip specs land here
│       └── .gitkeep
├── .claude/
│   └── commands/
│       └── yamlify.md            `/yamlify` slash command for Claude Code (notes → validated YAML)
├── src/trip_planner/
│   ├── __init__.py               Package version + public exception exports
│   ├── __main__.py               `python -m trip_planner` entry point
│   ├── cli.py                    Click CLI (render / validate / schema / full-trip-url)
│   ├── models.py                 Pydantic models for the trip spec
│   ├── loader.py                 YAML → models
│   ├── renderer.py               Jinja2 render pipeline
│   ├── maps.py                   Google Maps URL builders (Python; mirrors the runtime JS)
│   ├── consumption.py            §3.4 AC indicator algorithm (Python; mirrors the runtime JS)
│   ├── errors.py                 Typed exceptions
│   ├── logging_config.py         CLI logging setup
│   └── templates/
│       ├── trip.html.j2          HTML shell
│       ├── styles.css            All CSS (inlined into the render)
│       └── runtime.js            All runtime JS (inlined into the render)
└── tests/                        Pytest suite (incl. schema-drift check)
```

For the deeper engine spec — design goals, render pipeline diagram, full runtime architecture, exhaustive `§3.4` rationale — see [`docs/trip-planner.md`](docs/trip-planner.md). The README aims to get you productive; the spec aims to keep you correct when you extend the engine.

---

## Versioning and stability

Current version: **0.1.0** (see `src/trip_planner/__init__.py`).

The schema and CLI surface are still evolving. Until **1.0**, expect that:

- YAML field names may rename (with a transition path called out in release notes).
- The runtime JS API (function names, exposed globals) may change.
- Python module paths and exception classes under `trip_planner.*` are considered semi-stable: breaking changes will land in minor versions with deprecation notes.

`Trip`, `Plan`, `Day`, `Stop`, and `TripPlannerError` (+ subclasses) are the most stable surfaces — start there if you're embedding.

---

## License

[MIT](https://opensource.org/license/mit/). See `pyproject.toml` for the canonical declaration.
