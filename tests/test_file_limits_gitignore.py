"""file-limits skips git-ignored files and the toolkit's own work/ artifacts.

Both cases report violations nobody can act on: an ignored file never reaches
CI, and a session artifact is machine-written and regenerated every cycle.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from specy_road.file_limits_engine import (
    collect_tracked_files,
    git_ignored_paths,
    run_file_limits_scan,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _init_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "a@b.c")
    _git(root, "config", "user.name", "t")


def _write(root: Path, rel: str, lines: int) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x\n" * lines, encoding="utf-8")


def _scan(root: Path, cfg: dict, **kwargs) -> tuple[bool, str]:
    err = io.StringIO()
    failed = run_file_limits_scan(root, cfg, err=err, **kwargs)
    return failed, err.getvalue()


def test_git_ignored_paths_empty_outside_a_repo(tmp_path: Path) -> None:
    assert git_ignored_paths(tmp_path, ["a.md"]) == frozenset()


def test_ignored_file_is_not_scanned(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    _write(tmp_path, "build/generated.md", 900)
    cfg = {"max_lines_per_file": 400, "applies_to_globs": ["**/*.md"]}

    failed, out = _scan(tmp_path, cfg)
    assert failed is False
    assert "build/generated.md" not in out

    failed, out = _scan(tmp_path, cfg, respect_gitignore=False)
    assert failed is True
    assert "build/generated.md" in out


def test_tracked_file_is_scanned_even_when_a_rule_matches(tmp_path: Path) -> None:
    """git check-ignore consults the index, so tracking wins over the rule."""
    _init_repo(tmp_path)
    _write(tmp_path, "docs/long.md", 900)
    _git(tmp_path, "add", "-f", "docs/long.md")
    _git(tmp_path, "commit", "-m", "add")
    (tmp_path / ".gitignore").write_text("docs/long.md\n", encoding="utf-8")

    failed, out = _scan(tmp_path, {"max_lines_per_file": 400, "applies_to_globs": ["**/*.md"]})
    assert failed is True
    assert "docs/long.md" in out


def test_session_artifacts_are_exempt_even_when_tracked(tmp_path: Path) -> None:
    """Covers repos scaffolded before work/pr-body-*.md was gitignored."""
    _init_repo(tmp_path)
    _write(tmp_path, "work/pr-body-M1.1.md", 3500)
    _write(tmp_path, "work/brief-M1.1.md", 900)
    _write(tmp_path, "docs/real.md", 900)
    _git(tmp_path, "add", "-f", "work", "docs")
    _git(tmp_path, "commit", "-m", "add")

    failed, out = _scan(tmp_path, {"max_lines_per_file": 400, "applies_to_globs": ["**/*.md"]})
    assert failed is True
    assert "work/pr-body-M1.1.md" not in out
    assert "work/brief-M1.1.md" not in out
    assert "docs/real.md" in out


def test_collect_tracked_files_drops_ignored_paths(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("skip/\n", encoding="utf-8")
    _write(tmp_path, "skip/a.md", 1)
    _write(tmp_path, "keep/b.md", 1)
    cfg = {"applies_to_globs": ["**/*.md"]}

    kept = {p.relative_to(tmp_path).as_posix() for p in collect_tracked_files(tmp_path, cfg)}
    assert kept == {"keep/b.md"}

    both = collect_tracked_files(tmp_path, cfg, respect_gitignore=False)
    assert {p.relative_to(tmp_path).as_posix() for p in both} == {"keep/b.md", "skip/a.md"}
