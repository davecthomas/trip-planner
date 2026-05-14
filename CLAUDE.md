# Agent guide for trip-planner

This file orients any LLM coding agent running in this repo. For end-user-facing docs, see [`README.md`](README.md).

## What this project does

Renders a YAML trip spec into a single self-contained HTML file (CSS + JS inlined). EV-aware: understands plan variants, charge stops with SoC, hotel bookings, and a consumption envelope that drives an AC conservation indicator.

The YAML schema is **strict** (`extra="forbid"` on every Pydantic model). The runtime JS embedded in the HTML output is the source of truth for what the user sees; `src/trip_planner/maps.py` and `src/trip_planner/consumption.py` are Python mirrors of the same algorithms used for testing and offline reports. If you change one, change both.

## Common workflows

### "I have trip notes, give me a YAML I can render"

Use the [`/yamlify`](.claude/commands/yamlify.md) slash command. It locates the user's notes, loads [`prompts/markdown_to_yaml.md`](prompts/markdown_to_yaml.md) and [`schema/trip.schema.json`](schema/trip.schema.json), produces YAML, validates it via the CLI, and saves to `trips/private/<slug>.yaml`. The prompt itself is portable to any LLM if you're not in Claude Code.

### "Render the sample"

```bash
poetry run trip-planner render trips/sd_austin.yaml -o renders/sd_austin.html
```

### "Update the JSON Schema after changing models.py"

```bash
poetry run trip-planner schema -o schema/trip.schema.json
```

CI / pre-commit can drift-check with `poetry run trip-planner schema --check -o schema/trip.schema.json` (exits 3 on drift).

### "Run the tests"

```bash
poetry run pytest          # full suite
poetry run pytest --cov    # with coverage
```

## File-routing rules

| Path | Status | Note |
| --- | --- | --- |
| `trips/sd_austin.yaml` | **Tracked** | Public sanitized sample (City Hall endpoints, fake conf numbers). Safe to commit. |
| `trips/private/` | **Gitignored** | Default home for personal trip specs containing real addresses / hotel data. |
| `trips/<anything else>.yaml` | **Gitignored** (via `trips/*` rule) | Personal trips you want kept out of git. |
| `samples/` | **Gitignored** | User's personal planning docs (markdown specs, drafts). |
| `renders/` | **Gitignored** | Build output. |
| `schema/trip.schema.json` | **Tracked, generated** | Regenerate after model changes; CI may drift-check. |
| `prompts/markdown_to_yaml.md` | **Tracked** | Universal LLM prompt for notes → YAML. Edit when the schema evolves. |
| `.claude/commands/yamlify.md` | **Tracked** | Claude Code slash command wrapping the prompt above. |

## PII rules — non-negotiable

- **Never** commit a YAML containing real home addresses, hotel confirmation numbers, or phone numbers tied to a specific household.
- **Never** propose writing a personal trip to `trips/` root — that location is reserved for the sanitized public sample. Use `trips/private/` for anything with real PII.
- When generating YAML from user notes, default the output path to `trips/private/<slug>.yaml`. Only write elsewhere if the user explicitly asks.
- Do not fabricate Place IDs, conf numbers, or addresses to fill in gaps — use `# TODO:` comments instead.

## Coding conventions specific to this repo

- Python 3.11+. Pydantic v2. Click for CLI. Jinja2 for templates.
- YAML uses **snake_case**. The runtime JS uses camelCase — Pydantic's alias generator handles the boundary in `Renderer._build_trip_json`. Authors of YAML never see camelCase.
- `extra="forbid"` everywhere — typos fail loudly. Don't loosen this; instead update the schema.
- Errors flow through `trip_planner.errors.TripPlannerError` and its subclasses. CLI catches once, prints a one-line message, exits non-zero (1 for typed errors, 2 for unexpected, 3 for schema drift via `schema --check`).
- Logging namespace is `TripPlanner.*`. The CLI configures it; library users attach their own handlers.

## Where to look first

| If the user asks about… | Read this file |
| --- | --- |
| The YAML schema | `src/trip_planner/models.py` + `schema/trip.schema.json` |
| The runtime / browser behavior | `src/trip_planner/templates/runtime.js` + `docs/trip-planner.md` §4–§6 |
| Google Maps URL builders | `src/trip_planner/maps.py` (Python) + `templates/runtime.js` (JS mirror) |
| AC conservation indicator | `src/trip_planner/consumption.py` + `docs/trip-planner.md` §6.5 |
| CLI subcommands | `src/trip_planner/cli.py` |
| Engine spec / design rationale | `docs/trip-planner.md` |
| The bundled sample | `trips/sd_austin.yaml` |
