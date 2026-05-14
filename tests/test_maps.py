"""Tests for the Google Maps URL builders."""

from __future__ import annotations

import pytest

from trip_planner.maps import (
    audit_plan_place_quality,
    day_url,
    dir_url,
    encode_stops_as_path,
    full_trip_url,
    place_quality,
    place_url,
)
from trip_planner.models import Stop, StopType, Trip


# ---------------------------------------------------------------------------
# Single-stop builders
# ---------------------------------------------------------------------------


def _stop(**kwargs) -> Stop:
    base = {
        "type": "charge",
        "name": "Test SC",
        "address": "1 Test St, Testville CA",
        "city_hint": "Testville CA",
        "lat": 32.0,
        "lng": -117.0,
    }
    base.update(kwargs)
    return Stop.model_validate(base)


def test_dir_url_uses_address() -> None:
    s = _stop()
    url = dir_url(s)
    assert "destination=1%20Test%20St" in url
    assert "destination_place_id" not in url


def test_dir_url_includes_place_id_when_known() -> None:
    s = _stop(place_id="ChIJabc123")
    url = dir_url(s)
    assert "destination_place_id=ChIJabc123" in url


def test_place_url_business_uses_name_plus_city_hint() -> None:
    s = _stop(name="Hampton Inn Tucson", city_hint="Tucson AZ")
    url = place_url(s)
    assert "query=Hampton%20Inn%20Tucson%20Tucson%20AZ" in url


def test_place_url_business_falls_back_to_name_without_city_hint() -> None:
    s = _stop(city_hint=None)
    url = place_url(s)
    assert "query=Test%20SC" in url


def test_place_url_personal_endpoint_uses_address() -> None:
    s = _stop(
        type="origin",
        name="Home",
        city_hint=None,
        address="202 C St, San Diego CA",
    )
    url = place_url(s)
    # Personal endpoints query by address.
    assert "query=202%20C%20St" in url


def test_place_url_appends_query_place_id() -> None:
    s = _stop(place_id="ChIJabc123")
    url = place_url(s)
    assert "query_place_id=ChIJabc123" in url


# ---------------------------------------------------------------------------
# place_quality classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "type_, place_id, expected",
    [
        ("charge", "ChIJabc", "verified"),
        ("hotel",  "ChIJxyz", "verified"),
        ("meal",   "ChIJfoo", "verified"),
        ("charge", None,      "fallback"),
        ("hotel",  None,      "fallback"),
        ("origin", None,      "n/a"),
        ("origin", "ChIJabc", "n/a"),
        ("dest",   None,      "n/a"),
    ],
)
def test_place_quality_classification(type_, place_id, expected) -> None:
    s = _stop(type=type_, place_id=place_id, address="addr", name="n",
              city_hint=None, lat=1.0, lng=2.0)
    assert place_quality(s) == expected


# ---------------------------------------------------------------------------
# Multi-stop URLs — encoding + dedup
# ---------------------------------------------------------------------------


def test_path_style_url_business_segments() -> None:
    s1 = _stop(type="origin", name="Home", address="202 C St, San Diego CA",
               lat=1.0, lng=2.0, city_hint=None)
    s2 = _stop(type="charge", name="El Centro SC", address="3551 S Dogwood Rd",
               lat=3.0, lng=4.0)
    url = encode_stops_as_path([s1, s2])
    # Origin segment is address-only; charge segment is "Name, Address".
    assert url.startswith("https://www.google.com/maps/dir/")
    parts = url.replace("https://www.google.com/maps/dir/", "").split("/")
    assert len(parts) == 2
    assert "El+Centro+SC," in parts[1]
    assert "202+C+St" in parts[0]


def test_dedup_collapses_same_address() -> None:
    s1 = _stop(type="charge", name="SC", address="9095 S Rita Rd, Tucson AZ",
               lat=32.1, lng=-110.8)
    s2 = _stop(type="hotel", name="Hampton", address="9095 S Rita Rd, Tucson AZ",
               lat=32.1031, lng=-110.7980)
    url = encode_stops_as_path([s1, s2])
    parts = url.replace("https://www.google.com/maps/dir/", "").split("/")
    assert len(parts) == 1
    assert parts[0].startswith("SC,")


