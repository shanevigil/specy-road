"""A repo for ``orchestrate plan``: a four-model roster, its shipped profiles and one leaf."""

from __future__ import annotations

import shutil
from pathlib import Path

from tests.review_repo_helpers import git, make_review_repo
from tests.support.profiles import TEMPLATE_PROFILES

from specy_road.orchestration import orchestrate_plan as op

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - id: opus
    family: anthropic
    profile: model-profiles/anthropic-claude/claude-opus-5-5.md
    roles: [coordinator, executor, reviewer]
    class: senior
    subagent_family_lock: anthropic
  - id: sol
    family: openai
    profile: model-profiles/openai-gpt/gpt-6.1-sol.md
    roles: [executor, reviewer]
  - id: flash
    family: google
    profile: model-profiles/google-gemini/gemini-3.8-flash.md
    roles: [executor]
    may_process: [public, internal]
  - id: local
    family: local
    roles: [executor]
    may_process: [public, internal, restricted]
    preflight: "true"
policy: {reviewers_required: 2, reviewers_distinct_families: true}
"""


def plan_repo(
    tmp_path: Path, roster: str = ROSTER, node_extra: str = "", *, ready: bool = True
) -> Path:
    """``ready``: free the leaf (no claim, Not Started) so the planner sees it.

    ``prompt`` needs the opposite — a claimed leaf with its branch — so the
    enforcement tests pass ``ready=False`` and keep the helper's claim.
    """
    repo = make_review_repo(tmp_path, orchestration=roster)
    for rel in (
        "anthropic-claude/claude-opus-5-5.md",
        "openai-gpt/gpt-6.1-sol.md",
        "google-gemini/gemini-3.8-flash.md",
    ):
        dest = repo / "model-profiles" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(TEMPLATE_PROFILES / rel, dest)
    git(repo, "checkout", "-q", "dev")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    text = chunk.read_text()
    if ready:
        (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
        text = text.replace('"status": "In Progress"', '"status": "Not Started"')
    if node_extra:
        text = text.replace('"id": "M1.1",', f'"id": "M1.1", {node_extra},')
    chunk.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "ready" if ready else "claimed")
    return repo


def only_assignment(plan: op.OrchestrationPlan) -> op.Assignment:
    """The plan's one assignment; fails the test when there is not exactly one."""
    assert len(plan.batches) == 1 and len(plan.batches[0]) == 1
    return plan.batches[0][0]
