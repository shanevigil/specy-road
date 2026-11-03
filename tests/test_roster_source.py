"""M11.20: orchestrate plan and validate name where the roster is read from and how to make a change count.

Three copies are compared through the public CLI: the working tree, the local integration branch
(when it has unpushed commits) and ``origin/dev``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tests.review_repo_helpers import git
from tests.test_orchestrate_plan import ROSTER, only_assignment, plan_repo
from tests.test_worker_cli_fixes import EXECUTORLESS

from specy_road import orchestrate_plan as op
from specy_road.bundled_scripts import orchestrate_cli
from specy_road.bundled_scripts.validate_roadmap import validate_orchestration_contract


def _pushed(repo: Path, tmp_path: Path) -> None:
    """Give ``repo`` an ``origin`` holding its ``dev`` as now, so routing reads ``origin/dev``."""
    bare = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "dev")


def _cli(repo: Path, monkeypatch, capsys) -> tuple[dict, str, str]:
    """``orchestrate plan --json`` and ``validate`` as an adopter runs them: (plan, validate out, validate err)."""
    from specy_road.bundled_scripts import validate_roadmap
    capsys.readouterr()
    with pytest.raises(SystemExit):
        orchestrate_cli.main(["orchestrate", "plan", "--json", "--today", "2026-11-01", "--repo-root", str(repo)])
    plan = json.loads(capsys.readouterr().out)
    monkeypatch.setattr("sys.argv", ["validate", "--repo-root", str(repo)])
    validate_roadmap.main()
    out = capsys.readouterr()
    return plan, out.out, out.err


ROSTER_STATES = {
    # state: (roster pushed to origin/dev, step on the local dev, check out origin/dev after, drift)
    "in-sync": (ROSTER, None, False, None),
    "uncommitted": (EXECUTORLESS, "write", False,
                    "in the working tree differs from origin/dev, where the roster is read from; routing uses "
                    "the copy there until the change is committed to dev and pushed to origin"),
    "changed-unpushed": (EXECUTORLESS, "commit", True,
                         "on the local dev differs from origin/dev, where the roster is read from; routing uses "
                         "the copy there until dev is pushed to origin"),
    "changed-unpushed-on-dev": (EXECUTORLESS, "commit", False,
                                "on the local dev differs from origin/dev, where the roster is read from"),
    "added-unpushed": (None, "commit", True,
                       "is committed on the local dev but not on origin/dev, where the roster is read from, so "
                       "routing uses the default roster (no models) until dev is pushed to origin"),
    "deleted-uncommitted": (ROSTER, "unlink", False,
                            "is deleted in the working tree but still on origin/dev, where the roster is read from; "
                            "routing uses the copy there until the deletion is committed to dev and pushed to origin"),
    "deleted-unpushed": (ROSTER, "delete", True,
                         "is deleted on the local dev but still on origin/dev, where the roster is read from; "
                         "routing uses the copy there until dev is pushed to origin"),
}


def _arrange(repo: Path, step: str | None, detach: bool) -> None:
    """Put the roster in the state ``step`` names on the local dev, then optionally leave dev."""
    yaml_path = repo / "roadmap" / "orchestration.yaml"
    if step in ("write", "commit"):
        yaml_path.write_text(ROSTER)
    if step == "delete":
        git(repo, "rm", "-q", "roadmap/orchestration.yaml")
    if step == "unlink":
        yaml_path.unlink()
    if step in ("commit", "delete"):
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", f"roster {step}")   # on the local dev, not on origin/dev
    if detach:
        git(repo, "checkout", "-q", "-b", "feature/x", "origin/dev")   # working tree as pushed


def _remedy(repo: Path, step: str, detach: bool) -> None:
    """What the sentence says to do: commit (an uncommitted edit or deletion), push, fetch."""
    if step in ("write", "unlink"):
        git(repo, "commit", "-qam", "roster")
    git(repo, "push", "-q", "origin", "dev")
    git(repo, "fetch", "-q", "origin")
    if detach:
        git(repo, "merge", "-q", "--ff-only", "origin/dev")


@pytest.mark.parametrize("state", list(ROSTER_STATES))
def test_plan_and_validate_name_the_roster_source_and_remedy(
        state: str, tmp_path: Path, monkeypatch, capsys) -> None:
    pushed, step, detach, drift = ROSTER_STATES[state]
    repo = plan_repo(tmp_path, roster=pushed)
    _pushed(repo, tmp_path)
    _arrange(repo, step, detach)
    plan, out, err = _cli(repo, monkeypatch, capsys)
    assert plan["roster_ref"] == "origin/dev"
    problems = " ".join(p for b in plan["batches"] for a in b for p in a["problems"])
    if drift is None:
        assert plan["roster_drift"] is None and "warning: roadmap/orchestration.yaml" not in err
        assert plan["batches"][0][0]["executor"]
        return
    assert drift in plan["roster_drift"] and "warning: roadmap/orchestration.yaml" in err and drift in err
    assert "may_process containing" not in problems
    if step in ("unlink", "delete"):   # routing still uses origin/dev's roster, not the default policy
        assert "the default policy applies" not in out
    _remedy(repo, step, detach)
    plan, out, err = _cli(repo, monkeypatch, capsys)
    assert "warning: roadmap/orchestration.yaml" not in err
    if step in ("delete", "unlink"):   # pushed deletion: no roster anywhere, the docs notice and no warning
        assert plan["roster_drift"].startswith("no roadmap/orchestration.yaml on origin/dev")
        assert "docs/orchestration.md" in out
    else:
        assert plan["roster_drift"] is None


def test_no_roster_anywhere_points_at_the_docs_not_the_may_process_hint(
        tmp_path: Path, monkeypatch, capsys) -> None:
    from specy_road.bundled_scripts import validate_roadmap
    repo = plan_repo(tmp_path, roster=None)
    plan, _ = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    assert plan.roster_drift.startswith(f"no roadmap/orchestration.yaml on {plan.roster_ref}, where the roster")
    assert "nor in the working tree" in plan.roster_drift and "docs/orchestration.md" in plan.roster_drift
    problems = " ".join(only_assignment(plan).problems)
    assert "docs/orchestration.md" in problems and "may_process containing" not in problems
    capsys.readouterr()
    validate_orchestration_contract(repo)
    assert capsys.readouterr().err == ""   # no file: a notice on stdout, not a warning
    assert "docs/orchestration.md" in validate_roadmap.no_orchestration_notice(repo)
    monkeypatch.setattr("sys.argv", ["validate", "--repo-root", str(repo)])
    validate_roadmap.main()
    out = capsys.readouterr().out
    assert validate_roadmap.NO_ORCHESTRATION_NOTICE in out and "nor in the working tree" in out
