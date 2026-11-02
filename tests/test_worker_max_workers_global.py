"""``policy.max_workers`` across checkouts, and for resumed turns (M11.4).

Linked worktrees share the main checkout's ``work/.workers/``; every other
checkout is counted through its lease refs on the integration remote
(``refs/specy-road/leases/<checkout-id>/<worker-id>``), whatever branches exist
locally and whoever owns the claims.
"""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
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


def _unreachable(tmp_path: Path, repo: Path) -> None:
    git(repo, "remote", "add", "origin", str(tmp_path / "missing.git"))
    git(repo, "update-ref", "refs/remotes/origin/dev", "dev")   # as last fetched, before the remote went away
    git(repo, "remote", "set-head", "origin", "dev")


def _rejecting(remote: Path) -> None:
    """The remote stays readable but refuses every lease ref push."""
    hook = remote / "hooks" / "update"
    hook.write_text('#!/bin/sh\ncase "$1" in refs/specy-road/*) echo "no leases here" >&2; exit 1;; esac\nexit 0\n')
    hook.chmod(0o755)


def test_an_unreachable_remote_refuses_unless_offline(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    _unreachable(tmp_path, repo)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "cannot reach origin to count other checkouts' workers" in err and "--offline" in err
    assert ws.list_records(repo) == []
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--offline", "--repo-root", str(repo)) == 0
    assert capsys.readouterr().err.count("--offline: the global max_workers limit was not verified") == 1
    rec = wait_for_worker(repo, "w-0001")
    assert rec.state == "idle"
    with pytest.raises(ws.WorkerError, match="cannot reach origin to push the lease for w-0001.*--offline"):
        ops.resume(repo, rec.worker_id)
    assert run_worker_cli("worker", "resume", rec.worker_id, "--offline", "--repo-root", str(repo)) == 0
    assert wait_for_worker(repo, rec.worker_id).state == "idle"
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "x", "--offline", "--repo-root", str(repo)) == 0
    assert wait_for_worker(repo, rec.worker_id).state == "idle"


