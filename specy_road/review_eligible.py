"""Deprecated import path: its gate half folded into :mod:`specy_road.review_gate`.

Serves ``Identity``, ``writers`` and ``reviews_to_judge`` until the release after 0.3.1, which
removes it; import :mod:`specy_road.review_gate` instead.

``reviewer_eligibility`` and ``eligibility_lines`` moved into the ``review`` CLI entry point,
:mod:`specy_road.bundled_scripts.review_cli`, and this path does not serve them: a package module
never imports a CLI entry point, statically or by name at run time. Import them from the CLI module.
"""

import warnings

from specy_road.review_gate import (  # noqa: F401 — the old path keeps its gate names
    Identity, reviews_to_judge, writers,
)

warnings.warn("specy_road.review_eligible is folded into specy_road.review_gate; "
              "the old name is removed in the release after 0.3.1",
              DeprecationWarning, stacklevel=2)
