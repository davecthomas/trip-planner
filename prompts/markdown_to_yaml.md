# Convert trip notes (markdown or prose) → trip-planner YAML

You are converting human-written trip notes into a valid **trip-planner** YAML spec. The output must validate against the schema at `schema/trip.schema.json` (which is the source of truth — when this prompt and the schema disagree, trust the schema).

This prompt is portable: it works in Claude, ChatGPT, Cursor, or any LLM. If you are running inside Claude Code with this repo open, also follow the wrapper in `.claude/commands/yamlify.md` for file-routing and post-generation validation.

---

## 1 — What you produce

A single YAML file with three top-level sections — `meta`, `vehicle` (optional but recommended for EVs), and `plans` — plus an optional `_aliases` carrier list for reusable places (see §6).

Output **valid YAML only** — no surrounding markdown fences, no commentary, no leading explanation. The user wants the file content.

If the user's notes are incomplete or ambiguous (missing SoC values, unclear dates, no charger types), produce the best plausible YAML and add a `# TODO: …` comment on each line that needs human review. Do not silently invent dangerous values — e.g., don't fabricate hotel confirmation numbers, don't make up `place_id` strings (a fake Place ID breaks the Maps deep link).

---

## 2 — Hard validation rules (these fail loudly)

The Pydantic models use `extra="forbid"`, so **any unknown field name is a hard error**. Common typos that bite:

- `confimed` instead of `confirmed` (verification group)
- `socIn` / `socOut` instead of `soc_in` / `soc_out` (YAML uses snake_case; camelCase is the runtime-JS shape, never YAML)
- `placeId` instead of `place_id`
- `cityHint` instead of `city_hint`

Additional invariants the schema enforces:

| Rule | Constraint |
| --- | --- |
| `meta.default_plan` | Must match the `key` of one of the plans (exactly). |
| `meta.storage_prefix` | Regex `^[a-z][a-z0-9-]{0,31}$` — lowercase ASCII, starts with a letter. |
| Plan `key` | Regex `^[A-Za-z0-9_-]{1,16}$`, **unique across all plans**. |
| `days[]` | At least 1 per plan. |
| `stops[]` | At least 1 per day. |
| `stop.type` | One of `origin`, `charge`, `meal`, `hotel`, `dest`. |
| `stop.lat`, `stop.lng` | Required numbers on every stop. |
| `stop.elevation_ft` | Optional. Range `-1000 … 15000` ft. |
| `hotel.rating.stars` | Integer 1–5. |
| `hotel.rating.user` | Float 0.0–5.0. |
| `vehicle.usable_pack_kwh` | `0 < x ≤ 300` kWh. |
| `vehicle.baseline_wh_per_mi` | `0 < x ≤ 1000`. |
| `vehicle.ac_window_start` / `_end` | Regex `^\d{2}:\d{2}$` (zero-padded `HH:MM`). |
| Time strings (`arrive`, `depart`) | Use `HH:MM` 24-hour format. |
| SoC strings (`soc_in`, `soc_out`) | `"NN%"` with the percent sign — e.g. `"52%"`. |

If a field doesn't apply to a stop type, **omit it entirely** rather than setting it to `null`. The schema does not allow null for most optional fields.

---

## 3 — Schema overview (sections + key fields)

### `meta` (required)

```yaml
meta:
  title: "San Diego → Austin"
  version_label: "v15 · Tesla MYP · 69 mph"
  agenda_label: "Full Trip Agenda · v15"
  default_plan: "A"          # must match a plan key below
  storage_prefix: "sd-austin" # localStorage namespace
```

### `vehicle` (optional; required for the AC indicator to fire)

