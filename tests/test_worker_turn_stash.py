"""M15.25: stash list changes are attributed to the worker whose branch owns each entry."""

from __future__ import annotations

from pathlib import Path

from tests.review_repo_helpers import commit_file, git, make_review_repo

from specy_road import worker_state as ws
from specy_road import worker_turn_check as tc
from specy_road.worker_turn_stash import stash_branch, stash_findings


def test_stash_branch_reads_on_and_wip_subjects() -> None:
    assert stash_branch("On feature/rm-thing: wip") == "feature/rm-thing"
    assert stash_branch("WIP on feature/other: msg") == "feature/other"
    assert stash_branch("On (no branch): detached") is None
    assert stash_branch("notes for later") is None


def test_another_workers_stash_pop_during_observer_turn_flags_owner_not_observer(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    wt_b = tmp_path / "wt-b"
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-other", str(wt_b))
    commit_file(wt_b, "src/b.py", "b = 1\n", "other")
    rec_a = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    rec_b = ws.create_record(repo, "M1.2", "claude-code", "sol", wt_b, branch="feature/rm-other")
    (repo / "src" / "a.py").write_text("print('a')\nstashed\n")
    git(repo, "stash", "push", "-q", "-m", "a-wip")
    watch = tc.TurnWatch(repo, rec_b)
    git(repo, "stash", "pop", "-q")
    tc.close_turn(repo, rec_b, watch)
    assert tc.FLAG_POST_RUN not in ws.load_record(repo, rec_b.worker_id).flags
    rec_a = ws.load_record(repo, rec_a.worker_id)
    assert tc.FLAG_POST_RUN in rec_a.flags
    a_checks = [e for e in ws.events_since(repo, rec_a.worker_id, 0) if e.type == "post_run_check"]
    assert a_checks[-1].detail["findings"][0]["kind"] == "stash_rule_violation"


def test_another_workers_stash_add_flags_owner_and_notes_observer(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    wt_b = tmp_path / "wt-b"
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-other", str(wt_b))
    commit_file(wt_b, "src/b.py", "b = 1\n", "other")
    rec_a = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    rec_b = ws.create_record(repo, "M1.2", "claude-code", "sol", wt_b, branch="feature/rm-other")
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
    assert ws.events_since(repo, rec_a.worker_id, 0)[-1].detail["findings"][0]["kind"] == "stash_rule_violation"


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