def test_dedup_collapses_coord_proximity() -> None:
    """Hotel-as-end-of-day-N / hotel-as-origin-of-day-N+1 reprise."""
    s1 = _stop(type="hotel", name="X", address="100 Hotel St",
               lat=30.0000, lng=-100.0000)
    s2 = _stop(type="origin", name="X (depart)", address="100B Hotel St",
               lat=30.0005, lng=-100.0005)  # < 0.001° on both axes
    url = encode_stops_as_path([s1, s2])
    parts = url.replace("https://www.google.com/maps/dir/", "").split("/")
    assert len(parts) == 1


def test_no_dedup_when_far_apart() -> None:
    s1 = _stop(type="charge", name="A", address="1 A St", lat=30.0, lng=-100.0)
    s2 = _stop(type="charge", name="B", address="2 B St", lat=31.0, lng=-101.0)
    url = encode_stops_as_path([s1, s2])
    parts = url.replace("https://www.google.com/maps/dir/", "").split("/")
    assert len(parts) == 2


def test_spaces_become_plus_in_encoded_segments() -> None:
    s = _stop(type="charge", name="My Test SC", address="1 Spaces St, Tucson AZ",
              lat=30.0, lng=-100.0, city_hint="Tucson AZ")
    url = encode_stops_as_path([s])
    assert "+" in url
    assert "%20" not in url


def test_commas_preserved_in_encoded_segments() -> None:
    """Multi-stop URLs Google emits keep `,` as `,` rather than `%2C`."""
    s = _stop(type="charge", name="A", address="1 A St, Tucson AZ",
              lat=1.0, lng=2.0)
    url = encode_stops_as_path([s])
    assert "," in url
    assert "%2C" not in url


# ---------------------------------------------------------------------------
# Sample-spec parity — exercise the real data through full_trip_url / day_url
# ---------------------------------------------------------------------------


def test_sample_plan_a_full_trip_url_waypoint_count(sample_trip: Trip) -> None:
    """Plan A: 20 raw stops, 3 dedup collapses → 17 waypoints."""
    plan_a = next(p for p in sample_trip.plans if p.key == "A")
    url = full_trip_url(plan_a)
    parts = url.replace("https://www.google.com/maps/dir/", "").split("/")
    assert len(parts) == 17


def test_sample_plan_b_full_trip_url_waypoint_count(sample_trip: Trip) -> None:
    """Plan B: 21 raw stops, 3 dedup collapses → 18 waypoints."""
    plan_b = next(p for p in sample_trip.plans if p.key == "B")
    url = full_trip_url(plan_b)
    parts = url.replace("https://www.google.com/maps/dir/", "").split("/")
    assert len(parts) == 18


def test_sample_plan_c_full_trip_url_waypoint_count(sample_trip: Trip) -> None:
    """Plan C: 20 raw stops, 2 dedup collapses → 18 waypoints."""
    plan_c = next(p for p in sample_trip.plans if p.key == "C")
    url = full_trip_url(plan_c)
    parts = url.replace("https://www.google.com/maps/dir/", "").split("/")
    assert len(parts) == 18


def test_sample_plan_a_day1_url_collapses_tucson_pair(sample_trip: Trip) -> None:
    """Tucson Tech Park SC + Hampton Inn share 9095 S Rita Rd (Plan A Day 1)."""
    plan_a = next(p for p in sample_trip.plans if p.key == "A")
    day1 = plan_a.days[0]
    raw = len(day1.stops)
    parts = day_url(day1).replace("https://www.google.com/maps/dir/", "").split("/")
    assert len(parts) == raw - 1  # one collapse


def test_sample_place_quality_audit(sample_trip: Trip) -> None:
    """The audit numbers and fallback lists must match the spec's §18.5 table.

    Plan keys renamed in v15: Baseline→A, A→B, B→C. The set of fallback
    business stops is unchanged (still the same hotels lacking Place IDs).
    """
    by_key = {p.key: p for p in sample_trip.plans}

    audit = audit_plan_place_quality(by_key["A"])
    assert audit["fallback"] == []
    assert len(audit["verified"]) == 16

    audit = audit_plan_place_quality(by_key["B"])
    assert sorted(audit["fallback"]) == sorted([
        "Hampton Inn El Centro",
        "TownePlace Suites by Marriott Las Cruces",
        "Best Western Plus Fort Stockton Hotel",
    ])

    audit = audit_plan_place_quality(by_key["C"])
    assert sorted(audit["fallback"]) == sorted([
        "Hampton Inn & Suites Yuma",
        "Hampton Inn & Suites El Paso-Airport",
    ])
