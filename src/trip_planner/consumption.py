"""Consumption envelope + §3.4 AC conservation indicator.

This module is the Python mirror of the §3.4 trigger logic that runs in
the browser. Two reasons it lives here in addition to the runtime JS:

1. **Testability.** Pure Python with deterministic math is easy to assert
   against the spec's "expected fires" table — one fixture, one trip,
   one row of pass/fail per charge stop.
2. **Reusability.** The CLI (and downstream callers) can compute the same
   indicator status without spinning up a browser — useful for offline
   reports, CI checks, or simple "should this plan need an AC-OFF leg?"
   inspections.

The JS implementation in `templates/runtime.js` follows the same algorithm.
If you change behavior here, update the JS in the same edit so they don't
drift.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from trip_planner.models import Stop, StopType, Vehicle

log = logging.getLogger("TripPlanner.consumption")

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*%$")


# ---------------------------------------------------------------------------
# Small parse helpers — SoC values and clock times in the spec are strings.
# ---------------------------------------------------------------------------


def _parse_pct(s: Optional[str]) -> Optional[float]:
    """Parse "85%" → 85.0. Returns None for None/empty/invalid input."""
    if not s:
        return None
    m = _PCT_RE.match(s.strip())
    return float(m.group(1)) if m else None


def _parse_clock(s: Optional[str]) -> Optional[int]:
    """Parse "13:45" → minutes-since-midnight (825). None for invalid."""
    if not s:
        return None
    m = _TIME_RE.match(s.strip())
    if not m:
        return None
    h, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mm <= 59):
        return None
    return h * 60 + mm


def _in_window(clock: Optional[int], start: int, end: int) -> bool:
    """True iff `clock` (minutes-since-midnight) falls in [start, end).

    Caller passes the start of the leg in minutes; this returns whether
    that moment is inside the configured AC window. The window does not
    wrap past midnight (the spec's 10:00–18:00 is daytime only).
    """
    return clock is not None and start <= clock < end


# ---------------------------------------------------------------------------
# Indicator evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorEval:
    """Result of evaluating the §3.4 indicator for one charge stop.

    Attributes:
        fires: True iff both trigger conditions are satisfied
            (AC-on projection below threshold AND AC-off improvement
            meets the minimum percentage-point swing).
        ac_on_arrival_soc_pct: projected arrival SoC with AC on.
        ac_off_arrival_soc_pct: projected arrival SoC with AC off.
        leg_consumption_ac_on_wh_per_mi: total Wh/mi with AC on.
        leg_consumption_ac_off_wh_per_mi: total Wh/mi with AC off.
        climb_penalty_wh_per_mi: per-mile elevation penalty (>=0).
        ac_in_window: whether the leg start time falls in the AC window.
        reason: short human-readable explanation when `fires` is False;
            empty string when it fires.

    Returns None from `evaluate_indicator` when the trigger can't be
    computed at all (missing socOut, no next stop, etc.).
    """

    fires: bool
    ac_on_arrival_soc_pct: float
    ac_off_arrival_soc_pct: float
    leg_consumption_ac_on_wh_per_mi: float
    leg_consumption_ac_off_wh_per_mi: float
    climb_penalty_wh_per_mi: float
    ac_in_window: bool
    reason: str


def evaluate_indicator(
    current: Stop, next_stop: Stop, vehicle: Vehicle
) -> Optional[IndicatorEval]:
    """Evaluate the §3.4 trigger for one charge stop and its outbound leg.

    Args:
        current: The stop the car is parked at (a `charge` stop). Provides
            outbound SoC.
        next_stop: The very next stop in the day's sequence. Provides
            `leg_miles`, `depart` time (the moment the car leaves
            `current`, which is in fact stored on `current.depart` —
            but for symmetry with the spec's "next-leg departure time"
            wording, we accept either `next_stop.depart` or
            `current.depart`).
        vehicle: The vehicle envelope.

    Returns:
        An `IndicatorEval` describing the result, or None if we lack the
        data needed to compute it (e.g., `current.socOut` is missing).
    """
    if current.type is not StopType.CHARGE:
        return None
    if next_stop.type is StopType.ORIGIN:
        # An origin doesn't follow a charge stop in any well-formed day.
        return None
    if next_stop.leg_miles is None or next_stop.leg_miles <= 0:
        return None

    soc_out = _parse_pct(current.soc_out)
    if soc_out is None:
        return None

    # AC window check. "Departure time" of the upcoming leg in the spec
    # is the moment the car leaves the charge stop, which the YAML records
    # as `current.depart`. Fall back to the next stop's `arrive` − epsilon
    # if depart is missing (shouldn't happen, but defensive).
    depart_clock = _parse_clock(current.depart)
    win_start = _parse_clock(vehicle.ac_window_start) or 600  # 10:00 default
    win_end = _parse_clock(vehicle.ac_window_end) or 1080  # 18:00 default
    ac_in_window = _in_window(depart_clock, win_start, win_end)

    # Elevation penalty per mile. Climb only — descent is treated as 0 for
    # the AC indicator (the descent recovery is small relative to climb
    # cost on the legs that matter, and the indicator is about avoiding
    # arrival-SoC shortfall, not credit on descents).
    climb_penalty_wh_per_mi = 0.0
    if current.elevation_ft is not None and next_stop.elevation_ft is not None:
        net_climb_ft = next_stop.elevation_ft - current.elevation_ft
        if net_climb_ft > 0:
            climb_kwh = (net_climb_ft / 1000.0) * vehicle.climb_kwh_per_1000ft
            climb_wh = climb_kwh * 1000.0
            climb_penalty_wh_per_mi = climb_wh / next_stop.leg_miles

    # Per-mile Wh under each AC scenario.
    base = vehicle.baseline_wh_per_mi + climb_penalty_wh_per_mi
    ac_pen = vehicle.ac_penalty_wh_per_mi if ac_in_window else 0.0
    wh_per_mi_ac_on = base + ac_pen
    wh_per_mi_ac_off = base

    # Convert to SoC percentage points consumed on the leg.
    leg_kwh_on = wh_per_mi_ac_on * next_stop.leg_miles / 1000.0
    leg_kwh_off = wh_per_mi_ac_off * next_stop.leg_miles / 1000.0
    pp_on = (leg_kwh_on / vehicle.usable_pack_kwh) * 100.0
    pp_off = (leg_kwh_off / vehicle.usable_pack_kwh) * 100.0

    arrival_on = soc_out - pp_on
    arrival_off = soc_out - pp_off

    threshold = vehicle.ac_indicator_arrival_threshold_pct
    improvement_floor = vehicle.ac_indicator_min_improvement_pp
    improvement = arrival_off - arrival_on

    if arrival_on >= threshold:
        reason = f"projected arrival ({arrival_on:.0f}%) above threshold ({threshold:.0f}%)"
        fires = False
    elif improvement < improvement_floor:
        reason = (
            f"AC-off improvement ({improvement:.1f}pp) below floor "
            f"({improvement_floor:.1f}pp)"
        )
        fires = False
    else:
        reason = ""
        fires = True

    return IndicatorEval(
        fires=fires,
        ac_on_arrival_soc_pct=arrival_on,
        ac_off_arrival_soc_pct=arrival_off,
        leg_consumption_ac_on_wh_per_mi=wh_per_mi_ac_on,
        leg_consumption_ac_off_wh_per_mi=wh_per_mi_ac_off,
        climb_penalty_wh_per_mi=climb_penalty_wh_per_mi,
        ac_in_window=ac_in_window,
        reason=reason,
    )
