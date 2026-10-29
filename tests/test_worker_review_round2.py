"""Regressions from the second independent review (Gemini 4 Argon, 2026-10-27).

One test per finding: a prompt containing ``<prompt>`` cannot break out of
the shell quoting; the session id chosen up front survives the spawn; a
completed worker can take a review ``block`` as a message and a turn's READY
is judged against that turn; a linked worktree gets the brief; the guard
scopes tree-only commands to this worktree and sees ``checkout -f``,
``restore <path>``, brace groups, ``eval`` and ``$(…)``; an op id is bound to
its target; handoff refuses a closed worker; hook prompts are attributed by
line, not by second; adopt refuses a duplicate; reconcile treats an
unbuildable prompt as a contract change; Codex resume keeps its sandbox;
reviews_root stays inside a nested project; the CGNAT range is off-host.
"""

from __future__ import annotations

import ipaddress
import json
import os
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_cli import run_worker_cli, _repo, wait_for_worker

from specy_road import session_presence as sp
from specy_road import tool_call_guard as tg
from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_process as wp
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts import brainstorm_research as br
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.review_files import reviews_root


def test_a_prompt_containing_the_placeholder_cannot_break_the_quoting(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("Explain <prompt> and '{prompt}' then {session} $(touch pwned)")
    out = wa.substitute_prompt('claude -p "<prompt>" --sid {session}', p, "S1")
    assert out == "claude -p " + "'Explain <prompt> and '\"'\"'{prompt}'\"'\"' then {session} $(touch pwned)'" + " --sid S1"
    launch = wa.ADAPTERS["generic"]._custom("run {prompt} {session}", p)
    assert launch and launch.argv[2].endswith(f"{p} {launch.session_id}")


def test_the_session_id_chosen_up_front_is_on_disk_after_spawn(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wr.spawn(repo, rec, wa.Launch(["true"], session_id="sid-1234"))
    assert ws.load_record(repo, rec.worker_id).provider_session_id == "sid-1234"
    wait_for_worker(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).provider_session_id == "sid-1234"


def test_a_completed_worker_takes_a_review_block_as_a_message(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "completed", pid=None)
    rec = ops.message(repo, rec.worker_id, "fix the blocker")
    wait_for_worker(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state in ("idle", "completed")
    for closed in ("failed", "terminated"):
        ws.set_state(repo, rec, closed, pid=None)
        with pytest.raises(ws.WorkerError, match="delegate again"):
            ops.message(repo, rec.worker_id, "x")


def test_a_ready_from_the_previous_turn_does_not_complete_the_next(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
    d = reviews_root(repo) / "M1.1"
    d.mkdir(parents=True)
    head = git(repo, "rev-parse", "HEAD")
    text = (f"---\nnode_id: M1.1\nagent: old\nbranch: feature/rm-thing\ncommit: {head}\n"
            f"base: {head}\nchanged_paths: []\nverify: []\n---\n")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    lines = [{"type": "result", "subtype": "success", "result": "ok", "session_id": "n"}]
    writes = tmp_path / "writes.json"       # this turn's harness writes the READY
    writes.write_text(json.dumps({"lines": lines, "write": {"path": str(d / "READY-old.md"), "text": text}}))
    assert wr.run(repo, rec.worker_id, wa.adapter_for("claude-code").launch(
        writes, repo, "opus", f"{sys.executable} {script} {{prompt}}")) == 0
    assert ws.load_record(repo, rec.worker_id).state == "completed"
    quiet = tmp_path / "quiet.json"         # the next turn writes nothing: the READY is the checkpoint's
    quiet.write_text(json.dumps({"lines": lines}))
    wr.run(repo, rec.worker_id, wa.adapter_for("claude-code").launch(
        quiet, repo, "opus", f"{sys.executable} {script} {{prompt}}"), resumed=True)
    assert ws.load_record(repo, rec.worker_id).state == "idle"


def test_delegate_into_a_linked_worktree_carries_the_brief(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "work").mkdir(exist_ok=True)
    (repo / "work" / "brief-M1.1.md").write_text("# Brief\n")
    git(repo, "checkout", "-q", "dev")
    rec, created = ops.delegate(repo, "M1.1", "opus")
    assert created and Path(rec.worktree) != repo.resolve()
    assert (Path(rec.worktree) / "work" / "brief-M1.1.md").read_text() == "# Brief\n"
    wait_for_worker(repo, rec.worker_id)
    text, _p, err = build_prompt(repo, "M1.1", role="executor", model="opus")
    assert err is None and str(reviews_root(repo) / "M1.1") in text


def test_tree_only_commands_ignore_sessions_in_other_worktrees(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    sp.start_session(repo, "alice", paths=["src"], worktree=repo)
    assert tg.decide(wt, "git checkout -b feature/rm-other", agent="bob").allowed
    assert not tg.decide(repo, "git checkout -b feature/rm-other", agent="bob").allowed
    assert not tg.decide(wt, "git stash", agent="bob").allowed          # the stash stack is repo-wide


def test_a_worker_does_not_count_itself(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    # The guard matches the wrapper's resolved repo root as a whole argument (review round 6, B11).
    monkeypatch.setattr(wp, "_cmdline", lambda pid: f"python -m specy_road.worker_runner {repo.resolve()} w-0001")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "running", pid=os.getpid())
    assert not tg.decide(repo, "git checkout dev", agent="me").allowed
    monkeypatch.setenv("SPECY_ROAD_WORKER_ID", "w-0001")
    assert tg.decide(repo, "git checkout dev", agent="me").allowed
    monkeypatch.delenv("SPECY_ROAD_WORKER_ID")
    ws.set_state(repo, rec, "running", pid=999999)              # a dead pid is not a live worker
    assert tg.decide(repo, "git checkout dev", agent="me").allowed


@pytest.mark.parametrize("command", [
    "git checkout -f", "git checkout --force", "git restore src/a.py", "git restore -W src/a.py",
    "{ git stash; }", "eval git stash", "echo $(git reset --hard)", "x=`git stash`",
])
def test_more_destructive_shapes_are_classified(command: str) -> None:
    assert tg.classify(command), command


def test_staged_restore_of_a_path_is_fine() -> None:
    assert tg.classify("git restore --staged src/a.py") is None


def test_malformed_hook_stdin_denies() -> None:
    with pytest.raises(ValueError):
        tg.read_payload("not json")


def test_an_op_id_is_bound_to_its_target(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=4)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--op-id", "op-1", "--repo-root", str(repo)) == 0
    wait_for_worker(repo, "w-0001")
    assert run_worker_cli("worker", "delegate", "M9.9", "--model", "opus", "--op-id", "op-1", "--repo-root", str(repo)) != 0
    assert [r.worker_id for r in ws.list_records(repo)] == ["w-0001"]   # no replayed result, no second worker


def test_handoff_refuses_a_closed_worker(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ops.terminate(repo, rec.worker_id)
    with pytest.raises(ws.WorkerError, match="terminated"):
        ops.handoff(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state == "terminated"


def test_hook_prompts_are_attributed_by_line_and_only_under_a_human_lease(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    assert ops.record_hook_prompt(repo, "sid-1", "broker prompt") is None    # not an intervention
    ws.set_state(repo, rec, "idle", pid=None)
    ops.handoff(repo, rec.worker_id)
    ops.record_hook_prompt(repo, "sid-1", "human says hi")
    rec, detail = ops.reclaim(repo, rec.worker_id)
    assert detail["prompts"] == ["human says hi"] and ws.FLAG_EXTERNAL not in rec.flags
    ops.handoff(repo, rec.worker_id)                                        # same second: the old line does not count
    rec, detail = ops.reclaim(repo, rec.worker_id)
    assert detail["prompts"] == [] and ws.FLAG_EXTERNAL in rec.flags


def test_adopt_refuses_a_second_worker_on_the_leaf(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    ops.adopt(repo, "M1.1", "claude-code", "aaaaaaaa-0000-4000-8000-000000000001")
    with pytest.raises(ws.WorkerError, match="already has an active worker"):
        ops.adopt(repo, "M1.1", "claude-code", "aaaaaaaa-0000-4000-8000-000000000002")


def test_reconcile_counts_an_unbuildable_prompt_as_a_contract_change(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec, _c = ops.delegate(repo, "M1.1", "opus")
    wait_for_worker(repo, rec.worker_id)
    orch = repo / "roadmap" / "orchestration.yaml"
    orch.write_text(orch.read_text().replace("roles: [executor, reviewer], harness", "roles: [reviewer], harness"))
    git(repo, "commit", "-qm", "roster change", "--", "roadmap/orchestration.yaml")
    git(repo, "update-ref", "refs/heads/dev", "HEAD")     # routing reads the roster from the integration branch
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["contract_changed"] and delta["needs_reconcile"]


def test_reviews_root_stays_inside_a_nested_project(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    nested = repo / "sr"
    nested.mkdir()
    assert reviews_root(nested) == nested / "work" / "reviews"
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    assert reviews_root(wt) == repo.resolve() / "work" / "reviews"
    (wt / "sr").mkdir()
    assert reviews_root(wt / "sr") == repo.resolve() / "sr" / "work" / "reviews"


def test_cgnat_addresses_are_off_host(monkeypatch) -> None:
    assert not ipaddress.ip_address("100.64.0.1").is_private
    monkeypatch.setattr(br.socket, "getaddrinfo", lambda host, port: [(None, None, None, None, ("100.64.0.1", 0))])
    assert br._is_off_host("tailnet.example")
    monkeypatch.setattr(br.socket, "getaddrinfo", lambda host, port: [(None, None, None, None, ("93.184.216.34", 0))])
    assert not br._is_off_host("example.com")
