"""Deprecated import path: folded into :mod:`specy_road.review_gate`.

Held the fresh-session and resumed-delta rules. Kept as an alias until the release after 0.3.1,
which removes it; import the new module instead.
"""

import warnings

from specy_road.review_gate import (  # noqa: F401 — the old path keeps its public names
    FRESH_SESSION, RESUMED_KEY, fresh_only_note, fresh_session_problem, resumed_delta_on,
)

warnings.warn("specy_road.review_resumed_delta is folded into specy_road.review_gate; "
              "the old name is removed in the release after 0.3.1",
              DeprecationWarning, stacklevel=2)
