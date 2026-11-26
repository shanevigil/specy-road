"""Deprecated import path: folded into :mod:`specy_road.review_override`.

Held the bookkeeping carry. Kept as an alias until the release after 0.3.1, which removes it;
import the new module instead.
"""

import warnings

from specy_road.review_override import (  # noqa: F401 — the old path keeps its public names
    CARRY_NOTE, count_at_later_commit, heads_problem, only_planning_or_review_bookkeeping_since,
    policy_line, review_commit,
)

warnings.warn("specy_road.review_bookkeeping is folded into specy_road.review_override; "
              "the old name is removed in the release after 0.3.1",
              DeprecationWarning, stacklevel=2)
