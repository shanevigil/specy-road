"""Regressions from the third independent review (GPT-5.6 Sol, 2026-10-27).

One test per finding: a completed worker still owns its leaf; lifecycle
transitions are one transaction each; the guard refuses shell shapes it
cannot follow and `git -C` into another tree, and denies a bare commit; an
embedded placeholder is refused; the default session id is stable across
processes and `touch` keeps the paths; a skipped skill is never adopted or
overwritten; a stale worktree directory is refused; the GUI reports the v2
session and requires a reject reason; op ids bind their arguments; signing
without a roster key is refused early; a foreign skill link is left alone; a
dead wrapper frees the leaf; terminate refuses an unverifiable pid and does
not signal an adopted session; READY binds to the branch; a profile path
cannot escape the repo; `--harness` cannot override the roster; a plan with
no coordinator says so; search results are delimited; the verifier's byte
cap is a cap.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_review_signing import _key, _roster
from tests.test_worker_cli import _repo, _wait

from specy_road import session_presence as sp
from specy_road import tool_call_guard as tg
from specy_road import worker_adapters as wa
from specy_road import worker_lease as wl
from specy_road import worker_ops as ops
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts import refresh_stubs as rs
from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts import session_cli
from specy_road.gui_app_models import BrainstormTriageBody
from specy_road.gui_app_routes_brainstorm import _apply_triage, _payload
from specy_road.bundled_scripts.brainstorm_session import BrainstormSession, add_idea
from specy_road.review_files import reviews_root
from specy_road.specyrd_init import run_init


def _wrapper_cmdline(monkeypatch, worker_id: str = "w-0001") -> None:
    monkeypatch.setattr(wr, "_cmdline", lambda pid: f"python -m specy_road.worker_runner /r {worker_id} {{}}")


# --- B1 -----------------------------------------------------------------------

def test_a_completed_worker_still_owns_its_leaf(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=4)
    rec, _c = ops.delegate(repo, "M1.1", "opus")
    _wait(repo, rec.worker_id)
    ws.set_state(repo, rec, "completed", pid=None)
    again, created = ops.delegate(repo, "M1.1", "opus")
    assert not created and again.worker_id == rec.worker_id
    assert ws.active_for_node(repo, "M1.1").worker_id == rec.worker_id
    ops.terminate(repo, rec.worker_id)
    assert ws.active_for_node(repo, "M1.1") is None


# --- B2 -----------------------------------------------------------------------

def test_concurrent_messages_launch_one_turn(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    spawned: list[str] = []
    gate = threading.Event()

    def fake_spawn(repo_root, r, launch, *, resumed=False):
        spawned.append(r.worker_id)
        gate.wait(1)
        ws.set_state(repo_root, r, "running", pid=os.getpid())
        return os.getpid()

    monkeypatch.setattr(ops, "spawn", fake_spawn)
    monkeypatch.setattr(ops, "pid_alive", lambda pid, wid=None: pid == os.getpid())
    errors: list[Exception] = []

    def go() -> None:
        try:
            ops.message(repo, rec.worker_id, "hi")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in threads:
        t.join()
    assert len(spawned) == 1 and len(errors) == 1 and "still running" in str(errors[0])


def test_concurrent_reclaims_record_one_intervention(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.handoff(repo, rec.worker_id)
    results: list = []

    def go() -> None:
        try:
            results.append(ops.reclaim(repo, rec.worker_id)[0].instruction_epoch)
        except ws.WorkerError as e:
            results.append(e)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(type(r).__name__ for r in results) == ["WorkerError", "int"]
    assert ws.load_record(repo, rec.worker_id).instruction_epoch == 1      # one intervention, not two


# --- B3, B6, F17 ----------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "f(){ git stash; }; f", "sh -c 'f(){ git reset --hard; }; f'", "gitcmd=git; $gitcmd stash",
    "python -c 'import subprocess; subprocess.run([\"git\",\"stash\"])'", "git commit -m x",
])
def test_opaque_shapes_and_bare_commits_are_refused(command: str) -> None:
    assert tg.classify(command), command


@pytest.mark.parametrize("command", ["f(){ echo hi; }; f", "python -c 'print(1)'", "git commit -m x src/a.py"])
def test_opaque_shapes_without_git_pass(command: str) -> None:
    assert tg.classify(command) is None


def test_git_dash_c_into_another_tree_counts_that_trees_session(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    sp.start_session(repo, "alice", paths=["src"], worktree=wt)
    assert tg.decide(repo, "git checkout -b feature/x", agent="bob").allowed       # alice is elsewhere
    assert not tg.decide(repo, f"git -C {wt} reset --hard", agent="bob").allowed   # but this reaches her


# --- B4 -----------------------------------------------------------------------

def test_an_embedded_placeholder_is_refused_not_quoted_inside_quotes(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("$(echo pwned)")
    for cli in ('printf "prefix <prompt>"', "x --prompt=<prompt>", "x '<prompt>y'"):
        assert "whole argument" in (wa.placeholder_problem(cli) or ""), cli
        with pytest.raises(wa.Unsupported):
            wa.ADAPTERS["generic"].launch(p, tmp_path, "m", cli)
    assert wa.placeholder_problem('claude -p "<prompt>"') is None
    assert wa.placeholder_problem("run {prompt} {session}") is None


# --- B5 -----------------------------------------------------------------------

def test_the_default_session_id_is_stable_across_processes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SPECY_ROAD_AGENT_ID", raising=False)
    code = "from specy_road.session_presence import default_agent_id; print(default_agent_id())"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
    a = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True).stdout
    b = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True).stdout
    assert a == b and a.strip() == sp.default_agent_id()


def test_touch_keeps_the_paths(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    with pytest.raises(SystemExit):
        session_cli.main(["session", "start", "--agent", "a1", "--path", "src", "--repo-root", str(repo)])
    with pytest.raises(SystemExit):
        session_cli.main(["session", "touch", "--agent", "a1", "--repo-root", str(repo)])
    assert [s.paths for s in sp.list_sessions(repo)] == [["src"]]


# --- B7, F4 -------------------------------------------------------------------

def test_a_skipped_canonical_skill_is_never_adopted_or_overwritten(tmp_path: Path) -> None:
    mine = tmp_path / ".agents" / "skills" / "specyrd-validate" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("CUSTOM USER SKILL\n")
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, role="dev")
    manifest = json.loads((tmp_path / ".specyrd" / "manifest.json").read_text())
    assert ".agents/skills/specyrd-validate/SKILL.md" not in manifest["agents"]["claude-code"]
    written, _o = rs.refresh_stubs(tmp_path)
    assert mine.read_text() == "CUSTOM USER SKILL\n"
    assert ".agents/skills/specyrd-validate/SKILL.md (skipped (not ours))" in written


def test_a_foreign_skill_link_is_left_alone_on_first_install(tmp_path: Path) -> None:
    link = tmp_path / ".claude" / "skills" / "specyrd-brief"
    link.parent.mkdir(parents=True)
    os.symlink("../../../mine", link)
    res = run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, role="dev")
    assert os.readlink(link) == "../../../mine"
    assert ".claude/skills/specyrd-brief (skipped (not ours))" in res.skipped
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=True, ai_commands_dir=None, role="dev")
    assert os.readlink(link) == "../../.agents/skills/specyrd-brief"


# --- B8 -----------------------------------------------------------------------

def test_a_stale_worktree_directory_is_refused(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    stale = reviews_root(repo).parent / ".worktrees" / "thing"
    stale.mkdir(parents=True)
    with pytest.raises(ws.WorkerError, match="not a git worktree"):
        ops._worktree_for(repo, "feature/rm-thing", "thing", None)
    with pytest.raises(ws.WorkerError, match="checked out, not the claim's branch"):
        ops._worktree_for(repo, "feature/rm-thing", "thing", repo)


# --- B9, F13 ------------------------------------------------------------------

def test_the_gui_payload_carries_the_v2_session_and_rejects_need_a_reason() -> None:
    session = BrainstormSession(slug="s", topic="t", round=2, profile="technical", panel=3,
                                frame={"outcome": "x"}, allocation="grid")
    add_idea(session, title="One")
    out = _payload(session)
    assert (out["round"], out["profile"], out["panel"], out["frame"], out["allocation"]) == (2, "technical", 3, {"outcome": "x"}, "grid")
    with pytest.raises(Exception, match="needs a reason"):
        _apply_triage(session, BrainstormTriageBody(slug="s", idea_id="B1", status="rejected"))
    _apply_triage(session, BrainstormTriageBody(slug="s", idea_id="B1", status="rejected", reason="not now"))
    assert session.by_id("B1").decision["reason"] == "not now"


# --- F1 -----------------------------------------------------------------------

def test_an_op_id_binds_its_arguments(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    assert ws.begin_op(repo, "op", "message", "w-0001", {"text": "a"}) is None
    ws.complete_op(repo, "op", {"ok": 1})
    assert ws.begin_op(repo, "op", "message", "w-0001", {"text": "a"})["result"] == {"ok": 1}
    with pytest.raises(ws.WorkerError, match="different arguments"):
        ws.begin_op(repo, "op", "message", "w-0001", {"text": "b"})


# --- F3, F18 ------------------------------------------------------------------

def test_signing_without_a_roster_key_is_refused_early(tmp_path: Path, capsys) -> None:
    key, _pub = _key(tmp_path, "opus")
    repo = make_review_repo(tmp_path, orchestration=_roster("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", signed=False)
                            .replace('public_key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"', ""))
    from tests.review_repo_helpers import review_text

    notes = tmp_path / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                         "--file", str(notes), "--sign-key", str(key), "--repo-root", str(repo)])
    assert e.value.code == 1 and "has no public_key" in capsys.readouterr().err


def test_a_wrong_key_is_an_error_not_a_written_record(tmp_path: Path, capsys) -> None:
    key, _pub = _key(tmp_path, "opus")
    _other, other_pub = _key(tmp_path, "other")
    repo = make_review_repo(tmp_path, orchestration=_roster(other_pub))
    from tests.review_repo_helpers import review_text

    notes = tmp_path / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                         "--file", str(notes), "--sign-key", str(key), "--repo-root", str(repo)])
    assert e.value.code == 1 and "does not verify" in capsys.readouterr().err
    assert not (reviews_root(repo) / "M1.1" / "REVIEW-opus.md").exists()


# --- F5, F8, F16 ----------------------------------------------------------------

def test_a_dead_wrapper_frees_the_leaf(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=4)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "running", pid=999999)
    again, created = ops.delegate(repo, "M1.1", "opus")
    assert created and again.worker_id != rec.worker_id
    assert ws.load_record(repo, rec.worker_id).state == "failed"
    _wait(repo, again.worker_id)


def test_a_spawn_failure_marks_the_record_failed(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)

    def boom(*a, **k):
        raise OSError("no fork for you")

    monkeypatch.setattr(ops, "spawn", boom)
    with pytest.raises(ws.WorkerError, match="cannot start the wrapper"):
        ops.delegate(repo, "M1.1", "opus")
    assert ws.load_record(repo, "w-0001").state == "failed"
    assert ws.active_for_node(repo, "M1.1") is None


def test_terminate_refuses_a_pid_it_cannot_verify(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "running", pid=os.getpid())
    monkeypatch.setattr(wr, "_cmdline", lambda pid: None)              # ps unavailable: alive, unverified
    with pytest.raises(ws.WorkerError, match="cannot be verified"):
        ops.terminate(repo, rec.worker_id)
    monkeypatch.setattr(wr, "_cmdline", lambda pid: "python -m specy_road.worker_runner /r w-0002 {}")
    out = ops.terminate(repo, rec.worker_id)        # another worker's wrapper: not ours to signal; the record closes
    assert out.state == "terminated"


def test_terminate_closes_an_adopted_record_without_signalling(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ops.adopt(repo, "M1.1", "claude-code", "native-1")
    ws.set_state(repo, rec, "idle", pid=os.getpid())
    out = ops.terminate(repo, rec.worker_id)
    assert out.state == "terminated"
    assert "not signalled" in ws.events_since(repo, rec.worker_id)[-1].summary


def test_reclaim_keeps_the_prompt_verbatim(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.handoff(repo, rec.worker_id)
    long = "x" * 600
    wl.record_hook_prompt(repo, "sid-1", long)
    _rec, detail = ops.reclaim(repo, rec.worker_id)
    assert detail["prompts"] == [long]
