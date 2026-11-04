"""The shared-checkout rule reaches every agent entry point, in one wording.

Design note: docs/design-notes/agent-guidance-and-shared-checkouts.md. The
rules file ``.specyrd/AGENTS.md`` carries the full rule, the ``AGENTS.md`` stub
its core (the only part a Codex session is sure to read), the CLAUDE.md managed
block an import of the rules file, and the bootstrap prompt the same full rule,
so an adopter who merges the prompt's bullets by hand gets the scaffold's text.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.agent_guide_block import render_guide_lines
from specy_road.agents_md_block import render_agents_lines, render_rules

REPO = Path(__file__).resolve().parent.parent
AGENTS = render_rules()
PROMPT = REPO / "suggested_prompts" / "bootstrap-agents-md.md"

_SENTENCES = (
    "commit only with `git commit --only <paths>`",
    "switch branches in a tree another session may be using",
    "`base: <sha>`",
    "the toolkit's is the floor: stop and ask rather than relax it",
    "The opt-in tool-call guard (`specy-road session guard`) refuses these while another session is live",
)


def test_scaffold_agents_md_carries_the_full_rule() -> None:
    for s in _SENTENCES:
        assert s in AGENTS, s


def test_bootstrap_prompt_carries_the_same_rule() -> None:
    start = AGENTS.index("**Shared checkouts and other agents.**")
    rule = AGENTS[start:AGENTS.index("\n\n", start)]
    assert rule in PROMPT.read_text(encoding="utf-8")
    start = AGENTS.index("**Git in a shared tree:**")
    pointer = AGENTS[start:AGENTS.index("`https://", start)]
    assert pointer in PROMPT.read_text(encoding="utf-8")


def test_suggested_prompts_index_lists_every_kept_prompt() -> None:
    """suggested_prompts/README.md is the index; generic review prompts are gone."""
    index = PROMPT.parent / "README.md"
    text = index.read_text(encoding="utf-8")
    kept = sorted(p.name for p in PROMPT.parent.glob("*.md") if p.name != "README.md")
    assert kept == [
        "bootstrap-agents-md.md",
        "bootstrap-governance.md",
        "bootstrap-roadmap.md",
        "brainstorm-roadmap.md",
    ]
    for name in kept:
        assert f"]({name})" in text, name
    assert "docs/orchestration.md" in text


def test_claude_md_block_imports_it_and_the_agents_md_stub_keeps_its_core() -> None:
    lines = render_guide_lines("sr/")
    assert "@sr/.specyrd/AGENTS.md" in lines and "@sr/.specyrd/AGENTS.team.md" in lines
    stub = "\n".join(render_agents_lines())
    assert "other agents may be working here" in stub and "`git worktree list`" in stub
    assert "opt-in tool-call guard refuses stash, reset, branch switches and `-A`/`-a`" in stub
    assert "commit only with `git commit --only <paths>`" in stub
