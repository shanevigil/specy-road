"""The shared-checkout rule reaches every agent entry point, in one wording.

Design note: docs/design-notes/agent-guidance-and-shared-checkouts.md. The
scaffold AGENTS.md carries the full rule, the CLAUDE.md managed block a pointer
to it, and the bootstrap prompt the same full rule, so an adopter who merges
the prompt's bullets by hand gets the text the scaffold would have given them.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.agent_guide_block import render_guide_lines

REPO = Path(__file__).resolve().parent.parent
AGENTS = REPO / "specy_road" / "templates" / "specyrd" / "agents-md-block.md"
PROMPT = REPO / "suggested_prompts" / "bootstrap-agents-md.md"

_SENTENCES = (
    "Commit by explicit path (`git add <paths>`); never `git add -A` or `git commit -a`.",
    "switch branches in a tree another session may be using",
    "`base: <sha>`",
    "the toolkit's is the floor: stop and ask rather than relax it",
)


def test_scaffold_agents_md_carries_the_full_rule() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    for s in _SENTENCES:
        assert s in text, s


def test_bootstrap_prompt_carries_the_same_rule() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    start = agents.index("**Shared checkouts and other agents.**")
    rule = agents[start:agents.index("\n\n", start)]
    assert rule in PROMPT.read_text(encoding="utf-8")


def test_claude_md_block_points_at_it() -> None:
    text = "\n".join(render_guide_lines("sr/"))
    assert "Other agents share this checkout" in text
    assert "never\n  `-A`/`-a`" in text
    assert "Full rule in `sr/AGENTS.md`" in text
