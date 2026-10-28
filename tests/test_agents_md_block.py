"""The `AGENTS.md` managed block: specy-road owns a section, the project owns the file.

Design: docs/design-notes/agent-guidance-and-shared-checkouts.md, decision 3.
Mirrors tests/test_specyrd_init_guide_block.py for `CLAUDE.md`.
"""

from __future__ import annotations

from pathlib import Path

from specy_road import __version__
from specy_road.agents_md_block import (
    AGENTS_MD,
    agents_md_block_state,
    apply_agents_md_block,
    render_agents_lines,
    warn_if_agents_md_block_stale,
    warn_missing_load_order_paths,
)
from specy_road.bundled_scripts.refresh_stubs import refresh_stubs
from specy_road.init_project import run_init_project
from specy_road.managed_block import CREATED, UNCHANGED, UPDATED
from specy_road.specyrd_init import run_init

HAND_AUTHORED = """# Our agents guide

## House rules

- Ask before touching `infra/`.
- Tests live next to the code.
"""


def test_fresh_init_project_writes_agents_md_with_the_block(tmp_path: Path) -> None:
    assert run_init_project(tmp_path) == 0
    text = (tmp_path / AGENTS_MD).read_text(encoding="utf-8")
    assert text.startswith("# Agents — load order\n")
    assert "specy-road managed block" in text
    assert f"Written by specy-road {__version__}" in text
    assert "**Precedence.**" in text and "stop\nand ask a human" in text
    assert "**Shared checkouts and other agents.**" in text
    assert agents_md_block_state(tmp_path) == "current"


def test_existing_agents_md_gets_the_block_appended_not_replaced(tmp_path: Path) -> None:
    (tmp_path / AGENTS_MD).write_text(HAND_AUTHORED, encoding="utf-8")
    assert run_init_project(tmp_path) == 0
    text = (tmp_path / AGENTS_MD).read_text(encoding="utf-8")
    assert text.startswith(HAND_AUTHORED)
    assert "## House rules" in text and "specy-road managed block" in text
    assert text.count("# Agents — load order") == 0  # no scaffold H1 forced onto their file


def test_force_rewrites_only_the_block(tmp_path: Path) -> None:
    (tmp_path / AGENTS_MD).write_text(HAND_AUTHORED, encoding="utf-8")
    run_init_project(tmp_path)
    p = tmp_path / AGENTS_MD
    stale = p.read_text(encoding="utf-8").replace(f"Written by specy-road {__version__}", "Written by specy-road 0.0.1")
    p.write_text(stale, encoding="utf-8")
    assert agents_md_block_state(tmp_path) == "stale"
    assert run_init_project(tmp_path, force=True) == 0
    text = p.read_text(encoding="utf-8")
    assert text.startswith(HAND_AUTHORED) and f"Written by specy-road {__version__}" in text
    assert agents_md_block_state(tmp_path) == "current"


def test_block_is_idempotent(tmp_path: Path) -> None:
    # A missing file gets the H1 first, so the block itself reports `updated`.
    assert apply_agents_md_block(tmp_path) in (CREATED, UPDATED)
    assert apply_agents_md_block(tmp_path) == UNCHANGED
    (tmp_path / AGENTS_MD).write_text(HAND_AUTHORED, encoding="utf-8")
    assert apply_agents_md_block(tmp_path) == UPDATED
    assert apply_agents_md_block(tmp_path) == UNCHANGED


def test_dry_run_reports_without_writing(tmp_path: Path, capsys) -> None:
    assert run_init_project(tmp_path, dry_run=True) == 0
    assert "would write AGENTS.md (created)" in capsys.readouterr().out
    assert not (tmp_path / AGENTS_MD).exists()


def test_validate_warning_states(tmp_path: Path, capsys) -> None:
    warn_if_agents_md_block_stale(tmp_path)
    assert "has no specy-road section" in capsys.readouterr().err
    apply_agents_md_block(tmp_path)
    warn_if_agents_md_block_stale(tmp_path)
    assert capsys.readouterr().err == ""
    p = tmp_path / AGENTS_MD
    p.write_text(p.read_text(encoding="utf-8").replace("floor", "ceiling"), encoding="utf-8")
    warn_if_agents_md_block_stale(tmp_path)
    assert f"differs from what specy-road {__version__} writes" in capsys.readouterr().err


def test_validate_names_load_order_files_the_project_lacks(tmp_path: Path, capsys) -> None:
    """rc1: the load order sent agents to docs/supply-chain-security.md in repos that never had it."""
    run_init_project(tmp_path)
    warn_missing_load_order_paths(tmp_path)
    assert capsys.readouterr().err == ""

    (tmp_path / "docs" / "supply-chain-security.md").unlink()
    (tmp_path / "shared" / "README.md").unlink()
    warn_missing_load_order_paths(tmp_path)
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "names docs/supply-chain-security.md, shared/README.md, which do not exist" in err


def test_refresh_stubs_reapplies_the_block(tmp_path: Path) -> None:
    run_init_project(tmp_path)
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False,
             ai_commands_dir=None, write_claude_md=True)
    p = tmp_path / AGENTS_MD
    p.write_text(p.read_text(encoding="utf-8").replace("floor", "ceiling"), encoding="utf-8")
    assert agents_md_block_state(tmp_path) == "stale"
    written, _orphans = refresh_stubs(tmp_path)
    assert any(w.startswith("AGENTS.md") for w in written)
    assert agents_md_block_state(tmp_path) == "current"


def test_block_text_is_the_full_rule_set() -> None:
    text = "\n".join(render_agents_lines())
    for needle in ("### Load order", "## Finding things", "**Task pickup:**", "**Review roles:**",
                   "**Running many leaves:**", "**When nothing is pickable:**"):
        assert needle in text, needle
