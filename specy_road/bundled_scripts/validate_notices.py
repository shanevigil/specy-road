"""Non-fatal notices ``validate`` prints after the graph checks pass.

Notices go to stdout, so ``validate --strict`` does not count them as warnings.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.finish_ancestor_rollup import held_milestones, milestone_review_hold_notice


def notice_milestone_review_holds(root: Path, nodes: list[dict]) -> None:
    """One notice per milestone ``policy.milestone_full_review`` holds, with the ways out.

    Without it the only symptom of a hold was ``export --check`` / ``digest
    --check`` drift; ``upgrade`` shows these because it runs ``validate_at``.
    """
    for nid, why in held_milestones(root, nodes).items():
        print(milestone_review_hold_notice(nid, why))