```yaml
vehicle:
  name: "Tesla Model Y Performance"
  make: "Tesla"
  model: "Model Y Performance"
  year: 2024
  wheels: '21" Überturbine'
  notes: >-
    Stock aero. ~605 lb payload. 69 mph cruise.

  usable_pack_kwh: 75
  reserve_soc_pct: 20

  baseline_wh_per_mi: 330
  ac_penalty_wh_per_mi: 30
  ac_window_start: "10:00"
  ac_window_end: "18:00"
  climb_kwh_per_1000ft: 2.35
  regen_recovery: 0.65

  ac_indicator_arrival_threshold_pct: 25
  ac_indicator_min_improvement_pp: 3
```

If the user's notes don't include consumption details, you can omit the entire `vehicle` block — the engine continues to work, the AC indicator just never fires. Default to omitting it unless the user's notes clearly call for the indicator.

### `plans` → `days` → `stops`

```yaml
plans:
  - key: "A"
    label: "Plan A · 3D · 2N"
    tagline: "Sat 5/23 AM departure"            # optional sub-label
    summary: "Sat 5/23 – Mon 5/25 · ~1,340 mi · 14 charges"
    days:
      - title: "San Diego → Tucson"
        date: "Sat 5/23"
        stats: { miles: 433, drive: "6h 35m", charges: 5 }
        stops:
          - type: origin
            name: "San Diego City Hall"
            address: "202 C St, San Diego CA 92101"
            lat: 32.7174
            lng: -117.1628
            elevation_ft: 50
            depart: "06:45"
          - type: charge
            name: "El Centro Supercharger"
            address: "3551 S Dogwood Rd, El Centro CA 92243"
            city_hint: "El Centro CA"
            place_id: "ChIJ7e8kLs1n14ARXaJ4irX08UY"
            lat: 32.7608
            lng: -115.5325
            elevation_ft: 50
            leg_miles: 118
            leg_drive: "1h 47m"
            arrive: "08:32"
            depart: "09:00"
            soc_in: "52%"
            soc_out: "85%"
            charger_type: "V3 · 250 kW"
            meal: "breakfast"
            restaurants:
              - { name: "Celia's Kitchen", cuisine: "Mexican breakfast · 0.4 mi" }
          # ...
          - type: hotel
            name: "Hampton Inn & Suites Tucson Tech Park"
            address: "9095 S Rita Rd, Tucson AZ 85747"
            city_hint: "Tucson AZ"
            place_id: "ChIJt_eHI4th1oYRX4UjVvVvrY4"
            lat: 32.1031
            lng: -110.7980
            elevation_ft: 2500
            phone: "+1-520-989-7200"
            leg_miles: 0.1
            leg_drive: "< 1m"
            arrive: "15:55"
            rating: { stars: 3, user: 4.3 }
            rate: "~$169"
            booking_status: "BOOKED"
            conf_number: "ABC-12345"
            plan_label: "Plan A"
            check_in: "May 23 (Sat) 4:00 PM"
            check_out: "May 24 (Sun) 11:00 AM"
            cancel_by: "Free cancel through 22 May 2026 11:59 PM local"
            pet_policy: "Hilton: 2 dogs ≤75 lbs each, $50/stay"
            charger_prox: "On-site (0 min)"
```

### `verification` (optional, per plan)

```yaml
verification:
  confirmed:
    - "Origin: San Diego City Hall"
    - "Vehicle: Tesla Model Y Performance"
  estimates:
    - "Drive times computed at 69 mph + 5% allowance"
  tradeoffs:
    - "Tucson hotel chosen for on-site Supercharger access"
```

A fourth group, **Open in Maps · Quality Audit**, is computed at runtime — do not put it in YAML.

---

## 4 — Stop type → required fields

| `type` | Required fields beyond shared (`name`, `address`, `lat`, `lng`) | Common additional fields |
| --- | --- | --- |
| `origin` | — | `depart` |
| `charge` | `leg_miles`, `leg_drive`, `arrive`, `depart`, `soc_in`, `soc_out` | `charger_type`, `meal`, `restaurants`, `place_id`, `city_hint`, `elevation_ft` |
| `meal` | `leg_miles`, `leg_drive`, `arrive`, `depart` | `place_id`, `city_hint` |
| `hotel` | `leg_miles`, `leg_drive`, `arrive`, `booking_status` | `rating`, `rate`, `phone`, `conf_number`, `plan_label`, `check_in`, `check_out`, `cancel_by`, `pet_policy`, `charger_prox`, `place_id`, `city_hint` |
| `dest` | `leg_miles`, `leg_drive`, `arrive` | — |

