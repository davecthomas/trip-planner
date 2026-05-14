"""Logging setup for the CLI.

Tiny module by design — we want a single, predictable formatter for everything
under the `TripPlanner.*` namespace. Library users can ignore this entirely
and configure logging however they want.
"""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s — %(message)s"
_DATEFMT = "%H:%M:%S"


def configure(verbose: bool = False) -> None:
    """Configure stdlib logging for CLI use.

    Args:
        verbose: when True, sets root level to DEBUG (otherwise INFO).
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))

    root = logging.getLogger("TripPlanner")
    root.setLevel(level)
    # Replace any existing handlers so repeat-configures don't double up.
    root.handlers = [handler]
    root.propagate = False
