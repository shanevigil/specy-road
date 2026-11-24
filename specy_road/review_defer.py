"""Deprecated import path: renamed to :mod:`specy_road.review_defer_cli` (``review defer``).

Kept as an alias until the release after 0.3.1, which removes it; import the new module instead.
"""

import warnings

from specy_road.review_defer_cli import *  # noqa: F403 — the old path keeps its public names

warnings.warn("specy_road.review_defer is renamed to specy_road.review_defer_cli; the old name is "
              "removed in the release after 0.3.1", DeprecationWarning, stacklevel=2)
