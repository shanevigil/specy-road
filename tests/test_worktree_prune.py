"""M11.31: ``specy-road worktree prune <ID>`` removes a leaf's worktree only when nothing in it would be lost.

The fixture is the one-leaf pickup project (``M1``, ``leaf-one``) with its
worktree at ``work/.worktrees/leaf-one`` on ``feature/rm-leaf-one``. Landing it
merges the branch into ``main`` and pushes. The nested-repo cases add the M11.22
repositories: ``src/engine`` (covered, on the leaf's branch) and ``lib``
(detached), as linked worktrees, or ``lib`` as a full clone of the main
checkout's copy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.pickup_repo_helpers import FEATURE, make_pickup_project, run_specy_road
from tests.review_repo_helpers import commit_file, git
from tests.test_nested_repo_worktrees import COVERED, UNCOVERED, add_nested_repo

from specy_road.nested_repos import add_nested_worktrees
from specy_road.worktree_prune import PruneError, plan_prune, remove


def _leaf(tmp_path: Path, nested: tuple[str, ...] = ()) -> tuple[Path, Path]:
    root = make_pickup_project(tmp_path)
    for rel in nested:
        add_nested_repo(root, rel, "main")
    git(root, "push", "-q", "origin", "main")
    wt = root / "work" / ".worktrees" / "leaf-one"
    git(root, "worktree", "add", "-q", "-b", FEATURE, str(wt), "main")
    return root, wt


def _land(root: Path, wt: Path) -> None:
    commit_file(wt, "src/a.py", "a = 1\n", "leaf work")
    commit_file(wt, ".gitignore", (wt / ".gitignore").read_text() + "*.log\n"
                if (wt / ".gitignore").is_file() else "*.log\n", "ignore logs")
    git(root, "merge", "-q", "--no-ff", "--no-edit", FEATURE)
    git(root, "push", "-q", "origin", "main")


def _refusals(root: Path) -> str:
    return "\n".join(plan_prune(root, "M1").refusals)


def test_unmerged_branch_is_refused(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    commit_file(wt, "src/a.py", "a = 1\n", "leaf work")
    assert f"{FEATURE} is not merged into refs/remotes/origin/main" in _refusals(root)
    assert "the worktree's HEAD is not merged" in _refusals(root)


def test_merged_locally_but_not_pushed_is_refused(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    commit_file(wt, "src/a.py", "a = 1\n", "leaf work")
    git(root, "merge", "-q", "--no-ff", "--no-edit", FEATURE)
    assert "not merged into refs/remotes/origin/main" in _refusals(root)


def test_unknown_node_and_missing_worktree_are_errors(tmp_path: Path) -> None:
    root = make_pickup_project(tmp_path)
    with pytest.raises(PruneError, match="no roadmap node 'M9'"):
        plan_prune(root, "M9")
    with pytest.raises(PruneError, match="not a worktree of this repository"):
        plan_prune(root, "M1")


@pytest.mark.parametrize(("make", "why"), [
    (lambda wt: (wt / "src" / "a.py").write_text("a = 2\n"), "uncommitted or untracked: src/a.py"),
    (lambda wt: (wt / "notes.txt").write_text("x\n"), "uncommitted or untracked: notes.txt"),
    (lambda wt: ((wt / "src" / "a.py").write_text("a = 2\n"), git(wt, "stash", "push", "-q", "-m", "wip")),
     f"stashes made on {FEATURE}: On {FEATURE}: wip"),
])
def test_unsaved_work_in_the_worktree_is_refused(tmp_path: Path, make, why: str) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    make(wt)
    assert why in _refusals(root)
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1 and why in out.stderr
    assert wt.is_dir()


def test_clean_prune_lists_ignored_files_and_removes_only_with_yes(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    (wt / "build.log").write_text("x\n")
    listed = run_specy_road(root, "worktree", "prune", "M1")
    assert listed.returncode == 0, listed.stderr
    assert "build.log" in listed.stdout and "Re-run with --yes" in listed.stdout
    assert wt.is_dir()
    done = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert done.returncode == 0, done.stderr
    assert not wt.exists()
    assert git(root, "branch", "--list", FEATURE)   # the branch is left for `branches prune`


def _nested_leaf(tmp_path: Path) -> tuple[Path, Path]:
    root, wt = _leaf(tmp_path, (COVERED, UNCOVERED))
    add_nested_worktrees(root, wt, FEATURE, ["src"])
    _land(root, wt)
    return root, wt


def test_clean_prune_removes_nested_linked_worktrees(tmp_path: Path) -> None:
    root, wt = _nested_leaf(tmp_path)
    plan = plan_prune(root, "M1")
    assert plan.refusals == []
    assert {(d.name, linked) for _src, d, linked in plan.nested} == {("engine", True), ("lib", True)}
    assert remove(plan) is None
    assert not wt.exists()
    for rel in (COVERED, UNCOVERED):
        assert len(git(root / rel, "worktree", "list").splitlines()) == 1


def _detached_commit(wt: Path) -> None:
    commit_file(wt / UNCOVERED, "core.py", "x = 2\n", "detached work")


def _nested_edit(wt: Path) -> None:
    (wt / COVERED / "core.py").write_text("x = 3\n")


def _nested_stash(wt: Path) -> None:
    _nested_edit(wt)
    git(wt / COVERED, "stash", "push", "-q", "-m", "nested wip")


@pytest.mark.parametrize(("make", "why"), [
    (_detached_commit, f"nested repo {UNCOVERED} (linked worktree): commits on no branch"),
    (_nested_edit, f"nested repo {COVERED} (linked worktree): uncommitted or untracked: core.py"),
    (_nested_stash, f"nested repo {COVERED} (linked worktree): stashes: On {FEATURE}: nested wip"),
])
def test_unsaved_work_in_a_nested_linked_worktree_is_refused(tmp_path: Path, make, why: str) -> None:
    root, wt = _nested_leaf(tmp_path)
    make(wt)
    assert why in _refusals(root)


def test_a_commit_on_the_leaf_branch_of_a_nested_linked_worktree_is_kept_by_that_branch(tmp_path: Path) -> None:
    root, wt = _nested_leaf(tmp_path)
    commit_file(wt / COVERED, "core.py", "x = 4\n", "nested leaf work")
    assert _refusals(root) == ""


def _clone_leaf(tmp_path: Path) -> tuple[Path, Path, Path]:
    root, wt = _leaf(tmp_path, (UNCOVERED,))
    _land(root, wt)
    clone = wt / UNCOVERED
    git(root, "clone", "-q", str(root / UNCOVERED), str(clone))
    git(clone, "config", "user.email", "t@e.com")
    git(clone, "config", "user.name", "T")
    return root, wt, clone


def test_full_clone_branch_held_nowhere_is_refused_until_pushed(tmp_path: Path) -> None:
    root, wt, clone = _clone_leaf(tmp_path)
    plan = plan_prune(root, "M1")
    assert plan.refusals == [] and [linked for *_x, linked in plan.nested] == [False]
    git(clone, "checkout", "-q", "-b", "topic")
    commit_file(clone, "core.py", "x = 5\n", "clone work")
    git(clone, "checkout", "-q", "main")
    assert f"nested repo {UNCOVERED} (full clone): commits on no branch" in _refusals(root)
    assert "topic (" in _refusals(root)
    git(clone, "push", "-q", "origin", "topic")   # now a branch of the main checkout's copy
    assert _refusals(root) == ""
    assert remove(plan_prune(root, "M1")) is None
    assert not wt.exists()
    assert git(root / UNCOVERED, "branch", "--list", "topic")


@pytest.mark.parametrize(("make", "why"), [
    (lambda c: (c / "core.py").write_text("x = 6\n"), "(full clone): uncommitted or untracked: core.py"),
    (lambda c: ((c / "core.py").write_text("x = 6\n"), git(c, "stash", "push", "-q", "-m", "clone wip")),
     "(full clone): stashes: On main: clone wip"),
])
def test_unsaved_work_in_a_nested_full_clone_is_refused(tmp_path: Path, make, why: str) -> None:
    root, _wt, clone = _clone_leaf(tmp_path)
    make(clone)
    assert why in _refusals(root)


def test_a_plain_directory_at_a_nested_path_is_checked_as_part_of_the_worktree(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path, (UNCOVERED,))
    _land(root, wt)
    (wt / UNCOVERED).mkdir()
    (wt / UNCOVERED / "notes.txt").write_text("x\n")   # ignored by the main repo: listed, not skipped
    plan = plan_prune(root, "M1")
    assert plan.nested == [] and f"{UNCOVERED}/" in plan.ignored
