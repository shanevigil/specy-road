"""M15.10: try a roster before it lands — a working-tree dry-run plan, the models list diff, and
this clone's ``roster_add`` entries in ``roadmap/orchestration.local.yaml``."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tests.test_models_and_prompt import run_main
from tests.test_orchestrate_plan import ROSTER, only_assignment, plan_repo

from specy_road import orchestrate_plan as op
from specy_road import worker_ops as ops
from specy_road.bundled_scripts import grind_session_args, models_cli, orchestrate_cli, review_cli, role_prompt
from specy_road.bundled_scripts import worker_cli
from specy_road.orchestration_pinned import pinned_config
from specy_road.worker_state import WorkerError

BANNER = "DRY RUN: roster from the working tree, nothing may launch from this plan"
OPUS_OFF = ROSTER.replace("    class: senior\n", "    class: senior\n    available: false\n", 1)
TODAY = "2026-11-01"


def _roster(repo: Path, text: str) -> None:
    (repo / "roadmap" / "orchestration.yaml").write_text(text, encoding="utf-8")


def _local(repo: Path, text: str) -> None:
    (repo / "roadmap" / "orchestration.local.yaml").write_text(text, encoding="utf-8")


def _plan_cli(repo: Path, capsys, *extra: str) -> tuple[int, str, str]:
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        orchestrate_cli.main(["orchestrate", "plan", "--today", TODAY, "--repo-root", str(repo), *extra])
    out = capsys.readouterr()
    return e.value.code or 0, out.out, out.err


# A1 ------------------------------------------------------------------------------------------------


def test_worktree_dry_run_plans_the_uncommitted_roster_with_a_banner(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path, roster=OPUS_OFF)
    _roster(repo, ROSTER)   # uncommitted: opus available again
    _code, out, _err = _plan_cli(repo, capsys)
    assert BANNER not in out and "opus" not in out.split("batch 0:")[1]
    _code, out, _err = _plan_cli(repo, capsys, "--roster-from-worktree")
    assert out.splitlines()[0] == BANNER
    assert "roster: roadmap/orchestration.yaml in the working tree" in out
    assert "coordinator: opus" in out
    _code, out, err = _plan_cli(repo, capsys, "--roster-from-worktree", "--json")
    data = json.loads(out)
    assert data["roster_ref"] == "worktree" and data["batches"][0][0]["coordinator"] == "opus"
    assert BANNER in err
    _code, out, _err = _plan_cli(repo, capsys, "--json")
    assert json.loads(out)["roster_ref"] == "dev"


def test_delegation_still_reads_the_integration_branch_roster(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path, roster=OPUS_OFF, ready=False)
    _roster(repo, ROSTER)   # the working tree says opus is available; dev says it is not
    assert op.is_available(next(e for e in pinned_config(repo, worktree=True)[0]["roster"] if e["id"] == "opus"))
    _t, _p, err = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")
    assert err and "available: false" in err
    with pytest.raises(WorkerError, match="available: false"):
        ops.delegate(repo, "M1.1", "opus", offline=True)


@pytest.mark.parametrize("argv", [
    ["worker", "delegate", "M1.1", "--model", "opus", "--roster-from-worktree"],
    ["review", "delegate", "M1.1", "--model", "opus", "--roster-from-worktree"],
])
def test_delegate_entry_points_refuse_the_flag(argv: list[str], capsys) -> None:
    mod = worker_cli if argv[0] == "worker" else review_cli
    with pytest.raises(SystemExit) as e:
        mod.main(argv)
    assert e.value.code == 2 and "unrecognized arguments: --roster-from-worktree" in capsys.readouterr().err


def test_grind_session_refuses_the_flag(capsys) -> None:
    with pytest.raises(SystemExit) as e:
        grind_session_args.parse_grind_session_args(["--roster-from-worktree"])
    assert e.value.code == 2 and "--roster-from-worktree" in capsys.readouterr().err


# A2 ------------------------------------------------------------------------------------------------


def test_models_list_names_the_ref_and_the_uncommitted_diff(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path)
    capsys.readouterr()
    assert run_main(models_cli, "models", "list", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "roster: roadmap/orchestration.yaml at dev"
    assert "uncommitted roster changes" not in out
    edited = (ROSTER.replace("  - id: local\n    family: local\n    roles: [executor]\n"
                             "    may_process: [public, internal, restricted]\n    preflight: \"true\"\n",
                             "  - {id: extra, family: mistral, roles: [executor]}\n")
              .replace("    roles: [executor, reviewer]\n", "    roles: [executor]\n", 1))
    assert edited != ROSTER and "id: local" not in edited
    _roster(repo, edited)
    assert run_main(models_cli, "models", "list", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "uncommitted roster changes (working tree vs dev" in out
    assert "  added: extra\n" in out and "  removed: local\n" in out and "  changed: sol (roles)\n" in out
    assert run_main(models_cli, "models", "list", "--json", "--repo-root", str(repo)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["roster_ref"] == "dev"
    assert data["uncommitted_roster_changes"] == {"added": ["extra"], "removed": ["local"],
                                                  "changed": {"sol": ["roles"]}}
    assert "extra" not in {r["id"] for r in data["roster"]}   # the list itself is still the pinned roster


def test_models_list_diff_is_not_masked_by_the_local_availability_overlay(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path)
    _roster(repo, OPUS_OFF)                                    # uncommitted: opus available: false
    _local(repo, "roster:\n  - {id: opus, available: true}\n")   # this clone's overlay says true
    capsys.readouterr()
    assert run_main(models_cli, "models", "list", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "uncommitted roster changes (working tree vs dev" in out and "  changed: opus (available)\n" in out
    assert run_main(models_cli, "models", "list", "--json", "--repo-root", str(repo)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["uncommitted_roster_changes"] == {"added": [], "removed": [], "changed": {"opus": ["available"]}}


# A3 ------------------------------------------------------------------------------------------------

MINI = "  - {id: mini, family: mistral, roles: [executor], class: cheap}\n"


def test_roster_add_is_planned_labelled_local_and_used_for_delegation(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path)
    _local(repo, "roster:\n  - {id: sol, available: false}\nroster_add:\n" + MINI)
    plan, err = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    assert err is None and plan is not None
    a = only_assignment(plan)
    assert a.executor == "mini" and any("mini" in n and "[local]" in n for n in a.notes)
    assert "sol" not in a.reviewers   # the availability overlay in the same file still applies
    assert plan.local_roster == ["mini"] and plan.to_dict()["local_roster"] == ["mini"]
    _code, out, _err = _plan_cli(repo, capsys)
    assert "local roster entries (roadmap/orchestration.local.yaml roster_add, this clone only): mini" in out
    repo2 = plan_repo(tmp_path / "d", ready=False)
    _local(repo2, "roster_add:\n" + MINI)
    _t, _p, err = role_prompt.build_prompt(repo2, "M1.1", role="executor", model="mini")
    assert err is None


def test_roster_add_never_overrides_a_committed_id(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path)
    _local(repo, "roster_add:\n  - {id: opus, family: mistral, roles: [executor], class: cheap}\n")
    cfg, err = pinned_config(repo)
    assert err and "'opus' is already a roster entry" in err and "never overrides" in err
    assert [e["id"] for e in cfg["roster"]] == ["human"]
    plan, err = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    assert plan is None and "already a roster entry" in (err or "")


def test_roster_add_cli_needs_allow_local_cli(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path)
    channel = "  - {id: mini, family: mistral, roles: [executor], channels: {cli: 'mini-cli {prompt}'}}\n"
    _local(repo, "roster_add:\n" + channel)
    _cfg, err = pinned_config(repo)
    assert err and "channels.cli" in err and "allow_local_cli: true" in err
    profiled = ("  - {id: opus2, family: anthropic, roles: [executor], "
                "profile: model-profiles/anthropic-claude/claude-opus-5-5.md}\n")
    _local(repo, "roster_add:\n" + profiled)
    _cfg, err = pinned_config(repo)
    assert err and "access.cli" in err and "allow_local_cli: true" in err
    _local(repo, "allow_local_cli: true\nroster_add:\n" + channel + profiled)
    cfg, err = pinned_config(repo)
    assert err is None and {"mini", "opus2"} <= {e["id"] for e in cfg["roster"]}


def test_roster_add_entries_are_schema_checked(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path)
    _local(repo, "roster_add:\n  - {id: mini}\n")
    _cfg, err = pinned_config(repo)
    assert err and "roster_add" in err and "family" in err
