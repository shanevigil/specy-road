"""Every harness's shipped brainstorm skill makes `brainstorm start` the next tool call, alone (M21.33, CR5).

Composer 2.5 read "not even in the same step as this skill" as the turn and
grepped `roadmap/` in parallel with reading the skill. The rendered copy each
harness loads names the tool call and the parallel case instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.specyrd_init import run_init

SKILL = Path(".agents/skills/specyrd-brainstorm/SKILL.md")
RULE = (
    "After reading this skill, make `specy-road brainstorm start` your next tool call, alone in its "
    "tool-call batch, with no parallel read or search (not roadmap-context.md, roadmap/, planning/ or "
    "anything else); after it returns, read the prompt file it names and continue."
)


@pytest.mark.parametrize("agent", ["claude-code", "codex", "cursor"])
def test_shipped_skill_makes_start_the_next_tool_call_alone(tmp_path: Path, agent: str) -> None:
    run_init(target=tmp_path, agent=agent, dry_run=False, force=False, ai_commands_dir=None)
    skill = tmp_path / SKILL
    text = skill.read_text(encoding="utf-8")
    front, body = text.split("\n---\n", 1)
    desc = front.split("description:", 1)[1].strip().strip('"')
    assert RULE in desc
    assert len(desc) <= 1024
    first_paragraph = " ".join(body.strip().split("\n\n", 1)[0].split())
    assert RULE in first_paragraph
    assert "What you read before round 1 anchors every idea in it." in first_paragraph
    assert "same step" not in text
    if agent == "claude-code":
        assert (tmp_path / ".claude/skills/specyrd-brainstorm/SKILL.md").resolve() == skill.resolve()
