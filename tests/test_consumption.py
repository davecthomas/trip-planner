"""Tests for the §3.4 AC conservation indicator."""

from __future__ import annotations

import pytest

from trip_planner.consumption import (
    IndicatorEval,
    _parse_clock,
    _parse_pct,
    evaluate_indicator,
)
from trip_planner.models import Stop, Trip, Vehicle


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "s, expected",
    [
        ("85%", 85.0),
        ("0%", 0.0),
        ("100%", 100.0),
        ("52.5%", 52.5),
        (" 60 % ", 60.0),
        ("", None),
        (None, None),
        ("nope", None),
    ],
)
def test_parse_pct(s, expected) -> None:
    assert _parse_pct(s) == expected


@pytest.mark.parametrize(
    "s, expected",
    [
        ("00:00", 0),
        ("06:45", 6 * 60 + 45),
        ("13:30", 13 * 60 + 30),
        ("23:59", 23 * 60 + 59),
        ("24:00", None),  # out of range
        ("9:05", 9 * 60 + 5),
        ("", None),
        ("nope", None),
    ],
)
def test_parse_clock(s, expected) -> None:
    assert _parse_clock(s) == expected


# ---------------------------------------------------------------------------
# Indicator evaluation
# ---------------------------------------------------------------------------


def _vehicle(**overrides) -> Vehicle:
    base = dict(
        name="Test MYP",
        usable_pack_kwh=75,
        baseline_wh_per_mi=330,
        ac_penalty_wh_per_mi=30,
        ac_window_start="10:00",
        ac_window_end="18:00",
        climb_kwh_per_1000ft=2.35,
    )
    base.update(overrides)
    return Vehicle.model_validate(base)


def _stop(**kwargs) -> Stop:
    base = {
        "type": "charge",
        "name": "Test SC",
        "address": "1 Test St, Testville",
        "lat": 32.0,
        "lng": -110.0,
    }
    base.update(kwargs)
    return Stop.model_validate(base)


def test_returns_none_for_non_charge_stop() -> None:
    current = _stop(type="origin", name="Home", address="1 A St", lat=32.0, lng=-110.0)
    next_stop = _stop(leg_miles=100)
    assert evaluate_indicator(current, next_stop, _vehicle()) is None


def test_returns_none_when_socout_missing() -> None:
    current = _stop(depart="12:00")
    next_stop = _stop(leg_miles=100)
    assert evaluate_indicator(current, next_stop, _vehicle()) is None


def test_returns_none_when_next_leg_zero() -> None:
    current = _stop(soc_out="85%", depart="12:00")
    next_stop = _stop(leg_miles=0)
    assert evaluate_indicator(current, next_stop, _vehicle()) is None


def test_silent_on_short_easy_leg() -> None:
    """Short flat AC-on leg has plenty of margin — indicator silent."""
    current = _stop(soc_out="85%", depart="12:00", elevation_ft=140)
    next_stop = _stop(leg_miles=60, elevation_ft=140)  # flat, 60 mi
    result = evaluate_indicator(current, next_stop, _vehicle())
    assert result is not None
    assert result.fires is False
    assert "above threshold" in result.reason


def test_ac_window_skipped_outside_hours() -> None:
    """Depart 07:00 → AC penalty NOT applied; arrival SoC higher."""
    current = _stop(soc_out="85%", depart="07:00", elevation_ft=50)
    next_stop = _stop(leg_miles=120, elevation_ft=50)
    result = evaluate_indicator(current, next_stop, _vehicle())
    assert result is not None
    assert result.ac_in_window is False
    # AC on and AC off project the same arrival (no AC penalty in either branch).
    assert result.ac_on_arrival_soc_pct == result.ac_off_arrival_soc_pct


def test_climb_penalty_applied_when_elevations_present() -> None:
    """Net climb of +2,000 ft over 100 mi → ~47 Wh/mi extra."""
    current = _stop(soc_out="85%", depart="07:00", elevation_ft=1000)
    next_stop = _stop(leg_miles=100, elevation_ft=3000)
    result = evaluate_indicator(current, next_stop, _vehicle())
    assert result is not None
    # base 330 + climb (~47 Wh/mi at 2,000 ft / 100 mi) → ~377 Wh/mi
    assert result.leg_consumption_ac_off_wh_per_mi == pytest.approx(330 + 47, abs=1)


