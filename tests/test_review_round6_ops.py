"""Regressions from the sixth review round (independent review at 9f3b9df, ops items), 2026-10-27.

B13: session ids are validated and resume commands rendered with shlex.
F1/G1: a placeholder is a whole shell word; embedded or multi-word quoted
forms are refused, and validation and substitution walk the same tokens.
F2: ``message --op-id`` binds the message text, and a retry whose file is
gone answers from the outbox. F10: the hook matches by harness and id, refuses
ambiguity, and never waits long for the workers lock; ``delegate`` keeps its
preflight outside the lock. F11/G2: dead wrappers on any leaf are reaped by
``sync`` and before the ``max_workers`` count; pre-delegation dirt is not the
worker's; a crashed reclaim is repaired, not repeated; ``sync --ack`` is
serialised. G3: ``message`` from a linked worktree, and the brief in the same
checkout.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest import mock

import pytest
import yaml

from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_cli import _cli, _repo, _wait

from specy_road import worker_adapters as wa
from specy_road import worker_lease as wl
from specy_road import worker_ops as ops
from specy_road import worker_reconcile as wrc
from specy_road import worker_sessions as wsess
from specy_road import worker_state as ws
from specy_road import worker_witness as ww

UUID = "7f1c0000-1111-4222-8333-444444444444"


def _idle(repo: Path, node: str = "M1.1", harness: str = "claude-code", sid: str = "sid-1") -> ws.WorkerRecord:
    rec = ws.create_record(repo, node, harness, "opus", repo, branch="feature/rm-thing")
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", sid))
    ws.set_state(repo, rec, "idle", pid=None)
    return rec


def _hook(repo: Path, fmt: str, payload: dict) -> int:
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        return _cli("worker", "hook", "--format", fmt, "--repo-root", str(repo))
    finally:
        sys.stdin = sys.__stdin__


# --- B13 -----------------------------------------------------------------------

def test_resume_commands_are_shell_quoted_and_bad_ids_refused(tmp_path: Path) -> None:
    assert wsess.render_command(["claude", "--resume", "sid; touch /tmp/forged"]) == \
        "claude --resume 'sid; touch /tmp/forged'"
    repo = make_review_repo(tmp_path)
    with pytest.raises(ws.WorkerError, match="metacharacters"):
        ops.adopt(repo, "M1.1", "claude-code", "sid; touch /tmp/forged")
    with pytest.raises(ws.WorkerError, match="not a UUID"):
        ops.adopt(repo, "M1.1", "codex", "thr-1")
    assert ops.adopt(repo, "M1.1", "cursor", "chat_01:abc-DEF").provider_session_id == "chat_01:abc-DEF"
    # An id the harness output chose is refused at use, not rendered into a command.
    rec = _idle(repo, "M1.2", sid="$(touch /tmp/forged)")
    with pytest.raises(ws.WorkerError, match="metacharacters"):
        ops.handoff(repo, rec.worker_id)
    with pytest.raises(ws.WorkerError, match="metacharacters"):
        ops.message(repo, rec.worker_id, "hi")
    assert ws.load_record(repo, rec.worker_id).lease["holder"] == "broker"


def test_handoff_prints_a_quoted_command(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    rec = _idle(repo, sid="a.b:c-d")
    assert _cli("worker", "handoff", rec.worker_id, "--repo-root", str(repo)) == 0
    assert "claude --resume a.b:c-d" in capsys.readouterr().out
    assert _cli("worker", "open", rec.worker_id, "--repo-root", str(repo)) == 0
    assert "resume:   claude --resume a.b:c-d" in capsys.readouterr().out


# --- F1 / G1 ---------------------------------------------------------------------

@pytest.mark.parametrize("cli", [
    "claude -p --session-id={session} < {prompt}",
    'printf "prefix <prompt> suffix"',
    "run --prompt={prompt}",
    "run '<prompt> and more'",
    'run "$(cat {prompt})"',
    "run <prompt>'",
])
def test_embedded_placeholders_are_refused(cli: str) -> None:
    assert wa.placeholder_problem(cli) is not None


@pytest.mark.parametrize("cli", [
    "claude -p --session-id {session} < {prompt}",
    'claude -p "<prompt>"',
    "muse exec '<prompt>'",
    "run <{prompt}",
    "run '{session}' \"{prompt}\"",
])
def test_whole_word_placeholders_are_accepted(cli: str) -> None:
    assert wa.placeholder_problem(cli) is None


def test_prompt_text_cannot_run_a_command_substitution(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("hello $(echo INJECTED) world")
    out = subprocess.run(["sh", "-c", wa.substitute_prompt('printf "%s" "<prompt>"', p)],
                         capture_output=True, text=True, check=True).stdout
    assert out == "hello $(echo INJECTED) world"
    text = wa.substitute_prompt("x --session-id {session} <{prompt} '<prompt>'", p, "abc")
    assert text == f"x --session-id abc <{p} 'hello $(echo INJECTED) world'"


def test_an_embedded_session_placeholder_is_refused_by_the_adapter(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("hi")
    with pytest.raises(wa.Unsupported, match="whole argument"):
        wa.adapter_for("claude-code").launch(p, tmp_path, "m", "claude -p --session-id={session} < {prompt}")


# --- F2 ------------------------------------------------------------------------

def test_message_op_id_binds_the_text_and_survives_a_missing_file(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    _cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    _wait(repo, "w-0001")
    capsys.readouterr()
    msg = tmp_path / "message.txt"
    msg.write_text("first")
    assert _cli("worker", "message", "w-0001", "--file", str(msg), "--op-id", "same-op", "--json", "--repo-root", str(repo)) == 0
    first = json.loads(capsys.readouterr().out)
    _wait(repo, "w-0001")
    msg.write_text("second")
    assert _cli("worker", "message", "w-0001", "--file", str(msg), "--op-id", "same-op", "--json", "--repo-root", str(repo)) == 1
    assert "different arguments" in capsys.readouterr().err
    msg.unlink()
    assert _cli("worker", "message", "w-0001", "--file", str(msg), "--op-id", "same-op", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out) == first
    assert _cli("worker", "message", "w-0001", "--file", str(msg), "--repo-root", str(repo)) == 1
    assert "cannot read --file" in capsys.readouterr().err


# --- F10 -----------------------------------------------------------------------

def test_hook_matches_by_harness_and_refuses_ambiguity(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    a = _idle(repo, "M1.1", "claude-code", "same-id")
    b = _idle(repo, "M1.2", "cursor", "same-id")
    ops.handoff(repo, a.worker_id)
    ops.handoff(repo, b.worker_id)
    assert _hook(repo, "cursor", {"conversation_id": "same-id", "prompt": "cursor human"}) == 0
    assert not ops.interventions_path(repo, a.worker_id).is_file()
    assert "cursor human" in ops.interventions_path(repo, b.worker_id).read_text()
    with pytest.raises(ws.WorkerError, match="ambiguous"):
        ww.record_hook_prompt(repo, "same-id", "no harness given")
    assert _hook(repo, "claude-code", {"session_id": "same-id", "prompt": "claude human"}) == 0
    assert "claude human" in ops.interventions_path(repo, a.worker_id).read_text()


def test_hook_witness_does_not_wait_on_a_busy_lock(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = _idle(repo)
    ops.handoff(repo, rec.worker_id)
    release = threading.Event()
    taken = threading.Event()

    def hold() -> None:
        with ws.workers_lock(repo):
            taken.set()
            release.wait(10)
    t = threading.Thread(target=hold, daemon=True)
    t.start()
    taken.wait(5)
    t0 = time.monotonic()
    assert ww.record_hook_prompt(repo, "sid-1", "while busy", harness="claude-code", timeout=0.3) is None
    assert time.monotonic() - t0 < 2
    release.set()
    t.join(5)
    assert ww.record_hook_prompt(repo, "sid-1", "after", harness="claude-code", timeout=0.3) is not None
    _r, d = ops.reclaim(repo, rec.worker_id)
    assert d["prompts"] == ["after"]


def test_delegate_runs_preflight_outside_the_workers_lock(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    seen: dict[str, bool] = {}

    def probe(entry, root):
        with ww.try_workers_lock(root, 0.2) as held:   # re-entrant when this thread holds it
            seen["free"] = held
        # A stranger (another thread) must be able to take the lock while preflight runs.
        got = []
        t = threading.Thread(target=lambda: [got.append(h) for h in [ww.try_workers_lock(root, 0.5).__enter__()]])
        t.start()
        t.join(2)
        seen["other_thread"] = bool(got and got[0])
    monkeypatch.setattr(ops, "_preflight", probe)
    rec, created = ops.delegate(repo, "M1.1", "opus")
    assert created and seen == {"free": True, "other_thread": True}
    _wait(repo, rec.worker_id)


# --- F11 (a) / G2 ---------------------------------------------------------------

def _dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_sync_and_delegate_reap_dead_wrappers_on_any_leaf(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    dead = ws.create_record(repo, "M1.2", "claude-code", "opus", repo)
    ws.set_state(repo, dead, "running", pid=_dead_pid())
    assert wrc.sync(repo, ack=True)
    delta = wrc.sync(repo)
    assert delta == [] and ws.load_record(repo, dead.worker_id).state == "failed"
    assert [e.type for e in ws.events_since(repo, dead.worker_id)][-1] == "error"
    # A second dead record, not yet swept, must not hold the single slot.
    dead2 = ws.create_record(repo, "M1.3", "claude-code", "opus", repo)
    ws.set_state(repo, dead2, "running", pid=_dead_pid())
    rec, created = ops.delegate(repo, "M1.1", "opus")
    assert created and ws.load_record(repo, dead2.worker_id).state == "failed"
    _wait(repo, rec.worker_id)


# --- F11 (b) ---------------------------------------------------------------------

def test_reconcile_leaves_pre_delegation_dirt_to_the_coordinator(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "pre.txt").write_text("dirt before delegate\n")
    (repo / "src" / "a.py").write_text("edited before delegate\n")
    _cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    _wait(repo, "w-0001")
    (repo / "after.txt").write_text("the worker's\n")
    _r, d = ops.reconcile(repo, "w-0001")
    assert "pre.txt" not in d["changed"] and "src/a.py" not in d["changed"]
    assert "pre.txt" not in d["outside_touch_zones"] and "after.txt" in d["outside_touch_zones"]
    assert d["pre_existing_dirty"] == ["pre.txt", "src/a.py"]


# --- F11 (c) ---------------------------------------------------------------------

def test_a_crashed_reclaim_is_repaired_once_not_repeated(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = _idle(repo)
    ops.handoff(repo, rec.worker_id)
    real = wl.append_event
    with mock.patch.object(wl, "append_event", side_effect=OSError("crash after the record moved")):
        with pytest.raises(OSError):
            ops.reclaim(repo, rec.worker_id)
    mid = ws.load_record(repo, rec.worker_id)
    assert mid.instruction_epoch == 1 and mid.lease["holder"] == "broker" and mid.state == "idle"
    wl.append_event = real
    rec2, d = ops.reclaim(repo, rec.worker_id)          # the retry repairs the events
    evs = [e for e in ws.events_since(repo, rec.worker_id) if e.type in ("intervention", "reclaim")]
    assert rec2.instruction_epoch == 1 and [e.type for e in evs] == ["intervention", "reclaim"]
    assert evs[0].epoch == 1 and "repaired" in evs[0].summary
    with pytest.raises(ws.WorkerError, match="not handed off"):
        ops.reclaim(repo, rec.worker_id)                 # and a third call is refused, not repeated
    assert ws.load_record(repo, rec.worker_id).instruction_epoch == 1


def test_handoff_and_reclaim_move_the_record_in_one_write(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = _idle(repo)
    saves: list[tuple[str, str, int]] = []
    real = ws.save_record

    def spy(root, r):
        saves.append((r.lease["holder"], r.state, r.instruction_epoch))
        return real(root, r)
    with mock.patch.object(ws, "save_record", side_effect=spy):
        ops.handoff(repo, rec.worker_id)
        ops.reclaim(repo, rec.worker_id)
    # No save ever shows a half-moved record: human+handed_off, then broker+idle+epoch 1, never a mix.
    assert all(s in {("broker", "idle", 0), ("human", "handed_off", 0), ("broker", "idle", 1)} for s in saves)
    assert ("human", "idle", 0) not in saves and ("broker", "handed_off", 0) not in saves


# --- F11 (d) ---------------------------------------------------------------------

def test_sync_ack_runs_under_the_workers_lock(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    release = threading.Event()
    taken = threading.Event()
    done: list[float] = []

    def hold() -> None:
        with ws.workers_lock(repo):
            taken.set()
            release.wait(10)
    threading.Thread(target=hold, daemon=True).start()
    taken.wait(5)
    t = threading.Thread(target=lambda: (wrc.sync(repo, ack=True), done.append(time.monotonic())))
    t.start()
    time.sleep(0.5)
    assert not done                                   # blocked behind the other writer
    t0 = time.monotonic()
    release.set()
    t.join(5)
    assert done and done[0] >= t0
    marks = yaml.safe_load((ws.workers_dir(repo) / "sync.yaml").read_text())
    assert marks == {rec.worker_id: ws.load_record(repo, rec.worker_id).last_event_seq}


# --- G3 ------------------------------------------------------------------------

def test_message_from_a_linked_worktree_without_work_dir(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = _idle(repo, sid=UUID)
    wt = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", str(wt), "-b", "side")
    assert not (wt / "work").exists()
    ops.message(wt, rec.worker_id, "hi from the side")
    final = _wait(repo, rec.worker_id)
    assert final.state in ("idle", "completed") and (wt / "work" / f"prompt-{rec.worker_id}-message-2.md").is_file()


def test_delegate_in_the_same_checkout_writes_the_missing_brief(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    assert not (repo / "work" / "brief-M1.1.md").exists()
    rec, _c = ops.delegate(repo, "M1.1", "opus")
    assert rec.worktree == str(repo.resolve()) and (repo / "work" / "brief-M1.1.md").is_file()
    _wait(repo, rec.worker_id)
    assert os.path.getsize(repo / "work" / "brief-M1.1.md") > 0
