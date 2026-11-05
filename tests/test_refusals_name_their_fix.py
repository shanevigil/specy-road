"""Every refusal names its fix (M12.2): a non-zero exit prints what failed, why, and the next command.

The rule is in ``docs/contributor-guide.md`` ("Refusals"). The parametrized test
runs each refusal through ``specy_road.cli`` in a subprocess; the others pin the
behaviour behind each message.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import script_subprocess_env
from tests.review_repo_helpers import delegate_layout, git, make_review_repo, review_text
from tests.milestone_repo_helpers import make_milestone_repo
from tests.test_review_gate import TWO_FAMILIES
from tests.test_roadmap_crud import crud_fixture_repo, run_crud

from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.review_files import reviews_dir

NK991 = "10000000-0000-4000-8000-000000009902"
#: A runnable next step: a backticked ``specy-road …`` / ``git …`` command, or one leading a line.
NEXT_STEP = re.compile(r"`(?:specy-road|git) [^`]+`|^\s*(?:specy-road|git) \S", re.MULTILINE)


def _cli(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "specy_road.cli", *argv], cwd=cwd,
                          capture_output=True, text=True, env=script_subprocess_env())


def _deps(root: Path, nid: str) -> str:
    return run_crud(root, "--repo-root", str(root), "list-dependencies", nid).stdout


def _dirty(root: Path, n: int) -> None:
    for i in range(n):
        (root / f"stray-{i:02d}.txt").write_text("x\n")


def _approve(root: Path, node_id: str, models: tuple[str, ...], **extra) -> None:
    """An approving review record per model at ``HEAD``, so the gate passes and the clean check runs."""
    d = reviews_dir(root, node_id)
    d.mkdir(parents=True, exist_ok=True)
    for model in models:
        text = review_text(git(root, "rev-parse", "HEAD"), model=model, node_id=node_id, **extra)
        (d / f"REVIEW-{model}.md").write_text(text)


def _approved_leaf(tmp_path: Path) -> Path:
    """M1.1 on its feature branch with a summary and two families' approvals."""
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n")
    _approve(repo, "M1.1", ("opus", "sol"))
    return repo


def _approved_milestone(tmp_path: Path) -> Path:
    """Milestone M2 on ``dev`` with both leaves landed and a human approval at the tip."""
    root = make_milestone_repo(tmp_path)
    _approve(root, "M2", ("human",), acceptance={})   # a milestone has no A-items
    return root