`booking_status` defaults to `PENDING` with a warning log if omitted on a hotel. Set it explicitly.

---

## 5 — `place_id` policy

Google Place IDs make the **Open in Maps** button land on the business Place page directly (instead of doing a name+city search). They are nice-to-have, not required.

- **Do not fabricate Place IDs.** A bogus ID breaks the deep link; the name+city fallback is fine.
- If the user provides Place IDs in their notes, include them verbatim.
- For personal endpoints (`origin`, `dest`), **omit `place_id`** — Place semantics don't apply.
- For businesses without a Place ID, omit the field. The runtime classifies the stop as `fallback` (still works, just less precise) and lists it under "Open in Maps · Quality Audit" so the user can backfill later.

---

## 6 — Reusable places via YAML anchors

When the same physical location appears multiple times (a hotel that's end-of-day-N and origin-of-day-N+1, a Supercharger visited on multiple plan variants), use YAML anchors to define it once:

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
    # ...
    days:
      - # ...
        stops:
          - <<: *sc_elcentro    # merge the anchor into this stop
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

**Why this works:** keys starting with `_` are dropped by the loader before validation. PyYAML resolves `<<: *anchor` at parse time, so each stop ends up as a fully-merged mapping. This dramatically reduces duplication in a multi-plan spec.

Use anchors for **endpoints, Superchargers, hotels** — anything reused across days or plans. Keep per-visit fields (`leg_miles`, `arrive`, `depart`, `soc_in`, `soc_out`, booking metadata) on the using stop, not the anchor.

The full sample `trips/sd_austin.yaml` (in this repo) uses this pattern for ~20 reusable places across three plan variants.

---

## 7 — PII and where to save the output

Trip specs commonly include real home addresses, hotel confirmation numbers, phone numbers, and pet policies tied to a specific household. **Do not commit these to git.**

Conventions in this repo:

- `trips/sd_austin.yaml` — the **public sanitized sample** (City Hall endpoints, fake confirmation numbers). Committed.
- `trips/private/` — **personal trip specs**. Gitignored. This is where converted output should land by default.
- `trips/<anything else>.yaml` — also gitignored (see `.gitignore`).

Default output path: `trips/private/<slug>.yaml` where `<slug>` is a kebab-case derivation of the trip title or the source markdown filename. For example, `samples/thanksgiving_2026.md` → `trips/private/thanksgiving-2026.yaml`.

If the user passes an explicit output path, honor it. Otherwise propose the default and let them override.

---

## 8 — Validation

Before declaring the conversion complete, run:

```bash
poetry run trip-planner validate <output-path>
```

If validation fails, read the error message, fix the YAML, and re-validate. Common fixes:

- Add the missing required field the error names.
- Remove the typo'd field (`extra="forbid"` will name it).
- Quote a value that YAML is interpreting as a different type (a SoC like `52%` won't parse without quotes; bare `0.1` is a float but `"0.1"` is a string).

---

## 9 — Worked example (markdown → YAML)

**Source (markdown notes):**

```markdown
# Vegas weekend, Memorial Day 2026

Leaving SD Friday 5/23 around 7am. Two adults, one dog (~40 lb).
Tesla MYP, 80% start.

- 7:00 AM depart, San Diego (home)
- Charge stop: Barstow Supercharger. Arrive ~9:45, depart 10:15. SoC 35 → 80.
  V3 250 kW. Coffee.
- Vegas arrival: Bellagio. ~12:15 PM. 2 nights. Booked, conf #VGS-7788.
  $279/night. Pet policy: dogs under 50 lb, $100 fee.
- Sun 5/25 depart 10am, charge at Baker SC (V3 250). 11:00–11:25.
- Home by ~3:00 PM.

Total: ~660 mi, 4 charges, 2 nights.
```

**Output (YAML), saved to `trips/private/vegas-weekend.yaml`:**

```yaml
_aliases:
  - &home_sd
    name: "Home (San Diego)"
    address: "REPLACE_WITH_REAL_ADDRESS"    # TODO: real address
    lat: 32.7157
    lng: -117.1611
  - &sc_barstow
    name: "Barstow Supercharger"
    address: "2812 Lenwood Rd, Barstow CA 92311"
    city_hint: "Barstow CA"
    lat: 34.8542
    lng: -117.0859
  - &sc_baker
    name: "Baker Supercharger"
    address: "72220 Baker Blvd, Baker CA 92309"
    city_hint: "Baker CA"
    lat: 35.2683
    lng: -116.0717
  - &hotel_bellagio
    name: "Bellagio Las Vegas"
    address: "3600 S Las Vegas Blvd, Las Vegas NV 89109"
    city_hint: "Las Vegas NV"
    lat: 36.1126
    lng: -115.1767

meta:
  title: "San Diego → Las Vegas weekend"
  version_label: "v1 · MYP · 69 mph"
  agenda_label: "Vegas Weekend Agenda"
  default_plan: "A"
  storage_prefix: "vegas-mday-2026"

plans:
  - key: "A"
    label: "Vegas weekend · 2N"
    summary: "Fri 5/23 – Sun 5/25 · ~660 mi · 4 charges"
    days:
      - title: "San Diego → Las Vegas"
        date: "Fri 5/23"
        stats: { miles: 330, drive: "5h 00m", charges: 1 }   # TODO: confirm
        stops:
          - <<: *home_sd
            type: origin
            depart: "07:00"
          - <<: *sc_barstow
            type: charge
            leg_miles: 175                # TODO: confirm
            leg_drive: "2h 45m"           # TODO: confirm
            arrive: "09:45"
            depart: "10:15"
            soc_in: "35%"
            soc_out: "80%"
            charger_type: "V3 · 250 kW"
            meal: "coffee"
          - <<: *hotel_bellagio
            type: hotel
            leg_miles: 155                # TODO: confirm
            leg_drive: "2h 00m"           # TODO: confirm
            arrive: "12:15"
            rate: "~$279"
            booking_status: "BOOKED"
            conf_number: "VGS-7788"
            plan_label: "Vegas weekend"
            pet_policy: "Bellagio: dogs ≤50 lb, $100 fee"

      - title: "Las Vegas (stay)"
        date: "Sat 5/24"
        stats: { miles: 0, drive: "0m", charges: 0 }
        stops:
          - <<: *hotel_bellagio
            type: hotel
            leg_miles: 0
            leg_drive: "0m"
            arrive: "00:00"
            booking_status: "BOOKED"
            conf_number: "VGS-7788"
            plan_label: "Vegas weekend"

      - title: "Las Vegas → San Diego"
        date: "Sun 5/25"
        stats: { miles: 330, drive: "5h 00m", charges: 1 }   # TODO: confirm
        stops:
          - <<: *hotel_bellagio
            type: origin
            name: "Bellagio Las Vegas (depart)"
            depart: "10:00"
          - <<: *sc_baker
            type: charge
            leg_miles: 90                 # TODO: confirm
            leg_drive: "1h 00m"           # TODO: confirm
            arrive: "11:00"
            depart: "11:25"
            soc_in: "45%"                 # TODO: confirm
            soc_out: "80%"
            charger_type: "V3 · 250 kW"
            meal: "no meal"
          - <<: *home_sd
            type: dest
            leg_miles: 240                # TODO: confirm
            leg_drive: "3h 30m"           # TODO: confirm
            arrive: "15:00"

    verification:
      confirmed:
        - "Vehicle: Tesla Model Y Performance"
        - "Hotel: Bellagio, BOOKED conf #VGS-7788"
      estimates:
        - "Drive times approximate at 69 mph cruise"
      tradeoffs:
        - "Single-stop charging Day 1; two-stop possible for tighter buffer"
```

Notes on this example:

- Home address is stubbed (`REPLACE_WITH_REAL_ADDRESS`) with a `# TODO:` — never fabricate a real address.
- Charge leg miles are stubbed with `# TODO: confirm` because the source notes didn't include them.
- No Place IDs are invented; the runtime will mark these as `fallback`.
- `vehicle` block is omitted (notes didn't ask for the AC indicator).
- Two-night stay is modeled as a day with `miles: 0` and a single hotel stop referencing the existing anchor — keeps the booking metadata in one place.

---

## 10 — Cross-reference an existing YAML when one is present

**Before generating YAML from scratch, look for an existing YAML for the same trip in `trips/`.** A previously-rendered version of the same itinerary — even a sanitized public sample — typically contains:

- The full ordered stop sequences for every plan (SoC values, leg miles, arrive/depart times, meal types, restaurants).
- Precise lat/lng for every stop, including Superchargers and hotels.
- The current plan key naming (e.g. `A`, `B`, `C`) — which may differ from the source markdown if the trip was renamed after the markdown was last revised.
- Place IDs already captured.

This data is **expensive to recreate from prose** and easy to copy. When an existing YAML is present:

1. **Use it as the structural base.** Start from a copy.
2. **Apply overrides only where the source markdown explicitly contradicts** the existing YAML. The markdown is the source of truth for things the user has *changed*; the YAML is the source of truth for everything else.
3. **Common overrides** when working from a sanitized public sample:
   - **Endpoints.** Markdown often carries the real home/office address; the public YAML uses landmarks (e.g. City Hall). Swap the anchor's `name`, `address`, `lat`, `lng`, `elevation_ft`.
   - **Confirmation numbers.** Markdown carries real `confNumber` values; the public YAML uses placeholders like `EXAMPLE-1001`. Swap these in.
   - **Phone numbers, pet policies.** If the markdown has updates the YAML doesn't reflect, apply them.
   - **Place IDs.** If the markdown has a Place ID inventory the YAML hasn't been updated with, fold them in.
4. **Don't override what the markdown is silent on.** If the markdown doesn't mention SoC values at all, do not zero them out or replace them with TODOs — keep the YAML's existing values.
5. **Watch for stale terminology in the markdown.** Trip metadata (plan keys, plan labels, version labels) is most authoritative in the YAML if the markdown wasn't updated alongside a rename. If markdown says `Baseline` and YAML says `Plan A`, the rename happened — use the YAML's terminology.

If no existing YAML matches, generate from scratch per the rest of this prompt and use `# TODO:` comments for gaps.

**How to detect a match.** Look for any `trips/*.yaml` whose `meta.title` matches the source notes' trip title (case-insensitive, normalized). Also check `trips/private/` if accessible. When in doubt, ask the user.

---

## 11 — Final checklist

Before returning your output:

- [ ] Top-level keys are exactly `meta`, `vehicle` (optional), `plans`, and optionally `_aliases`. No others.
- [ ] All field names are `snake_case`.
- [ ] `meta.default_plan` matches a plan `key`.
- [ ] Plan keys are unique and match the regex.
- [ ] Every stop has `type`, `name`, `address`, `lat`, `lng`.
- [ ] Every non-`origin` stop has `arrive`, `leg_miles`, `leg_drive`. Every non-`dest` stop has `depart`.
- [ ] SoC values are quoted strings with `%` (e.g. `"52%"`).
- [ ] Time values are `HH:MM` 24-hour.
- [ ] No fabricated Place IDs or confirmation numbers — `# TODO:` comments mark gaps.
- [ ] Output is pure YAML, no fences, no preamble.
- [ ] If an existing YAML for the same trip was found in `trips/`, it was used as the base and only contradicting facts were overridden (see §10).
