"""M14.3: ``worktree prune`` refuses to delete another repository's worktree or checkout inside the leaf's.

The leaf is the one-leaf pickup project's ``M1`` worktree at ``work/.worktrees/leaf-one``, landed on
``origin``'s ``main``; ``sibling/`` is ignored on the leaf's branch, so without the check it would be
listed among the ignored files and deleted with the worktree.
"""

from __future__ import annotations

from pathlib import Path

from tests.pickup_repo_helpers import FEATURE, make_pickup_project, run_specy_road
from tests.review_repo_helpers import commit_file, git
from tests.test_nested_repo_worktrees import UNCOVERED, add_nested_repo

from specy_road.worktree_prune import plan_prune, remove


def _landed_leaf_ignoring_sibling(tmp_path: Path, nested: tuple[str, ...] = ()) -> tuple[Path, Path]:
    root = make_pickup_project(tmp_path)
    for rel in nested:
        add_nested_repo(root, rel, "main")
    git(root, "push", "-q", "origin", "main")
    wt = root / "work" / ".worktrees" / "leaf-one"
    git(root, "worktree", "add", "-q", "-b", FEATURE, str(wt), "main")
    commit_file(wt, ".gitignore", "sibling*/\n", "ignore the siblings")
    git(root, "merge", "-q", "--no-ff", "--no-edit", FEATURE)
    git(root, "push", "-q", "origin", "main")
    return root, wt


def _other_repo(tmp_path: Path) -> Path:
    """A second repository on ``main``, pushed to its own bare origin."""
    other = tmp_path / "other"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(tmp_path / "other.git"))
    git(tmp_path, "init", "-q", "-b", "main", str(other))
    git(other, "config", "user.email", "t@e.com")
    git(other, "config", "user.name", "T")
    commit_file(other, "core.py", "x = 1\n", "other base")
    git(other, "remote", "add", "origin", str(tmp_path / "other.git"))
    git(other, "push", "-q", "-u", "origin", "main")
    return other


def test_a_linked_worktree_of_another_repository_refuses_and_survives(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path)
    other = _other_repo(tmp_path)
    sib = wt / "sibling"
    git(other, "worktree", "add", "-q", "-b", "topic", str(sib), "main")
    git(sib, "push", "-q", "-u", "origin", "topic")
    commit_file(sib, "core.py", "x = 2\n", "unpushed sibling work")

    plan = plan_prune(root, "M1")
    assert plan.foreign == [sib]
    why = "\n".join(plan.refusals)
    assert f"sibling/ is a linked worktree of another repository, {other.resolve()}, on topic" in why
    assert "commits its upstream origin/topic lacks: " in why and "unpushed sibling work" in why
    assert f"`git -C {other.resolve()} worktree remove {sib}`" in why
    assert remove(plan) is not None and sib.is_dir() and wt.is_dir()   # remove() refuses on its own

    for args in ((), ("--yes",)):   # preview and removal
        out = run_specy_road(root, "worktree", "prune", "M1", *args)
        assert out.returncode == 1
        assert "sibling/ is a linked worktree of another repository" in out.stderr
        assert "unpushed sibling work" in out.stderr and "land or push those commits" in out.stderr
        assert sib.is_dir() and wt.is_dir()
    assert git(sib, "log", "-1", "--format=%s") == "unpushed sibling work"


def test_a_checkout_of_another_repository_refuses_with_commits_no_remote_holds(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path)
    sib = wt / "sibling"
    git(tmp_path, "clone", "-q", str(_other_repo(tmp_path)), str(sib))
    git(sib, "config", "user.email", "t@e.com")
    git(sib, "config", "user.name", "T")
    git(sib, "checkout", "-q", "--detach")
    commit_file(sib, "core.py", "x = 3\n", "detached clone work")
    out = run_specy_road(root, "worktree", "prune", "M1", "--yes")
    assert out.returncode == 1
    assert f"sibling/ is a checkout of another repository, {sib}, on HEAD" in out.stderr
    assert "commits every remote-tracking ref lacks: " in out.stderr and "detached clone work" in out.stderr
    assert sib.is_dir() and wt.is_dir()


def test_foreign_worktrees_whose_names_git_quotes_refuse_and_survive(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path)
    other = _other_repo(tmp_path)
    sibs = [wt / "sibling space", wt / "siblíng"]   # porcelain without -z prints both in "..." with escapes
    for i, sib in enumerate(sibs):
        git(other, "worktree", "add", "-q", "-b", f"topic{i}", str(sib), "main")
        commit_file(sib, "core.py", f"x = {i + 5}\n", f"unpushed work {i}")
    for args in ((), ("--yes",)):   # preview and removal
        out = run_specy_road(root, "worktree", "prune", "M1", *args)
        assert out.returncode == 1
        assert "sibling space/ is a linked worktree of another repository" in out.stderr
        assert "siblíng/ is a linked worktree of another repository" in out.stderr
        assert all(sib.is_dir() for sib in sibs) and wt.is_dir()


def test_a_foreign_worktree_inside_a_configured_nested_clone_refuses_and_survives(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path, (UNCOVERED,))
    clone = wt / UNCOVERED
    git(root, "clone", "-q", str(root / UNCOVERED), str(clone))
    (clone / ".git" / "info" / "exclude").write_text("sibling/\n")   # ignored inside the configured clone
    sib = clone / "sibling"
    git(_other_repo(tmp_path), "worktree", "add", "-q", "-b", "topic", str(sib), "main")
    commit_file(sib, "core.py", "x = 2\n", "unpushed nested sibling work")
    plan = plan_prune(root, "M1")
    assert [d for _src, d, _linked in plan.nested] == [clone] and plan.foreign == [sib]   # the clone itself is exempt
    for args in ((), ("--yes",)):
        out = run_specy_road(root, "worktree", "prune", "M1", *args)
        assert out.returncode == 1
        assert f"{UNCOVERED}/sibling/ is a linked worktree of another repository" in out.stderr
        assert "unpushed nested sibling work" in out.stderr
        assert sib.is_dir() and clone.is_dir() and wt.is_dir()
