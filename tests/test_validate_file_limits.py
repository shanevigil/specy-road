"""Tests for file limit validator."""

from __future__ import annotations

import subprocess
import sys
from tests.helpers import BUNDLED_SCRIPTS, REPO, script_subprocess_env


def test_file_limits_passes_on_repo() -> None:
    subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "validate_file_limits.py")],
        cwd=REPO,
        env=script_subprocess_env(),
        check=True,
    )


def _git(root, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo_with_an_ignored_oversize_file(tmp_path) -> None:
    _git(tmp_path, "init")
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        'max_lines_per_file: 10\napplies_to_globs:\n  - "**/*.md"\n', encoding="utf-8"
    )
    (tmp_path / ".gitignore").write_text("generated/\n", encoding="utf-8")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "big.md").write_text("x\n" * 50, encoding="utf-8")


def _run_file_limits(tmp_path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_file_limits.py"),
            "--repo-root",
            str(tmp_path),
            *extra,
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_ignored_files_are_skipped_by_default(tmp_path) -> None:
    _repo_with_an_ignored_oversize_file(tmp_path)
    r = _run_file_limits(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "generated/big.md" not in r.stderr


def test_no_respect_gitignore_flag_is_wired_up(tmp_path) -> None:
    """The documented escape hatch for repos that do want ignored files linted."""
    _repo_with_an_ignored_oversize_file(tmp_path)
    r = _run_file_limits(tmp_path, "--no-respect-gitignore")
    assert r.returncode == 1
    assert "generated/big.md" in r.stderr
