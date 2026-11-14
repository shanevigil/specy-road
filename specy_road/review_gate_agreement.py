"""Deprecated import path: folded into :mod:`specy_road.review_policy_pin`.

Held the gate and policy agreement check. Kept as an alias until the release after 0.3.1, which
removes it; import the new module instead.
"""

import warnings

from specy_road.review_policy_pin import (  # noqa: F401 — the old path keeps its public names
    GATE_FIX, GATE_KEY, gate_config_mismatch, report_gate_mismatch,
)

warnings.warn("specy_road.review_gate_agreement is folded into specy_road.review_policy_pin; "
              "the old name is removed in the release after 0.3.1",
              DeprecationWarning, stacklevel=2)