def test_climb_skipped_when_either_elevation_missing() -> None:
    """Without both elevations the indicator treats the leg as flat."""
    current = _stop(soc_out="85%", depart="07:00")  # no elevation
    next_stop = _stop(leg_miles=100, elevation_ft=3000)
    result = evaluate_indicator(current, next_stop, _vehicle())
    assert result is not None
    assert result.climb_penalty_wh_per_mi == 0.0


def test_descent_does_not_credit_consumption() -> None:
    """Downhill legs should not LOWER the indicator's consumption — climb only."""
    current = _stop(soc_out="50%", depart="12:00", elevation_ft=4000)
    next_stop = _stop(leg_miles=80, elevation_ft=1500)  # 2,500 ft descent
    result = evaluate_indicator(current, next_stop, _vehicle())
    assert result is not None
    assert result.climb_penalty_wh_per_mi == 0.0


def test_known_fires_plan_b_day2_casa_grande(sample_trip: Trip) -> None:
    """Spec §3.4 expected fires: Plan B Day 2 Casa Grande SC → Willcox.

    (Plan B is the renamed v14 "Plan A" — the 4D/3N variant.)
    Arrival projections: AC on ~17–19%, AC off ~22–24% per spec.
    """
    plan_b = next(p for p in sample_trip.plans if p.key == "B")
    day2 = plan_b.days[1]
    # Find the Casa Grande charge stop. The next stop should be Willcox.
    casa_idx = next(
        i for i, s in enumerate(day2.stops) if "Casa Grande" in s.name
    )
    casa = day2.stops[casa_idx]
    next_stop = day2.stops[casa_idx + 1]
    assert "Willcox" in next_stop.name

    result = evaluate_indicator(casa, next_stop, sample_trip.vehicle)
    assert result is not None
    assert result.fires is True
    assert result.ac_in_window is True
    # Spec's expected band: AC on ~17%, AC off ~22%. Allow ±3 pp for
    # rounding in our envelope constants vs. the spec's narrative numbers.
    assert 14 <= result.ac_on_arrival_soc_pct <= 22
    assert 19 <= result.ac_off_arrival_soc_pct <= 27
    assert result.ac_off_arrival_soc_pct - result.ac_on_arrival_soc_pct >= 3


def test_no_other_charge_stop_fires(sample_trip: Trip) -> None:
    """Spec §3.4 says only Plan B Day 2 Casa Grande fires. Verify all others silent."""
    fires: list[str] = []
    for plan in sample_trip.plans:
        for d_idx, day in enumerate(plan.days):
            for s_idx, stop in enumerate(day.stops):
                if stop.type.value != "charge":
                    continue
                if s_idx + 1 >= len(day.stops):
                    continue
                result = evaluate_indicator(
                    stop, day.stops[s_idx + 1], sample_trip.vehicle
                )
                if result and result.fires:
                    fires.append(
                        f"Plan {plan.key} Day {d_idx + 1} {stop.name} → {day.stops[s_idx + 1].name}"
                    )
    assert fires == [
        "Plan B Day 2 Casa Grande Supercharger → Willcox Supercharger"
    ], fires


def test_indicator_returns_dataclass(sample_trip: Trip) -> None:
    """Sanity: the return value is the documented dataclass."""
    plan_a = next(p for p in sample_trip.plans if p.key == "A")
    day1 = plan_a.days[0]
    # First charge stop in Plan A Day 1 is El Centro.
    el_centro = day1.stops[1]
    result = evaluate_indicator(el_centro, day1.stops[2], sample_trip.vehicle)
    assert isinstance(result, IndicatorEval)
    assert hasattr(result, "fires")
    assert hasattr(result, "ac_on_arrival_soc_pct")
    assert hasattr(result, "ac_off_arrival_soc_pct")
