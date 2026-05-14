"""Loader tests — YAML reading, anchor expansion, error mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from trip_planner.errors import SpecLoadError, SpecValidationError
from trip_planner.loader import load_trip


_MIN_SPEC = """
meta:
  title: T
  version_label: v1
  agenda_label: Agenda v1
  default_plan: Baseline
  storage_prefix: demo
plans:
  - key: Baseline
    label: Baseline · 1D
    summary: demo
    days:
      - title: A → B
        date: Sat 1/1
        stats: { miles: 100, drive: "1h 30m", charges: 0 }
        stops:
          - { type: origin, name: H, address: "1 A St", lat: 1.0, lng: 2.0, depart: "06:45" }
          - { type: dest,   name: G, address: "1 B St", lat: 3.0, lng: 4.0,
              arrive: "15:00", leg_miles: 100, leg_drive: "1h 30m" }
"""


def test_load_minimum_spec(tmp_path: Path) -> None:
    p = tmp_path / "trip.yaml"
    p.write_text(_MIN_SPEC, encoding="utf-8")
    trip = load_trip(p)
    assert trip.meta.title == "T"
    assert trip.plans[0].key == "Baseline"


def test_missing_file_raises_load_error(tmp_path: Path) -> None:
    with pytest.raises(SpecLoadError):
        load_trip(tmp_path / "nope.yaml")


def test_malformed_yaml_raises_load_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("{: not valid yaml :", encoding="utf-8")
    with pytest.raises(SpecLoadError):
        load_trip(p)


def test_top_level_not_mapping_raises_load_error(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(SpecLoadError):
        load_trip(p)


def test_validation_error_mapped_to_typed_exception(tmp_path: Path) -> None:
    spec = _MIN_SPEC.replace("default_plan: Baseline", "default_plan: Nope")
    p = tmp_path / "bad.yaml"
    p.write_text(spec, encoding="utf-8")
    with pytest.raises(SpecValidationError):
        load_trip(p)


def test_alias_carrier_keys_are_dropped(tmp_path: Path) -> None:
    """Top-level keys starting with `_` exist solely to host YAML anchors."""
    spec = """
_aliases:
  - &origin
    name: Home
    address: 1 Origin St, A CA
    lat: 1.0
    lng: 2.0
""" + _MIN_SPEC
    p = tmp_path / "aliased.yaml"
    p.write_text(spec, encoding="utf-8")
    trip = load_trip(p)
    assert trip.plans[0].key == "Baseline"


def test_anchor_merge_expands_into_stops(tmp_path: Path) -> None:
    """A reusable anchor merged into a stop should yield a fully-formed stop."""
    spec = """
_aliases:
  - &dest_anchor
    name: Goal
    address: 1 B St
    lat: 3.0
    lng: 4.0
meta:
  title: T
  version_label: v1
  agenda_label: Agenda v1
  default_plan: Baseline
  storage_prefix: demo
plans:
  - key: Baseline
    label: B · 1D
    summary: demo
    days:
      - title: A → B
        date: Sat 1/1
        stats: { miles: 100, drive: "1h 30m", charges: 0 }
        stops:
          - { type: origin, name: H, address: "1 A St", lat: 1.0, lng: 2.0, depart: "06:45" }
          - <<: *dest_anchor
            type: dest
            arrive: "15:00"
            leg_miles: 100
            leg_drive: "1h 30m"
"""
    p = tmp_path / "anchored.yaml"
    p.write_text(spec, encoding="utf-8")
    trip = load_trip(p)
    dest = trip.plans[0].days[0].stops[1]
    assert dest.name == "Goal"
    assert dest.address == "1 B St"
    assert dest.lat == 3.0
