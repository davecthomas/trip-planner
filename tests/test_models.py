"""Pydantic model tests — focus on validation behavior we rely on at the boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from trip_planner.models import (
    BookingStatus,
    Day,
    DayStats,
    Meta,
    Plan,
    Rating,
    Stop,
    StopType,
    Trip,
    Vehicle,
)


# ---------------------------------------------------------------------------
# Helpers — minimal valid building blocks for happy-path / negative tests
# ---------------------------------------------------------------------------


def _origin() -> dict:
    return {
        "type": "origin",
        "name": "Home",
        "address": "1 Origin St, A CA",
        "lat": 1.0,
        "lng": 2.0,
        "depart": "06:45",
    }


def _dest() -> dict:
    return {
        "type": "dest",
        "name": "Goal",
        "address": "1 Goal St, B TX",
        "lat": 3.0,
        "lng": 4.0,
        "arrive": "15:00",
        "leg_miles": 100,
        "leg_drive": "1h 30m",
    }


def _minimum_plan() -> dict:
    return {
        "key": "Baseline",
        "label": "Baseline · 1D",
        "summary": "demo",
        "days": [{
            "title": "A → B",
            "date": "Sat 1/1",
            "stats": {"miles": 100, "drive": "1h 30m", "charges": 0},
            "stops": [_origin(), _dest()],
        }],
    }


def _minimum_trip() -> dict:
    return {
        "meta": {
            "title": "T",
            "version_label": "v1",
            "agenda_label": "Agenda v1",
            "default_plan": "Baseline",
            "storage_prefix": "demo",
        },
        "plans": [_minimum_plan()],
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_minimum_trip_validates() -> None:
    trip = Trip.model_validate(_minimum_trip())
    assert len(trip.plans) == 1
    assert trip.plans[0].key == "Baseline"
    assert trip.meta.default_plan == "Baseline"


def test_dump_uses_camelcase_aliases() -> None:
    """The renderer relies on by_alias=True to emit camelCase JSON."""
    trip = Trip.model_validate(_minimum_trip())
    dumped = trip.model_dump(by_alias=True)
    assert "versionLabel" in dumped["meta"]
    assert "storagePrefix" in dumped["meta"]
    # snake_case keys should NOT appear in the aliased dump.
    assert "version_label" not in dumped["meta"]


def test_dump_camelcase_for_stop_fields() -> None:
    """Stops carry the most fields that need aliasing; spot-check a few."""
    trip = Trip.model_validate(_minimum_trip())
    stops = trip.model_dump(by_alias=True)["plans"][0]["days"][0]["stops"]
    origin = stops[0]
    dest = stops[1]
    assert "lat" in origin and "lng" in origin
    assert "legMiles" in dest
    assert "legDrive" in dest
    # Optional fields that weren't provided dump as null.
    assert origin.get("cityHint") is None


def test_hotel_with_booking_status() -> None:
    spec = _minimum_trip()
    spec["plans"][0]["days"][0]["stops"].insert(1, {
        "type": "hotel",
        "name": "Hampton",
        "address": "1 Hotel St, City TX",
        "lat": 2.0,
        "lng": 3.0,
        "arrive": "20:00",
        "booking_status": "BOOKED",
        "conf_number": "12345",
        "plan_label": "Baseline",
        "leg_miles": 50,
        "leg_drive": "0h 45m",
    })
    trip = Trip.model_validate(spec)
    hotel = trip.plans[0].days[0].stops[1]
    assert hotel.booking_status is BookingStatus.BOOKED
    assert hotel.conf_number == "12345"


# ---------------------------------------------------------------------------
# Negative tests — these are the validations we actually care about
# ---------------------------------------------------------------------------


def test_unknown_keys_rejected() -> None:
    """extra='forbid' surfaces typos in YAML immediately."""
    bad = _minimum_trip()
    bad["meta"]["versionLable"] = "oops"  # typo
    with pytest.raises(ValidationError):
        Trip.model_validate(bad)


def test_duplicate_plan_keys_rejected() -> None:
    bad = _minimum_trip()
    bad["plans"].append(_minimum_plan())  # same key
    with pytest.raises(ValidationError) as exc:
        Trip.model_validate(bad)
    assert "duplicate plan keys" in str(exc.value)


def test_default_plan_must_exist() -> None:
    bad = _minimum_trip()
    bad["meta"]["default_plan"] = "Nope"
    with pytest.raises(ValidationError) as exc:
        Trip.model_validate(bad)
    assert "default_plan" in str(exc.value)


def test_bad_plan_key_pattern_rejected() -> None:
    bad = _minimum_trip()
    bad["plans"][0]["key"] = "has spaces"
    bad["meta"]["default_plan"] = "has spaces"
    with pytest.raises(ValidationError):
        Trip.model_validate(bad)


def test_bad_storage_prefix_rejected() -> None:
    bad = _minimum_trip()
    bad["meta"]["storage_prefix"] = "Has-Uppercase"
    with pytest.raises(ValidationError):
        Trip.model_validate(bad)


def test_empty_plans_rejected() -> None:
    bad = _minimum_trip()
    bad["plans"] = []
    with pytest.raises(ValidationError):
        Trip.model_validate(bad)


def test_empty_stops_rejected() -> None:
    bad = _minimum_trip()
    bad["plans"][0]["days"][0]["stops"] = []
    with pytest.raises(ValidationError):
        Trip.model_validate(bad)


def test_rating_bounds() -> None:
    with pytest.raises(ValidationError):
        Rating.model_validate({"stars": 6, "user": 4.0})
    with pytest.raises(ValidationError):
        Rating.model_validate({"stars": 4, "user": 6.0})


def test_stop_type_enum() -> None:
    bad = _origin()
    bad["type"] = "nope"
    with pytest.raises(ValidationError):
        Stop.model_validate(bad)


def test_booking_status_to_book_value() -> None:
    """The enum spelling matches the runtime JS comparison ('TO BOOK')."""
    assert BookingStatus.TO_BOOK.value == "TO BOOK"


# ---------------------------------------------------------------------------
# Sample-spec parity — quick sanity that the bundled sample loads cleanly.
# Loaded indirectly via the fixture.
# ---------------------------------------------------------------------------


def test_sample_spec_loads(sample_trip: Trip) -> None:
    assert sample_trip.meta.default_plan == "Baseline"
    assert {p.key for p in sample_trip.plans} == {"Baseline", "A", "B"}


def test_sample_spec_plan_day_counts(sample_trip: Trip) -> None:
    days_by_plan = {p.key: len(p.days) for p in sample_trip.plans}
    assert days_by_plan == {"Baseline": 3, "A": 4, "B": 3}
