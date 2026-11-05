"""The context meter counts every file Cursor and Copilot inject, not only Codex's and Claude Code's.

Cursor reads AGENTS.md, CLAUDE.md and its always-applied `.cursor/rules`; Copilot
reads AGENTS.md, `.claude/CLAUDE.md` and `.github/copilot-instructions.md`
(docs/design-notes/harness-compatibility-triage.md, finding 6).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.agent_guide_block import AGENT_GUIDE
from specy_road.agents_md_block import AGENTS_MD, injected_context, print_injected_context

ALWAYS = "---\ndescription: house rule\nalwaysApply: true\n---\n\n- Always do this.\n"
SCOPED = "---\ndescription: only for tests\nglobs: tests/**\nalwaysApply: false\n---\n\n- Scoped.\n"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "no-home"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / AGENTS_MD).write_text("# Agents\n", encoding="utf-8")
    return root


def _write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


def _rels(root: Path, harness: str) -> list[str]:
    return [f.rel for f in injected_context(root)[harness]]


def test_cursor_reads_agents_claude_and_only_always_applied_rules(repo: Path) -> None:
    _write(repo, AGENT_GUIDE, "# Claude\n")
    _write(repo, ".cursor/rules/010-house.mdc", ALWAYS)
    _write(repo, ".cursor/rules/nested/020-house.md", ALWAYS)
    _write(repo, ".cursor/rules/030-tests.mdc", SCOPED)
    _write(repo, ".cursor/rules/040-no-frontmatter.mdc", "alwaysApply: true\n")
    _write(repo, ".cursor/rules/050-inline-comment.mdc", "---\nalwaysApply: true # all sessions\n---\nRule body\n")
    _write(repo, ".cursor/rules/060-yaml-true.mdc", "---\nalwaysApply: True\n---\nRule body\n")
    _write(repo, ".cursor/rules/070-quoted.mdc", "---\nalwaysApply: \"true\"\n---\nRule body\n")
    _write(repo, ".cursor/rules/080-unparsable.mdc", "---\nalwaysApply: true\ndescription: [unclosed\n---\nRule body\n")
    assert _rels(repo, "Cursor") == [AGENTS_MD, AGENT_GUIDE, ".cursor/rules/010-house.mdc",
                                     ".cursor/rules/050-inline-comment.mdc", ".cursor/rules/060-yaml-true.mdc",
                                     ".cursor/rules/nested/020-house.md"]


def test_cursor_walks_from_the_git_root_to_a_nested_project(repo: Path) -> None:
    _write(repo, "sr/AGENTS.md", "# Ours\n")
    _write(repo, "sr/.cursor/rules/house.mdc", ALWAYS)
    assert _rels(repo / "sr", "Cursor") == [AGENTS_MD, "sr/AGENTS.md", "sr/.cursor/rules/house.mdc"]


def test_copilot_reads_agents_dot_claude_and_its_repo_instructions(repo: Path) -> None:
    _write(repo, AGENT_GUIDE, "# Claude (not Copilot's)\n")
    _write(repo, ".claude/CLAUDE.md", "# Claude\n")
    _write(repo, ".github/copilot-instructions.md", "# Copilot\n- rule\n")
    _write(repo, "sr/AGENTS.md", "# Ours\n")
    _write(repo, "mid/AGENTS.md", "# not on the path\n")
    assert _rels(repo, "Copilot") == [AGENTS_MD, ".claude/CLAUDE.md", ".github/copilot-instructions.md"]
    assert _rels(repo / "sr", "Copilot") == [AGENTS_MD, ".claude/CLAUDE.md", "sr/AGENTS.md",
                                             ".github/copilot-instructions.md"]


def test_report_prints_one_line_per_harness_and_never_warns(repo: Path, capsys) -> None:
    _write(repo, ".github/copilot-instructions.md", "x" * 40_000 + "\n")
    print_injected_context(repo)
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert [ln.split(" reads ")[0] for ln in lines] == [
        "context: Codex", "context: Claude Code", "context: Cursor", "context: Copilot"]
    assert lines[2] == ("context: Cursor reads AGENTS.md 1 lines, 9 bytes — no documented limit; "
                        "total 1 lines, 9 bytes per session")
    assert lines[3].endswith("— no documented limit; total 2 lines, 40,010 bytes per session")
    assert err == ""


def test_claude_code_counts_what_claude_md_imports_and_notes_the_rest(repo: Path, capsys) -> None:
    """`@path` imports load with the file (relative to it, nested), except in code; the personal addendum is a note."""
    home = repo.parent / "no-home"
    _write(home, "notes.md", "# my notes\n")
    _write(repo, AGENT_GUIDE, "# Claude\n@sr/.specyrd/AGENTS.md\n`@sr/fenced.md` is a mention\n```\n@sr/fenced.md\n```\n"
                              "@sr/.specyrd/AGENTS.local.md and @missing.md, mail me@sr/fenced.md\n@~/notes.md\n")
    _write(repo, "sr/.specyrd/AGENTS.md", "# rules\n@AGENTS.team.md\n")
    _write(repo, "sr/.specyrd/AGENTS.team.md", "# team\n")
    _write(repo, "sr/.specyrd/AGENTS.local.md", "# mine\n")
    _write(repo, "sr/fenced.md", "# not imported\n")

    assert _rels(repo / "sr", "Claude Code") == [AGENT_GUIDE, "sr/.specyrd/AGENTS.md", "sr/.specyrd/AGENTS.team.md"]
    assert _rels(repo / "sr", "Codex") == [AGENTS_MD]
    print_injected_context(repo / "sr")
    out = capsys.readouterr().out
    assert ("context: note — sr/.specyrd/AGENTS.local.md 1 lines, 7 bytes, personal and gitignored; "
            "machine-local, not counted toward this repository's limit") in out
    assert (f"context: note — {(home / 'notes.md').resolve().as_posix()} 1 lines, 11 bytes, imported by a "
            "Claude Code file; machine-local") in out
    (repo / "sr/.specyrd/AGENTS.md").write_bytes(b"\xff@AGENTS.team.md\n")   # unreadable: counted, imports nothing
    assert _rels(repo / "sr", "Claude Code") == [AGENT_GUIDE, "sr/.specyrd/AGENTS.md"]


@pytest.mark.parametrize("example", [
    "```\n@example.md\n```\n",
    "```md\n~~~text\n@example.md\n~~~\n```\n",          # another fence character inside does not close it
    "````\n```\n@example.md\n```\n````\n",            # a shorter run inside does not close it
    "```\n@example.md\n``` not a closer\n```\n",       # a closer has nothing after the run
    "1.  Example:\n\n    ```md\n    @example.md\n    ```\n\n2.  ",   # fences indented in a list item; @after.md is item 2
], ids=["plain", "other-character-inside", "shorter-run-inside", "text-after-run", "list-indented"])
def test_an_import_inside_a_fenced_example_is_not_counted(repo: Path, example: str) -> None:
    """CommonMark fences: only the opener's character, at least as long, with nothing after it, closes one."""
    _write(repo, AGENT_GUIDE, f"# Claude\n{example}@after.md\n")
    _write(repo, "example.md", "# example\n")
    _write(repo, "after.md", "# after\n")
    assert _rels(repo, "Claude Code") == [AGENT_GUIDE, "after.md"]
