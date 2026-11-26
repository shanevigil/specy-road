"""``do-next-available-task --worktree``: claim from the main checkout, work in a linked worktree.

M11.53. The claim is registered and pushed on the integration branch in the main
checkout, and the leaf's branch goes into ``work/.worktrees/<codename>`` by
``git worktree add``, so no worktree ever holds the integration branch or pushes.
A pushing pickup run inside a linked worktree is refused with the way out.
"""

from __future__ import annotations

from pathlib import Path

from tests.support.extracted.baseline_gate_cli import (
    assert_nothing_claimed,
    branches,
    claimed_on,
    git,
)
from tests.support.pickup import FEATURE, make_pickup_project as project, run_pickup as pickup


def _linked(root: Path, tmp_path: Path) -> Path:
    wt = tmp_path / "lane"
    git(root, "worktree", "add", "-q", "-b", "lane", str(wt))
    return wt


def test_worktree_pickup_claims_on_the_remote_and_leaves_the_main_checkout_alone(tmp_path: Path) -> None:
    root = project(tmp_path)
    r = pickup(root, "--worktree")
    assert r.returncode == 0, r.stderr
    assert git(root, "branch", "--show-current") == "main"
    assert claimed_on(root, "main") and claimed_on(root, "origin/main")
    assert git(root, "rev-parse", "main") == git(root, "ls-remote", "origin", "refs/heads/main").split()[0]
    wt = root / "work" / ".worktrees" / "leaf-one"
    assert git(wt, "branch", "--show-current") == FEATURE
    assert Path(git(wt, "rev-parse", "--show-toplevel")).resolve() == wt.resolve()
    assert (wt / "work" / "brief-M1.md").is_file()
    assert not (root / "work" / "brief-M1.md").exists()   # moved, not copied: finish removes only the worktree's
    assert (wt / "work" / ".on-complete-M1.yaml").is_file()
    assert f"worktree: {wt}" in r.stdout


def test_worktree_pickup_refuses_an_existing_directory_before_claiming(tmp_path: Path) -> None:
    root = project(tmp_path)
    main_before = git(root, "rev-parse", "main")
    (root / "work" / ".worktrees" / "leaf-one").mkdir(parents=True)
    r = pickup(root, "--worktree")
    assert r.returncode != 0
    assert "already exists" in r.stderr
    assert_nothing_claimed(root, main_before)


def test_pickup_inside_a_linked_worktree_names_worktree_from_the_main_checkout(tmp_path: Path) -> None:
    root = project(tmp_path)
    main_before = git(root, "rev-parse", "main")
    wt = _linked(root, tmp_path)
    for extra in ((), ("--worktree",)):
        r = pickup(wt, *extra)
        assert r.returncode != 0
        assert "linked worktree" in r.stderr
        assert "--worktree` from the main checkout" in r.stderr and "--local" in r.stderr
    assert_nothing_claimed(root, main_before)
    assert branches(root) == ["lane", "main"]


def test_local_pickup_inside_a_linked_worktree_is_not_refused_as_a_worktree(tmp_path: Path) -> None:
    root = project(tmp_path)
    wt = _linked(root, tmp_path)
    r = pickup(wt, "--local")
    assert "linked worktree" not in r.stderr
    assert "expected integration branch" in r.stderr   # the usual branch check, unchanged
