"""YAML → Trip loader.

Two stages: read + parse the YAML, then validate against the Pydantic models.
Each stage maps its native exception class to a `TripPlannerError` subclass so
the CLI can present a clean message without leaking library tracebacks.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import yaml
from pydantic import ValidationError

from trip_planner.errors import SpecLoadError, SpecValidationError
from trip_planner.models import Trip

log = logging.getLogger("TripPlanner.loader")


def load_trip(path: Union[str, Path]) -> Trip:
    """Load and validate a YAML trip spec.

    Args:
        path: Path to a YAML file describing a trip.

    Returns:
        A validated `Trip` model.

    Raises:
        SpecLoadError: if the file can't be read or is malformed YAML.
        SpecValidationError: if the YAML doesn't match the schema.
    """
    p = Path(path)
    log.info("loading trip spec: %s", p)

    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecLoadError(f"could not read {p}: {exc}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SpecLoadError(f"YAML parse error in {p}: {exc}") from exc

    if not isinstance(data, dict):
        raise SpecLoadError(
            f"top-level YAML in {p} must be a mapping (got {type(data).__name__})"
        )

    # Top-level keys whose name starts with `_` are convention-only:
    # they exist solely to define YAML anchors (e.g. an `_aliases` list of
    # reusable place objects). After PyYAML resolves anchors at parse time
    # we no longer need the carrier keys, so we drop them before validation.
    for k in [k for k in data if k.startswith("_")]:
        log.debug("dropping anchor-carrier key from spec: %r", k)
        data.pop(k)

    try:
        trip = Trip.model_validate(data)
    except ValidationError as exc:
        # Re-raise as our typed exception with the pydantic message preserved.
        raise SpecValidationError(f"schema validation failed for {p}:\n{exc}") from exc

    log.info("loaded %d plan(s) from %s", len(trip.plans), p.name)
    return trip
