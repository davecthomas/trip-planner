"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from trip_planner.loader import load_trip
from trip_planner.models import Trip


REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_SPEC = REPO_ROOT / "trips" / "sd_austin.yaml"


@pytest.fixture(scope="session")
def sample_spec_path() -> Path:
    """Path to the canonical SD-Austin sample spec."""
    return SAMPLE_SPEC


@pytest.fixture(scope="session")
def sample_trip(sample_spec_path: Path) -> Trip:
    """Load the sample spec once per test session."""
    return load_trip(sample_spec_path)
