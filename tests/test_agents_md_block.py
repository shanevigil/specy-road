"""The `AGENTS.md` managed block: specy-road owns a section, the project owns the file.

Design: docs/design-notes/agent-guidance-and-shared-checkouts.md, decision 3.
Mirrors tests/test_specyrd_init_guide_block.py for `CLAUDE.md`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from specy_road import __version__
from specy_road.agent_guide_block import AGENT_GUIDE
from specy_road.agents_md_block import (
    AGENTS_MD,
    CLAUDE_MD_TARGET_LINES,
    CODEX_PROJECT_DOC_MAX_BYTES,
    agents_md_block_state,
    apply_agents_md_block,
    print_injected_context,
    render_agents_lines,
    warn_if_agents_md_block_stale,
    warn_if_context_over_limits,
    warn_missing_load_order_paths,
)
from specy_road.bundled_scripts.refresh_stubs import refresh_stubs
from specy_road.init_project import run_init_project
from specy_road.managed_block import CREATED, HTML_COMMENT, UNCHANGED, UPDATED
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


def test_context_meter_reports_what_each_harness_reads(tmp_path: Path, capsys, monkeypatch) -> None:
    """Codex reads every AGENTS.md from the git root down; Claude Code reads CLAUDE.md, else those."""
    monkeypatch.setenv("HOME", str(tmp_path / "no-user-claude"))
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / AGENTS_MD).write_text(HAND_AUTHORED, encoding="utf-8")
    block = f"{HTML_COMMENT.start}\n- one rule\n{HTML_COMMENT.end}"
    (tmp_path / "sr").mkdir()
    (tmp_path / "sr" / AGENTS_MD).write_text(f"# Ours\n{block}\n", encoding="utf-8")
    size = len(block.encode("utf-8"))
    agents = (f"AGENTS.md 6 lines, {len(HAND_AUTHORED)} bytes; "
              f"sr/AGENTS.md 4 lines, {size + 8} bytes (specy-road section 3 lines, {size} bytes)")

    print_injected_context(tmp_path / "sr")
    assert capsys.readouterr().out == (
        f"context: Codex reads {agents} — {len(HAND_AUTHORED) + size + 8:,} of its 32,768-byte "
        "project_doc_max_bytes budget\n"
        f"context: Claude Code reads {agents} — target under 200 lines per file\n"
    )

    (tmp_path / AGENT_GUIDE).write_text("# Claude\n\n", encoding="utf-8")
    print_injected_context(tmp_path / "sr")
    assert capsys.readouterr().out.splitlines()[1] == (
        "context: Claude Code reads CLAUDE.md 2 lines, 10 bytes — target under 200 lines per file"
    )


def test_context_warnings_fire_only_past_a_documented_limit(tmp_path: Path, capsys) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    agents, claude = tmp_path / AGENTS_MD, tmp_path / AGENT_GUIDE
    agents.write_text("x" * (CODEX_PROJECT_DOC_MAX_BYTES - 1) + "\n", encoding="utf-8")
    claude.write_text("- rule\n" * (CLAUDE_MD_TARGET_LINES - 1), encoding="utf-8")
    warn_if_context_over_limits(tmp_path)
    assert capsys.readouterr().err == ""

    agents.write_text("x" * CODEX_PROJECT_DOC_MAX_BYTES + "\n", encoding="utf-8")
    claude.write_text("- rule\n" * CLAUDE_MD_TARGET_LINES, encoding="utf-8")
    warn_if_context_over_limits(tmp_path)
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 2
    assert err[0].startswith("context: warning — AGENTS.md total 32,769 bytes, and Codex truncates")
    assert err[1].startswith("context: warning — CLAUDE.md is 200 lines; Claude Code's documented target")


def test_dot_claude_claude_md_suppresses_the_agents_fallback(tmp_path: Path, capsys) -> None:
    """`.claude/CLAUDE.md` is a project instruction, so Claude Code reads it and not AGENTS.md."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / AGENTS_MD).write_text(HAND_AUTHORED, encoding="utf-8")
    block = f"{HTML_COMMENT.start}\n- one rule\n{HTML_COMMENT.end}"
    text = f"# Claude\n{block}\n"
    path = tmp_path / ".claude" / AGENT_GUIDE
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")

    print_injected_context(tmp_path)
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith(f"context: Codex reads AGENTS.md 6 lines, {len(HAND_AUTHORED)} bytes —")
    assert "AGENTS.md" not in out[1]
    assert out[1] == (
        f"context: Claude Code reads .claude/CLAUDE.md {text.count(chr(10))} lines, "
        f"{len(text.encode())} bytes (specy-road section 3 lines, {len(block.encode())} bytes) "
        "— target under 200 lines per file"
    )


