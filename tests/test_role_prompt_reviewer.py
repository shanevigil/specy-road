"""M22.18: every reviewer channel asks for every required change in one pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step
from tests.review_repo_helpers import git
from tests.test_delta_review import FINDING, fix_round
from tests.test_models_and_prompt import run_main

from specy_road.bundled_scripts import review_packet, role_prompt
from specy_road.review_delegate import delegate
from specy_road.review_record_write import schema_lines

INSTRUCTION = (
    "List every required change you can find in this one review, not just the first. "
    "Before you answer, re-scan the diff for further instances of each defect class "
    "(other inputs, other call sites, other files) and for any acceptance line not fully met. "
    "A later round should find nothing you could have reported now."
)


@pytest.mark.parametrize("channel", ["delegate", "cli", "paste"])
def test_every_reviewer_channel_lists_every_required_change_once(tmp_path: Path, channel: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    if channel == "delegate":
        set_steps(repo, spec, verdict_step(repo))
        assert delegate(repo, "M1.1", "opus", sleep=lambda s: None)["outcome"] == "recorded"
    else:
        assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", channel,
                        "--repo-root", str(repo)) == 0
    text = (repo / "work" / "prompt-M1.1-reviewer-opus.md").read_text(encoding="utf-8")
    assert text.count(INSTRUCTION) == 1
    assert INSTRUCTION in "\n".join(schema_lines())


@pytest.mark.parametrize("model", ["sol", "opus"])
def test_only_the_blocker_named_by_fix_of_gets_the_fix_check(tmp_path: Path, model: str) -> None:
    repo, blocked, fix = fix_round(tmp_path)
    review_packet.main(["M1.1", "--repo-root", str(repo)])
    assert run_main(role_prompt, "M1.1", "--model", model, "--role", "reviewer", "--channel", "paste",
                    "--repo-root", str(repo)) == 0
    text = (repo / "work" / f"prompt-M1.1-reviewer-{model}.md").read_text(encoding="utf-8")
    section = text.partition("## Fix check: your block")[2].partition("\n---\n")[0]
    if model == "opus":   # the approver whose approval carries reviews nothing new
        assert not section
        return
    assert f"- correctness: {FINDING}" in section and "Add a finding only where this fix broke something" in section
    assert git(repo, "diff", f"{blocked}..{fix}") in section
