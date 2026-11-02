"""``policy.max_workers`` across checkouts, and for resumed turns (M11.4).

Linked worktrees share the main checkout's ``work/.workers/``; every other
checkout is counted through its lease refs on the integration remote
(``refs/specy-road/leases/<checkout-id>/<worker-id>``), whatever branches exist
locally and whoever owns the claims.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import git
from tests.test_worker_cli import _repo, run_worker_cli, wait_for_worker

from specy_road import worker_lease as lease
from specy_road import worker_ops as ops
from specy_road import worker_state as ws


def _remote_and_clone(tmp_path: Path, repo: Path) -> tuple[Path, Path]:
    """A bare integration remote for ``repo`` and a second clone of it: two checkouts sharing one registry."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "dev", "feature/rm-thing")
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "dev")   # with a remote, the policy is read from its default branch
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "-b", "dev", str(remote), str(clone))
    git(clone, "remote", "set-head", "origin", "dev")
    git(clone, "config", "user.email", "t@e.com")
    git(clone, "config", "user.name", "T")
    return remote, clone


def _leases(remote: Path) -> list[str]:
    out = subprocess.run(["git", "ls-remote", str(remote), lease.LEASES + "*"], capture_output=True, text=True,
                         check=True).stdout
    return sorted(line.split("\t")[1][len(lease.LEASES):] for line in out.splitlines())


def _idle(repo: Path, node: str, session: str = "sid-1") -> ws.WorkerRecord:
    rec = ws.create_record(repo, node, "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", session))
    return ws.set_state(repo, rec, "idle", pid=None)


def _foreign_worker(clone: Path, node: str = "M1.2") -> ws.WorkerRecord:
    """An idle worker in the other clone, holding its lease as a launch there would."""
    rec = _idle(clone, node)
    lease.acquire_lease(clone, rec, new=True)
    return rec


def test_a_linked_worktree_shares_the_checkout_id_and_a_clone_does_not(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    _, clone = _remote_and_clone(tmp_path, repo)
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-wt", str(wt), "dev")
    cid = lease.checkout_id(repo)
    assert cid and lease.checkout_id(repo) == cid and lease.checkout_id(wt) == cid
    assert lease.checkout_id(clone) not in (None, cid)


def test_two_checkouts_share_one_limit(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    remote, clone = _remote_and_clone(tmp_path, repo)
    theirs = _foreign_worker(clone)
    assert _leases(remote) == [f"{lease.checkout_id(clone)}/{theirs.worker_id}"]
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "0 workers active (and 1 leased by other checkouts" in capsys.readouterr().err
    assert ws.list_records(repo) == []


def test_a_foreign_lease_counts_when_its_branch_also_exists_here(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    _, clone = _remote_and_clone(tmp_path, repo)
    git(clone, "branch", "feature/rm-other")
    _foreign_worker(clone)
    git(repo, "branch", "feature/rm-other")   # the same branch name here says nothing about where the worker runs
    rec = _idle(repo, "M1.1")
    with pytest.raises(ws.WorkerError, match=r"0 workers active \(and 1 leased by other checkouts"):
        ops.resume(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state == "idle"


def test_leases_from_another_owner_count(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    _, clone = _remote_and_clone(tmp_path, repo)
    git(clone, "config", "user.name", "Someone Else")
    _foreign_worker(clone)
    rec = _idle(repo, "M1.1")
    with pytest.raises(ws.WorkerError, match=r"leased by other checkouts.*policy max_workers is 1"):
        ops.message(repo, rec.worker_id, "x")
    assert [e.type for e in ws.events_since(repo, rec.worker_id)].count("message") == 0


def test_a_lease_pushed_second_is_refused_and_withdrawn(tmp_path: Path) -> None:
    """Both launches got past their first count; the one that recounts after pushing sees the other and yields."""
    repo, _ = _repo(tmp_path, max_workers=1)
    remote, clone = _remote_and_clone(tmp_path, repo)
    theirs = _foreign_worker(clone)
    mine = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    with pytest.raises(ws.WorkerError, match="leased by other checkouts"):
        lease.acquire_lease(repo, mine, new=True)
    assert _leases(remote) == [f"{lease.checkout_id(clone)}/{theirs.worker_id}"]


def test_the_lease_follows_the_record(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    remote, _clone = _remote_and_clone(tmp_path, repo)
    cid = lease.checkout_id(repo)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 0
    rec = wait_for_worker(repo, "w-0001")
    assert rec.state == "idle" and _leases(remote) == [f"{cid}/w-0001"]   # idle keeps its slot, and its lease
    ops.terminate(repo, "w-0001")
    assert _leases(remote) == []


def test_sync_releases_a_dead_or_stale_workers_lease(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    remote, _clone = _remote_and_clone(tmp_path, repo)
    dead = _idle(repo, "M1.1")
    stale = _idle(repo, "M1.2", "sid-2")
    for rec in (dead, stale):
        lease.acquire_lease(repo, rec, new=True)
    ws.set_state(repo, dead, "running", pid=None)   # its wrapper is gone: sync marks it failed
    ws.set_state(repo, stale, "failed", pid=None)   # closed without its lease released
    assert len(_leases(remote)) == 2
    ops.sync(repo)
    assert ws.load_record(repo, dead.worker_id).state == "failed" and _leases(remote) == []


def test_an_unreachable_remote_counts_local_workers_and_warns_once(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    git(repo, "remote", "add", "origin", str(tmp_path / "missing.git"))
    git(repo, "update-ref", "refs/remotes/origin/dev", "dev")   # as last fetched, before the remote went away
    git(repo, "remote", "set-head", "origin", "dev")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 0
    err = capsys.readouterr().err
    assert err.count("max_workers counted this checkout's workers only, not other checkouts'") == 1
    assert wait_for_worker(repo, "w-0001").state == "idle"   # offline work goes on


def test_a_linked_worktree_counts_the_main_checkouts_workers(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    _idle(repo, "M1.2")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-wt", str(wt), "dev")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(wt)) == 1
    assert "1 workers active, policy max_workers is 1" in capsys.readouterr().err
    assert len(ws.list_records(wt)) == 1   # the one record, seen from the worktree as from the main checkout


def test_an_idle_worker_resumes_in_its_own_slot(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    rec = _idle(repo, "M1.1")
    ops.resume(repo, rec.worker_id)
    assert wait_for_worker(repo, rec.worker_id).state == "idle"


def test_a_resume_is_refused_when_other_workers_fill_the_limit(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    rec = _idle(repo, "M1.1")
    _idle(repo, "M1.2", "sid-2")   # launched under a higher limit, since lowered
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "x", "--repo-root", str(repo)) == 1
    assert "1 workers active, policy max_workers is 1" in capsys.readouterr().err
    assert ws.load_record(repo, rec.worker_id).state == "idle"
    assert [e.type for e in ws.events_since(repo, rec.worker_id)].count("message") == 0
