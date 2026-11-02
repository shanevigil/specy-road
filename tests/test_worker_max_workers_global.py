"""``policy.max_workers`` across checkouts, and for resumed turns (M11.4).

Linked worktrees share the main checkout's ``work/.workers/``; a separate clone
is counted through its claims on the integration branch: one per leaf this
checkout's ``user.name`` claims on a branch this repository has no local branch for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import git
from tests.test_worker_cli import _repo, run_worker_cli, wait_for_worker

from specy_road import worker_ops as ops
from specy_road import worker_state as ws


def _clone_with_claim(tmp_path: Path, repo: Path) -> Path:
    """A second clone of ``repo`` that claims M1.2 and marks M1.1 as T's, pushed to ``repo``'s integration branch."""
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "-b", "dev", str(repo), str(clone))   # only dev is a local branch there
    git(clone, "config", "user.email", "t@e.com")
    git(clone, "config", "user.name", "T")
    reg_path = clone / "roadmap" / "registry.yaml"
    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    reg["entries"][0]["owner"] = "T"
    reg["entries"].append({"codename": "other", "node_id": "M1.2", "branch": "feature/rm-other", "owner": "T"})
    reg_path.write_text(yaml.safe_dump(reg), encoding="utf-8")
    git(clone, "commit", "-qam", "claim M1.2")
    git(clone, "branch", "feature/rm-other")
    git(clone, "push", "-q", "origin", "dev")   # repo has feature/rm-thing checked out, so dev takes the push
    return clone


def _idle(repo: Path, node: str, session: str = "sid-1") -> ws.WorkerRecord:
    rec = ws.create_record(repo, node, "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", session))
    return ws.set_state(repo, rec, "idle", pid=None)


def test_each_clone_counts_the_others_claims(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    clone = _clone_with_claim(tmp_path, repo)
    assert ops.claimed_elsewhere(repo, set()) == ["M1.2"]     # M1.1's branch is local here: its worker is in this checkout
    git(clone, "fetch", "-q", "origin")
    assert ops.claimed_elsewhere(clone, set()) == ["M1.1"]    # and the other way round
    assert ops.claimed_elsewhere(repo, {"M1.2"}) == []        # a leaf with a worker here is not counted twice


def test_two_checkouts_share_one_limit(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    _clone_with_claim(tmp_path, repo)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert ("0 workers active (and 1 claimed in other clones: M1.2), policy max_workers is 1"
            in capsys.readouterr().err)
    assert ws.list_records(repo) == []


def test_a_claim_by_another_user_is_not_counted(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    _clone_with_claim(tmp_path, repo)
    git(repo, "config", "user.name", "Someone Else")
    assert ops.claimed_elsewhere(repo, set()) == []


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


def test_a_resume_is_refused_when_another_clone_fills_the_limit(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    rec = _idle(repo, "M1.1")
    _clone_with_claim(tmp_path, repo)
    with pytest.raises(ws.WorkerError, match=r"0 workers active \(and 1 claimed in other clones: M1.2\)"):
        ops.resume(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state == "idle"
