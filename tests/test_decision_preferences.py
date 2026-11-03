"""Routing preferences in ``roadmap/decisions.yaml``: add, expiry, list order, plan notice (M11.58)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from specy_road import orchestrate_plan as op
from specy_road.bundled_scripts import orchestrate_cli
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.decisions import add_preference, preference_active, read_decisions, schema_errors
from tests.test_decisions import SKILL, _add_args, _decisions_repo, _run
from tests.test_orchestrate_plan import ROSTER, plan_repo


def _prefer(repo: Path, *extra: str) -> list[str]:
    return ["decisions", "add", "--repo-root", str(repo), "--kind", "preference", *extra]


def _ledger(repo: Path) -> list[dict]:
    return read_decisions(repo / "roadmap" / "decisions.yaml")["entries"]


def test_add_preference_writes_structured_fields_without_a_node(tmp_path: Path) -> None:
    repo = _decisions_repo(tmp_path)
    assert _run(_prefer(
        repo, "--summary", "Docs-only leaves go to sol while its budget lasts", "--role", "executor",
        "--model", "sol", "--model", "opus", "--applies-to", "docs", "--applies-to", "data",
        "--expires", "2026-11-07", "--why", "opus budget is low this week",
    )) == 0
    (e,) = _ledger(repo)
    assert e["id"] == "P1" and e["kind"] == "preference" and e["status"] == "open" and "node" not in e
    assert e["models"] == ["sol", "opus"] and e["applies_to"] == ["docs", "data"]
    assert e["role"] == "executor" and e["expires"] == "2026-11-07" and e["why_now"]
    assert _run(_add_args(repo)) == 0   # decision ids keep their own D# sequence
    assert [x["id"] for x in _ledger(repo)] == ["P1", "D1"]


@pytest.mark.parametrize("argv_tail,needle", [
    (["--kind", "preference", "--summary", "x", "--option", "a|b"], "does not take --option"),
    (["--kind", "preference", "--summary", "x", "--needed-by", "2026-12-01"], "does not take --needed-by"),
    (["M1.1", "--kind", "decision", "--summary", "x"], "needs --why, --option"),
    (["--kind", "preference", "--summary", "x", "--expires", "next friday"], "not a date or datetime"),
    (["--kind", "preference", "--summary", "x", "--expires", "2026-02-30"], "not a calendar date"),
])
def test_add_refuses_flags_the_kind_does_not_take(tmp_path: Path, capsys, argv_tail: list[str], needle: str) -> None:
    repo = _decisions_repo(tmp_path)
    assert _run(["decisions", "add", "--repo-root", str(repo), *argv_tail]) == 1
    assert needle in capsys.readouterr().err
    assert not (repo / "roadmap" / "decisions.yaml").is_file()


def test_decision_refuses_preference_flags(tmp_path: Path, capsys) -> None:
    repo = _decisions_repo(tmp_path)
    assert _run(_add_args(repo, "--model", "sol")) == 1
    assert "--model apply only to --kind preference" in capsys.readouterr().err


def test_schema_keeps_the_two_shapes_apart() -> None:
    pref = {"id": "P1", "kind": "preference", "summary": "s", "asked": "2026-11-01", "status": "open"}
    assert schema_errors({"version": 1, "entries": [pref]}) == []
    assert schema_errors({"version": 1, "entries": [{**pref, "options": [{"label": "a", "effect": "b"}]}]})
    assert schema_errors({"version": 1, "entries": [{**pref, "kind": "decision", "node": "M1.1"}]})


def test_expiry_is_inclusive_through_the_date_and_exact_for_a_datetime() -> None:
    base = {"id": "P1", "kind": "preference", "status": "open", "summary": "s"}
    assert preference_active({**base, "expires": "2026-11-05"}, date(2026, 11, 5))
    assert not preference_active({**base, "expires": "2026-11-05"}, date(2026, 11, 6))
    at = {**base, "expires": "2026-11-05T12:00:00Z"}
    assert preference_active(at, datetime(2026, 11, 5, 11, 59, tzinfo=timezone.utc))
    assert not preference_active(at, datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc))
    assert preference_active(base, date(2999, 1, 1))
    assert not preference_active({**base, "status": "closed"}, date(2026, 1, 1))


def test_list_shows_active_preferences_first_and_drops_expired(tmp_path: Path, capsys) -> None:
    repo = _decisions_repo(tmp_path)
    assert _run(_add_args(repo, "--id", "Ddue", "--needed-by", "2026-11-05", "--summary", "Due question")) == 0
    assert _run(_prefer(repo, "--summary", "Expired rule", "--expires", "2020-01-01", "--id", "Pold")) == 0
    assert _run(_prefer(repo, "--summary", "Later rule", "--asked", "2026-11-02", "--id", "Plater")) == 0
    assert _run(_prefer(repo, "--summary", "Earlier rule", "--asked", "2026-11-01",
                        "--expires", "2999-01-01", "--id", "Pearly")) == 0
    capsys.readouterr()
    assert _run(["decisions", "list", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "Pold" not in out and "Expired rule" not in out
    assert out.index("Pearly") < out.index("Plater") < out.index("Ddue")
    assert _run(["decisions", "list", "--json", "--repo-root", str(repo)]) == 0
    assert [e["id"] for e in json.loads(capsys.readouterr().out)] == ["Pearly", "Plater", "Ddue"]
    assert any(e["id"] == "Pold" and e["status"] == "open" for e in _ledger(repo))   # dropped, not closed


def test_supersede_and_close_a_preference_without_a_sheet_record(tmp_path: Path, capsys) -> None:
    repo = _decisions_repo(tmp_path)
    assert _run(_prefer(repo, "--summary", "Use sol for docs", "--model", "sol")) == 0
    assert _run(_prefer(repo, "--summary", "Use flash for docs", "--model", "flash", "--supersedes", "P1")) == 0
    old, new = _ledger(repo)
    assert old["status"] == "closed" and old["answer"] == "superseded by P2" and old.get("closed")
    assert new["status"] == "open"
    assert _run(_prefer(repo, "--summary", "again", "--supersedes", "P1")) == 1
    assert "not an open preference" in capsys.readouterr().err
    assert _run(["decisions", "close", "P2", "--answer", "human dropped it", "--repo-root", str(repo)]) == 0
    assert _ledger(repo)[1]["status"] == "closed"
    capsys.readouterr()
    assert _run(["decisions", "list", "--repo-root", str(repo)]) == 0
    assert "No open decisions" in capsys.readouterr().out


def _plan(repo: Path, *extra: str) -> int:
    with pytest.raises(SystemExit) as e:
        orchestrate_cli.main(["orchestrate", "plan", "--today", "2026-11-05", "--repo-root", str(repo), *extra])
    return int(e.value.code or 0)


def test_plan_prints_active_preferences_with_roster_availability(tmp_path: Path, capsys) -> None:
    roster = ROSTER.replace("    roles: [executor, reviewer]\n", "    roles: [executor, reviewer]\n    paused_until: 2026-11-10\n", 1)
    roster = roster.replace("policy: {reviewers_required: 2", "policy: {reviewers_required: 1")
    repo = plan_repo(tmp_path, roster=roster)
    add_preference(repo, summary="Docs leaves go to sol, then flash", role="executor",
                   models=["sol", "flash", "ghost"], applies_to=["docs"], expires="2026-11-05")
    add_preference(repo, summary="Gone yesterday", expires="2026-11-04")
    code = _plan(repo)
    out = capsys.readouterr().out
    assert code == 0
    assert "preferences not applied automatically" in out
    assert "P1 [preference] role executor; prefer sol, flash, ghost; leaf kinds docs" in out
    assert "! sol: paused until 2026-11-10 (roster)" in out and "! ghost: not in the roster (roster)" in out
    assert "flash:" not in out.split("preferences not applied", 1)[1]
    assert "Gone yesterday" not in out
    _plan(repo, "--json")
    data = json.loads(capsys.readouterr().out)
    (pref,) = data["preferences_not_applied"]
    assert pref["id"] == "P1" and pref["roster_notes"] == ["sol: paused until 2026-11-10", "ghost: not in the roster"]
    assert data["preferences_error"] is None


def test_plan_without_preferences_or_with_a_broken_ledger(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path)
    plan, _ = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    assert plan is not None and plan.preferences_not_applied == [] and plan.preferences_error is None
    assert "preferences" not in "\n".join(orchestrate_cli.render(plan))
    (repo / "roadmap" / "decisions.yaml").write_text("version: 1\nentries:\n  - id: P1\n", encoding="utf-8")
    code = _plan(repo)
    out = capsys.readouterr().out
    assert code == 0 and "! preferences: roadmap/decisions.yaml fails its schema" in out


def test_coordinator_prompt_and_skill_name_the_preference_routine(tmp_path: Path) -> None:
    repo = _decisions_repo(tmp_path)
    text, _, err = build_prompt(repo, "M1.1", role="coordinator", model="human")
    assert err is None
    for blob in (text, SKILL.read_text(encoding="utf-8")):
        assert "--kind preference" in blob and "--supersedes" in blob
        assert "start of every session" in blob and "before each" in blob
        assert "worker delegate" in blob and "reviewer launch" in blob
        assert "paused_until" in blob and "not a preference" in blob