def _mark_reviewed(root: Path, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        mir.main([*args, "--repo-root", str(root)])
        raise SystemExit(0)
    return e.value.code or 0


# --- the refusals, each set up as a user meets it -------------------------------------------

def _unlisted_dependency(tmp_path: Path) -> tuple[Path, list[str]]:
    root = tmp_path / "crud"
    root.mkdir()
    crud_fixture_repo(root)
    return root, ["remove-dependency", "M99.2", "M99", "--repo-root", str(root)]


def _leaf_approval_on_a_dirty_tree(tmp_path: Path) -> tuple[Path, list[str]]:
    repo = _approved_leaf(tmp_path)
    _dirty(repo, 1)
    return repo, ["mark-implementation-reviewed", "--yes", "--repo-root", str(repo)]


def _milestone_approval_on_a_dirty_tree(tmp_path: Path) -> tuple[Path, list[str]]:
    root = _approved_milestone(tmp_path)
    _dirty(root, 1)
    return root, ["mark-implementation-reviewed", "M2", "--yes", "--repo-root", str(root)]


def _abort_while_the_base_is_held(tmp_path: Path, monkeypatch) -> tuple[Path, list[str]]:
    _repo_root, leaf, _bare = delegate_layout(tmp_path, monkeypatch)
    return leaf, ["abort-task-pickup", "--repo-root", str(leaf)]


@pytest.mark.parametrize("setup", [_unlisted_dependency, _leaf_approval_on_a_dirty_tree,
                                   _milestone_approval_on_a_dirty_tree, _abort_while_the_base_is_held])
def test_each_refusal_exits_1_and_names_a_runnable_next_step(tmp_path: Path, monkeypatch, setup) -> None:
    args = (tmp_path, monkeypatch) if setup is _abort_while_the_base_is_held else (tmp_path,)
    cwd, argv = setup(*args)
    r = _cli(cwd, *argv)
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stderr.startswith("error:") or "\nerror:" in r.stderr, r.stderr
    assert NEXT_STEP.search(r.stderr), r.stderr
    if setup in (_leaf_approval_on_a_dirty_tree, _milestone_approval_on_a_dirty_tree):
        stash, = re.findall(r"`(git -C [^`]+ stash push [^`]+)`", r.stderr)
        subprocess.run(stash, shell=True, cwd=tmp_path, check=True, capture_output=True)
        assert git(cwd, "status", "--porcelain", "--", ":/", ":(exclude)work") == ""
        assert _cli(cwd, *argv).returncode == 0   # the retry the message asks for now succeeds


# --- A1: remove-dependency ------------------------------------------------------------------

def test_remove_dependency_by_display_id(tmp_path: Path) -> None:
    # Removal by node_key: tests/test_roadmap_crud_dependencies.py::test_add_remove_dependency_cli.
    crud_fixture_repo(tmp_path)
    assert NK991 in _deps(tmp_path, "M99.2")
    r = run_crud(tmp_path, "--repo-root", str(tmp_path), "remove-dependency", "M99.2", "M99.1")
    assert r.returncode == 0, r.stderr
    assert f"[ok] removed {NK991!r} from M99.2" in r.stdout
    assert "(none)" in _deps(tmp_path, "M99.2")


def test_remove_dependency_not_listed_names_the_actual_ones(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    r = run_crud(tmp_path, "--repo-root", str(tmp_path), "remove-dependency", "M99.2", "M99")
    assert r.returncode == 1
    assert "did not list" not in r.stdout + r.stderr
    assert f"M99.2 does not list dependency 'M99'; its dependencies: M99.1 ({NK991})." in r.stderr
    assert "`specy-road list-dependencies M99.2`" in r.stderr
    assert NK991 in _deps(tmp_path, "M99.2")   # nothing was written
    none = run_crud(tmp_path, "--repo-root", str(tmp_path), "remove-dependency", "M99.1", "M99.2")
    assert none.returncode == 1 and "its dependencies: none." in none.stderr


def test_remove_dependency_unknown_ref_keeps_the_resolver_error(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    r = run_crud(tmp_path, "--repo-root", str(tmp_path), "remove-dependency", "M99.2", "nope")
    assert r.returncode == 1
    assert "error: dependency 'nope' is neither a node id nor a node_key in the roadmap" in r.stderr
    assert "`specy-road list-dependencies M99.2`" in r.stderr


# --- A2: mark-implementation-reviewed on a dirty tree ----------------------------------------

def _assert_lists(err: str, n: int) -> None:
    assert "error: working tree is not clean" in err
    shown = min(n, 20)
    for i in range(shown):
        assert f"?? stray-{i:02d}.txt" in err
    assert f"stray-{shown:02d}.txt" not in err
    assert ("… and 5 more" in err) == (n == 25)
    assert "stash push -u -m 'specy-road: unclean tree'" in err and "work/ are ignored" in err
    assert "<path>" not in err and "<tag>" not in err


@pytest.mark.parametrize("n", [1, 25])
def test_leaf_approval_lists_the_dirty_paths(tmp_path: Path, capsys, n: int) -> None:
    repo = _approved_leaf(tmp_path)
    _dirty(repo, n)
    (repo / "work" / "notes.md").write_text("ignored\n")
    assert _mark_reviewed(repo, "--yes") == 1
    err = capsys.readouterr().err
    _assert_lists(err, n)
    assert "notes.md" not in err


@pytest.mark.parametrize("n", [1, 25])
def test_milestone_approval_lists_the_dirty_paths(tmp_path: Path, capsys, n: int) -> None:
    root = _approved_milestone(tmp_path)
    _dirty(root, n)
    assert _mark_reviewed(root, "M2", "--yes") == 1
    _assert_lists(capsys.readouterr().err, n)


# --- A3: abort-task-pickup's worktree hint ---------------------------------------------------

def test_abort_hint_removes_the_worktree_pickup_left(tmp_path: Path, monkeypatch) -> None:
    repo, leaf, _bare = delegate_layout(tmp_path, monkeypatch)
    (leaf / "work").mkdir(exist_ok=True)
    (leaf / "work" / "brief-M1.1.md").write_text("# brief\n")   # what pickup leaves, untracked
    r = _cli(leaf, "abort-task-pickup", "--repo-root", str(leaf))
    assert r.returncode == 1
    assert "work/brief-M1.1.md" in r.stderr
    status, = re.findall(r"`(git -C [^`]+ status --short)`", r.stderr)
    assert "?? work/" in subprocess.run(status, shell=True, cwd=repo, capture_output=True, text=True,
                                        check=True).stdout
    remove, = re.findall(r"`(git worktree remove [^`]+)`", r.stderr)
    plain = subprocess.run(f"git worktree remove {leaf}", shell=True, cwd=repo, capture_output=True)
    assert plain.returncode != 0   # why the hint needs --force
    subprocess.run(remove, shell=True, cwd=repo, check=True)
    assert not leaf.exists()
    assert str(leaf) not in git(repo, "worktree", "list")
