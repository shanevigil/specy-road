"""Deprecated import path: folded into :mod:`specy_road.review_gate_ready`.

Held the CHANGELOG reminder ``ready`` prints. Kept as an alias until the release after 0.3.1, which
removes it; import the new module instead.
"""

import warnings

from specy_road.review_gate_ready import (  # noqa: F401 — the old path keeps its public names
    missing_entry_warning,
)

warnings.warn("specy_road.changelog_check is folded into specy_road.review_gate_ready; "
              "the old name is removed in the release after 0.3.1",
              DeprecationWarning, stacklevel=2)
