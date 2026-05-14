"""Google Maps URL builders — Python implementation.

The browser renders Maps URLs at runtime via the JS embedded in the HTML
template. This module is a Python port of that same algorithm so the build
side has something testable and so the CLI can surface URLs without opening
a browser.

The runtime JS in `templates/runtime.js` is the source of truth for what the
user sees. These two implementations must stay aligned — tests exercise the
Python side; a sample-rendered HTML, opened in a browser, validates the JS
side. The algorithm is small enough that drift is unlikely as long as both
files are touched together.

Builders:

  - `dir_url(stop)`        — Directions to a single stop (routable)
  - `place_url(stop)`      — Open a single stop on its Place page
  - `place_quality(stop)`  — Verified / fallback / n/a classification
  - `full_trip_url(plan)`  — Multi-stop URL covering an entire plan
  - `day_url(day)`         — Multi-stop URL covering a single day
"""

from __future__ import annotations

import logging
from typing import Iterable, Literal
from urllib.parse import quote

from trip_planner.models import Day, Plan, Stop, StopType

log = logging.getLogger("TripPlanner.maps")

# Stops we treat as "businesses" for Open-in-Maps semantics. Personal
# endpoints (origin / dest) get an address-only query because they're
# private addresses without a Google Place page to land on.
_BUSINESS_TYPES = {StopType.CHARGE, StopType.HOTEL, StopType.MEAL}


def _is_business(stop: Stop) -> bool:
    return stop.type in _BUSINESS_TYPES


# ---------------------------------------------------------------------------
# Single-stop URLs
# ---------------------------------------------------------------------------


def dir_url(stop: Stop) -> str:
    """Build a Google Maps Directions URL targeting a single stop's address.

    `destination_place_id` is appended when available — Google uses it as
    the canonical resolver and the `destination` text becomes the display
    fallback. Without a place_id we just get an address resolve.
    """
    url = "https://www.google.com/maps/dir/?api=1&destination=" + quote(stop.address, safe="")
    if stop.place_id:
        url += "&destination_place_id=" + quote(stop.place_id, safe="")
    return url


def place_url(stop: Stop) -> str:
    """Build an Open-in-Maps URL pointing at a single stop's Place page.

    For businesses we query by `<name> <city_hint>` so Google lands on the
    business Place page (phone, hours, photos, Call button). For personal
    endpoints we query by address.
    """
    if _is_business(stop):
        query_text = f"{stop.name} {stop.city_hint}" if stop.city_hint else stop.name
    else:
        query_text = stop.address

    url = "https://www.google.com/maps/search/?api=1&query=" + quote(query_text, safe="")
    if stop.place_id:
        url += "&query_place_id=" + quote(stop.place_id, safe="")
    return url


PlaceQuality = Literal["verified", "fallback", "n/a"]


def place_quality(stop: Stop) -> PlaceQuality:
    """Runtime audit classification for the Open in Maps link of a stop.

    Returns:
        - `verified` for business stops with a known Place ID
        - `fallback` for business stops without one
        - `n/a` for personal endpoints (origin / dest)
    """
    if not _is_business(stop):
        return "n/a"
    return "verified" if stop.place_id else "fallback"


# ---------------------------------------------------------------------------
# Multi-stop path-style URLs
# ---------------------------------------------------------------------------


# Tunable: how close in degrees lat/lng counts as "the same point" for dedup.
# 0.001° ≈ 110m at the equator; tight enough to coalesce the
# hotel-end-of-day-N / origin-of-day-N+1 reprise but loose enough to absorb
# minor coordinate jitter in the source data.
_COORD_PROXIMITY = 0.001


def _dedup_consecutive(stops: Iterable[Stop]) -> list[Stop]:
    """Collapse consecutive stops that are effectively the same point.

    Rule (any one is sufficient):
      1. Same address, case-insensitive, whitespace-trimmed.
      2. Coordinates within `_COORD_PROXIMITY` on both lat and lng.

    Catches the SC + on-site hotel pair (same address, different `type`) and
    every hotel-as-end-of-day-N / hotel-as-origin-of-day-N+1 reprise.
    """
    out: list[Stop] = []
    for s in stops:
        if out:
            last = out[-1]
            same_addr = last.address.strip().lower() == s.address.strip().lower()
            close_lat = abs(last.lat - s.lat) < _COORD_PROXIMITY
            close_lng = abs(last.lng - s.lng) < _COORD_PROXIMITY
            if same_addr or (close_lat and close_lng):
                continue
        out.append(s)
    return out


def _encode_segment(stop: Stop) -> str:
    """Encode one stop as a path segment.

    Businesses are emitted as `"<Name>, <Address>"` so the multi-stop pin
    on the resulting map page carries the business label. Personal
    endpoints are address-only.

    The encoding matches what Google emits when you share a multi-stop
    route from the Maps UI: spaces become `+`, commas stay as `,`.
    """
    text = f"{stop.name}, {stop.address}" if _is_business(stop) else stop.address
    return quote(text, safe="").replace("%20", "+").replace("%2C", ",")


def encode_stops_as_path(stops: Iterable[Stop]) -> str:
    """Render a list of stops as a `/maps/dir/seg1/.../segN` URL.

    Implementation note: this is the shared core used by both
    `full_trip_url` and `day_url` so the dedup + encoding rules can't
    drift apart between the full-trip and per-day buttons.
    """
    deduped = _dedup_consecutive(list(stops))
    segments = [_encode_segment(s) for s in deduped]
    return "https://www.google.com/maps/dir/" + "/".join(segments)


def full_trip_url(plan: Plan) -> str:
    """Build a single Google Maps URL containing every stop of a plan."""
    all_stops: list[Stop] = [s for d in plan.days for s in d.stops]
    log.debug("full-trip URL for plan %s: %d raw stops", plan.key, len(all_stops))
    return encode_stops_as_path(all_stops)


def day_url(day: Day) -> str:
    """Build a Google Maps URL containing every stop of a single day."""
    return encode_stops_as_path(day.stops)


# ---------------------------------------------------------------------------
# Audit helpers (used by the renderer's verification group and the CLI)
# ---------------------------------------------------------------------------


def audit_plan_place_quality(plan: Plan) -> dict[str, list[str]]:
    """Count Place-verified vs fallback business stops in a plan.

    Returns a dict with two lists, by stop name:
        {"verified": [...], "fallback": [...]}

    Personal endpoints (origin/dest) are excluded from both lists. Names
    are deduplicated so a hotel appearing as both end-of-day-N and
    origin-of-day-N+1 only counts once.
    """
    verified: set[str] = set()
    fallback: set[str] = set()
    for day in plan.days:
        for stop in day.stops:
            q = place_quality(stop)
            if q == "verified":
                verified.add(stop.name)
            elif q == "fallback":
                fallback.add(stop.name)
    return {"verified": sorted(verified), "fallback": sorted(fallback)}
