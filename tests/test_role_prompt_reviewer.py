"""M22.18: every reviewer channel asks for every required change in one pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step
from tests.test_models_and_prompt import run_main

from specy_road.bundled_scripts import role_prompt
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
