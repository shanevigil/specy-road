"""The baseline gate end to end: real pickup and grind-session CLIs in a disposable repo.

Each test builds a one-leaf project with a bare ``origin``, runs the command as a
user would, and checks only what a user could see afterwards: exit code, output,
the registry on the integration branch (local and pushed), and the branches.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

# The project and CLI runners live in pickup_repo_helpers; the old private names
# stay for the modules that import them from here.
from tests.pickup_repo_helpers import (  # noqa: F401 — SHEET is re-exported
    FEATURE, SHEET, make_pickup_project as _project, run_pickup as _pickup, run_specy_road as _run,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _claimed_on(root: Path, ref: str) -> bool:
    return "leaf-one" in _git(root, "show", f"{ref}:roadmap/registry.yaml")


def _branches(root: Path) -> list[str]:
    return _git(root, "branch", "--format=%(refname:short)").split()


def _assert_nothing_claimed(root: Path, main_before: str) -> None:
    assert _git(root, "rev-parse", "main") == main_before
    assert _git(root, "rev-parse", "origin/main") == main_before
    assert not _claimed_on(root, "main")
    assert FEATURE not in _branches(root)


# ---------------------------------------------------------------------------
# do-next-available-task
# ---------------------------------------------------------------------------


def test_passing_baseline_lets_the_pickup_through(tmp_path: Path) -> None:
    root = _project(tmp_path)
    r = _pickup(root, "--baseline-cmd", "true")
    assert r.returncode == 0, r.stderr
    assert "baseline on main: true" in r.stdout
    assert _git(root, "branch", "--show-current") == FEATURE
    assert _claimed_on(root, "main") and _claimed_on(root, "origin/main")


def test_failing_baseline_refuses_and_claims_nothing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _git(root, "rev-parse", "HEAD")
    r = _pickup(root, "--baseline-cmd", "exit 3")
    assert r.returncode == 1
    assert "baseline failed on 'main' (exit 3); no leaf was claimed" in r.stderr
    assert "--baseline-warn" in r.stderr
    assert _git(root, "branch", "--show-current") == "main"
    assert _git(root, "rev-parse", "HEAD") == before
    _assert_nothing_claimed(root, before)


def test_baseline_warn_picks_up_from_a_red_base(tmp_path: Path) -> None:
    root = _project(tmp_path)
    r = _pickup(root, "--baseline-cmd", "exit 3", "--baseline-warn")
    assert r.returncode == 0, r.stderr
    assert "warning: baseline failed on 'main' (exit 3); picking up anyway" in r.stderr
    assert _git(root, "branch", "--show-current") == FEATURE
    assert _claimed_on(root, "origin/main")


def test_baseline_that_commits_is_refused(tmp_path: Path) -> None:
    """The tree stays clean, but a claim pushed now would carry the new commit."""
    root = _project(tmp_path)
    before = _git(root, "rev-parse", "HEAD")
    r = _pickup(root, "--baseline-cmd", "git commit -q --allow-empty -m sneaky")
    assert r.returncode == 1
    assert f"must only check, but it moved git state: HEAD {before} -> " in r.stderr
    assert "No leaf was claimed" in r.stderr
    assert _git(root, "rev-parse", "origin/main") == before
    assert not _claimed_on(root, "HEAD")
    assert FEATURE not in _branches(root)


@pytest.mark.parametrize("cmd, moved", [
    ("git checkout -q -b elsewhere", "branch refs/heads/main -> refs/heads/elsewhere"),
    ("git checkout -q --detach", "branch refs/heads/main -> (detached)"),
    ("echo '# touched' >> roadmap/git-workflow.yaml",
     "working tree clean -> changed outside work/"),
])
def test_baseline_that_moves_git_state_is_refused_even_when_warned(
    tmp_path: Path, cmd: str, moved: str
) -> None:
    root = _project(tmp_path)
    before = _git(root, "rev-parse", "HEAD")
    r = _pickup(root, "--baseline-cmd", cmd, "--baseline-warn")
    assert r.returncode == 1
    assert f"must only check, but it moved git state: {moved}." in r.stderr
    assert _git(root, "rev-parse", "HEAD") == before
    _assert_nothing_claimed(root, before)


def test_baseline_may_write_under_work(tmp_path: Path) -> None:
    root = _project(tmp_path)
    r = _pickup(root, "--baseline-cmd", "mkdir -p work && echo ok > work/baseline.log")
    assert r.returncode == 0, r.stderr
    assert _claimed_on(root, "origin/main")


def test_git_workflow_baseline_applies_and_an_empty_flag_turns_it_off(tmp_path: Path) -> None:
    root = _project(tmp_path, "baseline_cmd: exit 4\n")
    before = _git(root, "rev-parse", "HEAD")
    r = _pickup(root)
    assert r.returncode == 1
    assert "baseline on main: exit 4" in r.stdout
    _assert_nothing_claimed(root, before)
    r = _pickup(root, "--baseline-cmd", "")
    assert r.returncode == 0, r.stderr
    assert "baseline on" not in r.stdout
    assert _claimed_on(root, "origin/main")


# ---------------------------------------------------------------------------
# grind-session --step pickup forwards the gate to its pickup
# ---------------------------------------------------------------------------


def _events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def test_grind_step_pickup_refused_by_the_baseline_exits_5(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _git(root, "rev-parse", "HEAD")
    r = _run(root, "grind-session", "--step", "pickup", "--json", "--on-complete", "merge",
             "--baseline-cmd", "exit 3")
    assert r.returncode == 5
    failed = [e for e in _events(r.stdout) if e["event"] == "hook_failed"]
    assert [(e["phase"], e["node_id"]) for e in failed] == [("pickup", "M1")]
    assert "baseline failed on 'main' (exit 3)" in r.stderr
    _assert_nothing_claimed(root, before)


def test_grind_step_pickup_with_a_passing_baseline_claims(tmp_path: Path) -> None:
    root = _project(tmp_path)
    r = _run(root, "grind-session", "--step", "pickup", "--json", "--on-complete", "merge",
             "--baseline-cmd", "true")
    assert r.returncode == 0, r.stderr
    assert [e["event"] for e in _events(r.stdout)] == ["picked"]
    assert _git(root, "branch", "--show-current") == FEATURE
    assert _claimed_on(root, "origin/main")
