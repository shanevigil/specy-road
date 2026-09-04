"""The IDE-indexing policy: what is hidden from the index, and what is not."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.agent_ignores import (
    CURSOR_INDEXING_IGNORE,
    GITIGNORE,
    INDEXING_IGNORE_LINES,
    apply_agent_ignores,
)
from specy_road.managed_block import CREATED, UNCHANGED


def test_it_writes_the_cursor_indexing_ignore_not_the_hard_one(tmp_path: Path) -> None:
    """.cursorignore would block reading and break every path search returns."""
    apply_agent_ignores(tmp_path)

    assert (tmp_path / CURSOR_INDEXING_IGNORE).is_file()
    assert not (tmp_path / ".cursorignore").exists()


def test_it_never_writes_claude_code_read_denials(tmp_path: Path) -> None:
    """Claude Code builds no index, and deny rules would break pointer-following."""
    apply_agent_ignores(tmp_path)

    settings = tmp_path / ".claude" / "settings.json"
    assert not settings.exists()


def test_the_archived_and_duplicated_corpus_is_excluded(tmp_path: Path) -> None:
    apply_agent_ignores(tmp_path)
    text = (tmp_path / CURSOR_INDEXING_IGNORE).read_text(encoding="utf-8")

    assert "roadmap/archive/" in text
    assert "work/brief-*.md" in text


def test_unique_prose_stays_indexed(tmp_path: Path) -> None:
    """Implementation summaries are the one non-duplicated record in work/."""
    assert not any("implementation-summary" in ln for ln in INDEXING_IGNORE_LINES)


def test_the_ignore_file_says_how_to_reach_what_it_hides(tmp_path: Path) -> None:
    apply_agent_ignores(tmp_path)
    text = (tmp_path / CURSOR_INDEXING_IGNORE).read_text(encoding="utf-8")

    assert "specy-road search" in text
    assert "roadmap-context.md" in text


def test_the_derived_caches_are_gitignored(tmp_path: Path) -> None:
    """Fixes an upgrade gap: init project skips a .gitignore that already exists."""
    (tmp_path / GITIGNORE).write_text("node_modules/\n", encoding="utf-8")

    apply_agent_ignores(tmp_path)
    text = (tmp_path / GITIGNORE).read_text(encoding="utf-8")

    assert ".specyrd/cache/" in text
    assert "node_modules/" in text


def test_git_actually_ignores_the_caches_afterwards(tmp_path: Path) -> None:
    """The rule is only worth writing if git honours it."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    apply_agent_ignores(tmp_path)
    cache = tmp_path / ".specyrd" / "cache"
    cache.mkdir(parents=True)
    (cache / "roadmap-history.json").write_text("{}", encoding="utf-8")

    porcelain = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert ".specyrd/cache" not in porcelain
    assert ".specyrd/manifest.json" not in porcelain  # not created, but never ignored


def test_applying_twice_reports_unchanged(tmp_path: Path) -> None:
    first = apply_agent_ignores(tmp_path)
    second = apply_agent_ignores(tmp_path)

    assert first[CURSOR_INDEXING_IGNORE] == CREATED
    assert all(outcome == UNCHANGED for outcome in second.values())


# --- nested layout ----------------------------------------------------------


def test_nested_layout_prefixes_every_entry(tmp_path: Path) -> None:
    """The shipped breakage: entries are project-relative, the file is not.

    Both ignore files land at the git root. Under a nested layout an unprefixed
    ``roadmap/archive/`` matches nothing there, so archived material stayed in
    the IDE index while appearing to be excluded.
    """
    apply_agent_ignores(tmp_path, "sr/")
    text = (tmp_path / CURSOR_INDEXING_IGNORE).read_text(encoding="utf-8")

    assert "sr/roadmap/archive/" in text
    assert "sr/work/brief-*.md" in text
    assert "sr/roadmap.md" in text
    assert "\nroadmap/archive/" not in text  # never the unprefixed form


def test_nested_layout_prefixes_the_gitignore_block_too(tmp_path: Path) -> None:
    apply_agent_ignores(tmp_path, "sr/")
    text = (tmp_path / GITIGNORE).read_text(encoding="utf-8")

    assert "sr/.specyrd/cache/" in text


def test_embedded_layout_is_byte_identical_to_before(tmp_path: Path) -> None:
    """An empty prefix must change nothing for the overwhelmingly common case."""
    other = tmp_path / "other"
    other.mkdir()
    apply_agent_ignores(tmp_path)
    apply_agent_ignores(other, "")

    assert (tmp_path / CURSOR_INDEXING_IGNORE).read_text(encoding="utf-8") == (
        other / CURSOR_INDEXING_IGNORE
    ).read_text(encoding="utf-8")


def test_a_prefixed_block_actually_matches_in_git(tmp_path: Path) -> None:
    """End-to-end: git must agree the nested archive path is ignored."""
    subprocess.run(
        ["git", "-C", str(tmp_path), "init", "-q", "-b", "main"],
        check=True,
        capture_output=True,
    )
    (tmp_path / "sr" / "roadmap" / "archive").mkdir(parents=True)
    apply_agent_ignores(tmp_path, "sr/")
    # .cursorindexingignore is not a git file, so assert through the gitignore
    # block, which uses the same prefixing path.
    (tmp_path / "sr" / ".specyrd" / "cache").mkdir(parents=True)
    (tmp_path / "sr" / ".specyrd" / "cache" / "x.json").write_text("{}")

    proc = subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "sr/.specyrd/cache/x.json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, "nested cache path should be gitignored"
