"""Rollup git, reconcile and the PR hint, through the public entry points."""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts import open_milestone_pr, reconcile_milestone_status
from specy_road.milestone_rollup_git import (
    cherry_pick_bookkeeping_to_integration,
    current_branch,
    merge_leaf_into_rollup,
)
from specy_road.milestone_session import milestone_session_path, write_milestone_session
from specy_road.registry_yaml import read_registry, registry_path, write_registry
from tests.milestone_repo_helpers import make_milestone_repo
from tests.review_repo_helpers import commit_file, git
from tests.scenarios.milestone.repos import (
    INTEGRATION,
    LEAF,
    PARENT,
    REMOTE,
    ROLLUP,
    bookkeeping_repo,
    landed_milestone,
    parent_node,
)


def test_cherry_pick_lands_bookkeeping_on_integration(tmp_path: Path) -> None:
    """The leaf's bookkeeping commit lands on integration and is pushed."""
    repo = bookkeeping_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", LEAF)
    write_registry(registry_path(repo), {"version": 1, "entries": []})
    git(repo, "add", "roadmap/registry.yaml")
    git(repo, "commit", "-qm", "chore(rm-alpha): complete, deregister")
    sha = git(repo, "rev-parse", "HEAD")

    ok, err = cherry_pick_bookkeeping_to_integration(
        repo,
        remote=REMOTE,
        integration_branch=INTEGRATION,
        bookkeeping_commit=sha,
        leaf_branch=LEAF,
    )

    assert ok, err
    assert current_branch(repo) == INTEGRATION
    names = {e.get("codename") for e in read_registry(registry_path(repo))["entries"]}
    assert names == set()
    assert git(repo, "rev-parse", "HEAD") == git(repo, "rev-parse", f"{REMOTE}/{INTEGRATION}")


def test_merge_leaf_into_rollup_keeps_the_leaf_and_returns_to_integration(
    tmp_path: Path,
) -> None:
    """The rollup gains a merge of the leaf, and the checkout returns to integration."""
    repo = bookkeeping_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", ROLLUP)
    commit_file(repo, "roadmap/rollup-note.txt", "rollup\n", "chore: open the rollup")
    git(repo, "push", "-q", "-u", REMOTE, ROLLUP)
    git(repo, "checkout", "-q", "-b", LEAF, INTEGRATION)
    commit_file(repo, "src/alpha.py", "print('alpha')\n", "feat(alpha): implement")
    git(repo, "checkout", "-q", INTEGRATION)

    ok, err = merge_leaf_into_rollup(
        repo,
        remote=REMOTE,
        rollup_branch=ROLLUP,
        leaf_branch=LEAF,
        integration_branch=INTEGRATION,
    )

    assert ok, err
    assert current_branch(repo) == INTEGRATION
    assert git(repo, "rev-parse", "-q", "--verify", f"{ROLLUP}^2")
    assert git(repo, "show", f"{ROLLUP}:src/alpha.py") == "print('alpha')"
    assert git(repo, "show", f"{ROLLUP}:roadmap/rollup-note.txt") == "rollup"


def test_reconcile_open_plan_promotes_when_leaves_are_complete(
    tmp_path: Path, capsys
) -> None:
    """An open plan whose leaves are done promotes to ``pending_mr`` and does not close."""
    root = landed_milestone(tmp_path, state="active")

    reconcile_milestone_status.main(["--repo-root", str(root), "--apply"])

    out = capsys.readouterr().out
    assert f"promote: {PARENT!r}" in out
    assert "close milestone" not in out
    execution = parent_node(root)["milestone_execution"]
    assert execution["state"] == "pending_mr"
    assert parent_node(root)["status"] == "Not Started"


def test_reconcile_closed_plan_completes_the_parent(tmp_path: Path, capsys) -> None:
    """A closed plan whose rollup is complete sets the parent status to Complete."""
    root = landed_milestone(tmp_path, state="closed")

    reconcile_milestone_status.main(["--repo-root", str(root), "--apply"])

    out = capsys.readouterr().out
    assert f"sync parent {PARENT!r} status -> Complete" in out
    assert parent_node(root)["status"] == "Complete"
    assert parent_node(root)["milestone_execution"]["state"] == "closed"


def test_open_milestone_pr_prints_the_rollup_command(tmp_path: Path, capsys) -> None:
    """The command prints the one ``gh pr create`` from the rollup branch to integration."""
    root = make_milestone_repo(tmp_path, land=False)
    write_milestone_session(
        milestone_session_path(root / "work"),
        parent_node_id=PARENT,
        parent_codename="milestone-two",
        integration_branch=INTEGRATION,
        remote=REMOTE,
    )

    open_milestone_pr.main(["--repo-root", str(root)])

    out = capsys.readouterr().out
    assert (
        "gh pr create --base dev --head feature/rm-milestone-two "
        "--title '[M2] Node M2'"
    ) in out
    assert "Remote: 'origin'" in out