def test_offline_is_bound_into_the_op_id(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    _unreachable(tmp_path, repo)
    args = ("worker", "delegate", "M1.1", "--model", "opus", "--op-id", "op-1", "--repo-root", str(repo))
    assert run_worker_cli(*args, "--offline") == 0
    wait_for_worker(repo, "w-0001")
    capsys.readouterr()
    assert run_worker_cli(*args) != 0
    assert "ran with different arguments" in capsys.readouterr().err


def test_a_rejected_lease_push_refuses_message_and_resume(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    remote, _clone = _remote_and_clone(tmp_path, repo)
    _rejecting(remote)
    rec = _idle(repo, "M1.1")
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "x", "--repo-root", str(repo)) == 1
    assert f"origin rejected the lease for {rec.worker_id}" in capsys.readouterr().err
    with pytest.raises(ws.WorkerError, match=f"origin rejected the lease for {rec.worker_id}"):
        ops.resume(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state == "idle"
    assert [e.type for e in ws.events_since(repo, rec.worker_id)].count("message") == 0


def test_a_rejected_lease_push_refuses_a_launch(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    remote, _clone = _remote_and_clone(tmp_path, repo)
    _rejecting(remote)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "origin rejected the lease for w-0001" in capsys.readouterr().err
    assert ws.load_record(repo, "w-0001").state == "failed" and _leases(remote) == []


def test_sync_keeps_a_lease_created_after_its_first_read(tmp_path: Path, monkeypatch) -> None:
    """The sweep reads the remote, then a launch lands before it deletes: the new worker's lease survives."""
    repo, _ = _repo(tmp_path)
    remote, _clone = _remote_and_clone(tmp_path, repo)
    cid = lease.checkout_id(repo)
    stale = _idle(repo, "M1.1")
    lease.acquire_lease(repo, stale, new=True)
    ws.set_state(repo, stale, "failed", pid=None)   # closed without its lease released
    real, late = lease.run, []

    def run(args, cwd, **kw):
        if args[0] == "fetch" and args[-1].startswith(f"+{lease.LEASES}") and not late:   # the sweep's read
            late.append(_idle(repo, "M1.2", "sid-2"))   # a launch between the sweep's start and its delete
            lease.acquire_lease(repo, late[0], new=True)
        return real(args, cwd, **kw)

    monkeypatch.setattr(lease, "run", run)
    ops.sync(repo)
    assert _leases(remote) == [f"{cid}/{late[0].worker_id}"]


def _id_file(repo: Path) -> Path:
    return repo / ".git" / "specy-road-checkout-id"


def test_a_missing_checkout_id_is_created_and_the_count_still_holds(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    _, clone = _remote_and_clone(tmp_path, repo)
    _foreign_worker(clone)
    _id_file(repo).unlink(missing_ok=True)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "0 workers active (and 1 leased by other checkouts" in capsys.readouterr().err
    assert re.fullmatch(r"[0-9a-f]{32}", _id_file(repo).read_text(encoding="utf-8").strip())
    assert ws.list_records(repo) == []


@pytest.mark.parametrize("content", ["", "\n", "half-writ"])
def test_an_empty_or_unusable_checkout_id_is_rewritten_and_the_limit_holds(tmp_path: Path, capsys,
                                                                           content: str) -> None:
    """An id file with no uuid in it is uninitialized, never "no id, so no leases": a new id is written and counted."""
    repo, _ = _repo(tmp_path, max_workers=1)
    _, clone = _remote_and_clone(tmp_path, repo)
    _foreign_worker(clone)
    _id_file(repo).write_text(content, encoding="utf-8")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "0 workers active (and 1 leased by other checkouts" in capsys.readouterr().err
    assert re.fullmatch(r"[0-9a-f]{32}", _id_file(repo).read_text(encoding="utf-8").strip())
    assert ws.list_records(repo) == []


def test_a_launch_after_an_empty_checkout_id_leases_under_the_new_one(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    remote, _clone = _remote_and_clone(tmp_path, repo)
    _id_file(repo).write_text("", encoding="utf-8")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 0
    wait_for_worker(repo, "w-0001")
    assert _leases(remote) == [f"{_id_file(repo).read_text(encoding='utf-8').strip()}/w-0001"]


def test_a_checkout_id_that_cannot_be_written_refuses_the_launch(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    _remote_and_clone(tmp_path, repo)
    (_id_file(repo) / "x").mkdir(parents=True)   # not a file, and not one that can be set aside and removed
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "cannot write the checkout id" in capsys.readouterr().err
    assert ws.list_records(repo) == []


def test_offline_still_counts_the_lease_refs_last_fetched(tmp_path: Path, capsys) -> None:
    """--offline skips the push and the fetch; a foreign worker known from the last fetch still counts."""
    repo, _ = _repo(tmp_path, max_workers=1)
    _, clone = _remote_and_clone(tmp_path, repo)
    _foreign_worker(clone)
    ops.sync(repo)   # an online worker command: fetches the lease refs into this checkout
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--offline", "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "0 workers active (and 1 leased by other checkouts" in err and "limit was not verified" in err
    assert ws.list_records(repo) == []
    rec = _idle(repo, "M1.1")   # an idle worker here: resuming it offline is refused at the limit too
    assert run_worker_cli("worker", "resume", rec.worker_id, "--offline", "--repo-root", str(repo)) == 1
    assert "leased by other checkouts" in capsys.readouterr().err
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "x", "--offline", "--repo-root", str(repo)) == 1
    assert "leased by other checkouts" in capsys.readouterr().err
    assert ws.load_record(repo, rec.worker_id).state == "idle"


def test_offline_warns_and_launches_on_a_stale_mirror(tmp_path: Path, capsys) -> None:
    """The local-only escape: a foreign worker started after the last fetch is not seen, and the warning says so."""
    repo, _ = _repo(tmp_path, max_workers=1)
    remote, clone = _remote_and_clone(tmp_path, repo)
    ops.sync(repo)   # the last fetch: no foreign worker yet
    theirs = _foreign_worker(clone)   # started since, so this checkout's mirror is stale
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--offline", "--repo-root", str(repo)) == 0
    assert capsys.readouterr().err.count("warning: --offline: the global max_workers limit was not verified") == 1
    assert wait_for_worker(repo, "w-0001").state == "idle"
    assert _leases(remote) == [f"{lease.checkout_id(clone)}/{theirs.worker_id}"]   # and it pushed no lease


def test_concurrent_first_calls_agree_on_one_checkout_id(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    with ThreadPoolExecutor(8) as pool:
        ids = list(pool.map(lambda _i: lease.checkout_id(repo), range(32)))
    assert len(set(ids)) == 1 and ids[0] == _id_file(repo).read_text(encoding="utf-8").strip()
    assert list(_id_file(repo).parent.glob(".specy-road-checkout-id.*")) == []   # no temporary file left behind


def test_an_adopted_worker_in_another_clone_counts(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    remote, clone = _remote_and_clone(tmp_path, repo)
    adopted = ops.adopt(clone, "M1.1", "claude-code", str(uuid.uuid4()))
    assert _leases(remote) == [f"{lease.checkout_id(clone)}/{adopted.worker_id}"]
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "0 workers active (and 1 leased by other checkouts" in capsys.readouterr().err
    assert ws.list_records(repo) == []


def test_an_adopt_whose_lease_cannot_be_pushed_is_refused(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    remote, clone = _remote_and_clone(tmp_path, repo)
    _rejecting(remote)
    with pytest.raises(ws.WorkerError, match="origin rejected the lease for w-0001"):
        ops.adopt(clone, "M1.1", "claude-code", str(uuid.uuid4()))
    assert [r.state for r in ws.list_records(clone)] == ["terminated"]   # closed: nothing here holds the slot unseen


def test_sync_pushes_a_lease_for_an_active_worker_without_one(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    remote, _clone = _remote_and_clone(tmp_path, repo)
    rec = _idle(repo, "M1.1")   # registered before leases existed, or launched --offline
    assert _leases(remote) == []
    ops.sync(repo)
    assert _leases(remote) == [f"{lease.checkout_id(repo)}/{rec.worker_id}"]


def test_a_retry_returns_the_existing_worker_while_the_remote_is_down(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    _unreachable(tmp_path, repo)
    rec = _idle(repo, "M1.1")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--json", "--repo-root", str(repo)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["worker_id"] == rec.worker_id and out["created"] is False
    ws.set_state(repo, rec, "terminated", pid=None)   # an actual launch still needs the global count
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "cannot reach origin to count other checkouts' workers" in capsys.readouterr().err
    assert [r.worker_id for r in ws.list_records(repo)] == [rec.worker_id]


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
