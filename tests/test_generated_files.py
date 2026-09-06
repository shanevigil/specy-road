"""roadmap.md and roadmap-context.md are generated AND committed.

An adopter who gitignores one of them sees a clean local checkout while a fresh
clone and CI see the file missing. ``git check-ignore`` alone stays silent once
the file is tracked, so the detection here passes ``--no-index`` on purpose.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.generated_files import (
    GENERATED_COMMITTED,
    ignored_generated_files,
    unstageable_generated_files,
    warn_if_generated_files_ignored,
)
from tests.test_history_walk import commit, git, repo  # noqa: F401 - fixture

__all__ = ["repo"]


def test_both_generated_files_are_named() -> None:
    assert set(GENERATED_COMMITTED) == {"roadmap.md", "roadmap-context.md"}


def test_a_clean_repo_reports_nothing(repo: Path) -> None:  # noqa: F811
    assert ignored_generated_files(repo) == []


def test_outside_a_git_worktree_it_stays_silent(tmp_path: Path) -> None:
    assert ignored_generated_files(tmp_path) == []


def test_a_tracked_but_ignored_digest_is_reported(repo: Path) -> None:  # noqa: F811
    (repo / ".gitignore").write_text("roadmap-context.md\n", encoding="utf-8")
    git(repo, "add", "-f", ".gitignore", "roadmap-context.md")
    commit(repo, "gitignore the digest anyway")

    assert ignored_generated_files(repo) == ["roadmap-context.md"]


def test_the_warning_names_the_file_and_the_fix(repo: Path, capsys) -> None:  # noqa: F811
    (repo / ".gitignore").write_text("roadmap-context.md\n", encoding="utf-8")

    warn_if_generated_files_ignored(repo)

    err = capsys.readouterr().err
    assert "roadmap-context.md" in err
    assert "generated AND committed" in err
    assert "specy-road digest" in err
    assert "git add -f roadmap-context.md" in err


def test_a_clean_repo_warns_about_nothing(repo: Path, capsys) -> None:  # noqa: F811
    warn_if_generated_files_ignored(repo)

    assert capsys.readouterr().err == ""


def test_validate_surfaces_the_warning(repo: Path, capsys) -> None:  # noqa: F811
    (repo / ".gitignore").write_text("roadmap.md\n", encoding="utf-8")

    validate_at(repo)  # a warning, never a failure

    err = capsys.readouterr().err
    assert "roadmap.md is matched by .gitignore" in err
    assert "specy-road export" in err


def test_a_tracked_but_ignored_file_is_warned_about_but_still_stageable(
    repo: Path,  # noqa: F811
) -> None:
    """`git add` accepts a tracked ignored path; only untracked ones abort it."""
    (repo / ".gitignore").write_text("roadmap-context.md\n", encoding="utf-8")
    git(repo, "add", "-f", ".gitignore", "roadmap-context.md")
    commit(repo, "gitignore the digest anyway")

    assert ignored_generated_files(repo) == ["roadmap-context.md"]
    assert unstageable_generated_files(repo) == []


def test_an_untracked_ignored_file_is_the_one_git_add_refuses(
    repo: Path,  # noqa: F811
) -> None:
    (repo / ".gitignore").write_text("roadmap-context.md\n", encoding="utf-8")
    (repo / "roadmap-context.md").unlink()
    git(repo, "rm", "-q", "--cached", "roadmap-context.md")
    commit(repo, "stop tracking the digest")
    (repo / "roadmap-context.md").write_text("regenerated\n", encoding="utf-8")

    assert unstageable_generated_files(repo) == ["roadmap-context.md"]


def test_outside_a_worktree_nothing_is_unstageable(tmp_path: Path) -> None:
    assert unstageable_generated_files(tmp_path) == []
