"""M14.3: ``worktree prune`` refuses to delete another repository's worktree or checkout inside the leaf's.

The leaf is the one-leaf pickup project's ``M1`` worktree at ``work/.worktrees/leaf-one``, landed on
``origin``'s ``main``; ``sibling/`` is ignored on the leaf's branch, so without the check it would be
listed among the ignored files and deleted with the worktree.
"""

from __future__ import annotations

import re
import shlex
import subprocess
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


def _other_repo(tmp_path: Path, name: str = "other") -> Path:
    """A second repository on ``main``, pushed to its own bare origin."""
    other = tmp_path / name
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(tmp_path / f"{name}.git"))
    git(tmp_path, "init", "-q", "-b", "main", str(other))
    git(other, "config", "user.email", "t@e.com")
    git(other, "config", "user.name", "T")
    commit_file(other, "core.py", "x = 1\n", "other base")
    git(other, "remote", "add", "origin", str(tmp_path / f"{name}.git"))
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
    other = _other_repo(tmp_path, "other repo")
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
    # The suggested next step names each path as one shell word, so it runs as printed once the work is pushed.
    step = re.search(r"`(git -C [^`]* worktree remove [^`]*sibling space[^`]*)`", out.stderr)
    assert step and shlex.split(step[1]) == ["git", "-C", str(other.resolve()), "worktree", "remove", str(sibs[0])]
    assert subprocess.run(shlex.split(step[1]), capture_output=True, check=False).returncode == 0
    assert not sibs[0].exists()


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


def _own_checkout(d: Path, branch: str, msg: str) -> None:
    """An independent repository at ``d`` (which may already hold files) with one commit on ``branch``."""
    d.mkdir(parents=True, exist_ok=True)
    git(d, "init", "-q", "-b", branch)
    git(d, "config", "user.email", "t@e.com")
    git(d, "config", "user.name", "T")
    commit_file(d, "core.py", "x = 1\n", msg)


def _refused_both_ways(root: Path, *keep: Path) -> str:
    """Preview and ``--yes`` both exit 1 and leave every path in ``keep``; the ``--yes`` stderr."""
    for args in ((), ("--yes",)):
        out = run_specy_road(root, "worktree", "prune", "M1", *args)
        assert out.returncode == 1, out.stdout
        assert all(p.is_dir() for p in keep)
    return out.stderr


def test_a_foreign_checkout_in_a_clean_tracked_directory_refuses_and_survives(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path)
    commit_file(wt, "vendor/core.py", "x = 1\n", "vendor code")
    git(root, "merge", "-q", "--no-ff", "--no-edit", FEATURE)
    git(root, "push", "-q", "origin", "main")
    _own_checkout(wt / "vendor", "private", "private vendor history")   # same core.py: the leaf's status is clean
    assert git(wt, "status", "--porcelain", "--ignored") == ""
    why = _refused_both_ways(root, wt / "vendor", wt)
    assert f"vendor/ is a checkout of another repository, {wt / 'vendor'}, on private" in why
    assert "private vendor history" in why


def test_an_initialized_submodule_refuses_and_survives(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path)
    upstream = tmp_path / "upstream"
    _own_checkout(upstream, "private", "submodule base")
    git(wt, "-c", "protocol.file.allow=always", "submodule", "add", "-q", "-b", "private", str(upstream), "vendor")
    git(wt, "commit", "-qm", "add the submodule")
    git(root, "merge", "-q", "--no-ff", "--no-edit", FEATURE)
    git(root, "push", "-q", "origin", "main")
    sub = wt / "vendor"
    git(sub, "config", "user.email", "t@e.com")
    git(sub, "config", "user.name", "T")
    git(sub, "checkout", "-q", "-b", "private-topic")
    commit_file(sub, "core.py", "x = 2\n", "submodule-only work")
    git(sub, "checkout", "-q", "private")   # back at the recorded commit: the leaf's status is clean
    assert git(wt, "status", "--porcelain", "--ignored") == ""
    why = _refused_both_ways(root, sub, wt)
    assert "vendor/ is a checkout of another repository" in why and "on private" in why
    assert git(sub, "log", "-1", "--format=%s", "private-topic") == "submodule-only work"


