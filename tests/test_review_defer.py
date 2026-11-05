"""M12.1: the fix-round budget, RCA ``defer_findings``, and the human-only ``review defer`` with its audit trail."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_cli import _ready
from tests.test_review_rca import ROSTER, _block_round, _run, _status

from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate

ROSTER4 = ROSTER + "  - {id: sonnet, family: anthropic, roles: [reviewer]}\n"
BUDGET = "policy: {max_fix_rounds: 2}\n"
SCHEMA = Path(__file__).resolve().parents[1] / "specy_road" / "schemas" / "rca-record.schema.json"


def _item(commit: str, **kw) -> dict:
    return {"finding": "round 2/opus: CRLF input still warns", "reviewer": "opus", "commit": commit,
            "category": "boundary", "acceptance_id": "A1", "input_class": "CRLF line endings",
            "follow_up_title": "Handle CRLF input", "follow_up_acceptance": "CRLF input parses like LF", **kw}


def _record(round_: int, items: list[dict] | None, *, action: str = "defer_findings", disposition_class=None) -> dict:
    data = {
        "node_id": "M1.1", "model": "sol", "date": "2026-11-04",
        "trigger": {"rule": "forced", "acceptance_ids": [], "round": round_, "reason": "fix-round budget spent"},
        "classification": {"primary": "hard_problem", "confidence": 0.7},
        "evidence": [{"kind": "finding", "ref": f"round {round_}/opus", "note": "a new input class"}],
        "recommended_action": {"type": action, "instructions": "defer the new class",
                               "requires_human_approval": True},
    }
    if items is not None:
        data["deferred_findings"] = items
    if disposition_class:
        data["classification"]["primary"] = "specification"
        data["criterion_rewrite"] = {
            "acceptance_id": "A1", "original_text": "a.py exists", "proposed_text": "src/a.py exists",
            "finding_disposition": [{"finding": "round 1/opus", "label": "out_of_scope_now",
                                     "input_class": disposition_class}]}
    return data


def _write_rca(repo: Path, data: dict) -> Path:
    path = reviews_dir(repo, "M1.1") / f"RCA-{data['trigger']['round']}.md"
    path.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nreasoning\n")
    return path


def _review(repo: Path, model: str, verdict: str = "block") -> None:
    notes = repo.parent / f"notes-{model}.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model, verdict=verdict,
                                 a1="fail" if verdict == "block" else "pass"))
    assert _run("review", "record", "M1.1", "--model", model, "--verdict", verdict,
                "--file", str(notes), "--repo-root", str(repo)) == 0


class _Tty:
    def isatty(self) -> bool:
        return True


@pytest.fixture
def human(monkeypatch):
    """A person at a terminal answering ``y``."""
    monkeypatch.setattr("sys.stdin", _Tty())
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")


def _untouched(repo: Path) -> None:
    assert not (repo / "roadmap" / "decisions.yaml").exists()
    assert not list(reviews_dir(repo, "M1.1").glob("DEFERRAL-*"))
    assert [n["id"] for n in load_roadmap(repo)["nodes"]] == ["M1.1"]


def test_schema_accepts_defer_findings_only_with_its_list() -> None:
    v = Draft202012Validator(json.loads(SCHEMA.read_text()))
    assert not list(v.iter_errors(_record(2, [_item("abc1234")])))
    assert list(v.iter_errors(_record(2, None)))
    assert list(v.iter_errors(_record(2, [])))
    for key in ("input_class", "follow_up_title", "follow_up_acceptance"):
        bad = _item("abc1234")
        del bad[key]
        assert list(v.iter_errors(_record(2, [bad])))
    assert not list(v.iter_errors(_record(2, None, action="escalate_human", disposition_class="CRLF")))


def test_budget_unset_reports_nothing_new(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    for n in (1, 2):
        _block_round(repo, n)
    code, st = _status(repo, capsys)
    assert (code, st["state"]) == (1, "blocked") and "fix_round_budget" not in st
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    assert "fix_round" not in capsys.readouterr().out


def test_budget_spent_names_the_rca_then_the_defer_command(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    code, st = _status(repo, capsys)
    assert (code, st["state"]) == (1, "blocked")
    assert st["fix_round_budget"]["blocking_rounds"] == 1 and not st["fix_round_budget"]["spent"]
    _two_fail_round(repo, 2, correctness=False)   # a finding review defer can bind
    code, st = _status(repo, capsys)
    assert (code, st["state"]) == (1, "fix_round_budget_spent")
    assert st["fix_round_budget"]["next"] == (
        "specy-road prompt M1.1 --role rca --force --reason 'fix-round budget spent' --model sol")
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    out = capsys.readouterr().out
    assert "M1.1: fix_round_budget_spent" in out and "policy.max_fix_rounds 2" in out
    rca = _write_rca(repo, _record(2, [_item(git(repo, "rev-parse", "HEAD"))]))
    st = _status(repo, capsys)[1]
    assert st["state"] == "fix_round_budget_spent" and not any("RCA" in p for p in st["problems"])
    assert st["fix_round_budget"]["next"] == f"specy-road review defer M1.1 --rca {rca}"


def test_defer_refuses_a_run_without_a_terminal(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    _block_round(repo, 2)
    rca = _write_rca(repo, _record(2, [_item(git(repo, "rev-parse", "HEAD"))]))
    monkeypatch.setattr("builtins.input", lambda _p="": pytest.fail("must not prompt"))
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "human-only" in err and "interactive terminal" in err and "no --yes" in err
    _untouched(repo)


def test_defer_applies_and_resolves_only_that_reviewers_block_at_that_commit(tmp_path: Path, capsys,
                                                                              human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER4 + BUDGET)
    _block_round(repo, 1)
    _two_fail_round(repo, 2, correctness=False)   # opus: boundary 'CRLF input still warns', A1 fails
    _review(repo, "sonnet")   # another reviewer blocks the same commit
    head = git(repo, "rev-parse", "HEAD")
    rca = _write_rca(repo, _record(2, [_item(head[:12])]))
    capsys.readouterr()
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 0
    new = next(n for n in load_roadmap(repo)["nodes"] if n["id"] != "M1.1")
    assert new.get("parent_id") == NODE["parent_id"] and f"[ok] added {new['id']}" in capsys.readouterr().out
    assert (new["title"], new["acceptance"], new["status"]) == (
        "Handle CRLF input", ["CRLF input parses like LF"], "Not Started")
    entry = yaml.safe_load((repo / "roadmap" / "decisions.yaml").read_text())["entries"][0]
    assert (entry["kind"], entry["node"], entry["status"]) == ("decision", "M1.1", "closed")
    for part in ("T <t@e.com>", "round 2/opus: CRLF input still warns", "'CRLF line endings'", f"-> {new['id']}"):
        assert part in entry["answer"]
    marker = yaml.safe_load((reviews_dir(repo, "M1.1") / "DEFERRAL-2.yaml").read_text())
    assert (marker["decision"], marker["deferred"][0]["commit"]) == (entry["id"], head)
    gate = evaluate_gate(repo, NODE, head)
    assert [b.model for b in gate.blocks] == ["sonnet"]   # another reviewer's block still counts
    assert any(r.data["model"] == "opus" and why == f"deferred by {entry['id']}" for r, why in gate.ineligible)
    code, st = _status(repo, capsys)   # applied, sonnet still blocks: still spent, never `review defer` again
    b = st["fix_round_budget"]
    assert (code, st["state"], b["state"], b["step"]) == (1, "fix_round_budget_spent",
                                                          "spent_defer_applied_no_executor", "blocked")
    assert b["next"].startswith("specy-road decisions add M1.1") and "RCA-2.md is applied" in b["next_why"]
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    assert "review defer" not in capsys.readouterr().out
    _block_round(repo, 3)   # the same reviewer on a later commit
    later = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert [b.model for b in later.blocks] == ["opus"]


def test_an_open_or_missing_decision_does_not_resolve_the_block(tmp_path: Path, human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    _two_fail_round(repo, 2, correctness=False)   # opus: boundary 'CRLF input still warns', A1 fails
    head = git(repo, "rev-parse", "HEAD")
    rca = _write_rca(repo, _record(2, [_item(head)]))
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 0
    (repo / "roadmap" / "decisions.yaml").unlink()
    assert [b.model for b in evaluate_gate(repo, NODE, head).blocks] == ["opus"]


def test_refuses_an_input_class_an_earlier_record_named(tmp_path: Path, capsys, human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    _write_rca(repo, _record(1, None, action="escalate_human", disposition_class="empty final message"))
    _block_round(repo, 2)
    rca = _write_rca(repo, _record(2, [_item(git(repo, "rev-parse", "HEAD"), input_class="Empty  Final message")]))
    capsys.readouterr()
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "input class 'Empty  Final message' was already named in RCA-1.md" in err and "nothing was written" in err
    _untouched(repo)


def test_refuses_a_correctness_finding_on_an_id_an_earlier_round_passed(tmp_path: Path, capsys, human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)   # A2 passes in every round
    _block_round(repo, 2)
    item = _item(git(repo, "rev-parse", "HEAD"), category="correctness", acceptance_id="A2")
    rca = _write_rca(repo, _record(2, [item]))
    capsys.readouterr()
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 1
    assert "a correctness finding on A2, which round 1 marked pass" in capsys.readouterr().err
    _untouched(repo)


def test_a_finding_on_an_earlier_commit_needs_a_block_there(tmp_path: Path, capsys, human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    _block_round(repo, 2)
    stray = commit_file(repo, "src/z.py", "z\n", "unreviewed")
    rca = _write_rca(repo, _record(2, [_item(stray)]))
    capsys.readouterr()
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 1
    assert "no blocking record from opus at that commit" in capsys.readouterr().err
    _untouched(repo)


def test_rca_prompt_states_the_deferral_rule_and_shape(tmp_path: Path) -> None:
    from specy_road.bundled_scripts import role_prompt

    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="rca", model="sol", force_reason="budget")
    assert err is None and "`defer_findings`" in text and "specy-road review defer M1.1 --rca" in text
    assert "deferred_findings:" in text and "follow_up_acceptance" in text
    assert "lower-cased, whitespace collapsed" in text and "earlier round marked `pass`" in text


def _two_fail_round(repo: Path, n: int, *, correctness: bool) -> None:
    """opus blocks on A1 (boundary) and, when ``correctness``, on A2 with a correctness finding."""
    commit_file(repo, f"src/m{n}.py", f"m = {n}\n", f"mixed {n}")
    text = review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict="block", a1="fail")
    if correctness:
        text = text.replace("A2: pass", "A2: fail").replace("correctness: []", "correctness:\n  - A2 regressed")
    notes = repo.parent / "notes.md"
    notes.write_text(text.replace("boundary: []", "boundary:\n  - CRLF input still warns"))
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0


def _forge_closed_deferral(repo: Path, items: list[dict]) -> None:
    """A closed decision and a marker written by hand: the gate must re-check them against the history."""
    (repo / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump({"version": 1, "entries": [{
        "id": "D9", "node": "M1.1", "kind": "decision", "summary": "s", "why_now": "w",
        "options": [{"label": "a", "effect": "b"}], "recommendation": "a", "recommendation_reason": "r",
        "default_if_unanswered": "a", "asked": "2026-11-04", "status": "closed", "answer": "x",
        "closed": "2026-11-04"}]}))
    (reviews_dir(repo, "M1.1") / "DEFERRAL-9.yaml").write_text(yaml.safe_dump(
        {"node_id": "M1.1", "rca": "RCA-9.md", "round": 9, "decision": "D9", "deferred": items}))
