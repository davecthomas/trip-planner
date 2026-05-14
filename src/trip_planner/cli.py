"""Click-based command-line interface.

Subcommands:
    render        Render a trip spec to an HTML file.
    validate      Validate a trip spec without rendering.
    full-trip-url Print the Google Maps URL for an entire plan.

Every command:
    - Catches `TripPlannerError` and exits with a non-zero code + clean message.
    - Reraises other exceptions only when `--verbose` is set, so users see a
      one-line failure summary by default and a full traceback when debugging.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable, NoReturn

import click

from trip_planner import __version__
from trip_planner.errors import TripPlannerError
from trip_planner.loader import load_trip
from trip_planner.logging_config import configure as configure_logging
from trip_planner.maps import full_trip_url
from trip_planner.renderer import Renderer

log = logging.getLogger("TripPlanner.cli")


def _die(msg: str, code: int = 1) -> NoReturn:
    """Print an error and exit. Goes to stderr to keep stdout clean for pipes."""
    click.echo(f"error: {msg}", err=True)
    raise SystemExit(code)


def _wrap(action: Callable[[], None], *, verbose: bool, on_error_code: int = 1) -> None:
    """Run `action`, mapping our typed exceptions to clean CLI failures.

    Other exceptions re-raise (so verbose mode shows a traceback) unless
    verbose=False, in which case we still surface a short message.
    """
    try:
        action()
    except TripPlannerError as exc:
        _die(str(exc), code=on_error_code)
    except Exception as exc:  # noqa: BLE001 — final safety net
        if verbose:
            raise
        _die(f"unexpected: {exc.__class__.__name__}: {exc}", code=2)


# ---------------------------------------------------------------------------
# Click app
# ---------------------------------------------------------------------------


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="trip-planner")
@click.option("--verbose", "-v", is_flag=True, help="Enable DEBUG logging and tracebacks.")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Render self-contained HTML itineraries from YAML trip specs."""
    configure_logging(verbose=verbose)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@main.command()
@click.argument("spec", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--output", "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("build") / "trip.html",
    show_default=True,
    help="Where to write the rendered HTML.",
)
@click.option(
    "--templates-dir",
    type=click.Path(file_okay=False, exists=True, path_type=Path),
    default=None,
    help="Override the default templates directory.",
)
@click.pass_context
def render(
    ctx: click.Context,
    spec: Path,
    output: Path,
    templates_dir: Path,
) -> None:
    """Render SPEC (a YAML trip spec) to an HTML file."""

    def _do() -> None:
        trip = load_trip(spec)
        renderer = Renderer(templates_dir=templates_dir)
        out = renderer.render_to_file(trip, output)
        click.echo(f"wrote {out}")

    _wrap(_do, verbose=ctx.obj["verbose"])


@main.command()
@click.argument("spec", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def validate(ctx: click.Context, spec: Path) -> None:
    """Validate SPEC against the schema without rendering."""

    def _do() -> None:
        trip = load_trip(spec)
        n_stops = sum(len(d.stops) for p in trip.plans for d in p.days)
        click.echo(
            f"ok: {spec} — {len(trip.plans)} plan(s), "
            f"{sum(len(p.days) for p in trip.plans)} day(s), "
            f"{n_stops} stop(s)"
        )

    _wrap(_do, verbose=ctx.obj["verbose"])


@main.command("full-trip-url")
@click.argument("spec", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--plan", "plan_key", required=True, help="Plan key (e.g. Baseline, A, B).")
@click.pass_context
def full_trip_url_cmd(ctx: click.Context, spec: Path, plan_key: str) -> None:
    """Print the Google Maps full-trip URL for PLAN."""

    def _do() -> None:
        trip = load_trip(spec)
        match = next((p for p in trip.plans if p.key == plan_key), None)
        if match is None:
            keys = ", ".join(p.key for p in trip.plans)
            _die(f"plan {plan_key!r} not found in spec (have: {keys})")
        click.echo(full_trip_url(match))

    _wrap(_do, verbose=ctx.obj["verbose"])


# Entry point referenced from pyproject.toml `[tool.poetry.scripts]`.
if __name__ == "__main__":
    main()
