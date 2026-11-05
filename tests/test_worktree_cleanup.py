"""M12.5: ``worktree cleanup <ID>`` and ``worktree sweep`` retire landed worktrees, saving hand-off files first.

The fixture is the one-leaf pickup project (``M1``, ``leaf-one``) with ``work/`` ignored and the leaf's
worktree at ``work/.worktrees/leaf-one`` on ``feature/rm-leaf-one``, as pickup lays it out. Landing merges
the branch into ``main`` and pushes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tests.pickup_repo_helpers import FEATURE, make_pickup_project, run_specy_road
from tests.review_repo_helpers import commit_file, git

from specy_road.bundled_scripts.grind_session_cleanup import after_landing
from specy_road.bundled_scripts.grind_session_events import EventEmitter
from specy_road.session_presence import list_sessions, start_session
from specy_road.worker_state import create_record, load_record, set_state
from specy_road.worktree_cleanup import cleanup_after_land, regenerable

HISTORY = Path("work/reviews/M1/history/REVIEW-codex-1.md")


def _leaf(tmp_path: Path) -> tuple[Path, Path]:
    root = make_pickup_project(tmp_path)
    commit_file(root, ".gitignore", "work/\n*.log\n__pycache__/\n", "ignore work")
    git(root, "push", "-q", "origin", "main")
    wt = root / "work" / ".worktrees" / "leaf-one"
    git(root, "worktree", "add", "-q", "-b", FEATURE, str(wt), "main")
    return root, wt


def _land(root: Path, wt: Path, branch: str = FEATURE, rel: str = "src/a.py") -> None:
    commit_file(wt, rel, "a = 1\n", "leaf work")
    git(root, "merge", "-q", "--no-ff", "--no-edit", branch)
    git(root, "push", "-q", "origin", "main")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_cleanup_saves_a_worktree_only_history_file_and_removes_the_worktree(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    _write(wt / HISTORY, "round 1\n")
    _write(wt / "work/reviews/M1/RUN-codex.log", "run log\n")
    _write(wt / "work/brief-M1.md", "brief\n")                  # regenerable
    _write(wt / "src/__pycache__/a.cpython.pyc", "x")         # regenerable
    rec = create_record(root, "M1", "generic", "m", wt, branch=FEATURE)
    set_state(root, rec, "idle")
    out = run_specy_road(root, "worktree", "cleanup", "M1")
    assert out.returncode == 0, out.stderr
    assert (root / HISTORY).read_text() == "round 1\n"
    assert (root / "work/reviews/M1/RUN-codex.log").read_text() == "run log\n"
    assert not wt.exists()
    assert load_record(root, rec.worker_id).state == "terminated"
    assert f"[ok] removed worktree {wt}" in out.stdout


def test_a_different_same_named_hand_off_file_is_kept_beside_the_existing_one(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    _write(root / HISTORY, "main's copy\n")
    _write(wt / HISTORY, "worktree's copy\n")
    same = Path("work/reviews/M1/REVIEW-codex.md")
    _write(root / same, "same\n")
    _write(wt / same, "same\n")
    removed, lines = cleanup_after_land(root, "M1")
    assert removed, lines
    assert (root / HISTORY).read_text() == "main's copy\n"
    assert (root / f"{HISTORY}.from-worktree1").read_text() == "worktree's copy\n"
    assert (root / same).read_text() == "same\n"
    assert not (root / f"{same}.from-worktree1").exists()


@pytest.mark.parametrize(("make", "why"), [
    (lambda root, wt: commit_file(wt, "src/b.py", "b = 1\n", "after landing"),
     "the worktree's HEAD is not merged into origin's main"),
    (lambda root, wt: (wt / "src" / "a.py").write_text("a = 2\n"), "uncommitted or untracked: src/a.py"),
    (lambda root, wt: (wt / "notes.txt").write_text("x\n"), "uncommitted or untracked: notes.txt"),
    (lambda root, wt: (wt / "build.log").write_text("x\n"), "ignored files that are not regenerable: build.log"),
])
def test_cleanup_refuses_and_removes_nothing(tmp_path: Path, make, why: str) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    _write(wt / HISTORY, "round 1\n")
    rec = create_record(root, "M1", "generic", "m", wt, branch=FEATURE)
    set_state(root, rec, "idle")
    make(root, wt)
    out = run_specy_road(root, "worktree", "cleanup", "M1")
    assert out.returncode == 1
    assert any(line.startswith("  - ") and why in line for line in out.stderr.splitlines()), out.stderr
    assert wt.is_dir()
    assert load_record(root, rec.worker_id).state == "idle"
    assert (root / HISTORY).read_text() == "round 1\n"   # saved even though nothing was removed


def test_cleanup_ends_the_leafs_reviewer_and_session_records(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    start_session(root, "codex-reviewer-M1", paths=[], worktree=wt)   # in the worktree, on its branch
    other = start_session(root, "leaf-session", paths=["src"], worktree=root)
    raw = yaml.safe_load(other.path.read_text())
    other.path.write_text(yaml.safe_dump({**raw, "branch": FEATURE, "worktree": str(tmp_path / "elsewhere")}))
    start_session(root, "bystander", paths=[], worktree=root)
    removed, lines = cleanup_after_land(root, "M1")
    assert removed, lines
    assert [s.agent for s in list_sessions(root, live_only=False)] == ["bystander"]
    assert "ended session record codex-reviewer-M1" in lines and "ended session record leaf-session" in lines


def test_regenerable_patterns() -> None:
    assert regenerable("sr/work/prompt-M1.md", "sr/") and regenerable("node_modules/x/y.js", "")
    assert regenerable("gui/.ruff_cache/a", "") and regenerable(".specyrd/cache/k", "sr/")
    assert not regenerable("sr/work/reviews/M1/a.md", "sr/") and not regenerable("work/prompt-x/y.md", "")
    assert not regenerable("build.log", "")


def _side(root: Path, path: Path, branch: str) -> Path:
    git(root, "worktree", "add", "-q", "-b", branch, str(path), "main")
    return path


def test_sweep_keeps_claimed_live_and_dirty_worktrees_and_removes_the_rest(tmp_path: Path) -> None:
    root, _wt = _leaf(tmp_path)
    claimed = _side(root, tmp_path / "wt-claimed", "feature/rm-claimed")
    live = _side(root, tmp_path / "wt-live", "feature/rm-live")
    dirty = _side(root, tmp_path / "wt-dirty", "feature/rm-dirty")
    done = _side(root, tmp_path / ".claude" / "worktrees" / "agent-1", "feature/rm-done")
    for path, branch in ((live, "feature/rm-live"), (dirty, "feature/rm-dirty"), (done, "feature/rm-done")):
        _land(root, path, branch, f"src/{path.name}.py")
    _land(root, _wt)
    (root / "roadmap" / "registry.yaml").write_text(yaml.safe_dump({"version": 1, "entries": [
        {"codename": "claimed", "node_id": "M9", "branch": "feature/rm-claimed", "owner": "t"}]}))
    start_session(root, "agent-live", paths=[], worktree=live)
    (dirty / "notes.txt").write_text("x\n")
    _write(done / HISTORY, "round 1\n")
    dry = run_specy_road(root, "worktree", "sweep", "--dry-run")
    assert dry.returncode == 0, dry.stderr
    lines = dry.stdout.splitlines()
    assert f"kept {claimed}: branch feature/rm-claimed live: claimed by M9" in lines
    assert f"kept {live}: branch feature/rm-live live: session agent-live" in lines
    assert f"kept {dirty}: uncommitted or untracked: notes.txt" in lines
    assert f"would remove {done}" in lines
    assert done.is_dir() and not (root / HISTORY).exists()
    swept = run_specy_road(root, "worktree", "sweep")
    assert swept.returncode == 0, swept.stderr
    assert f"removed {done}" in swept.stdout.splitlines()
    assert f"kept {dirty}: uncommitted or untracked: notes.txt" in swept.stdout.splitlines()
    assert not done.exists() and claimed.is_dir() and live.is_dir() and dirty.is_dir()
    assert (root / HISTORY).read_text() == "round 1\n"
    assert git(root, "branch", "--list", "feature/rm-done")   # the branch stays without the flag


def test_sweep_removes_a_landed_pickup_worktree_so_its_branch_can_go(tmp_path: Path) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    held = subprocess.run(["git", "-C", str(root), "branch", "-d", FEATURE], capture_output=True, text=True)
    assert held.returncode != 0   # checked out in the worktree: the '(worktree)' skip
    out = run_specy_road(root, "worktree", "sweep", "--delete-local-branch")
    assert out.returncode == 0, out.stderr
    assert f"removed {wt}; deleted branch {FEATURE}" in out.stdout.splitlines()
    assert not wt.exists() and not git(root, "branch", "--list", FEATURE)
    assert git(root, "ls-remote", "origin", "refs/heads/main")   # the remote is untouched


@pytest.mark.parametrize("policy", ["off", "between_leaves"])
def test_grind_session_cleans_up_each_landed_leaf_and_sweeps_by_policy(tmp_path: Path, capsys, policy: str) -> None:
    root, wt = _leaf(tmp_path)
    _land(root, wt)
    stale = _side(root, tmp_path / "stale", "feature/rm-stale")
    _land(root, stale, "feature/rm-stale", "src/stale.py")
    (root / "roadmap" / "orchestration.yaml").write_text(yaml.safe_dump({
        "version": 1, "roster": [{"id": "human", "family": "human", "roles": ["coordinator", "reviewer"]}],
        "policy": {"worktree_sweep": policy}}))
    _write(wt / HISTORY, "round 1\n")
    after_landing(SimpleNamespace(milestone_subtree=False), root, EventEmitter(as_json=True), "M1")
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[0]["event"] == "worktree_cleanup" and events[0]["removed"], events
    assert not wt.exists() and (root / HISTORY).is_file()
    if policy == "off":
        assert len(events) == 1 and stale.is_dir()
    else:
        assert events[1]["event"] == "worktree_sweep" and f"removed {stale}" in events[1]["lines"]
        assert not stale.exists()
