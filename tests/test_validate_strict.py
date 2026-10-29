"""`validate --strict`: a passing validation that warned exits 1 (rc1 feedback: CI after an upgrade)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.init_project import run_init_project
from tests.helpers import REPO, script_subprocess_env


def _validate(root: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "validate", "--repo-root", str(root), *args],
        cwd=REPO, env=env or script_subprocess_env(), capture_output=True, text=True,
    )


def _scaffold(root: Path) -> Path:
    """A fresh scaffold validates quietly."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert run_init_project(root) == 0
    return root


def _clear_acceptance(root: Path) -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "edit-node", "M1.1", "--repo-root", str(root),
         "--set", "acceptance="],
        cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def _overlong_claude_md(root: Path) -> None:
    (root / "CLAUDE.md").write_text("- rule\n" * 201, encoding="utf-8")


@pytest.mark.parametrize(("spoil", "warning"), [
    (_clear_acceptance, "has no acceptance criteria"),
    (_overlong_claude_md, "CLAUDE.md is 201 lines; Claude Code's documented target is under 200"),
])
def test_strict_fails_a_validation_that_warned(tmp_path: Path, spoil, warning: str) -> None:
    root = _scaffold(tmp_path)
    spoil(root)

    assert _validate(root).returncode == 0
    r = _validate(root, "--strict")

    assert r.returncode == 1
    assert warning in r.stderr
    assert "FAILED (--strict)" in r.stderr
    assert "OK: roadmap and registry validate." in r.stdout


def test_strict_warns_when_an_ancestor_claude_file_hits_200_lines(tmp_path: Path) -> None:
    """A CLAUDE.md above the git root is injected; 199 lines is under the target, 200 is not."""
    root = tmp_path / "repo"
    root.mkdir()
    _scaffold(root)
    ancestor = tmp_path / "CLAUDE.md"
    ancestor.write_text("- rule\n" * 199, encoding="utf-8")
    assert _validate(root, "--strict").returncode == 0

    ancestor.write_text("- rule\n" * 200, encoding="utf-8")
    r = _validate(root, "--strict")
    assert r.returncode == 1
    assert f"{ancestor.resolve().as_posix()} is 200 lines" in r.stderr


def test_user_claude_outside_home_is_noted_and_does_not_fail_strict(tmp_path: Path) -> None:
    """The user file is reported for a repo that is not under HOME, and 201 lines of it is not a warning."""
    home, root = tmp_path / "home", tmp_path / "repo"
    root.mkdir()
    _scaffold(root)
    user = home / ".claude" / "CLAUDE.md"
    user.parent.mkdir(parents=True)
    user.write_text("- rule\n" * 201, encoding="utf-8")
    env = script_subprocess_env()
    env["HOME"] = str(home)

    r = _validate(root, "--strict", env=env)

    assert r.returncode == 0, r.stderr
    assert r.stderr == ""
    shown = user.resolve().as_posix()
    assert r.stdout.count(shown) == 1
    assert f"{shown} 201 lines" in r.stdout and "user-level (this machine)" in r.stdout


def test_strict_passes_a_fresh_scaffold(tmp_path: Path) -> None:
    """The scaffold's sample task carries acceptance criteria, so a new project starts clean."""
    root = _scaffold(tmp_path)

    r = _validate(root, "--strict")

    assert r.returncode == 0, r.stderr
    assert r.stderr == ""
    assert "context: Codex reads AGENTS.md " in r.stdout
    assert "context: Claude Code reads AGENTS.md " in r.stdout
