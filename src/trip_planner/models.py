"""Pydantic models for the YAML trip specification.

Two surfaces meet here:

  - YAML / Python use snake_case (natural for both).
  - The runtime JS embedded in the rendered HTML uses camelCase keys
    (natural for JS, and matching the field names the hand-written
    sample render uses).

The models accept snake_case input and emit camelCase when dumped with
`by_alias=True`, via a per-class alias generator. The renderer uses that
path when it serializes the trip into the `<script>` tag.

Validation is strict (`extra="forbid"`) — unknown keys raise immediately,
which catches typos in the YAML file early.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

log = logging.getLogger("TripPlanner.models")


# ---------------------------------------------------------------------------
# Base config — every model in this file inherits this behavior.
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """Shared model config.

    `populate_by_name=True` lets callers pass either the snake_case Python
    name or the camelCase serialization alias on input. `extra="forbid"`
    rejects unknown keys so a typo in YAML doesn't silently swallow data.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StopType(str, Enum):
    """The shape-of-a-stop discriminator.

    Hotels and charge stops both render extended detail blocks; meal stops are
    treated like business stops for Open-in-Maps purposes but render a lighter
    card. Origin and destination are the trip endpoints — they get an address
    query rather than a name query in the URL builders.
    """

    ORIGIN = "origin"
    CHARGE = "charge"
    MEAL = "meal"
    HOTEL = "hotel"
    DEST = "dest"


class BookingStatus(str, Enum):
    """Hotel booking state. Drives the colored pill on hotel cards."""

    BOOKED = "BOOKED"
    PENDING = "PENDING"
    TO_BOOK = "TO BOOK"


# ---------------------------------------------------------------------------
# Leaf models
# ---------------------------------------------------------------------------


class Rating(_Base):
    """A simple star + user-rating pair for a hotel."""

    stars: int = Field(..., ge=1, le=5)
    user: float = Field(..., ge=0.0, le=5.0)


class Restaurant(_Base):
    """A recommended restaurant near a charge stop."""

    name: str
    cuisine: str


class DayStats(_Base):
    """Per-day totals shown in the day-head and the agenda summary."""

    miles: int = Field(..., ge=0)
    drive: str  # free-form, e.g. "6h 35m"
    charges: int = Field(..., ge=0)


class Verification(_Base):
    """The three editorial verification groups rendered at the bottom of each day view.

    The fourth group (Open in Maps Quality Audit) is computed at runtime
    from each stop's `place_id`; it is not declared in YAML.
    """

    confirmed: list[str] = Field(default_factory=list)
    estimates: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------


class Stop(_Base):
    """A single point in the day.

    Most fields are optional because their applicability depends on `type`.
    The model-level validator below enforces type-specific requirements so
    bad input fails loudly at load time rather than producing a half-broken
    render.
    """

    # Shared
    type: StopType
    name: str
    address: str
    city_hint: Optional[str] = None
    place_id: Optional[str] = None
    lat: float
    lng: float
    # Elevation in feet above sea level. Optional; when present at both
    # ends of a leg, the §3.4 AC indicator uses the delta to compute the
    # climb penalty. Legs with missing elevation on either end are treated
    # as flat for indicator purposes.
    elevation_ft: Optional[float] = Field(default=None, ge=-1000, le=15000)
    notes: Optional[str] = None

    # Leg / timing
    leg_miles: Optional[float] = Field(default=None, ge=0)
    leg_drive: Optional[str] = None
    arrive: Optional[str] = None
    depart: Optional[str] = None

    # Charge-specific
    soc_in: Optional[str] = None
    soc_out: Optional[str] = None
    charger_type: Optional[str] = None
    meal: Optional[str] = None
    restaurants: Optional[list[Restaurant]] = None

    # Hotel-specific
    rating: Optional[Rating] = None
    rate: Optional[str] = None
    phone: Optional[str] = None
    booking_status: Optional[BookingStatus] = None
    conf_number: Optional[str] = None
    plan_label: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    cancel_by: Optional[str] = None
    pet_policy: Optional[str] = None
    charger_prox: Optional[str] = None

    @model_validator(mode="after")
    def _enforce_type_requirements(self) -> "Stop":
        """Type-specific field requirements.

        These are the minimal subset that the render would otherwise
        fail to display sensibly. Stricter coupling (e.g. "every BOOKED
        hotel must have conf_number") would be too rigid for a planning
        spec that evolves over time, so we keep the contract loose.
        """
        if self.type is StopType.HOTEL and self.booking_status is None:
            log.warning("hotel stop %r missing booking_status; defaulting to PENDING", self.name)
            object.__setattr__(self, "booking_status", BookingStatus.PENDING)
        return self


# ---------------------------------------------------------------------------
# Day / Plan / Trip
# ---------------------------------------------------------------------------


class Day(_Base):
    """One leg of the trip — a date and an ordered list of stops."""

    title: str
    date: str
    stats: DayStats
    stops: list[Stop] = Field(..., min_length=1)


