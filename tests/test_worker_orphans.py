"""Held workers whose leaf is over (M11.57): they free their ``max_workers`` slot, show as orphaned in
``worker list`` / ``sync``, end in one ``worker terminate --orphaned``, and ``finish-this-task`` ends the
finished leaf's own.
"""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import NODE, commit_file, git
from tests.test_branch_cleanup import BR, _exit, _merge_mode_repo
from tests.test_worker_cli import _repo, run_worker_cli, wait_for_worker

from specy_road import worker_lease as lease
from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import finish_task
from specy_road.worker_orphans import end_finished_workers, holding_slots, orphans

OTHER = "feature/rm-other"


def _worker(repo: Path, node: str, state: str, *, branch: str | None = None, worktree: Path | None = None,
            session: str | None = None) -> ws.WorkerRecord:
    rec = ws.create_record(repo, node, "claude-code", "opus", worktree or repo, branch=branch)
    if session:
        ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", session))
    return ws.set_state(repo, rec, state, pid=None)


def _on_dev(repo: Path, rel: str, edit, msg: str) -> None:
    """Commit ``edit(text)`` to ``rel`` on the integration branch; the checkout stays on the leaf's branch."""
    git(repo, "checkout", "-q", "dev")
    text = (repo / rel).read_text(encoding="utf-8")
    if (after := edit(text)) != text:   # an unclaim of a leaf never claimed changes nothing
        commit_file(repo, rel, after, msg)
    git(repo, "checkout", "-q", BR)


def _registry(entries) -> Callable[[str], str]:
    def edit(text: str) -> str:
        reg = yaml.safe_load(text)
        reg["entries"] = entries(reg["entries"])
        return yaml.safe_dump(reg)
    return edit


def _claim(repo: Path, node: str, branch: str) -> None:
    """A registry claim for ``node``, registered on the integration branch as pickup registers it."""
    row = {"codename": "other", "node_id": node, "branch": branch, "touch_zones": ["src"],
           "implementation_review": "pending"}
    _on_dev(repo, "roadmap/registry.yaml", _registry(lambda es: [*es, row]), f"claim {node}")


def _unclaim(repo: Path, node: str) -> None:
    """The claim removed on the integration branch, as ``registry-prune --remove`` or a landed finish does."""
    _on_dev(repo, "roadmap/registry.yaml", _registry(lambda es: [e for e in es if e["node_id"] != node]),
            f"unclaim {node}")


def _status_on_dev(repo: Path, node: str, status: str) -> None:
    """``node``'s status in the integration branch's graph (added to it, keyed per node, when absent)."""
    def edit(text: str) -> str:
        doc = json.loads(text)
        n = next((x for x in doc["nodes"] if x["id"] == node), None)
        if n is None:
            n = copy.deepcopy(NODE)
            digit = node.rsplit(".", 1)[1]
            n.update(id=node, codename=f"other{digit}", node_key=f"{digit * 8}-{digit * 4}-5{digit * 3}-8{digit * 3}-{digit * 12}")
            doc["nodes"].append(n)
        n["status"] = status
        return json.dumps(doc)
    _on_dev(repo, "roadmap/phases/M1.json", edit, f"{node} {status}")


def _complete_on_dev(repo: Path, node: str) -> None:
    _status_on_dev(repo, node, "Complete")


def _land(repo: Path, node: str) -> None:
    """The leaf as a landed finish leaves it on the integration branch: Complete, its claim removed."""
    _complete_on_dev(repo, node)
    _unclaim(repo, node)


def _stale_origin(repo: Path, rev: str = "dev") -> None:
    """``origin/dev`` pinned at ``rev``: a remote-tracking ref last fetched then."""
    git(repo, "update-ref", "refs/remotes/origin/dev", rev)


# --- A1: what holds a slot: only a leaf unclaimed AND Complete at every integration ref frees it ---------------