def test_an_ignored_foreign_checkout_with_a_carriage_return_in_its_name_refuses_and_survives(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path)
    sib = wt / "sibling\rname"   # text-mode decoding would read it as sibling\nname
    _own_checkout(sib, "private", "carriage-return work")
    why = _refused_both_ways(root, sib, wt)
    assert "is a checkout of another repository" in why and "carriage-return work" in why


def test_an_unreadable_directory_refuses_instead_of_being_skipped(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path)
    locked = wt / "sibling-locked"
    _own_checkout(locked / "inner", "private", "hidden work")
    locked.chmod(0)
    try:
        why = _refused_both_ways(root, wt)
        assert f"cannot read {locked}: Permission denied" in why
    finally:
        locked.chmod(0o755)
    assert (locked / "inner" / ".git").is_dir()


def test_a_foreign_worktree_inside_a_configured_clones_git_directory_refuses_and_survives(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path, (UNCOVERED,))
    clone = wt / UNCOVERED
    git(root, "clone", "-q", str(root / UNCOVERED), str(clone))
    sib = clone / ".git" / "foreign-worktree"   # removing the clone deletes its .git and this with it
    git(_other_repo(tmp_path), "worktree", "add", "-q", "-b", "topic", str(sib), "main")
    commit_file(sib, "core.py", "x = 2\n", "work inside the clone's git directory")
    plan = plan_prune(root, "M1")
    assert plan.foreign == [sib]   # the clone and its own .git stay exempt
    assert remove(plan) is not None and sib.is_dir() and clone.is_dir()
    why = _refused_both_ways(root, sib, clone, wt)
    assert f"{UNCOVERED}/.git/foreign-worktree/ is a linked worktree of another repository" in why
    assert "work inside the clone's git directory" in why


def test_an_owning_repository_with_a_carriage_return_in_its_name_is_named_exactly(tmp_path: Path) -> None:
    root, wt = _landed_leaf_ignoring_sibling(tmp_path)
    other = _other_repo(tmp_path, "other\rrepo")   # text-mode decoding would name other\nrepo, which does not exist
    sib = wt / "sibling"
    git(other, "worktree", "add", "-q", "-b", "topic", str(sib), "main")
    plan = plan_prune(root, "M1")
    why = "\n".join(plan.refusals)
    assert f"linked worktree of another repository, {other.resolve()}, on topic" in why
    assert f"git -C {shlex.quote(str(other.resolve()))} worktree remove" in why
    _refused_both_ways(root, sib, wt)


def test_every_foreign_repository_in_anything_removal_deletes_refuses_at_any_depth(tmp_path: Path) -> None:
    """The scan covers what removal deletes: the leaf and a configured full clone, its ``.git`` included."""
    root, wt = _landed_leaf_ignoring_sibling(tmp_path, (UNCOVERED,))
    clone = wt / UNCOVERED
    git(root, "clone", "-q", str(root / UNCOVERED), str(clone))
    (clone / ".git" / "info" / "exclude").write_text("sibling*/\n")
    other = _other_repo(tmp_path)
    checkouts = [wt / "sibling-a", wt / "sibling-deep" / "x" / "y", clone / "sibling-inner" / "z",
                 clone / ".git" / "info" / "sibling-meta", clone / ".git" / "refs" / "sibling-ref" / "deep"]
    linked = [wt / "sibling-wt", wt / "sibling-deep" / "w", clone / ".git" / "sibling-linked"]
    for i, d in enumerate(checkouts):
        _own_checkout(d, "private", f"checkout work {i}")
    for i, d in enumerate(linked):
        git(other, "worktree", "add", "-q", "-b", f"topic{i}", str(d), "main")
    plan = plan_prune(root, "M1")
    assert plan.foreign == sorted(checkouts + linked)   # the leaf, the clone and the clone's .git are exempt
    assert remove(plan) is not None
    why = _refused_both_ways(root, *checkouts, *linked, clone, wt)
    for d in checkouts:
        assert f"{d.relative_to(wt).as_posix()}/ is a checkout of another repository" in why
    for d in linked:
        assert f"{d.relative_to(wt).as_posix()}/ is a linked worktree of another repository" in why
