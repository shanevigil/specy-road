"""Slice 3: `orchestrate plan` assignment, and the routing rules `prompt` enforces."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road import orchestrate_plan as op
from specy_road.bundled_scripts import orchestrate_cli, role_prompt

REPO = Path(__file__).resolve().parent.parent
PROFILES = REPO / "specy_road" / "templates" / "project" / "model-profiles"

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - id: opus
    family: anthropic
    profile: model-profiles/anthropic-claude/claude-opus-5-5.md
    roles: [coordinator, executor, reviewer]
    class: senior
    subagent_family_lock: anthropic
  - id: sol
    family: openai
    profile: model-profiles/openai-gpt/gpt-6.1-sol.md
    roles: [executor, reviewer]
  - id: flash
    family: google
    profile: model-profiles/google-gemini/gemini-3.8-flash.md
    roles: [executor]
    may_process: [public, internal]
  - id: local
    family: local
    roles: [executor]
    may_process: [public, internal, restricted]
    preflight: "true"
policy: {reviewers_required: 2, reviewers_distinct_families: true}
"""


def plan_repo(tmp_path: Path, roster: str = ROSTER, node_extra: str = "", *, ready: bool = True) -> Path:
    """``ready``: free the leaf (no claim, Not Started) so the planner sees it.

    ``prompt`` needs the opposite — a claimed leaf with its branch — so the
    enforcement tests pass ``ready=False`` and keep the helper's claim.
    """
    repo = make_review_repo(tmp_path, orchestration=roster)
    for rel in ("anthropic-claude/claude-opus-5-5.md", "openai-gpt/gpt-6.1-sol.md", "google-gemini/gemini-3.8-flash.md"):
        dest = repo / "model-profiles" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PROFILES / rel, dest)
    git(repo, "checkout", "-q", "dev")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    text = chunk.read_text()
    if ready:
        (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
        text = text.replace('"status": "In Progress"', '"status": "Not Started"')
    if node_extra:
        text = text.replace('"id": "M1.1",', f'"id": "M1.1", {node_extra},')
    chunk.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "ready" if ready else "claimed")
    return repo


def only_assignment(plan: op.OrchestrationPlan) -> op.Assignment:
    assert len(plan.batches) == 1 and len(plan.batches[0]) == 1
    return plan.batches[0][0]


def test_default_leaf_gets_cheapest_executor_and_two_families(tmp_path: Path) -> None:
    plan, err = op.build_orchestration_plan(plan_repo(tmp_path), today=date(2026, 11, 1))
    assert err is None and plan is not None and plan.ok
    a = only_assignment(plan)
    assert a.executor == "flash"                      # $0.75/$3.75, executor score 3
    assert set(a.reviewers) == {"sol", "opus"}        # two families, highest reviewer scores
    assert a.coordinator == "opus"                    # highest coordinator score
    assert any("cheapest capable" in n for n in a.notes)


def test_restricted_leaf_routes_only_to_a_model_that_may_process_it(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path, node_extra='"sensitivity": "restricted"')
    plan, _ = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    a = only_assignment(plan)
    assert a.executor == "local"
    assert a.reviewers == [] and not a.ok
    assert "may process 'restricted'" in a.problems[0]


def test_senior_eligibility_picks_the_tagged_class(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path, node_extra='"executor_eligibility": "senior"')
    a = only_assignment(op.build_orchestration_plan(repo, today=date(2026, 11, 1))[0])
    assert a.executor == "opus"
    assert "opus" not in a.reviewers and set(a.reviewers) == {"sol", "human"}


def test_unavailable_model_is_skipped_until_its_date(tmp_path: Path) -> None:
    roster = ROSTER.replace("    may_process: [public, internal]\n", "    may_process: [public, internal]\n    unavailable_until: 2026-11-10\n", 1)
    repo = plan_repo(tmp_path, roster=roster)
    assert only_assignment(op.build_orchestration_plan(repo, today=date(2026, 11, 5))[0]).executor == "sol"
    assert only_assignment(op.build_orchestration_plan(repo, today=date(2026, 11, 11))[0]).executor == "flash"


