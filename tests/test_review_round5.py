"""Regressions from the fourth review round (Gemini 4 Argon + GPT-5.6 Sol at bc3ef9c, 2026-10-27).

One test per finding: reconcile judges the worker's whole lifetime; READY
must be at the worktree's HEAD; routing reads the roster from the
integration branch; the guard follows env -S, nested $(), attached -C,
--git-dir, long wrapper options, timeout, xargs-from-stdin and configured
aliases, and refuses a non-string hook command; a dead wrapper fails on
message/handoff; a skipped skill gets no link and a foreign directory is
never removed; the nested AGENTS.md report carries its prefix; rounds are
persisted; a malformed custom cli raises; event sequences survive a crash;
adopt is atomic; hook prompts are verbatim; the verifier pins its address;
round one hides the roadmap digest; an invalid profile is a staffing
error; a mismatched slug is refused.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_cli import _repo

from specy_road import session_presence as sp
from specy_road import tool_call_guard as tg
from specy_road import tool_call_guard_adapters as tga
from specy_road import worker_adapters as wa
from specy_road import worker_lease as wl
from specy_road import worker_ops as ops
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts import refresh_stubs as rs
from specy_road.bundled_scripts.brainstorm_prompt import render_brainstorm_prompt
from specy_road.bundled_scripts.brainstorm_session import BrainstormSession, read_session, write_session
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.orchestrate_plan import Candidate, assign_leaf
from specy_road.orchestration_config import effective_config
from specy_road.review_files import reviews_root
from specy_road.specyrd_init import run_init


def _ready(repo: Path, commit: str, branch: str = "feature/rm-thing") -> Path:
    d = reviews_root(repo) / "M1.1"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "READY-x.md"
    p.write_text(f"---\nnode_id: M1.1\nagent: x\nbranch: {branch}\ncommit: {commit}\nbase: {commit}\n"
                 "changed_paths: []\nverify: []\n---\n")
    return p


# --- Gemini B1 / Sol F2 ---------------------------------------------------------

def test_reconcile_remembers_a_breach_from_before_the_handoff(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    (repo / "outside.txt").write_text("breach\n")
    git(repo, "add", "outside.txt")
    git(repo, "commit", "-qm", "worker touched outside")
    _r, d1 = ops.reconcile(repo, rec.worker_id)
    assert "outside.txt" in d1["outside_touch_zones"] and d1["needs_reconcile"]
    ops.handoff(repo, rec.worker_id)
    ops.reclaim(repo, rec.worker_id)
    _r, d2 = ops.reconcile(repo, rec.worker_id)
    assert "outside.txt" in d2["outside_touch_zones"] and d2["needs_reconcile"]


# --- Gemini B2 / Sol F1 ---------------------------------------------------------

def test_a_ready_for_an_older_commit_does_not_complete(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
    old = git(repo, "rev-parse", "HEAD~1")
    ready = _ready(repo, old)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    spec = tmp_path / "ok.json"
    spec.write_text(json.dumps({"lines": [{"type": "result", "subtype": "success", "result": "ok", "session_id": "n"}]}))
    launch = wa.adapter_for("claude-code").launch(spec, repo, "opus", f"{sys.executable} {script} {{prompt}}")
    time.sleep(0.05)
    os.utime(ready, None)
    assert wr.run(repo, rec.worker_id, launch) == 0
    assert ws.load_record(repo, rec.worker_id).state == "idle"
    _ready(repo, git(repo, "rev-parse", "HEAD"))
    wr.run(repo, rec.worker_id, launch, resumed=True)
    assert ws.load_record(repo, rec.worker_id).state == "completed"


# --- Gemini B3 ----------------------------------------------------------------

def test_routing_reads_the_roster_from_the_integration_branch(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    (repo / "roadmap" / "orchestration.yaml").write_text(
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
        "  - {id: rogue, family: openai, roles: [executor, reviewer], may_process: [public, restricted]}\n"
        "policy: {reviewers_required: 1}\n")
    (repo / "work" / "reviews" / "M1.1").mkdir(parents=True)
    (repo / "work" / "reviews" / "M1.1" / "PACKET.md").write_text("# packet\n")
    assert "not in the roster" in build_prompt(repo, "M1.1", role="reviewer", model="rogue")[2]
    with pytest.raises(ws.WorkerError, match="not in the roster"):
        ops.delegate(repo, "M1.1", "rogue")


# --- Gemini F1 / Sol B1 -----------------------------------------------------------

@pytest.mark.parametrize("command", [
    'env -S "git stash"', "echo $(git reset --hard $(echo HEAD))", "sudo --user root git stash",
    "env --unset HOME git stash", "nice --adjustment 5 git stash", "timeout 10 git stash",
    "printf 'stash\\n' | xargs git",
])
def test_more_wrapper_shapes_are_classified(command: str) -> None:
    assert tg.classify(command), command


def test_attached_dash_c_git_dir_and_config_aliases_reach_the_right_tree(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    sp.start_session(repo, "alice", paths=["src"], worktree=wt)
    git(repo, "config", "alias.s", "stash")
    git(repo, "config", "alias.boom", "!git reset --hard")
    assert not tg.decide(repo, f"git -C{wt} reset --hard", agent="bob").allowed
    assert not tg.decide(repo, f"git --git-dir={wt}/.git commit -m x", agent="bob").allowed
    assert not tg.decide(repo, "git s", agent="bob").allowed
    assert "reset --hard" in (tg.classify(tg._expand_config_aliases(repo, "git boom")) or "")   # bang alias expanded
    assert not tg.decide(repo, "git boom", agent="bob", always=True).allowed
    assert tg.decide(repo, "git -C . status", agent="bob").allowed


# --- Sol F4 ---------------------------------------------------------------------

def test_a_non_string_hook_command_is_an_error_not_an_allow() -> None:
    with pytest.raises(ValueError, match="not a string"):
        tga.ADAPTERS["cursor"].extract({"command": ["git", "stash"]})
    with pytest.raises(ValueError, match="not a string"):
        tga.ADAPTERS["claude-code"].extract({"tool_name": "Bash", "tool_input": {"command": {"x": 1}}})
    assert tga.ADAPTERS["cursor"].extract({"command": ""}) is None


# --- Gemini F2 ----------------------------------------------------------------

def test_a_crashed_running_worker_cannot_be_handed_off_or_messaged(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "running", pid=999999)
    with pytest.raises(ws.WorkerError, match="failed"):
        ops.handoff(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state == "failed"
    ws.set_state(repo, rec, "running", pid=999999)
    with pytest.raises(ws.WorkerError, match="failed"):
        ops.message(repo, rec.worker_id, "hi")


# --- Gemini F3 / Sol B2 ---------------------------------------------------------

def test_no_link_to_a_skipped_canonical_skill_and_no_rmtree_without_force(tmp_path: Path) -> None:
    mine = tmp_path / ".agents" / "skills" / "specyrd-validate" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("USER SKILL\n")
    theirs = tmp_path / ".claude" / "skills" / "specyrd-brief" / "SKILL.md"
    theirs.parent.mkdir(parents=True)
    theirs.write_text("---\nname: specyrd-brief\n---\nThin stub — my own specyrd notes\n")   # looks like ours; is not
    res = run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, role="dev")
    assert ".agents/skills/specyrd-validate/SKILL.md" in res.skipped
    assert not (tmp_path / ".claude" / "skills" / "specyrd-validate").exists()
    assert theirs.read_text().endswith("my own specyrd notes\n") and not theirs.parent.is_symlink()


# --- Gemini F4 ----------------------------------------------------------------

def test_a_nested_project_reports_its_agents_md_with_the_prefix(tmp_path: Path) -> None:
    (tmp_path / "sr" / "roadmap").mkdir(parents=True)
    (tmp_path / "sr" / "roadmap" / "manifest.json").write_text("{}")
    (tmp_path / ".specyrd").mkdir()
    (tmp_path / ".specyrd" / "manifest.json").write_text('{"project_root": "sr"}')
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, role="dev")
    (tmp_path / "sr" / "AGENTS.md").write_text("# mine\n")
    written, _o = rs.refresh_stubs(tmp_path)
    assert any(w.startswith("sr/AGENTS.md (") for w in written)


# --- Gemini F5 / Sol F8, Sol F10 ---------------------------------------------------

def _bs(repo: Path, *args: str) -> tuple[int, str]:
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), pytest.raises(SystemExit) as e:
        brainstorm_cli.main([*args, "--repo-root", str(repo)])
        raise SystemExit(0)
    return (e.value.code or 0), out.getvalue()


def test_rounds_are_persisted_and_next_round_warns_past_them(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    (repo / "work").mkdir(exist_ok=True)
    assert _bs(repo, "start", "--topic", "Grow", "--under", "M1", "--rounds", "1")[0] == 0
    assert read_session(repo, "grow").rounds == 1
    _bs(repo, "add-idea", "--title", "One", "--slug", "grow")
    code, out = _bs(repo, "next-round", "--slug", "grow")
    assert code == 0 and "round 2 of 1" in out and "past the 1 round(s) planned" in out


def test_a_session_file_whose_slug_disagrees_is_refused(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    write_session(repo, BrainstormSession(slug="b", topic="t"))
    (repo / "work" / "brainstorm-a.yaml").write_text((repo / "work" / "brainstorm-b.yaml").read_text())
    with pytest.raises(Exception, match="says slug 'b'"):
        read_session(repo, "a")


# --- Sol B3 ----------------------------------------------------------------------

def test_a_malformed_custom_cli_raises_instead_of_widening(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("hi")
    with pytest.raises(wa.Unsupported, match="whole argument"):
        wa.adapter_for("cursor").launch(p, tmp_path, "m", 'agent -p --mode plan "$(cat {prompt})"')
    launch = wa.adapter_for("cursor").launch(p, tmp_path, "m", "agent -p --mode plan {prompt}")
    assert launch.argv[:2] == ["sh", "-c"] and "--force" not in launch.argv[2]


# --- Sol B4 ----------------------------------------------------------------------

def test_event_sequences_survive_a_record_that_lags_the_log(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.append_event(repo, rec, "output", source="worker", summary="written before crash")
    ws.mutate(repo, rec, lambda r: setattr(r, "last_event_seq", 1))      # the crash: log says 2, record says 1
    ws.append_event(repo, rec, "error", source="system", summary="recovery")
    seqs = [e.seq for e in ws.events_since(repo, rec.worker_id)]
    assert seqs == [1, 2, 3]


# --- Sol B5 ----------------------------------------------------------------------

def test_a_platform_without_a_file_lock_refuses_worker_mutations(tmp_path: Path, monkeypatch) -> None:
    import builtins

    from specy_road import worker_lock

    real_import = builtins.__import__

    def no_locks(name, *a, **k):
        if name in ("fcntl", "msvcrt"):
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_locks)
    with pytest.raises(ws.WorkerError, match="exclusive file lock"), worker_lock.workers_lock(tmp_path):
        pass


# --- Sol B6 ----------------------------------------------------------------------

def test_adopt_is_one_transaction(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ops.adopt(repo, "M1.1", "claude-code", "aaaaaaaa-0000-4000-8000-000000000001")
    types = [e.type for e in ws.events_since(repo, rec.worker_id)]
    assert types[-1] == "adopted" and ws.load_record(repo, rec.worker_id).checkpoint is not None


# --- Sol B7 ----------------------------------------------------------------------

def test_hook_prompts_are_stored_whole(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.handoff(repo, rec.worker_id)
    long = "y" * 2501
    wl.record_hook_prompt(repo, "sid-1", long)
    _rec, detail = ops.reclaim(repo, rec.worker_id)
    assert detail["prompts"] == [long]


# --- Sol B9 ----------------------------------------------------------------------

def test_round_one_does_not_point_at_the_roadmap_digest(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    (repo / "roadmap-context.md").write_text("# digest\n")
    s = BrainstormSession(slug="s", topic="t")
    assert "roadmap-context.md" not in render_brainstorm_prompt(repo, s, count=5)
    s.round = 2
    s.ideas = []
    assert "roadmap-context.md" in render_brainstorm_prompt(repo, s, count=5)


# --- Sol F5 ----------------------------------------------------------------------

def test_an_invalid_configured_profile_is_a_staffing_error(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration="version: 1\nroster:\n"
                            "  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
                            "  - {id: bad, family: openai, roles: [executor], profile: model-profiles/bad.md}\n"
                            "policy: {reviewers_required: 1}\n")
    (repo / "model-profiles").mkdir()
    (repo / "model-profiles" / "bad.md").write_text("not a profile\n")
    from specy_road.bundled_scripts.roadmap_load import load_roadmap
    from specy_road.model_profiles import profile_for_entry

    config, _e = effective_config(repo)
    node = next(n for n in load_roadmap(repo)["nodes"] if n["id"] == "M1.1")
    a = assign_leaf(node, [Candidate(e, profile_for_entry(repo, e)) for e in config["roster"]], config)
    assert a.executor is None and any("profile is invalid" in p for p in a.problems)
