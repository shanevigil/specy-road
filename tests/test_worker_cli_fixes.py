"""M3.9: resume permissions, roster provenance, event gaps, ``--path`` values, nested-layout paths.

One test per acceptance item: ``{session_flag}`` lets one Claude command
launch and resume; ``orchestrate plan`` and ``validate`` say where the roster
came from and when the working-tree copy is not it; ``worker sync`` reports a
gap in event sequence numbers; ``session start --path`` takes several values;
in the nested layout the executor prompt and brief name the project root and
give the summary and hand-off paths from the git root, and a delegated
worktree's brief sits where the prompt says.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_orchestrate_plan import ROSTER, _only
from tests.test_orchestrate_plan import _repo as _plan_repo
from tests.test_worker_cli import FAKE, _cli, _roster, _wait

from specy_road import orchestrate_plan as op
from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import orchestrate_cli, session_cli
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.bundled_scripts.validate_roadmap import validate_orchestration_contract


# --- A1: {session_flag} --------------------------------------------------------

def test_one_claude_command_launches_and_resumes_with_session_flag(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("task")
    cli = "claude -p --permission-mode dontAsk {session_flag} < {prompt}"
    claude = wa.adapter_for("claude-code")
    launch = claude.launch(p, tmp_path, None, cli)
    assert launch.session_id and launch.argv[2] == (
        f"claude -p --permission-mode dontAsk --session-id {launch.session_id} < {p}")
    again = claude.resume(launch.session_id, p, tmp_path, None, cli)
    assert again.argv[2] == f"claude -p --permission-mode dontAsk --resume {launch.session_id} < {p}"


@pytest.mark.parametrize("harness", ["codex", "cursor", "generic"])
def test_session_flag_is_refused_where_it_has_no_meaning(tmp_path: Path, harness: str) -> None:
    with pytest.raises(wa.Unsupported, match="session_flag"):
        wa.adapter_for(harness).launch(tmp_path / "p.md", tmp_path, None, "run {session_flag} {prompt}")


@pytest.mark.parametrize("cli", ["run {prompt} --x{session_flag}", "run {prompt} <{session_flag}"])
def test_session_flag_must_be_whole_arguments(cli: str) -> None:
    assert wa.placeholder_problem(cli)


# --- A2: roster provenance -----------------------------------------------------

EXECUTORLESS = "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"


def _plan_text(repo: Path, capsys) -> str:
    with pytest.raises(SystemExit):
        orchestrate_cli.main(["orchestrate", "plan", "--today", "2026-11-01", "--repo-root", str(repo)])
    return capsys.readouterr().out


def test_text_plan_always_names_the_roster_ref(tmp_path: Path, capsys) -> None:
    repo = _plan_repo(tmp_path)
    plan, err = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    assert err is None and plan.roster_ref and plan.roster_drift is None
    out = _plan_text(repo, capsys)
    assert f"roster: roadmap/orchestration.yaml at {plan.roster_ref}\n" in out and "! " not in out
    (repo / "roadmap" / "orchestration.yaml").write_text(ROSTER + "# local edit\n")
    out = _plan_text(repo, capsys)
    assert f"roster: roadmap/orchestration.yaml at {plan.roster_ref}\n" in out
    assert "! roadmap/orchestration.yaml in the working tree differs from" in out


def test_a_roster_that_differs_from_the_integration_branch_is_named_not_the_may_process_hint(
        tmp_path: Path, capsys) -> None:
    repo = _plan_repo(tmp_path, roster=EXECUTORLESS)
    (repo / "roadmap" / "orchestration.yaml").write_text(ROSTER)   # executors added, not committed
    plan, _ = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    problems = " ".join(_only(plan).problems)
    assert "differs from" in problems and plan.roster_ref in problems and "may_process containing" not in problems
    validate_orchestration_contract(repo)
    assert "warning: roadmap/orchestration.yaml in the working tree differs from" in capsys.readouterr().err


def test_a_roster_absent_on_the_integration_branch_is_named(tmp_path: Path, capsys) -> None:
    repo = _plan_repo(tmp_path, roster=None)
    (repo / "roadmap" / "orchestration.yaml").write_text(ROSTER)
    plan, _ = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    assert plan.roster_drift and "is not on" in plan.roster_drift
    assert any("is not on" in p for p in _only(plan).problems)
    validate_orchestration_contract(repo)
    assert "is not on" in capsys.readouterr().err


# --- A3: sync gaps -------------------------------------------------------------

def test_sync_reports_a_gap_in_event_sequence_numbers(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    for i in range(4):
        ws.append_event(repo, rec, "output", source="worker", summary=f"line {i}")
    log = ws.events_path(repo, rec.worker_id)
    lines = log.read_text().splitlines()
    seqs = [json.loads(ln)["seq"] for ln in lines]
    lost = seqs[1:3]
    log.write_text("\n".join([lines[0], "{not json", *lines[3:]]) + "\n")   # two events lost
    assert _cli("worker", "sync", "--repo-root", str(repo)) == 0
    assert f"! gap: event(s) #{lost[0]}–#{lost[1]} missing" in capsys.readouterr().out
    delta = ops.sync(repo, ack=True)
    assert delta[0]["gaps"] == [lost]
    ws.append_event(repo, rec, "output", source="worker", summary="after")
    assert ops.sync(repo)[0]["gaps"] == []   # reported once, then behind the mark


# --- A4: --path values ---------------------------------------------------------

@pytest.mark.parametrize("cmd", ["start", "touch", "check"])
def test_path_takes_several_values_or_repeats(cmd: str) -> None:
    ns = session_cli.build_parser().parse_args(["session", cmd, "--path", "a", "b", "--path", "c"])
    assert ns.path == ["a", "b", "c"]


# --- A5: nested layout ---------------------------------------------------------

def _nested(tmp_path: Path) -> tuple[Path, Path]:
    """``(git root, project root)``: the review repo's tree under ``sr/``, the claim's branch checked out."""
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    flat = make_review_repo(tmp_path, orchestration=_roster(f"{sys.executable} {script} {{prompt}} {{session}}"))
    top = tmp_path / "top"
    git(flat, "checkout", "-q", "dev")
    shutil.copytree(flat, top / "sr", ignore=shutil.ignore_patterns(".git"))
    (top / "sr" / ".gitignore").write_text("work/reviews/\nwork/prompt-*.md\nwork/.workers/\nwork/.worktrees/\n")
    (top / ".specyrd").mkdir()
    (top / ".specyrd" / "manifest.json").write_text('{"project_root": "sr"}\n')
    git(top, "init", "-q", "-b", "dev")
    git(top, "config", "user.email", "t@e.com")
    git(top, "config", "user.name", "T")
    git(top, "add", "-A")
    git(top, "commit", "-qm", "graph")
    git(top, "checkout", "-q", "-b", "feature/rm-thing")
    (top / "src").mkdir()
    (top / "src" / "a.py").write_text("print('a')\n")
    git(top, "add", "-A")
    git(top, "commit", "-qm", "impl")
    return top.resolve(), (top / "sr").resolve()


def test_nested_prompt_and_brief_give_paths_from_the_git_root(tmp_path: Path) -> None:
    _top, project = _nested(tmp_path)
    text, _p, err = build_prompt(project, "M1.1", role="executor", model="opus")
    assert err is None
    assert "The project root is `sr/`" in text and 'cd "$(git rev-parse --show-toplevel)"' in text
    assert "`sr/work/brief-M1.1.md` does not exist" in text
    assert "':(top,exclude)sr/work/implementation-summary-*.md'" in text
    assert "4. Write `sr/work/implementation-summary-M1.1.md`" in text
    assert "main checkout's `sr/work/reviews/M1.1`" in text
    assert "Write `work/implementation-summary" not in text
    assert ("- **Project root:** `sr/` under the git root. Work from the git root; from there this leaf's "
            "implementation summary is `sr/work/implementation-summary-M1.1.md`") in text   # the brief's line


def test_nested_delegate_puts_the_brief_under_the_worktrees_project_root(tmp_path: Path) -> None:
    top, project = _nested(tmp_path)
    git(top, "checkout", "-q", "dev")
    rec, created = ops.delegate(project, "M1.1", "opus")
    wt = Path(rec.worktree)
    assert created and wt != top and (wt / "sr" / "work" / "brief-M1.1.md").is_file()
    assert not (wt / "work").exists()
    _wait(project, rec.worker_id)
    ops.terminate(project, rec.worker_id)
    again, created = ops.delegate(project, "M1.1", "opus")   # its own untracked brief is bookkeeping
    assert created and Path(again.worktree) == wt
    _wait(project, again.worker_id)
