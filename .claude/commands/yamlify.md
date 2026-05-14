---
description: Convert a trip markdown/notes file into a validated trip-planner YAML spec, save to trips/private/, and print the render command.
argument-hint: [path/to/notes.md]
---

# /yamlify — markdown trip notes → validated YAML

You are converting a user's trip notes (markdown, prose, or pasted text) into a valid **trip-planner** YAML spec, validating the result, saving it to a PII-safe location, and telling the user how to render it.

The argument (if provided) is a path to the source notes: `$ARGUMENTS`

## Step 1 — Locate the source notes

- If `$ARGUMENTS` is non-empty and points to a real file, read it with the Read tool.
- If `$ARGUMENTS` is empty, look for trip notes in this priority order:
  1. The most recently modified `*.md` under `samples/` (gitignored, where personal specs live in this repo)
  2. Any `*.md` at repo root that isn't `README.md`, `CLAUDE.md`, or a doc explicitly under `docs/`
  3. If nothing obvious turns up, ask the user where their notes are.
- If the user's notes are pasted into chat rather than a file, use the pasted content directly and skip the Read.

## Step 2 — Load the conversion rules and schema

Read these two files (they are the contract for what valid output looks like):

1. `prompts/markdown_to_yaml.md` — the universal conversion prompt: schema overview, hard validation rules, anchor idiom, worked example, PII guardrails, and **§10 cross-reference rule**. **Follow it precisely.** That prompt is portable to any LLM; this command is the Claude Code wrapper around it.
2. `schema/trip.schema.json` — the machine-readable JSON Schema derived from the Pydantic models. The schema is the source of truth when prose disagrees with it. If the schema file is missing, run `poetry run trip-planner schema -o schema/trip.schema.json` to regenerate it.

## Step 2.5 — Check for an existing YAML for the same trip

Per §10 of the conversion prompt, before generating from scratch, list `trips/*.yaml` (and `trips/private/*.yaml` if accessible) and look for a YAML whose `meta.title` matches the trip described in the source notes. This is the single highest-leverage check in the whole workflow: an existing YAML carries the per-stop sequences, lat/lng, and current plan naming that source notes typically lack.

**If a match exists:**

- Treat the existing YAML as the **structural base**.
- Copy it to the target output path (see Step 4).
- Apply targeted overrides from the source notes per §10 of the prompt — typically: endpoint addresses, confirmation numbers, phone numbers, Place IDs.
- Do **not** wipe data the source notes are silent on (SoC values, leg miles, restaurant lists).
- Trust the YAML's plan keys / labels / version_label over the markdown's if they differ — the markdown is often the artifact that drifted out of sync.

**If no match exists:** generate from scratch per the rest of the prompt, using `# TODO:` markers for gaps.

If you find a public sanitized sample (e.g. `trips/sd_austin.yaml` with City Hall endpoints and `EXAMPLE-*` conf numbers), that counts as a match — treat it as the base and apply the user's real PII overrides on top.

## Step 3 — Produce the YAML

Generate the YAML output following every rule in `prompts/markdown_to_yaml.md`. In particular:

- All field names `snake_case`.
- `meta.default_plan` must match a plan `key`.
- Required per-stop fields per the type table.
- SoC values quoted with `%` ("52%"), times as `HH:MM`.
- Reusable places under `_aliases` with anchor merge (`<<: *anchor`).
- **Never fabricate** Place IDs, confirmation numbers, or street addresses. Use `# TODO: …` inline comments where the user's notes left a gap.
- Default vehicle block omitted unless the user's notes call for the AC consumption indicator.

## Step 4 — Save to a PII-safe path

Default output: `trips/private/<slug>.yaml`

- `<slug>` is a kebab-case derivation of either the trip's `meta.title` or the source markdown filename (without extension). Examples: `Vegas weekend Memorial Day 2026` → `vegas-weekend-memorial-day-2026`; `samples/thanksgiving_2026.md` → `thanksgiving-2026`.
- If `trips/private/` doesn't exist, create it. The directory is gitignored by `.gitignore` (`trips/*` rule with no negation for `trips/private/`).
- If the file already exists, ask the user whether to overwrite or write to `trips/private/<slug>-2.yaml`.
- If the user explicitly passes an output path elsewhere, honor it — but warn them if it's a tracked location (anywhere outside `trips/private/` and not the public sample).

## Step 5 — Validate

Run the validator:

```bash
poetry run trip-planner validate trips/private/<slug>.yaml
```

If it fails:

- Read the Pydantic error message carefully — it names the field that broke and why.
- Fix the YAML directly (Edit tool).
- Re-run `validate`.
- Repeat until clean. Cap retries at 5; if you still can't get it clean, surface the remaining error to the user with your best diagnosis instead of looping.

A successful validation prints something like:

```
ok: trips/private/<slug>.yaml — 1 plan(s), 3 day(s), 12 stop(s)
```

## Step 6 — Tell the user how to render

After validation passes, print a short closing message with the next command — actually paste the command so the user can copy it:

```
Saved to trips/private/<slug>.yaml — 1 plan, 3 days, 12 stops.

Render it:

    poetry run trip-planner render trips/private/<slug>.yaml -o renders/<slug>.html
    open renders/<slug>.html

Print the full Maps URL for plan A:

    poetry run trip-planner full-trip-url trips/private/<slug>.yaml --plan A
```

If the YAML contains `# TODO:` comments (gaps in the source notes), explicitly call out the count and ask whether the user wants to fill them in before rendering, or render now and iterate.

## Step 7 — Stop

Do not proceed to render the HTML yourself unless the user asks. Stop after step 6 — they may want to review the YAML, fill in TODOs, or tweak things before rendering.

---

## Notes on tone and scope

- This command is for **converting** notes to YAML. It is not a chat-with-the-planner agent. Do not propose changes to the trip itself (different stops, different hotels) unless the user explicitly asks.
- If the user's notes are radically incomplete (no stops, no dates), say so directly and ask for the missing pieces rather than producing a placeholder YAML.
- PII is real. Default behavior is to write under `trips/private/` — never propose writing a personal trip to `trips/` root or anywhere committed.
