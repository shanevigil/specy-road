"""Lean changes and tests: the rule block, the role prompts, the packet note, the profile tendencies.

Source: two lean-code research reports (2026-10-27). The managed block is injected
into every adopter agent's context, so the section is pinned to its exact wording
in the template, the bootstrap prompt and the toolkit's own AGENTS.md.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tests.review_repo_helpers import git, make_review_repo
from tests.test_models_and_prompt import ROSTER, TEMPLATE_PROFILES

from specy_road.bundled_scripts import review_packet as rp
from specy_road.bundled_scripts import role_prompt
from specy_road.review_files import PACKET_NAME, reviews_dir

REPO = Path(__file__).resolve().parent.parent
BLOCK = REPO / "specy_road" / "templates" / "specyrd" / "agents-md-block.md"
PROMPT = REPO / "suggested_prompts" / "bootstrap-agents-md.md"
AGENTS = REPO / "AGENTS.md"
HEADING = "## Lean changes and tests"


def _section(text: str) -> str:
    start = text.index(HEADING)
    return text[start:text.index("\n## ", start + 1)].rstrip()


def _bullets(section: str) -> list[str]:
    return [ln[2:] for ln in section.splitlines() if ln.startswith("- ")]


def test_block_section_is_short_and_covers_the_rules() -> None:
    section = _section(BLOCK.read_text(encoding="utf-8"))
    assert len(section.splitlines()) <= 12
    text = section.lower()
    for needle in ("smallest behaviour-complete change", "search for an existing one", "validate at boundaries only",
                   "reachable trigger", "one test per observable behaviour", "mock counts", "`_`-prefixed",
                   "extend or parametrize", "distinct regression", "overrides any general",
                   "never weaken", "list every helper"):
        assert needle in text, needle


def test_bootstrap_prompt_and_toolkit_agents_md_mirror_the_block() -> None:
    bullets = _bullets(_section(BLOCK.read_text(encoding="utf-8")))
    prompt = PROMPT.read_text(encoding="utf-8")
    for b in bullets:
        assert b in prompt, b
    assert _section(AGENTS.read_text(encoding="utf-8")) == _section(BLOCK.read_text(encoding="utf-8"))


def test_principle_9_carries_the_two_test_rules() -> None:
    line = next(ln for ln in (REPO / "constitution" / "principles.md").read_text(encoding="utf-8").splitlines()
                if ln.startswith("9. "))
    assert "one test per observable behaviour" in line and "no guard without a reachable trigger" in line


def _profiled_repo(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    dest = repo / "model-profiles" / "anthropic-claude"
    dest.mkdir(parents=True)
    shutil.copy(TEMPLATE_PROFILES / "anthropic-claude" / "claude-opus-5-5.md", dest)
    git(repo, "add", "model-profiles", "roadmap/orchestration.yaml")
    git(repo, "commit", "-qm", "roster + profile")
    git(repo, "update-ref", "refs/heads/dev", "HEAD")
    return repo


def test_reviewer_prompt_carries_the_excess_checklist(tmp_path: Path) -> None:
    repo = _profiled_repo(tmp_path)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / PACKET_NAME).write_text("# Review packet: `M1.1`\n", encoding="utf-8")
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None
    for cls in ("*Test pins internals*", "*Unreachable defence*", "*Duplicated logic*", "*Overlapping test*"):
        assert cls in text, cls
    assert "If you cannot prove it, recommend no change." in text
    assert "Never recommend removing error handling without a completed caller trace." in text
    # the counter-rule from the profile's Prompting rules reaches the prompt; the tendencies do not
    assert "Name the smallest behaviour-complete change" in text
    assert "## Code and test tendencies" not in text


def test_executor_prompt_asks_for_the_added_inventory(tmp_path: Path) -> None:
    repo = _profiled_repo(tmp_path)
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")
    assert err is None
    assert "ending with an `## Added` inventory" in text and "mock and test you added" in text


def test_packet_notes_a_summary_without_an_added_inventory(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    summary = repo / "work" / "implementation-summary-M1.1.md"
    summary.parent.mkdir()
    summary.write_text("## Summary\nDid it.\n", encoding="utf-8")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert text.count(rp.NO_INVENTORY) == 1
    summary.write_text("## Summary\nDid it.\n\n## Added\n- none\n", encoding="utf-8")
    assert rp.NO_INVENTORY not in rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    summary.unlink()
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert rp.SUMMARY_MISSING in text and rp.NO_INVENTORY not in text


def test_every_profile_has_a_dated_tendency_line_and_a_counter_rule() -> None:
    from specy_road import model_profiles as mp

    profiles = mp.list_profiles(TEMPLATE_PROFILES.parent)
    measured = {"anthropic-claude", "openai-gpt", "google-gemini", "cursor-composer"}
    for p in profiles:
        lines = p.bullets("Code and test tendencies")
        assert lines, p.path.name
        assert all("2026-10-27" in ln and "not human-verified" in ln for ln in lines), p.path.name
        if p.path.parent.name in measured:
            assert not any("No measured" in ln for ln in lines), p.path.name
        else:
            assert any("No measured code-shape or test data" in ln for ln in lines), p.path.name
        assert len(p.bullets("Prompting rules")) >= 2 or p.path.parent.name not in measured, p.path.name
    readme = (TEMPLATE_PROFILES / "README.md").read_text(encoding="utf-8")
    assert "## Code and test tendencies" in readme and "2026-10-27" in readme