def test_a_completed_worker_on_a_landed_leaf_frees_its_slot(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    mine = _worker(repo, "M1.1", "idle", session="sid-1")
    _claim(repo, "M1.2", OTHER)
    done = _worker(repo, "M1.2", "completed", branch=OTHER)
    _land(repo, "M1.2")
    assert orphans(repo) == {done.worker_id: "M1.2 is Complete and unclaimed on dev"}
    assert [r.worker_id for r in holding_slots(repo, ws.list_records(repo))] == [mine.worker_id]
    ops.resume(repo, mine.worker_id)   # the one slot is free: the finished leaf's worker no longer holds it
    assert wait_for_worker(repo, mine.worker_id).state == "idle"
    assert ws.load_record(repo, done.worker_id).state == "completed"   # freed, not closed


@pytest.mark.parametrize("half", ["claim gone, not Complete", "Complete, still claimed"])
def test_either_half_alone_keeps_the_worker(tmp_path: Path, capsys, half: str) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    mine = _worker(repo, "M1.1", "idle", session="sid-1")
    if half.startswith("Complete"):
        _claim(repo, "M1.2", OTHER)
        _complete_on_dev(repo, "M1.2")
    else:
        _status_on_dev(repo, "M1.2", "In Progress")   # delegated under a claim since removed; the leaf is open
    held = _worker(repo, "M1.2", "idle", branch=OTHER)
    assert orphans(repo) == {}
    assert run_worker_cli("worker", "resume", mine.worker_id, "--repo-root", str(repo)) == 1
    assert f"1 idle: {held.worker_id}" in capsys.readouterr().err


def test_a_completed_worker_on_an_unfinished_leaf_holds_its_slot(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    mine = _worker(repo, "M1.1", "idle", session="sid-1")
    _claim(repo, "M1.2", OTHER)
    held = _worker(repo, "M1.2", "completed", branch=OTHER)   # a review block may still send it a fix round
    assert orphans(repo) == {}
    assert run_worker_cli("worker", "resume", mine.worker_id, "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert (f"1 workers active, policy max_workers is 1; 1 completed: {held.worker_id}; "
            f"`specy-road worker terminate {held.worker_id}` frees it") in err
    assert ws.load_record(repo, mine.worker_id).state == "idle"


def test_a_running_worker_on_a_landed_leaf_still_holds_its_slot(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    _land(repo, "M1.2")
    running = _worker(repo, "M1.2", "running", branch=OTHER)   # still at work: not this rule's to free
    assert orphans(repo) == {} and holding_slots(repo, [running]) == [running]


def test_a_gone_worktree_alone_keeps_the_worker(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    wt = tmp_path / "lane"
    shutil.copytree(repo, wt)
    rec = _worker(repo, "M1.1", "idle", branch=BR, worktree=wt)
    shutil.rmtree(wt)
    assert orphans(repo) == {}   # M1.1 is still claimed and open on dev
    assert holding_slots(repo, [rec]) == [rec]


@pytest.mark.parametrize("stale", ["Complete and unclaimed", "Complete, still claimed"])
def test_a_reopened_leaf_keeps_its_worker_against_a_stale_complete_integration_ref(
        tmp_path: Path, capsys, stale: str) -> None:
    """origin/dev last fetched while the leaf was Complete; dev has since reopened it, claimed. The refs
    disagree, so the worker keeps its slot, is not orphaned, and survives terminate --orphaned."""
    repo, _ = _repo(tmp_path, max_workers=1)
    mine = _worker(repo, "M1.1", "idle", session="sid-1")
    _claim(repo, "M1.2", OTHER)
    held = _worker(repo, "M1.2", "completed", branch=OTHER)
    if stale.startswith("Complete and"):
        _land(repo, "M1.2")
        _stale_origin(repo)
        _claim(repo, "M1.2", OTHER)
    else:
        _complete_on_dev(repo, "M1.2")
        _stale_origin(repo)
    _status_on_dev(repo, "M1.2", "In Progress")   # reopened on dev
    assert run_worker_cli("worker", "list", "--json", "--repo-root", str(repo)) == 0
    assert {w["worker_id"]: w["orphaned"] for w in json.loads(capsys.readouterr().out)["workers"]} == {
        mine.worker_id: None, held.worker_id: None}
    assert holding_slots(repo, [held]) == [held]
    assert run_worker_cli("worker", "resume", mine.worker_id, "--repo-root", str(repo)) == 1
    assert f"1 completed: {held.worker_id}" in capsys.readouterr().err
    assert run_worker_cli("worker", "terminate", "--orphaned", "--repo-root", str(repo)) == 0
    assert "No orphaned workers." in capsys.readouterr().out
    assert ws.load_record(repo, held.worker_id).state == "completed"


def test_a_landing_not_yet_on_the_remote_tracking_ref_keeps_the_worker_until_it_is(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    _claim(repo, "M1.2", OTHER)
    _stale_origin(repo)   # origin/dev: still claimed, not in its graph
    rec = _worker(repo, "M1.2", "completed", branch=OTHER)
    _land(repo, "M1.2")
    assert orphans(repo) == {} and holding_slots(repo, [rec]) == [rec]
    _stale_origin(repo)   # pushed and fetched: the refs agree
    assert orphans(repo) == {rec.worker_id: "M1.2 is Complete and unclaimed on dev and origin/dev"}


def test_an_older_lanes_registry_snapshot_neither_frees_nor_keeps_a_worker(tmp_path: Path, capsys) -> None:
    """Two linked worktrees whose registries differ judge a shared worker the same way: by the integration
    branch. One that predates a live claim must not free or end its worker; one that still holds a claim
    since landed must not keep it."""
    repo, _ = _repo(tmp_path, max_workers=1)
    mine = _worker(repo, "M1.1", "idle", session="sid-1")
    old = tmp_path / "old-lane"
    git(repo, "worktree", "add", "-q", "--detach", str(old), BR)   # its registry has no M1.2 claim
    _claim(repo, "M1.2", OTHER)
    new = tmp_path / "new-lane"
    git(repo, "worktree", "add", "-q", "--detach", str(new), "dev")   # its registry has the claim
    held = _worker(repo, "M1.2", "completed", branch=OTHER)
    for lane in (old, new):
        assert run_worker_cli("worker", "list", "--json", "--repo-root", str(lane)) == 0
        assert {w["worker_id"]: w["orphaned"] for w in json.loads(capsys.readouterr().out)["workers"]} == {
            mine.worker_id: None, held.worker_id: None}
        assert run_worker_cli("worker", "terminate", "--orphaned", "--repo-root", str(lane)) == 0
        assert "No orphaned workers." in capsys.readouterr().out
        assert run_worker_cli("worker", "resume", mine.worker_id, "--repo-root", str(lane)) == 1   # still held
        assert f"1 completed: {held.worker_id}" in capsys.readouterr().err
    assert ws.load_record(repo, held.worker_id).state == "completed"

    _land(repo, "M1.2")   # the leaf really lands; the new lane's snapshot still shows the claim
    assert run_worker_cli("worker", "terminate", "--orphaned", "--repo-root", str(new)) == 0
    assert f"{held.worker_id}: terminated (M1.2 is Complete and unclaimed on dev)" in capsys.readouterr().out
    assert ws.load_record(repo, mine.worker_id).state == "idle"


def test_an_unreadable_integration_registry_keeps_the_worker(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    _land(repo, "M1.2")
    rec = _worker(repo, "M1.2", "completed", branch=OTHER)
    _on_dev(repo, "roadmap/registry.yaml", lambda _text: "entries: [\n", "break the registry")
    assert orphans(repo) == {} and holding_slots(repo, [rec]) == [rec]


def test_no_integration_branch_keeps_the_worker(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    _land(repo, "M1.2")
    rec = _worker(repo, "M1.2", "completed", branch=OTHER)
    git(repo, "branch", "-q", "-m", "dev", "elsewhere")   # neither dev nor origin/dev: nothing authoritative to read
    assert orphans(repo) == {} and holding_slots(repo, [rec]) == [rec]


# --- A2: the refusal names running and held workers apart ---------------------------------------------------------

def test_the_refusal_lists_running_and_held_workers_separately(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    recs = [_worker(repo, "M1.1", s) for s in ("running", "starting", "completed")]
    msg = str(lease.slot_error(recs, [], 3))
    assert msg == ("3 workers active, policy max_workers is 3; 2 running: w-0001, w-0002; 1 completed: w-0003; "
                   "`specy-road worker terminate w-0003` frees it, or wait for a running one to finish or raise the limit")
    assert str(lease.slot_error(recs[:2], ["c/w-0009"], 3)) == (
        "2 workers active (and 1 leased by other checkouts: c/w-0009), policy max_workers is 3; "
        "2 running: w-0001, w-0002; wait for one to finish or raise the limit")


# --- A3: list, sync, terminate --orphaned --------------------------------------------------------------------------

def _three(tmp_path: Path) -> tuple[Path, ws.WorkerRecord, ws.WorkerRecord, ws.WorkerRecord]:
    """Two orphans on landed leaves (one whose worktree is gone too) and one that still owns its open leaf."""
    repo, _ = _repo(tmp_path)
    _land(repo, "M1.2")
    _land(repo, "M1.3")
    landed = _worker(repo, "M1.2", "completed", branch=OTHER)
    wt = tmp_path / "lane"
    wt.mkdir()
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-lane", str(wt), "dev")
    no_tree = _worker(repo, "M1.3", "idle", branch="feature/rm-lane", worktree=wt)
    git(repo, "worktree", "remove", "--force", str(wt))
    keep = _worker(repo, "M1.1", "idle", branch=BR)
    return repo, landed, no_tree, keep


def test_list_and_sync_mark_orphaned_workers(tmp_path: Path, capsys) -> None:
    repo, unclaimed, no_tree, keep = _three(tmp_path)
    assert run_worker_cli("worker", "list", "--repo-root", str(repo)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any(ln.startswith(unclaimed.worker_id) and "orphaned: M1.2 is Complete and unclaimed on dev" in ln
               for ln in lines)
    assert any(ln.startswith(no_tree.worker_id) and "orphaned: M1.3 is Complete and unclaimed on dev; worktree" in ln
               for ln in lines)
    assert any(ln.startswith(keep.worker_id) and "orphaned" not in ln for ln in lines)
    assert "(`specy-road worker terminate --orphaned` ends them)" in lines
    assert run_worker_cli("worker", "list", "--json", "--repo-root", str(repo)) == 0
    rows = {w["worker_id"]: w["orphaned"] for w in json.loads(capsys.readouterr().out)["workers"]}
    assert rows[keep.worker_id] is None and rows[unclaimed.worker_id] and rows[no_tree.worker_id]

    assert run_worker_cli("worker", "sync", "--ack", "--json", "--repo-root", str(repo)) == 0
    assert set(json.loads(capsys.readouterr().out)["orphaned"]) == {unclaimed.worker_id, no_tree.worker_id}
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0   # no new events: orphans still shown
    out = capsys.readouterr().out
    assert "No new worker events." in out and f"orphaned: {unclaimed.worker_id} (M1.2 is Complete" in out


def test_terminate_orphaned_ends_every_orphan_in_one_step(tmp_path: Path, capsys) -> None:
    repo, unclaimed, no_tree, keep = _three(tmp_path)
    assert run_worker_cli("worker", "terminate", "--orphaned", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert f"{unclaimed.worker_id}: terminated (M1.2 is Complete and unclaimed on dev)" in out
    assert f"{no_tree.worker_id}: terminated (M1.3 is Complete and unclaimed on dev; worktree" in out
    assert [ws.load_record(repo, r.worker_id).state for r in (unclaimed, no_tree, keep)] == ["terminated", "terminated", "idle"]
    assert ws.events_since(repo, unclaimed.worker_id)[-1].type == "terminated"
    assert run_worker_cli("worker", "terminate", "--orphaned", "--repo-root", str(repo)) == 0
    assert "No orphaned workers." in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["w-0001", "--orphaned"], ["--orphaned", "--op-id", "x"]])
def test_terminate_takes_one_worker_or_orphaned(tmp_path: Path, argv: list[str]) -> None:
    repo, _ = _repo(tmp_path)
    assert run_worker_cli("worker", "terminate", *argv, "--repo-root", str(repo)) == 2   # argparse's usage error


def test_terminate_one_worker_still_works(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    rec = _worker(repo, "M1.1", "completed", branch=BR)
    assert run_worker_cli("worker", "terminate", rec.worker_id, "--repo-root", str(repo)) == 0
    assert f"{rec.worker_id}: terminated" in capsys.readouterr().out
    assert ws.load_record(repo, rec.worker_id).state == "terminated"


# --- A3: finish-this-task ------------------------------------------------------------------------------------------

def test_finish_terminates_the_finished_leafs_idle_and_completed_workers(tmp_path: Path, monkeypatch, capsys) -> None:
    repo, _bare = _merge_mode_repo(tmp_path, monkeypatch)
    done = _worker(repo, "M1.1", "completed", branch=BR)
    idle = _worker(repo, "M1.1", "idle", branch=BR)
    running = _worker(repo, "M1.1", "running", branch=BR)   # mid-turn: finish leaves it alone
    other = _worker(repo, "M1.2", "idle", branch=OTHER)     # another leaf's
    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert f"[ok] terminated worker {done.worker_id}: M1.1 finished while {done.worker_id} was completed" in out
    assert f"[ok] terminated worker {idle.worker_id}: M1.1 finished while {idle.worker_id} was idle" in out
    states = {r.worker_id: r.state for r in ws.list_records(repo)}
    assert states == {done.worker_id: "terminated", idle.worker_id: "terminated",
                      running.worker_id: "running", other.worker_id: "idle"}
    assert ws.events_since(repo, done.worker_id)[-1].type == "terminated"


def test_end_finished_workers_with_none_ends_nothing(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    assert end_finished_workers(repo, "M1.1") == []
    assert not ws.workers_dir(repo).exists()   # no lock taken: a checkout with no workers gets no work/.workers/
