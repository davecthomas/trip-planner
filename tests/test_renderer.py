"""Renderer tests — smoke-level checks that the output contains the right pieces."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from trip_planner.errors import RenderError
from trip_planner.models import Trip
from trip_planner.renderer import Renderer


@pytest.fixture(scope="module")
def rendered(sample_trip: Trip) -> str:
    """Render the sample trip once and reuse across assertions."""
    return Renderer().render(sample_trip)


def test_output_starts_with_doctype(rendered: str) -> None:
    assert rendered.lstrip().startswith("<!doctype html>")


def test_title_includes_version_label(rendered: str) -> None:
    assert "<title>San Diego → Austin · v14 · Tesla MYP · 69 mph</title>" in rendered


def test_brand_and_meta_appear(rendered: str) -> None:
    assert ">San Diego → Austin<" in rendered
    assert ">v14 · Tesla MYP · 69 mph<" in rendered


def test_plan_buttons_emitted(rendered: str) -> None:
    for key in ("Baseline", "A", "B"):
        assert f'data-plan="{key}"' in rendered


def test_inline_css_embedded(rendered: str) -> None:
    # A handful of sentinel selectors that prove the static CSS made it in.
    for marker in (
        ".stop-card",
        ".booking-pill.booked",
        ".verification .group.audit",
        "header.sticky",
    ):
        assert marker in rendered, f"missing CSS sentinel: {marker}"


def test_inline_js_embedded(rendered: str) -> None:
    for marker in (
        "buildFullTripMapsUrl",
        "buildDayMapsUrl",
        "encodeStopsAsMapsPath",
        "renderDayView",
        "renderAgendaView",
        "placeQuality",
    ):
        assert marker in rendered, f"missing JS function: {marker}"


def test_trip_json_payload_is_parseable_and_camelcase(rendered: str) -> None:
    """Extract the JSON blob from `window.__TRIP__ = …;` and parse it."""
    m = re.search(r"window\.__TRIP__\s*=\s*(\{.*?\});", rendered, flags=re.DOTALL)
    assert m, "could not locate the trip JSON payload"
    payload = json.loads(m.group(1))

    # camelCase aliases
    assert "versionLabel" in payload["meta"]
    assert "storagePrefix" in payload["meta"]
    # dayLabels was added by the renderer
    assert "dayLabels" in payload
    assert set(payload["dayLabels"].keys()) == {"Baseline", "A", "B"}
    # Spot-check one stop's camelCase fields
    first_stop = payload["plans"][0]["days"][0]["stops"][0]
    assert "cityHint" in first_stop  # value may be None for the origin, but the key exists


def test_trip_json_escapes_script_close_sequence(sample_trip: Trip) -> None:
    """Free-text that happens to contain `</` must not break out of the script tag."""
    spec = sample_trip.model_dump()
    spec["plans"][0]["verification"]["confirmed"].append("attack vector: </script><b>boom</b>")
    rebuilt = Trip.model_validate(spec)
    out = Renderer().render(rebuilt)
    # The literal "</script>" must NOT appear inside the JSON payload region.
    payload = re.search(r"window\.__TRIP__\s*=\s*(\{.*?\});", out, flags=re.DOTALL).group(1)
    assert "</script>" not in payload
    assert "<\\/script>" in payload


def test_render_to_file_writes_output(sample_trip: Trip, tmp_path: Path) -> None:
    out = tmp_path / "sub" / "trip.html"
    path = Renderer().render_to_file(sample_trip, out)
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_render_missing_templates_dir() -> None:
    with pytest.raises(RenderError):
        Renderer(templates_dir=Path("/nonexistent/templates"))


def test_render_to_file_creates_parent_dir(sample_trip: Trip, tmp_path: Path) -> None:
    out = tmp_path / "deep" / "nest" / "out.html"
    Renderer().render_to_file(sample_trip, out)
    assert out.is_file()


def test_day_labels_match_plan_day_counts(sample_trip: Trip) -> None:
    """The renderer pre-computes dayLabels to match each plan's days."""
    out = Renderer().render(sample_trip)
    payload = json.loads(
        re.search(r"window\.__TRIP__\s*=\s*(\{.*?\});", out, flags=re.DOTALL).group(1)
    )
    for plan in sample_trip.plans:
        assert len(payload["dayLabels"][plan.key]) == len(plan.days)
