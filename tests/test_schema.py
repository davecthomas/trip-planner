"""Sanity tests for the JSON Schema export.

The `trip-planner schema` CLI subcommand serializes the Pydantic Trip model
into JSON Schema for IDE validation and LLM-assisted YAML generation. These
tests confirm:

  1. The schema is generated cleanly (no exceptions, valid JSON).
  2. The committed `schema/trip.schema.json` matches what the model would emit
     today — i.e., nobody changed `models.py` without regenerating the schema.
  3. A handful of structural invariants that LLM authors and IDE users rely on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trip_planner.models import Trip

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMITTED_SCHEMA = REPO_ROOT / "schema" / "trip.schema.json"


@pytest.fixture(scope="module")
def generated_schema() -> dict:
    """Generate the schema the way the CLI does — snake_case field names."""
    return Trip.model_json_schema(by_alias=False)


def test_generated_schema_is_valid_json(generated_schema: dict) -> None:
    # If model_json_schema returned anything non-JSON-serializable we'd crash here.
    encoded = json.dumps(generated_schema)
    assert encoded
    assert json.loads(encoded) == generated_schema


def test_top_level_required_keys(generated_schema: dict) -> None:
    required = set(generated_schema.get("required", []))
    # `meta` and `plans` are required at the top level; `vehicle` is optional.
    assert {"meta", "plans"}.issubset(required)
    assert "vehicle" not in required


def test_top_level_forbids_extras(generated_schema: dict) -> None:
    # extra="forbid" on the Pydantic Trip model surfaces as
    # additionalProperties: false in JSON Schema. The whole point is that
    # typos in YAML keys fail loudly.
    assert generated_schema.get("additionalProperties") is False


def test_stop_type_enum_is_present(generated_schema: dict) -> None:
    defs = generated_schema.get("$defs", {})
    assert "StopType" in defs, "StopType enum should be referenced from $defs"
    assert set(defs["StopType"]["enum"]) == {"origin", "charge", "meal", "hotel", "dest"}


def test_committed_schema_matches_generated(generated_schema: dict) -> None:
    """If this fails, regenerate: `poetry run trip-planner schema -o schema/trip.schema.json`.

    The committed file exists so editors (yaml-language-server) and LLMs can
    reference a stable URL without invoking Python. It must stay in sync with
    the Pydantic models or its consumers will see lies.
    """
    assert COMMITTED_SCHEMA.exists(), (
        f"missing {COMMITTED_SCHEMA} — run "
        f"`poetry run trip-planner schema -o schema/trip.schema.json`"
    )
    on_disk = json.loads(COMMITTED_SCHEMA.read_text(encoding="utf-8"))
    assert on_disk == generated_schema, (
        "committed JSON Schema is stale — regenerate with "
        "`poetry run trip-planner schema -o schema/trip.schema.json`"
    )
