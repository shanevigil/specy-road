"""Roster availability: available, paused_until, and orchestration.local.yaml overlay (M11.39)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, git, make_review_repo, review_text

from specy_road import orchestrate_plan as op
from specy_road import worker_ops as ops
from specy_road.bundled_scripts import role_prompt
from specy_road.orchestration_config import effective_config, roster_entry
from specy_road.review_eligible import reviewer_eligibility
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.worker_state import WorkerError

from tests.test_orchestrate_plan import ROSTER, only_assignment, plan_repo


def _write_local(repo: Path, text: str) -> None:
    (repo / "roadmap" / "orchestration.local.yaml").write_text(text, encoding="utf-8")


def test_available_false_skips_planning_and_refuses_delegate(tmp_path: Path) -> None:
    roster = ROSTER.replace("    class: senior\n", "    class: senior\n    available: false\n", 1)
    repo = plan_repo(tmp_path, roster=roster)
    a = only_assignment(op.build_orchestration_plan(repo, today=date(2026, 11, 1))[0])
    assert "opus" not in (a.executor, *a.reviewers, a.coordinator)
    repo2 = plan_repo(tmp_path / "d", roster=roster, ready=False)
    _t, _p, err = role_prompt.build_prompt(repo2, "M1.1", role="executor", model="opus")
    assert err and "available: false" in err
    with pytest.raises(WorkerError, match="available: false"):
        ops.delegate(repo2, "M1.1", "opus", offline=True)


def test_paused_until_date_in_future_and_past(tmp_path: Path) -> None:
    roster = ROSTER.replace("    may_process: [public, internal]\n",
                            "    may_process: [public, internal]\n    paused_until: 2026-11-10\n", 1)
    repo = plan_repo(tmp_path, roster=roster)
    assert only_assignment(op.build_orchestration_plan(repo, today=date(2026, 11, 5))[0]).executor == "sol"
    assert only_assignment(op.build_orchestration_plan(repo, today=date(2026, 11, 11))[0]).executor == "flash"


def test_paused_until_datetime() -> None:
    paused = {"paused_until": "2026-11-10T12:00:00Z"}
    assert not op.is_available(paused, datetime(2026, 11, 10, 11, 0, tzinfo=timezone.utc))
    assert op.is_available(paused, datetime(2026, 11, 10, 13, 0, tzinfo=timezone.utc))


def test_local_overlay_overrides_committed_roster(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path, ready=False)
    git(repo, "checkout", "-q", "dev")
    committed = (repo / "roadmap" / "orchestration.yaml").read_text()
    assert "available: false" not in committed
    _write_local(repo, "version: 1\nroster:\n  - {id: opus, available: false}\n")
    cfg, err = effective_config(repo, "dev")
    assert err is None and not op.is_available(roster_entry(cfg, "opus") or {})
    with pytest.raises(WorkerError, match="available: false"):
        ops.delegate(repo, "M1.1", "opus", offline=True)


def test_past_review_still_counts_when_model_is_paused(tmp_path: Path) -> None:
    roster = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
policy: {reviewers_required: 1}
"""
    repo = make_review_repo(tmp_path, orchestration=roster)
    head = git(repo, "rev-parse", "HEAD")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "REVIEW-opus.md").write_text(review_text(head, model="opus"))
    _write_local(repo, "version: 1\nroster:\n  - {id: opus, available: false}\n")
    gate = evaluate_gate(repo, NODE, head, branch="feature/rm-thing")
    assert gate.passed


def test_paused_counted_reviewer_still_shows_as_counting(tmp_path: Path) -> None:
    roster = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
policy: {reviewers_required: 2}
"""
    repo = make_review_repo(tmp_path, orchestration=roster)
    head = git(repo, "rev-parse", "HEAD")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "REVIEW-opus.md").write_text(review_text(head, model="opus"))
    _write_local(repo, "version: 1\nroster:\n  - {id: opus, available: false}\n")
    gate = evaluate_gate(repo, NODE, head, branch="feature/rm-thing")
    assert not gate.passed and [a.model for a in gate.approvals] == ["opus"]
    rows = {r["model"]: r for r in reviewer_eligibility(repo, NODE, gate, "feature/rm-thing")}
    assert rows["opus"]["eligible"] and rows["opus"]["reason"].startswith("its approval counts")
