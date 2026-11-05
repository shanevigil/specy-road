"""M15.11 A4: `orchestrate plan` names this session as coordinator when none is rostered, and `--spread`
assigns executors round-robin among the capable entries by leaf order."""

from __future__ import annotations

import json
from pathlib import Path

from specy_road import orchestrate_plan as op
from specy_road.bundled_scripts import orchestrate_cli

from tests.review_repo_helpers import git
from tests.test_models_and_prompt import run_main
from tests.test_orchestrate_plan import plan_repo

ROSTER = """version: 1
roster:
  - {id: exec-a, family: alpha, roles: [executor], class: cheap}
  - {id: exec-b, family: beta, roles: [executor]}
  - {id: rev, family: gamma, roles: [reviewer]}
policy: {reviewers_required: 1}
"""


def three_leaf_repo(tmp_path: Path, roster: str = ROSTER) -> Path:
    """M1.1-M1.3, ready, no shared touch zones, so one batch in id order."""
    repo = plan_repo(tmp_path, roster)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    nodes = json.loads(chunk.read_text())["nodes"]
    for i in (2, 3):
        key = f"{i}{i}{i}{i}{i}{i}{i}{i}-1111-5111-8111-111111111111"
        node = {**nodes[0], "id": f"M1.{i}", "node_key": key, "codename": f"thing-{i}", "title": f"Thing {i}",
                "sibling_order": i, "touch_zones": [f"src{i}"], "planning_dir": f"planning/M1.{i}_thing-{i}_{key}.md"}
        nodes.append(node)
        (repo / node["planning_dir"]).write_text(f"# M1.{i} Thing {i}\n\n## Intent\n\nDo it.\n\n## References\n")
    chunk.write_text(json.dumps({"nodes": nodes}))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "three leaves")
    return repo


def executors(plan: op.OrchestrationPlan) -> list[tuple[str, str | None]]:
    return [(a.node_id, a.executor) for b in plan.batches for a in b]


def test_spread_assigns_three_leaves_round_robin_over_two_capable_entries(tmp_path: Path) -> None:
    repo = three_leaf_repo(tmp_path)
    plan, err = op.build_orchestration_plan(repo)
    assert err is None and plan is not None and plan.ok
    assert executors(plan) == [("M1.1", "exec-a"), ("M1.2", "exec-a"), ("M1.3", "exec-a")]   # cheapest
    plan, err = op.build_orchestration_plan(repo, spread=True)
    assert err is None and plan is not None and plan.ok
    assert executors(plan) == [("M1.1", "exec-a"), ("M1.2", "exec-b"), ("M1.3", "exec-a")]
    notes = [a.notes[0] for b in plan.batches for a in b]
    assert all(n.startswith("executor: round-robin (--spread) over 2 capable") for n in notes)
    again, _ = op.build_orchestration_plan(repo, spread=True)
    assert again is not None and executors(again) == executors(plan)   # deterministic


def test_spread_flag_on_the_cli(tmp_path: Path, capsys) -> None:
    repo = three_leaf_repo(tmp_path)
    assert run_main(orchestrate_cli, "orchestrate", "plan", "--spread", "--json", "--repo-root", str(repo)) == 0
    data = json.loads(capsys.readouterr().out)
    assert [a["executor"] for b in data["batches"] for a in b] == ["exec-a", "exec-b", "exec-a"]


def test_no_rostered_coordinator_means_this_session(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path, ROSTER)
    assert run_main(orchestrate_cli, "orchestrate", "plan", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "coordinator: this session   executor: exec-a" in out
    assert "to roster a model coordinator see docs/orchestration-roster.md" in out
    plan, _ = op.build_orchestration_plan(repo)
    assert plan is not None and plan.batches[0][0].to_dict()["coordinator_is_session"] is True


def test_a_rostered_coordinator_that_cannot_take_the_leaf_is_still_a_problem(tmp_path: Path) -> None:
    roster = ROSTER.replace("policy:", "  - {id: chair, family: delta, roles: [coordinator], available: false}\npolicy:")
    plan, _ = op.build_orchestration_plan(plan_repo(tmp_path, roster))
    assert plan is not None
    a = plan.batches[0][0]
    assert not a.coordinator_is_session and any("no eligible coordinator" in p for p in a.problems)

