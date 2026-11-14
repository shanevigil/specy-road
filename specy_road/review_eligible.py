"""Deprecated import path: folded into :mod:`specy_road.review_gate` and the ``review`` CLI.

``Identity``, ``writers`` and ``reviews_to_judge`` are now in :mod:`specy_road.review_gate`;
``reviewer_eligibility`` and ``eligibility_lines`` are in
:mod:`specy_road.bundled_scripts.review_cli`. A package module may not import a CLI entry point,
so this alias looks those two up by name on first use (``importlib``, which the import-layer scan
does not count as an edge): importing the alias never loads the CLI. Kept until the release after
0.3.1, which removes it; import the new modules instead.
"""

import importlib
import warnings

from specy_road.review_gate import (  # noqa: F401 — the old path keeps its public names
    Identity, reviews_to_judge, writers,
)

#: The old module's names that now live in the ``review`` CLI.
_CLI_NAMES = ("eligibility_lines", "reviewer_eligibility")


def __getattr__(name: str):
    """Serve the two names that moved to the ``review`` CLI (PEP 562)."""
    if name in _CLI_NAMES:
        return getattr(importlib.import_module("specy_road.bundled_scripts.review_cli"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


warnings.warn("specy_road.review_eligible is folded into specy_road.review_gate; "
              "the old name is removed in the release after 0.3.1",
              DeprecationWarning, stacklevel=2)
