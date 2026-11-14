"""Deprecated import path: its gate half folded into :mod:`specy_road.review_gate`.

``reviewer_eligibility`` and ``eligibility_lines`` moved to
:mod:`specy_road.bundled_scripts.review_cli`, which a package module may not import, so this alias
does not serve them. Kept until the release after 0.3.1, which removes it; import the new module
instead.
"""

import warnings

from specy_road.review_gate import (  # noqa: F401 — the old path keeps its public names
    Identity, reviews_to_judge, writers,
)

warnings.warn("specy_road.review_eligible is folded into specy_road.review_gate; "
              "the old name is removed in the release after 0.3.1",
              DeprecationWarning, stacklevel=2)
