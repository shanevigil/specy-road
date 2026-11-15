"""Deprecated import path: renamed to :mod:`specy_road.review_defer_rules` (the deferral rules).

Kept as an alias until the release after 0.3.1, which removes it; import the new module instead.
"""

import warnings

from specy_road.review_defer_rules import *  # noqa: F403 — the old path keeps its public names

warnings.warn("specy_road.review_deferral is renamed to specy_road.review_defer_rules; the old "
              "name is removed in the release after 0.3.1", DeprecationWarning, stacklevel=2)
