"""Deprecated import path: folded into :mod:`specy_road.review_gate`.

Held the strong-review rules. Kept as an alias until the release after 0.3.1, which removes it;
import the new module instead.
"""

import warnings

from specy_road.review_gate import (  # noqa: F401 — the old path keeps its public names
    applicable_items, human_closes_strong, item_label, strong_problem, touch_zones,
    unmet_strong, zones_meet,
)

warnings.warn("specy_road.review_strong is folded into specy_road.review_gate; "
              "the old name is removed in the release after 0.3.1",
              DeprecationWarning, stacklevel=2)