class Plan(_Base):
    """A plan variant. Each plan is a tab in the plan toggle."""

    key: str = Field(..., pattern=r"^[A-Za-z0-9_-]{1,16}$")
    label: str
    summary: str
    # Short human-readable hint surfaced as the plan button's sub-label —
    # e.g. "leaves Sat 5/23 AM". Helps users pick a plan without
    # remembering what the letter codes mean.
    tagline: Optional[str] = None
    days: list[Day] = Field(..., min_length=1)
    verification: Verification = Field(default_factory=Verification)


class Meta(_Base):
    """Top-of-page presentation metadata."""

    title: str
    version_label: str
    agenda_label: str
    default_plan: str
    storage_prefix: str = Field(..., pattern=r"^[a-z][a-z0-9-]{0,31}$")


class Vehicle(_Base):
    """EV vehicle profile + consumption envelope.

    All consumption parameters are explicit so the engine works for any EV,
    not just the Tesla Model Y Performance used in the bundled sample. To
    use a different vehicle, swap this block in the YAML — the runtime
    pulls every constant from here.

    The §3.4 AC conservation indicator (runtime) reads `baseline_wh_per_mi`,
    `ac_penalty_wh_per_mi`, `ac_window_start/end`, `climb_kwh_per_1000ft`,
    `usable_pack_kwh`, `ac_indicator_arrival_threshold_pct`, and
    `ac_indicator_min_improvement_pp` directly. Removing any of these
    fields means refactoring the runtime in lockstep.
    """

    # ---------------- Identity ----------------
    name: str  # Display name in headers / verification copy.
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=1990, le=2100)
    wheels: Optional[str] = None  # e.g. "21\" Überturbine"
    notes: Optional[str] = None

    # ---------------- Pack / budget ----------------
    # Usable pack capacity in kWh. For a Tesla MYP this is ~75; for a
    # base Model 3 SR it's ~50; for a Lightning ER it's ~131.
    usable_pack_kwh: float = Field(..., gt=0, le=300)
    # Minimum SoC to reserve on arrival to every charge stop, as a percent
    # of full pack (not of usable_pack_kwh). Tesla's "Set Off" target uses
    # the same convention.
    reserve_soc_pct: float = Field(default=20.0, ge=0, le=80)

    # ---------------- Consumption envelope ----------------
    # Wh/mi at planning cruise speed with payload but no AC, no climbing,
    # no headwind. The "baseline" of §3.3.
    baseline_wh_per_mi: float = Field(..., gt=0, le=1000)
    # Wh/mi added when AC is on. Spec §3.1 puts this at 25–35 Wh/mi for a
    # Tesla MYP at 69 mph in hot conditions; pick the midpoint by default.
    ac_penalty_wh_per_mi: float = Field(..., ge=0, le=200)
    # Local-time window during which AC is assumed on. Strings parsed as
    # HH:MM at runtime. Used by the §3.4 indicator to decide whether to
    # apply the AC penalty for a given upcoming leg.
    ac_window_start: str = Field(default="10:00", pattern=r"^\d{2}:\d{2}$")
    ac_window_end: str = Field(default="18:00", pattern=r"^\d{2}:\d{2}$")
    # Energy in kWh to lift the loaded vehicle 1,000 ft (after drivetrain
    # losses). Spec §3.2 derives ~2.35 for a 5,000 lb car. Scale with the
    # vehicle + payload weight.
    climb_kwh_per_1000ft: float = Field(..., gt=0, le=10)
    # Fraction of climb energy recovered on descent via regen. 0.6–0.7 is
    # typical for modern EVs in light/moderate descents; less in steep ones.
    regen_recovery: float = Field(default=0.65, ge=0.0, le=1.0)

    # ---------------- §3.4 AC indicator thresholds ----------------
    # The indicator fires when projected arrival SoC (AC on) falls below
    # this threshold AND turning AC off would meaningfully widen the
    # margin. 25% is the spec default.
    ac_indicator_arrival_threshold_pct: float = Field(default=25.0, ge=0, le=100)
    # Minimum SoC swing in percentage points between AC-on and AC-off
    # projections before the indicator surfaces. Below this, the AC-off
    # advice would be cosmetic.
    ac_indicator_min_improvement_pp: float = Field(default=3.0, ge=0, le=100)


class Trip(_Base):
    """A full trip spec. The root model of the YAML schema."""

    meta: Meta
    vehicle: Optional[Vehicle] = None
    plans: list[Plan] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _check_plan_keys_and_default(self) -> "Trip":
        keys = [p.key for p in self.plans]
        if len(set(keys)) != len(keys):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError(f"duplicate plan keys: {dupes}")
        if self.meta.default_plan not in keys:
            raise ValueError(
                f"meta.default_plan={self.meta.default_plan!r} is not a known plan key "
                f"(have: {keys})"
            )
        return self

    @field_validator("plans")
    @classmethod
    def _check_plan_minimum(cls, plans: list[Plan]) -> list[Plan]:
        # Pydantic already enforces min_length=1; this is a hook for future
        # cross-plan invariants (e.g. shared origin/dest).
        return plans
