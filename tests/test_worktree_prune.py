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
    assert f"{FEATURE} is not merged into origin's main" in _refusals(root)
    assert "the worktree's HEAD is not merged" in _refusals(root)


def test_merged_locally_but_not_pushed_is_refused(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    commit_file(wt, "src/a.py", "a = 1\n", "leaf work")
    git(root, "merge", "-q", "--no-ff", "--no-edit", FEATURE)
    assert "not merged into origin's main" in _refusals(root)


def test_an_unmerged_remote_leaf_branch_refuses_when_the_local_one_is_gone(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    commit_file(wt, "src/b.py", "b = 1\n", "pushed after landing")
    git(wt, "push", "-q", "origin", FEATURE)
    git(wt, "checkout", "-q", "--detach", "HEAD~1")   # back at the landed commit
    git(root, "branch", "-q", "-D", FEATURE)
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1
    assert f"origin/{FEATURE} is not merged into origin's main" in out.stderr
    assert wt.is_dir()


def test_a_peer_push_to_the_leaf_branch_after_it_merged_refuses(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    git(wt, "push", "-q", "origin", FEATURE)   # origin/feature/rm-leaf-one here: merged
    peer = tmp_path / "peer"
    git(tmp_path, "clone", "-q", "-b", FEATURE, str(tmp_path / "origin.git"), str(peer))
    git(peer, "config", "user.email", "p@e.com")
    git(peer, "config", "user.name", "P")
    commit_file(peer, "src/c.py", "c = 1\n", "peer work")
    git(peer, "push", "-q", "origin", FEATURE)   # this checkout's origin/feature/rm-leaf-one is now stale
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1
    assert f"origin/{FEATURE} is not merged into origin's main" in out.stderr
    assert wt.is_dir()


def test_a_peer_push_outside_the_fetch_refspec_refuses(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    git(wt, "push", "-q", "origin", FEATURE)   # origin/feature/rm-leaf-one here: merged
    git(root, "config", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/main")   # main only
    peer = tmp_path / "peer"
    git(tmp_path, "clone", "-q", "-b", FEATURE, str(tmp_path / "origin.git"), str(peer))
    git(peer, "config", "user.email", "p@e.com")
    git(peer, "config", "user.name", "P")
    commit_file(peer, "src/c.py", "c = 1\n", "peer work")
    git(peer, "push", "-q", "origin", FEATURE)   # a plain fetch here would never see it
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1
    assert f"{FEATURE} on origin is not merged into origin's main" in out.stderr
    assert wt.is_dir()


def test_an_unreachable_remote_refuses(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    git(root, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1 and "cannot read origin (git ls-remote origin" in out.stderr
    assert wt.is_dir()


def test_with_both_leaf_refs_gone_a_merged_head_is_pruned(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    git(wt, "checkout", "-q", "--detach")
    git(root, "branch", "-q", "-D", FEATURE)
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 0, out.stderr
    assert not wt.exists()


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
     f"stashes that may be this worktree's: On {FEATURE}: wip"),
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


def test_a_custom_subject_stash_refuses_but_another_branchs_does_not(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "a.py").write_text("a = 9\n")
    git(root, "stash", "push", "-q", "-m", "main checkout wip")   # On main: ...: not this worktree's
    (wt / "src" / "a.py").write_text("a = 2\n")
    sha = git(wt, "stash", "create")
    git(wt, "stash", "store", "-m", "notes for later", sha)   # a subject that names no branch
    git(wt, "checkout", "--", "src/a.py")
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1
    assert "stashes that may be this worktree's: notes for later" in out.stderr
    assert "main checkout wip" not in out.stderr
    assert wt.is_dir()


def test_the_dry_run_names_each_ignored_file_inside_an_ignored_directory(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    commit_file(wt, ".gitignore", "build/\n", "ignore build output")
    git(root, "merge", "-q", "--no-ff", "--no-edit", FEATURE)
    git(root, "push", "-q", "origin", "main")
    (wt / "build" / "deep").mkdir(parents=True)
    (wt / "build" / "app.bin").write_text("x\n")
    (wt / "build" / "deep" / "cache.db").write_text("x\n")
    listed = run_specy_road(root, "worktree", "prune", "M1")
    assert listed.returncode == 0, listed.stderr
    assert "  build/app.bin\n" in listed.stdout and "  build/deep/cache.db\n" in listed.stdout
    assert wt.is_dir()
    done = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert done.returncode == 0, done.stderr
    assert not wt.exists()


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


def test_a_stash_made_in_a_detached_nested_linked_worktree_refuses_the_prune(tmp_path: Path) -> None:
    root, wt = _nested_leaf(tmp_path)
    (wt / UNCOVERED / "core.py").write_text("x = 7\n")
    git(wt / UNCOVERED, "stash", "push", "-q", "-m", "detached nested wip")   # subject: On (no branch): ...
    why = f"nested repo {UNCOVERED} (linked worktree): stashes: On (no branch): detached nested wip"
    assert why in _refusals(root)
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1 and why in out.stderr
    assert (wt / UNCOVERED).is_dir() and wt.is_dir()


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


def test_a_full_clone_branch_held_only_by_its_own_stale_remote_tracking_ref_is_refused(tmp_path: Path) -> None:
    root, wt, clone = _clone_leaf(tmp_path)
    git(clone, "checkout", "-q", "-b", "topic")
    commit_file(clone, "core.py", "x = 8\n", "clone work")
    git(clone, "push", "-q", "origin", "topic")
    git(clone, "checkout", "-q", "main")
    git(root / UNCOVERED, "branch", "-q", "-D", "topic")   # gone from the copy; the clone's origin/topic is stale
    assert git(clone, "rev-parse", "--verify", "origin/topic")
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1
    assert f"nested repo {UNCOVERED} (full clone): commits on no branch or remote-tracking ref of" in out.stderr
    assert "topic (" in out.stderr
    assert clone.is_dir() and wt.is_dir()


def test_a_full_clone_remote_tracking_ref_whose_branch_left_the_copy_is_refused(tmp_path: Path) -> None:
    root, wt, clone = _clone_leaf(tmp_path)
    git(clone, "checkout", "-q", "-b", "topic")
    commit_file(clone, "core.py", "x = 9\n", "clone work")
    git(clone, "push", "-q", "origin", "topic")
    git(clone, "checkout", "-q", "main")
    git(clone, "branch", "-q", "-D", "topic")   # only origin/topic holds it in the clone
    git(root / UNCOVERED, "branch", "-q", "-D", "topic")   # and nothing in the copy does
    assert not git(clone, "branch", "--list", "topic") and git(clone, "rev-parse", "--verify", "origin/topic")
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1
    assert f"nested repo {UNCOVERED} (full clone): commits on no branch or remote-tracking ref of" in out.stderr
    assert "origin/topic (" in out.stderr
    assert clone.is_dir() and wt.is_dir()


@pytest.mark.parametrize("config", [
    "version: 1\nintegration_branch: main\nnested_repos: [lib\n",   # does not parse
    "version: 1\nintegration_branch: main\nremote: origin\nnested_repos:\n  - ../lib\n",   # fails the schema
])
def test_an_unreadable_git_workflow_config_refuses_and_keeps_a_nested_clone(tmp_path: Path, config: str) -> None:
    root, wt, clone = _clone_leaf(tmp_path)
    git(clone, "checkout", "-q", "-b", "topic")
    sha = commit_file(clone, "core.py", "x = 10\n", "clone work held nowhere else")
    (root / "roadmap" / "git-workflow.yaml").write_text(config)
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1
    assert "git-workflow.yaml" in out.stderr and "nested repositories cannot be checked" in out.stderr
    assert clone.is_dir() and wt.is_dir()
    assert git(clone, "rev-parse", "topic") == sha


def _break_stash(git_dir: Path) -> None:
    """``refs/stash`` naming a missing object: ``git stash list`` fails, status and other refs still read."""
    (git_dir / "refs" / "stash").write_text("0123456789012345678901234567890123456789\n")


def test_an_unreadable_stash_list_in_the_leaf_worktree_refuses(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    _break_stash(root / ".git")   # the leaf worktree shares the main checkout's stash
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1 and "  - cannot read the stash list\n" in out.stderr
    assert wt.is_dir()


def test_an_unreadable_stash_list_in_a_nested_full_clone_refuses(tmp_path: Path) -> None:
    root, wt, clone = _clone_leaf(tmp_path)
    _break_stash(clone / ".git")
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1
    assert f"nested repo {UNCOVERED} (full clone): cannot read the stash list" in out.stderr
    assert clone.is_dir() and wt.is_dir()


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
    assert plan.nested == [] and f"{UNCOVERED}/notes.txt" in plan.ignored