def test_substitute_counts_as_a_reviewer(tmp_path: Path) -> None:
    roster = ROSTER.replace("  - id: sol\n    family: openai\n    profile: model-profiles/openai-gpt/gpt-6.1-sol.md\n    roles: [executor, reviewer]\n",
                            "  - id: sol\n    family: openai\n    profile: model-profiles/openai-gpt/gpt-6.1-sol.md\n    roles: [executor]\n")
    roster += "substitutions:\n  - {slot: reviewer-openai, use: sol, decided: 2026-10-01, expires: 2026-12-31}\n"
    a = only_assignment(op.build_orchestration_plan(plan_repo(tmp_path, roster=roster), today=date(2026, 11, 1))[0])
    assert "sol" in a.reviewers and any("[substitute]" in n for n in a.notes)


def test_cli_text_and_json_and_exit_code(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        orchestrate_cli.main(["orchestrate", "plan", "--today", "2026-11-01", "--repo-root", str(repo)])
    assert (e.value.code or 0) == 0
    out = capsys.readouterr().out
    assert "policy: 2 distinct-family reviewer(s)" in out and "executor: flash" in out
    with pytest.raises(SystemExit) as e:
        orchestrate_cli.main(["orchestrate", "plan", "--json", "--today", "2026-11-01", "--repo-root", str(repo)])
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] and data["batches"][0][0]["executor"] == "flash"
    restricted = plan_repo(tmp_path / "r2", node_extra='"sensitivity": "restricted"')
    with pytest.raises(SystemExit) as e:
        orchestrate_cli.main(["orchestrate", "plan", "--today", "2026-11-01", "--repo-root", str(restricted)])
    assert e.value.code == 1
    assert "! need 2 distinct-family reviewers" in capsys.readouterr().out


def test_cli_rejects_an_unknown_parent(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as e:
        orchestrate_cli.main(["orchestrate", "plan", "NOPE", "--repo-root", str(plan_repo(tmp_path))])
    assert e.value.code == 1 and "unknown node id" in capsys.readouterr().err


# --- prompt enforcement -------------------------------------------------------

def test_prompt_refuses_a_model_that_may_not_see_the_leaf(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path, node_extra='"sensitivity": "restricted"', ready=False)
    _t, _p, err = role_prompt.build_prompt(repo, "M1.1", role="executor", model="flash")
    assert err and "may process only ['public', 'internal']" in err
    text, _p, err = role_prompt.build_prompt(repo, "M1.1", role="executor", model="local")
    assert err is None and "## Your role: executor" in text


def test_prompt_refuses_an_unavailable_model(tmp_path: Path) -> None:
    roster = ROSTER.replace("    class: senior\n", "    class: senior\n    unavailable_until: 2999-01-01\n", 1)
    _t, _p, err = role_prompt.build_prompt(plan_repo(tmp_path, roster=roster, ready=False), "M1.1", role="executor", model="opus")
    assert err and "unavailable until 2999-01-01" in err


def test_executor_prompt_states_the_family_lock(tmp_path: Path) -> None:
    text, _p, err = role_prompt.build_prompt(plan_repo(tmp_path, ready=False), "M1.1", role="executor", model="opus")
    assert err is None and "spawn sub-agents only of family `anthropic`" in text
    text, _p, _e = role_prompt.build_prompt(plan_repo(tmp_path / "b", ready=False), "M1.1", role="executor", model="sol")
    assert "spawn sub-agents only" not in text


def test_preflight_runs_before_the_cli_channel(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path, roster=ROSTER.replace('    preflight: "true"\n', '    preflight: "false"\n'), ready=False)
    with pytest.raises(SystemExit) as e:
        role_prompt.main(["M1.1", "--model", "local", "--role", "executor", "--channel", "cli", "--repo-root", str(repo)])
    assert e.value.code == 1
    assert "preflight failed" in capsys.readouterr().err