def test_claude_walks_ancestors_and_falls_back_to_dot_claude_agents(tmp_path: Path, capsys) -> None:
    """Above the git root, CLAUDE.local.md, and .claude/AGENTS.md are launch-time files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    above = tmp_path / "CLAUDE.md"
    above.write_text("# above\n", encoding="utf-8")
    (repo / "CLAUDE.local.md").write_text("# local\n", encoding="utf-8")
    (repo / AGENTS_MD).write_text(HAND_AUTHORED, encoding="utf-8")
    (repo / ".claude").mkdir()
    (repo / ".claude" / AGENTS_MD).write_text("# nested\n", encoding="utf-8")

    print_injected_context(repo)
    out = capsys.readouterr().out
    reads = [ln for ln in out.splitlines() if ln.startswith("context: Claude Code reads ")][0]
    assert above.resolve().as_posix() not in reads
    assert "CLAUDE.local.md 1 lines" in reads
    assert "AGENTS.md" not in reads
    assert f"{above.resolve().as_posix()} 1 lines" in out and "user-level / machine-local" in out

    above.unlink()
    (repo / "CLAUDE.local.md").unlink()
    print_injected_context(repo)
    claude = capsys.readouterr().out.splitlines()[1]
    assert claude.startswith("context: Claude Code reads AGENTS.md ")
    assert ".claude/AGENTS.md 1 lines" in claude


def test_user_claude_md_under_home_is_listed_once(tmp_path: Path, monkeypatch, capsys) -> None:
    """A repo under HOME finds the user file on the ancestor walk; the report names it once."""
    monkeypatch.setenv("HOME", str(tmp_path))
    user = tmp_path / ".claude" / AGENT_GUIDE
    user.parent.mkdir()
    user.write_text("# user\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / AGENTS_MD).write_text(HAND_AUTHORED, encoding="utf-8")

    print_injected_context(repo)
    out = capsys.readouterr().out
    shown = user.resolve().as_posix()
    assert out.count(shown) == 1
    assert f"{shown} 1 lines" in out and "user-level / machine-local" in out
    reads = [ln for ln in out.splitlines() if ln.startswith("context: Claude Code reads ")][0]
    assert shown not in reads and "AGENTS.md " in reads


def test_codex_user_layer_is_a_note(tmp_path: Path, monkeypatch, capsys) -> None:
    """``~/.codex`` is reported and not metered, even when the file is past the budget."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    codex = tmp_path / "home" / ".codex"
    codex.mkdir(parents=True)
    (codex / AGENTS_MD).write_text("x" * (CODEX_PROJECT_DOC_MAX_BYTES + 1), encoding="utf-8")
    override = codex / "AGENTS.override.md"
    override.write_text("# home override\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / AGENTS_MD).write_text("# repo\n", encoding="utf-8")

    print_injected_context(repo)
    warn_if_context_over_limits(repo)
    out, err = capsys.readouterr()
    shown = override.resolve().as_posix()
    assert out.splitlines()[0].startswith("context: Codex reads AGENTS.md ")
    assert (codex / AGENTS_MD).resolve().as_posix() not in out
    assert f"{shown} 1 lines" in out and "user-level / machine-local" in out
    assert err == ""


def test_codex_meters_a_nonempty_override_instead_of_agents_md(tmp_path: Path, capsys) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    agents, override = tmp_path / AGENTS_MD, tmp_path / "AGENTS.override.md"
    agents.write_text("x" * CODEX_PROJECT_DOC_MAX_BYTES + "\n", encoding="utf-8")
    override.write_text("", encoding="utf-8")
    print_injected_context(tmp_path)
    warn_if_context_over_limits(tmp_path)
    out, err = capsys.readouterr()
    assert out.splitlines()[0].startswith("context: Codex reads AGENTS.md ")
    assert err.startswith("context: warning — AGENTS.md total")

    override.write_text("y" * CODEX_PROJECT_DOC_MAX_BYTES + "\n", encoding="utf-8")
    print_injected_context(tmp_path)
    warn_if_context_over_limits(tmp_path)
    out, err = capsys.readouterr()
    assert out.splitlines()[0].startswith("context: Codex reads AGENTS.override.md ")
    assert "AGENTS.md " not in out.splitlines()[0]
    assert err.startswith("context: warning — AGENTS.override.md total")
    assert "AGENTS.md" not in err


def test_block_text_is_the_full_rule_set() -> None:
    text = "\n".join(render_agents_lines())
    for needle in ("### Load order", "## Finding things", "**Task pickup:**", "**Review roles:**",
                   "**Running many leaves:**", "**When nothing is pickable:**"):
        assert needle in text, needle
