"""The roster as the integration branch has it: what prompts, plans and workers must route by.

The review gate reads ``roadmap/orchestration.yaml`` from the integration
branch (``review_gate.policy_source``), never from the working tree an agent
can edit without a trace. Routing has to read the same file: a working-tree
roster could widen ``may_process`` on an outside model, add a ``channels.cli``
or ``preflight`` command, or name a reviewer the gate will later refuse.
Outside git the working tree is all there is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.orchestration_config import effective_config
from specy_road.review_gate import policy_source


def pinned_config(repo_root: Path) -> tuple[dict[str, Any], str | None]:
    """``(config, error)`` from the integration branch; an unreadable branch is an error, not a fallback."""
    ref, err = policy_source(repo_root)
    if err:
        return {}, err
    return effective_config(repo_root, ref)
