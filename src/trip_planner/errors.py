"""Typed exceptions raised across the trip-planner pipeline.

The CLI catches `TripPlannerError` once and turns it into a clean exit code +
message. Internal modules should raise the most specific subclass that fits so
callers can distinguish a parse failure from a schema failure from a render
failure.
"""

from __future__ import annotations


class TripPlannerError(Exception):
    """Base class for every error raised by this package."""


class SpecLoadError(TripPlannerError):
    """Raised when a YAML spec file can't be read or parsed."""


class SpecValidationError(TripPlannerError):
    """Raised when a YAML spec parses but does not match the schema."""


class RenderError(TripPlannerError):
    """Raised when the renderer can't produce or write output."""
