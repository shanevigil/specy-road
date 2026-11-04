"""M11.22: ``nested_repos`` worktrees in pickup and ``worker delegate``, and ``worker reconcile`` over them.

The fixture is a project with one separately versioned repository under its
root, with its own bare ``origin``, ignored by the main repository and named in
``roadmap/git-workflow.yaml``. Where it sits decides whether the leaf's touch
zones (``src``) cover it: ``src/engine`` is covered, ``lib`` is not.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.pickup_repo_helpers import FEATURE, make_pickup_project, run_pickup
from tests.review_repo_helpers import git
from tests.test_worker_cli import run_worker_cli, wait_for_worker
from tests.worker_repo_helpers import make_worker_repo

from specy_road import worker_ops as ops
from specy_road import worker_reconcile as wrc
from specy_road.git_workflow_config import load_git_workflow_config, validate_git_workflow_dict
from specy_road import worker_state as ws
from specy_road.nested_repos import NestedRepoError, add_nested_worktrees, covers, nested_repos

COVERED, UNCOVERED = "src/engine", "lib"


def add_nested_repo(project: Path, rel: str, branch: str) -> Path:
    """A repository at ``project/rel`` on ``branch``, pushed to its own bare origin, ignored and configured in ``project``.

    The main repository must be on its integration branch; the config commit lands there. A second call
    adds a second repository to the same list.
    """
    nested = project / rel
    nested.mkdir(parents=True)
    git(nested, "init", "-q", "-b", branch)
    git(nested, "config", "user.email", "t@e.com")
    git(nested, "config", "user.name", "T")
    (nested / "core.py").write_text("x = 1\n", encoding="utf-8")
    git(nested, "add", "-A")
    git(nested, "commit", "-qm", "nested root")
    origin = project.parent / (rel.replace("/", "+") + "-origin.git")
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(nested, "remote", "add", "origin", str(origin))
    git(nested, "push", "-q", "-u", "origin", branch)
    ignore = project / ".gitignore"
    ignore.write_text((ignore.read_text() if ignore.is_file() else "") + f"{rel}/\n", encoding="utf-8")
    cfg = project / "roadmap" / "git-workflow.yaml"
    text = cfg.read_text()
    cfg.write_text(text + ("" if "nested_repos:" in text else "nested_repos:\n") + f"  - {rel}\n", encoding="utf-8")
    git(project, "add", ".gitignore", "roadmap/git-workflow.yaml")
    git(project, "commit", "-qm", "nested repo")
    return nested


def _cfg(extra: dict) -> str | None:
    return validate_git_workflow_dict({"version": 1, "integration_branch": "main", "remote": "origin", **extra})


def test_schema_takes_paths_and_objects_and_refuses_escapes() -> None:
    assert _cfg({"nested_repos": ["svc", {"path": "web/app", "integration_branch": "trunk", "remote": "up"}]}) is None
    for bad in ("../up", "/abs", "a/./b", "a/../b"):
        assert _cfg({"nested_repos": [bad]}) is not None, bad
    assert _cfg({"nested_repos": [{"path": "svc", "branch": "x"}]}) is not None


@pytest.mark.parametrize("twice", [["svc", "svc/"], ["a//b", {"path": "a/b/"}]])
def test_schema_refuses_two_spellings_of_one_directory(twice: list) -> None:
    """uniqueItems compares spellings; a second row for one directory would fail the second worktree add."""
    err = _cfg({"nested_repos": twice})
    assert err is not None and err.startswith("nested_repos: ") and "names the same directory as" in err
    assert repr(twice[1]) in err and repr(twice[0]) in err


def test_a_duplicated_nested_repo_is_a_config_error_not_two_rows(tmp_path: Path) -> None:
    root = make_pickup_project(tmp_path, "nested_repos:\n  - gui/app\n  - gui/app/\n")
    _data, err = load_git_workflow_config(root)
    assert err and "'gui/app/' names the same directory as 'gui/app' (gui/app)" in err
    assert nested_repos(root) == []


def test_entries_default_to_the_main_repositorys_branch_and_remote(tmp_path: Path) -> None:
    root = make_pickup_project(tmp_path, "nested_repos:\n  - svc/\n  - x//y\n  - {path: web, integration_branch: trunk, remote: up}\n")
    assert [(n.path, n.integration_branch, n.remote) for n in nested_repos(root)] == [
        ("svc", "main", "origin"), ("x/y", "main", "origin"), ("web", "trunk", "up")]


@pytest.mark.parametrize(("zones", "covered"), [
    (["src"], True), (["src/engine/api"], True), (["src/*"], True), (["sr/src/engine"], True),
    (["src/other"], False), (["lib"], False), ([], False),
])
def test_covers_reads_zones_from_either_root(zones: list[str], covered: bool) -> None:
    assert covers(zones, "src/engine", "sr/") is covered


@pytest.mark.parametrize(("rel", "on_branch"), [(COVERED, True), (UNCOVERED, False)])
def test_worktree_pickup_gives_the_nested_repo_its_worktree(tmp_path: Path, rel: str, on_branch: bool) -> None:
    root = make_pickup_project(tmp_path)
    nested = add_nested_repo(root, rel, "main")
    git(root, "push", "-q", "origin", "main")
    r = run_pickup(root, "--worktree")
    assert r.returncode == 0, r.stderr
    inner = root / "work" / ".worktrees" / "leaf-one" / rel
    assert Path(git(inner, "rev-parse", "--show-toplevel")).resolve() == inner.resolve()
    assert git(inner, "rev-parse", "HEAD") == git(nested, "rev-parse", "origin/main")
    assert git(inner, "branch", "--show-current") == (FEATURE if on_branch else "")
    assert git(nested, "branch", "--show-current") == "main"   # the repository's own checkout is untouched
    assert f"nested repo {rel}: " + ("on " if on_branch else "detached at ") in r.stdout


def _leaf_worktree_delegate(tmp_path: Path, rel: str) -> tuple[Path, Path, Path, str]:
    """``(repo, nested repo, leaf worktree, worker id)``: delegated from the coordinator checkout on ``dev``."""
    repo, _script = make_worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    nested = add_nested_repo(repo, rel, "dev")
    rec, created = ops.delegate(repo, "M1.1", "opus")
    assert created
    wait_for_worker(repo, rec.worker_id)
    return repo, nested, Path(rec.worktree), rec.worker_id


def test_delegate_adds_the_nested_worktree_on_the_leaf_branch(tmp_path: Path) -> None:
    repo, nested, wt, _wid = _leaf_worktree_delegate(tmp_path, COVERED)
    assert wt == (repo / "work" / ".worktrees" / "thing").resolve()
    assert git(wt / COVERED, "branch", "--show-current") == "feature/rm-thing"
    assert git(nested, "branch", "--show-current") == "dev"
    # A re-run leaves it alone: the worktree is already there.
    assert add_nested_worktrees(repo, wt, "feature/rm-thing", ["src"]) == []


def test_delegate_refuses_a_nested_repo_path_that_is_no_repository(tmp_path: Path, capsys) -> None:
    repo, _script = make_worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    cfg = repo / "roadmap" / "git-workflow.yaml"
    cfg.write_text(cfg.read_text() + "nested_repos:\n  - ghost\n", encoding="utf-8")
    git(repo, "commit", "-qam", "ghost nested repo")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "nested repo 'ghost'" in capsys.readouterr().err


def test_delegate_refuses_an_ordinary_directory_where_the_nested_worktree_goes(tmp_path: Path, capsys) -> None:
    repo, _script = make_worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    add_nested_repo(repo, COVERED, "dev")
    wt = repo / "work" / ".worktrees" / "thing"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    (wt / COVERED).mkdir(parents=True)
    (wt / COVERED / "core.py").write_text("left by a build\n", encoding="utf-8")   # no repository, no branch
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert f"nested repo {COVERED!r}" in err and "exists but is not a git worktree" in err
    assert not ws.list_records(repo)


def test_an_existing_nested_worktree_in_the_wrong_state_is_refused(tmp_path: Path) -> None:
    repo, _nested, wt, _wid = _leaf_worktree_delegate(tmp_path, COVERED)
    # Zones that no longer cover it want it detached; it holds the leaf's branch.
    with pytest.raises(NestedRepoError, match="must be detached"):
        add_nested_worktrees(repo, wt, "feature/rm-thing", ["docs"])


def test_a_detached_nested_worktree_off_the_integration_tip_is_refused(tmp_path: Path) -> None:
    repo, nested, wt, _wid = _leaf_worktree_delegate(tmp_path, UNCOVERED)
    inner = wt / UNCOVERED
    assert add_nested_worktrees(repo, wt, "feature/rm-thing", ["src"]) == []   # at the tip: kept
    (nested / "core.py").write_text("x = 9\n", encoding="utf-8")
    git(nested, "commit", "-qam", "the integration branch moves on")
    git(nested, "push", "-q", "origin", "dev")
    with pytest.raises(NestedRepoError, match="is detached at .*, not at the integration tip"):
        add_nested_worktrees(repo, wt, "feature/rm-thing", ["src"])
    git(inner, "checkout", "-q", "--detach", "origin/dev")   # back on the tip: accepted again
    assert add_nested_worktrees(repo, wt, "feature/rm-thing", ["src"]) == []


@pytest.mark.parametrize("dirt", ["tracked", "untracked"])
def test_delegate_launches_nothing_over_a_dirty_nested_worktree(tmp_path: Path, capsys, dirt: str) -> None:
    repo, _script = make_worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    add_nested_repo(repo, COVERED, "dev")
    wt = repo / "work" / ".worktrees" / "thing"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    add_nested_worktrees(repo, wt, "feature/rm-thing", ["src"])
    name = "core.py" if dirt == "tracked" else "scratch.txt"
    (wt / COVERED / name).write_text("someone's unsaved work\n", encoding="utf-8")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "uncommitted changes the worker could overwrite" in err and f"{COVERED}/{name}" in err
    assert not ws.list_records(repo) and not (repo / "work" / "prompt-M1.1-executor-opus.md").exists()
    assert (wt / COVERED / name).read_text(encoding="utf-8") == "someone's unsaved work\n"


@pytest.mark.parametrize("rel", [COVERED, UNCOVERED])
def test_delegate_refuses_a_nested_repo_without_its_integration_branch(tmp_path: Path, capsys, rel: str) -> None:
    """The config says dev; the repository has only main. Its HEAD is not a stand-in for the tip."""
    repo, _script = make_worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    add_nested_repo(repo, rel, "main")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert f"nested repo {rel!r}: neither origin/dev nor a local dev exists" in capsys.readouterr().err
    assert not ws.list_records(repo)
    assert not (repo / "work" / ".worktrees" / "thing" / rel).exists()


def test_reconcile_diffs_the_nested_repo_and_flags_edits_outside_the_zones(tmp_path: Path) -> None:
    repo, _nested, wt, wid = _leaf_worktree_delegate(tmp_path, COVERED)
    inner = wt / COVERED
    (inner / "core.py").write_text("x = 2\n", encoding="utf-8")
    git(inner, "commit", "-qam", "in zone")
    (inner / "notes.txt").write_text("scratch\n", encoding="utf-8")
    _rec, delta = wrc.reconcile(repo, wid)
    assert delta["nested_changed"] == [f"{COVERED}/core.py"]
    assert f"{COVERED}/notes.txt" in delta["untracked"]
    # The fixture's branch already carries docs/x.md outside the zones; nothing nested is.
    assert not [p for p in delta["outside_touch_zones"] + delta["untracked_outside_touch_zones"] if p.startswith(COVERED)]
    assert not any(p.rstrip("/") == COVERED for p in delta["untracked"])   # the directory is not an untracked file


def test_reconcile_flags_an_edit_in_a_detached_nested_repo(tmp_path: Path) -> None:
    repo, _nested, wt, wid = _leaf_worktree_delegate(tmp_path, UNCOVERED)
    inner = wt / UNCOVERED
    assert git(inner, "branch", "--show-current") == ""
    (inner / "core.py").write_text("x = 3\n", encoding="utf-8")
    _rec, delta = wrc.reconcile(repo, wid)
    assert delta["nested_changed"] == [f"{UNCOVERED}/core.py"] and delta["needs_reconcile"]
    assert f"{UNCOVERED}/core.py" in delta["outside_touch_zones"]
    assert any("nested repos: 1 path(s)" in ln for ln in wrc.reconcile_lines({"worker_id": wid, "delta": delta}))
