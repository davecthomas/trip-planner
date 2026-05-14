# trip-planner

A small Python tool that renders a single-page, fully self-contained HTML itinerary from a YAML trip specification. Targeted at EV road trips: it knows about plans, days, charge stops, hotels with booking metadata, and Google Maps link-outs, and emits one HTML file you can open on any modern mobile browser without a build step or backend.

The included sample (`trips/sd_austin.yaml`) is a real EV plan from San Diego to Austin with three plan variants, hotel bookings, and Supercharger sequencing.

## Quick start

```bash
poetry install
poetry run trip-planner render trips/sd_austin.yaml --output build/sd_austin.html
open build/sd_austin.html
```

Run tests:

```bash
poetry run pytest
```

## What it does

- Loads a YAML trip spec (`docs/trip-planner.md` documents the format)
- Validates it with Pydantic models
- Renders it through a Jinja2 template that embeds:
  - The trip data as JSON
  - All CSS inline
  - All runtime JS inline (plan/day toggling, Google Maps URL builders, agenda view, place-quality audit)
- Writes one self-contained HTML file

The browser does the interactive work — plan switching, day switching, URL rebuilds, state persistence in `localStorage` and the URL fragment. Python's job is just to bake a validated, beautifully-styled HTML around the data.

## Layout

```
trip-planner/
├── docs/trip-planner.md      Engine spec (YAML schema, render pipeline, customization)
├── trips/sd_austin.yaml      Sample trip
├── src/trip_planner/
│   ├── models.py             Pydantic models for the trip spec
│   ├── loader.py             YAML → models
│   ├── maps.py               Google Maps URL builders (Python; same algorithm as runtime JS)
│   ├── renderer.py           Jinja2 render pipeline
│   ├── cli.py                Click CLI
│   └── templates/            HTML template, CSS, runtime JS
└── tests/                    Pytest suite
```

## CLI

```
trip-planner render <spec.yaml> [--output FILE] [--verbose]
trip-planner validate <spec.yaml>
trip-planner full-trip-url <spec.yaml> --plan Baseline
```

See `docs/trip-planner.md` for the full design and YAML schema.
