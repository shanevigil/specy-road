"""`validate --strict`: a passing validation that warned exits 1 (rc1 feedback: CI after an upgrade)."""

from __future__ import annotations

import json
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


def test_ancestor_claude_above_the_git_root_does_not_fail_strict(tmp_path: Path) -> None:
    """A CLAUDE.md above the git root is a note. Over 200 lines does not fail --strict."""
    root = tmp_path / "repo"
    root.mkdir()
    _scaffold(root)
    ancestor = tmp_path / "CLAUDE.md"
    ancestor.write_text("- rule\n" * 201, encoding="utf-8")

    r = _validate(root, "--strict")

    assert r.returncode == 0, r.stderr
    assert r.stderr == ""
    shown = ancestor.resolve().as_posix()
    assert f"{shown} 201 lines" in r.stdout and "user-level / machine-local" in r.stdout


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
    assert f"{shown} 201 lines" in r.stdout and "user-level / machine-local" in r.stdout


def test_strict_passes_a_fresh_scaffold(tmp_path: Path) -> None:
    """The scaffold's sample task carries acceptance criteria, so a new project starts clean."""
    root = _scaffold(tmp_path)

    r = _validate(root, "--strict")

    assert r.returncode == 0, r.stderr
    assert r.stderr == ""
    assert "context: Codex reads AGENTS.md " in r.stdout
    assert "context: Claude Code reads AGENTS.md " in r.stdout


def _add_placeholder_leaf(root: Path) -> None:
    """``add-node`` writes the scaffold sheet and sets no acceptance: a leaf pickup skips as unauthored."""
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "add-node", "--repo-root", str(root),
         "--id", "M1.2", "--type", "task", "--title", "Later work", "--parent-id", "M1"],
        cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def test_a_placeholder_leaf_passes_the_starter_strict_check(tmp_path: Path) -> None:
    """M11.46: planning roadmap-first leaves unauthored leaves open; the starter's validate --strict still passes."""
    root = _scaffold(tmp_path)
    _add_placeholder_leaf(root)
    starter = json.loads((root / "roadmap" / "phases" / "M1.json").read_text(encoding="utf-8"))["nodes"][1]
    assert starter["id"] == "M1.1" and "specy-road validate --strict passes" in starter["acceptance"][-1]

    r = _validate(root, "--strict")

    assert r.returncode == 0, r.stderr
    assert r.stderr == ""
    assert "notice: 1 open leaf/leaves have a placeholder planning sheet and no acceptance criteria" in r.stdout
    assert "  M1.2: planning/M1.2_" in r.stdout


def test_strict_authoring_counts_the_placeholder_leaf_again(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    _add_placeholder_leaf(root)

    r = _validate(root, "--strict-authoring")

    assert r.returncode == 1
    assert "warning: 1 open leaf/leaves have a placeholder planning sheet" in r.stderr
    assert "(M1.2) has no acceptance criteria" in r.stderr
    assert "FAILED (--strict)" in r.stderr
    assert "OK: roadmap and registry validate." in r.stdout
