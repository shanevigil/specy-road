"""The context meter counts Claude rules, notes auto memory and Cursor's nested AGENTS.md, and counts
Copilot's path-specific instructions; a Claude file over 4 MiB is reported as never loaded.

Sources: code.claude.com/docs/en/memory, the Cursor CLI changelog 2026.10.22 and the
Copilot CLI release 1.0.100 (2026-11-02 harness-capabilities research).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from specy_road.agent_guide_block import AGENT_GUIDE
from specy_road.agents_md_block import (
    AGENTS_MD,
    injected_context,
    print_injected_context,
    warn_if_context_over_limits,
)
from specy_road.harness_instruction_files import CLAUDE_MAX_FILE_BYTES, claude_memory_loaded

SCOPED = "---\npaths:\n  - \"src/**/*.py\"\n---\n\n- Only for src.\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return home


@pytest.fixture
def repo(tmp_path: Path, home: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / AGENTS_MD).write_text("# Agents\n", encoding="utf-8")
    return root


def _write(root: Path, rel: str, text: str) -> Path:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")
    return root / rel


def _rels(root: Path, harness: str) -> list[str]:
    return [f.rel for f in injected_context(root)[harness]]


def _memory(home: Path, checkout: Path, text: str) -> Path:
    project = re.sub(r"[^A-Za-z0-9]", "-", checkout.resolve().as_posix())
    return _write(home, f".claude/projects/{project}/memory/MEMORY.md", text)


def test_claude_counts_rules_recursively_beside_the_claude_md_family(repo: Path, capsys) -> None:
    _write(repo, AGENT_GUIDE, "# Claude\n")
    _write(repo, ".claude/rules/style.md", "- Style.\n")
    _write(repo, ".claude/rules/sub/deep.md", "- Deep.\n")
    _write(repo, ".claude/rules/scoped.md", SCOPED)
    _write(repo, ".claude/rules/notes.txt", "not a rule\n")
    _write(repo, "sr/.claude/rules/ours.md", "- Ours.\n")
    assert _rels(repo, "Claude Code") == [AGENT_GUIDE, ".claude/rules/style.md", ".claude/rules/sub/deep.md"]
    assert _rels(repo / "sr", "Claude Code") == [AGENT_GUIDE, ".claude/rules/style.md",
                                                 ".claude/rules/sub/deep.md", "sr/.claude/rules/ours.md"]
    external = _write(repo.parent, "external.md", "- outside\n" * 201)
    (repo / ".claude/rules/linked.md").symlink_to(external)
    assert _rels(repo, "Claude Code") == [AGENT_GUIDE, ".claude/rules/style.md", ".claude/rules/sub/deep.md"]
    warn_if_context_over_limits(repo)
    assert capsys.readouterr().err == ""
    print_injected_context(repo)
    out = capsys.readouterr().out.splitlines()
    assert "linked.md" not in next(ln for ln in out if ln.startswith("context: Claude Code reads"))
    assert (f"context: note — .claude/rules/linked.md 201 lines, {external.stat().st_size:,} bytes, "
            "user-level / machine-local; not counted toward this repository's limit") in out


def test_auto_memory_is_a_machine_local_note_shared_by_worktrees(repo: Path, home: Path, capsys) -> None:
    facts = [f"- fact {i}\n" for i in range(300)]
    memory = _memory(home, repo, "".join(facts))
    print_injected_context(repo)
    out = capsys.readouterr().out
    note = [ln for ln in out.splitlines() if "MEMORY.md" in ln]
    assert note == [f"context: note — {memory.resolve().as_posix()} 300 lines, {memory.stat().st_size:,} bytes, "
                    "Claude Code auto memory: it loads the first 200 lines or 25 KB "
                    f"(200 lines, {len(''.join(facts[:200])):,} bytes here); "
                    "machine-local, not counted toward this repository's limit"]
    assert "MEMORY.md" not in out.split("context: Claude Code reads")[1].splitlines()[0]
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    subprocess.run([*git, "worktree", "add", "-q", str(repo.parent / "wt")], check=True)
    print_injected_context(repo.parent / "wt")
    assert memory.resolve().as_posix() in capsys.readouterr().out


def test_auto_memory_load_stops_at_25_kb_before_200_lines(tmp_path: Path) -> None:
    path = _write(tmp_path, "MEMORY.md", ("x" * 499 + "\n") * 100)
    assert claude_memory_loaded(path) == (50, 25_000)


def test_cursor_notes_nested_agents_md_below_the_root(repo: Path, capsys) -> None:
    _write(repo, "sr/AGENTS.md", "# Ours\n")
    _write(repo, "pkg/AGENTS.md", "# Package\n- rule\n")
    _write(repo, "pkg/deep/AGENTS.md", "# Deep\n")
    _write(repo, ".gitignore", "ignored/\n")
    _write(repo, "ignored/AGENTS.md", "# never applied\n")
    assert _rels(repo / "sr", "Cursor") == [AGENTS_MD, "sr/AGENTS.md"]
    print_injected_context(repo / "sr")
    out = capsys.readouterr().out
    assert ("context: note — Cursor also applies pkg/AGENTS.md 2 lines, 17 bytes; pkg/deep/AGENTS.md 1 lines, "
            "7 bytes when the agent edits a file below it; not counted per session") in out.splitlines()


def test_copilot_counts_its_path_specific_instructions(repo: Path) -> None:
    _write(repo, ".github/copilot-instructions.md", "# Copilot\n")
    _write(repo, ".github/instructions/python.instructions.md", "---\napplyTo: \"**/*.py\"\n---\n- Py.\n")
    _write(repo, ".github/instructions/web/ts.instructions.md", "- TS.\n")
    _write(repo, ".github/instructions/README.md", "# not an instructions file\n")
    assert _rels(repo, "Copilot") == [AGENTS_MD, ".github/copilot-instructions.md",
                                      ".github/instructions/python.instructions.md",
                                      ".github/instructions/web/ts.instructions.md"]


def test_claude_file_over_4_mib_is_reported_not_loaded_never_counted(repo: Path, home: Path, capsys) -> None:
    _write(repo, AGENT_GUIDE, "x" * (CLAUDE_MAX_FILE_BYTES + 1))
    _write(repo, ".claude/rules/at-cap.md", "x" * CLAUDE_MAX_FILE_BYTES)
    _write(home, f".claude/{AGENT_GUIDE}", "y" * (CLAUDE_MAX_FILE_BYTES + 1))
    _write(repo, "CLAUDE.local.md", "@big.md\n")   # an import too large to load: skipped, and its own imports unread
    _write(repo, "big.md", "@child.md\n" + "x" * CLAUDE_MAX_FILE_BYTES)
    _write(repo, "child.md", "# never loaded\n")
    assert _rels(repo, "Claude Code") == ["CLAUDE.local.md", ".claude/rules/at-cap.md"]
    warn_if_context_over_limits(repo)
    err = capsys.readouterr().err
    assert f"context: warning — big.md is {CLAUDE_MAX_FILE_BYTES + 10:,} bytes, over Claude Code's 4 MiB" in err
    assert (f"context: warning — {AGENT_GUIDE} is {CLAUDE_MAX_FILE_BYTES + 1:,} bytes, over Claude Code's 4 MiB "
            "limit, so Claude Code loads none of it; its sessions here never see it.") in err
    assert ".claude/rules/at-cap.md is" not in err
    print_injected_context(repo)
    out = capsys.readouterr().out
    user = (home / ".claude" / AGENT_GUIDE).resolve().as_posix()
    assert (f"context: note — {user} is {CLAUDE_MAX_FILE_BYTES + 1:,} bytes, over Claude Code's 4 MiB limit, "
            "so Claude Code loads none of it; machine-local, not counted") in out.splitlines()
    assert "user-level" not in out
