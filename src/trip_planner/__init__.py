"""Trip Planner — render a self-contained HTML itinerary from a YAML trip spec."""

from trip_planner.errors import (
    TripPlannerError,
    SpecLoadError,
    SpecValidationError,
    RenderError,
)
from trip_planner.models import Trip

__version__ = "0.1.0"

__all__ = [
    "Trip",
    "TripPlannerError",
    "SpecLoadError",
    "SpecValidationError",
    "RenderError",
    "__version__",
]
