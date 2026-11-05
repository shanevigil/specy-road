"""M15.25: stash list changes are attributed to the worker whose branch owns each entry."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo

from specy_road import worker_state as ws
from specy_road import worker_turn_check as tc
from specy_road.worker_turn_stash import stash_branch, stash_findings

_HASH = "2afd3b089e9aa06b729d8c791db744a3f174e6bb"
_SUBJECT = "On feature/rm-thing: a-wip"


def _two_workers(tmp_path: Path) -> tuple[Path, ws.WorkerRecord, ws.WorkerRecord]:
    repo = make_review_repo(tmp_path)
    wt_b = tmp_path / "wt-b"
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-other", str(wt_b))
    commit_file(wt_b, "src/b.py", "b = 1\n", "other")
    rec_a = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    rec_b = ws.create_record(repo, "M1.2", "claude-code", "sol", wt_b, branch="feature/rm-other")
    return repo, rec_a, rec_b


def test_stash_branch_reads_on_and_wip_subjects() -> None:
    assert stash_branch("On feature/rm-thing: wip") == "feature/rm-thing"
    assert stash_branch("on feature/rm-x: msg") == "feature/rm-x"
    assert stash_branch("WIP on feature/other: msg") == "feature/other"
    assert stash_branch("On (no branch): detached") is None
    assert stash_branch("WIP on (no branch): 0123abc wip") is None
    assert stash_branch("notes for later") is None


@pytest.mark.parametrize(
    "before,after",
    [
        (None, ((_HASH, _SUBJECT),)),
        ((), None),
    ],
    ids=["unknown_before", "unknown_after"],
)
def test_unknown_stash_snapshot_yields_one_finding_and_no_owner_events(
        tmp_path: Path, before: tuple[tuple[str, str], ...] | None,
        after: tuple[tuple[str, str], ...] | None) -> None:
    repo, rec_a, rec_b = _two_workers(tmp_path)
    found = stash_findings(repo, rec_b, before, after)
    assert len(found) == 1 and found[0]["kind"] == "stash"
    assert "stash state unknown" in found[0]["summary"]
    assert not [e for e in ws.events_since(repo, rec_a.worker_id, 0) if e.type == "post_run_check"]


@pytest.mark.parametrize(
    "observer,expect_kind,expect_owner_events",
    [
        ("self", "stash_rule_violation", 0),
        ("other", "stash_other", 1),
    ],
    ids=["own_branch", "another_workers_branch"],
)
def test_stash_hash_change_on_known_snapshots(
        tmp_path: Path, observer: str, expect_kind: str, expect_owner_events: int) -> None:
    repo, rec_a, rec_b = _two_workers(tmp_path)
    rec = rec_a if observer == "self" else rec_b
    entry = ((_HASH, _SUBJECT),)
    found = stash_findings(repo, rec, (), entry)
    assert len(found) == 1 and found[0]["kind"] == expect_kind
    owner_checks = [e for e in ws.events_since(repo, rec_a.worker_id, 0) if e.type == "post_run_check"]
    assert len(owner_checks) == expect_owner_events


def test_already_attributed_hash_skips_second_observer_and_owner_pop(tmp_path: Path) -> None:
    repo, rec_a, rec_b = _two_workers(tmp_path)
    entry = ((_HASH, _SUBJECT),)
    rec_c = ws.create_record(repo, "M1.3", "claude-code", "opus", repo, branch="dev")
    assert stash_findings(repo, rec_b, (), entry)[0]["kind"] == "stash_other"
    assert len([e for e in ws.events_since(repo, rec_a.worker_id, 0) if e.type == "post_run_check"]) == 1
    assert stash_findings(repo, rec_c, (), entry) == []
    assert len([e for e in ws.events_since(repo, rec_a.worker_id, 0) if e.type == "post_run_check"]) == 1
    assert stash_findings(repo, rec_a, entry, ()) == []
    assert len([e for e in ws.events_since(repo, rec_a.worker_id, 0) if e.type == "post_run_check"]) == 1


def test_another_workers_stash_pop_during_observer_turn_flags_owner_not_observer(tmp_path: Path) -> None:
    repo, rec_a, rec_b = _two_workers(tmp_path)
    (repo / "src" / "a.py").write_text("print('a')\nstashed\n")
    git(repo, "stash", "push", "-q", "-m", "a-wip")
    watch = tc.TurnWatch(repo, rec_b)
    git(repo, "stash", "pop", "-q")
    tc.close_turn(repo, rec_b, watch)
    assert tc.FLAG_POST_RUN not in ws.load_record(repo, rec_b.worker_id).flags
    rec_a = ws.load_record(repo, rec_a.worker_id)
    assert tc.FLAG_POST_RUN in rec_a.flags
    a_checks = [e for e in ws.events_since(repo, rec_a.worker_id, 0) if e.type == "post_run_check"]
    assert len(a_checks) == 1 and a_checks[0].detail["findings"][0]["kind"] == "stash_rule_violation"


def test_another_workers_stash_add_flags_owner_and_notes_observer(tmp_path: Path) -> None:
    repo, rec_a, rec_b = _two_workers(tmp_path)
    watch = tc.TurnWatch(repo, rec_b)
    (repo / "src" / "a.py").write_text("print('a')\nstashed\n")
    git(repo, "stash", "push", "-q", "-m", "a-wip")
    tc.close_turn(repo, rec_b, watch)
    assert tc.FLAG_POST_RUN not in ws.load_record(repo, rec_b.worker_id).flags
    [check] = [e for e in ws.events_since(repo, rec_b.worker_id, 0) if e.type == "post_run_check"]
    assert check.detail["findings"][0]["kind"] == "stash_other"
    assert check.detail["findings"][0]["worker_id"] == rec_a.worker_id
    rec_a = ws.load_record(repo, rec_a.worker_id)
    assert tc.FLAG_POST_RUN in rec_a.flags
    assert len([e for e in ws.events_since(repo, rec_a.worker_id, 0) if e.type == "post_run_check"]) == 1


def test_own_turn_stash_is_a_rule_violation_on_this_worker(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    watch = tc.TurnWatch(repo, rec)
    (repo / "src" / "a.py").write_text("print('a')\nstashed\n")
    git(repo, "stash", "push", "-q", "-m", "self")
    tc.close_turn(repo, rec, watch)
    rec = ws.load_record(repo, rec.worker_id)
    assert tc.FLAG_POST_RUN in rec.flags
    [check] = [e for e in ws.events_since(repo, rec.worker_id, 0) if e.type == "post_run_check"]
    finding = check.detail["findings"][0]
    assert finding["kind"] == "stash_rule_violation"
    assert "executor prompt forbids stashing" in finding["summary"]


def test_stash_with_no_matching_worker_keeps_stash_finding_on_observer(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    before = tc.git_state(repo)
    (repo / "src" / "a.py").write_text("print('a')\ndirty\n")
    sha = git(repo, "stash", "create")
    git(repo, "stash", "store", "-m", "notes for later", sha)
    git(repo, "checkout", "-q", "--", "src/a.py")
    after = tc.git_state(repo)
    found = stash_findings(repo, rec, before.stash, after.stash)
    assert len(found) == 1 and found[0]["kind"] == "stash"
    assert "notes for later" in found[0]["summary"]
