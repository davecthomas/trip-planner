"""Renderer — turn a validated Trip model into a self-contained HTML file.

The renderer's job is intentionally small: it loads the static CSS and runtime
JS, dumps the trip data as a JSON blob keyed for browser consumption (camelCase
field names), and feeds all of it into a Jinja2 template. The interactive
behavior lives in the runtime JS, not here.

Customization:
    Pass `templates_dir` to swap in an alternate template set. The directory
    must contain `trip.html.j2`, `styles.css`, and `runtime.js`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional, Union

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

from trip_planner.errors import RenderError
from trip_planner.models import Plan, Trip

log = logging.getLogger("TripPlanner.renderer")

# Files we expect inside the templates directory. The renderer surfaces a
# clean RenderError if any are missing rather than dying on a Jinja2 traceback.
_DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"
_TEMPLATE_NAME = "trip.html.j2"
_CSS_FILE = "styles.css"
_JS_FILE = "runtime.js"


class Renderer:
    """Build a single HTML file from a `Trip` model.

    A Renderer instance holds a `templates_dir` and a configured Jinja2
    environment. It is cheap to construct (no I/O until `render` is called)
    so callers can build one per request without worry.
    """

    def __init__(self, templates_dir: Optional[Path] = None) -> None:
        self.templates_dir = Path(templates_dir or _DEFAULT_TEMPLATES_DIR)
        if not self.templates_dir.is_dir():
            raise RenderError(f"templates_dir does not exist: {self.templates_dir}")

        # StrictUndefined makes typos in template variables a hard failure
        # rather than rendering blank — better for development sanity.
        self._env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=False,  # We hand-control escaping; CSS/JS must pass through verbatim.
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def render(self, trip: Trip) -> str:
        """Render a Trip into an HTML string.

        Args:
            trip: A validated `Trip` model.

        Returns:
            The complete HTML document as a string.

        Raises:
            RenderError: if a template asset is missing or rendering fails.
        """
        log.info("rendering trip: %r (%d plan(s))", trip.meta.title, len(trip.plans))

        inline_css = self._read_asset(_CSS_FILE)
        inline_js = self._read_asset(_JS_FILE)
        trip_json = self._build_trip_json(trip)

        # The HTML template accesses fields like `meta.title` and
        # `meta.version_label`, so we pass the model directly. Pydantic's
        # attribute access works inside Jinja2 templates.
        context: dict[str, Any] = {
            "meta": trip.meta,
            "plans": trip.plans,
            "inline_css": inline_css,
            "inline_js": inline_js,
            "trip_json": trip_json,
        }

        try:
            template = self._env.get_template(_TEMPLATE_NAME)
            return template.render(**context)
        except TemplateError as exc:
            raise RenderError(f"Jinja2 render failed: {exc}") from exc

    def render_to_file(self, trip: Trip, output: Union[str, Path]) -> Path:
        """Render a Trip and write it to disk.

        Args:
            trip: A validated `Trip` model.
            output: Path to write to. Parent directories are created.

        Returns:
            The absolute path of the written file.
        """
        out_path = Path(output)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RenderError(f"could not create output directory: {exc}") from exc

        html = self.render(trip)

        try:
            out_path.write_text(html, encoding="utf-8")
        except OSError as exc:
            raise RenderError(f"could not write {out_path}: {exc}") from exc

        log.info("wrote %d bytes to %s", len(html), out_path)
        return out_path.resolve()

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    def _read_asset(self, name: str) -> str:
        """Read an inline asset (CSS or JS) from the templates dir."""
        path = self.templates_dir / name
        if not path.is_file():
            raise RenderError(f"missing template asset: {path}")
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RenderError(f"could not read template asset {path}: {exc}") from exc

    def _build_trip_json(self, trip: Trip) -> str:
        """Serialize the Trip for the browser.

        - Field names switch to camelCase via the model's alias generator.
        - Enum values dump as their string values (`"BOOKED"`, `"hotel"`).
        - A computed `dayLabels` map is added so the runtime doesn't have to
          re-derive day toggle metadata at every render.

        The JSON is embedded directly in an HTML `<script>` tag, so we escape
        `</script>` and `<!--` sequences to prevent a hostile payload (or
        innocent free-text containing those substrings) from prematurely
        closing the script context.
        """
        data: dict[str, Any] = trip.model_dump(by_alias=True, mode="json")
        data["dayLabels"] = self._compute_day_labels(trip.plans)

        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        # JSON-safe in HTML: escape script-closing and HTML-comment openers.
        # The substitutions stay valid JSON because backslash-escaped
        # characters parse the same.
        encoded = encoded.replace("</", "<\\/").replace("<!--", "<\\!--")
        return encoded

    @staticmethod
    def _compute_day_labels(plans: list[Plan]) -> dict[str, list[dict[str, Any]]]:
        """Pre-compute the day toggle label objects for every plan.

        Each entry is `{n, label, sub}` where:
            - `n` is the 1-indexed day number
            - `label` is "Day N"
            - `sub` is the day's date string

        The runtime reads these directly instead of formatting at render time.
        """
        return {
            plan.key: [
                {"n": i + 1, "label": f"Day {i + 1}", "sub": day.date}
                for i, day in enumerate(plan.days)
            ]
            for plan in plans
        }
