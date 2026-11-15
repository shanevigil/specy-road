"""M12.1: the fix-round budget, RCA ``defer_findings``, and the human-only ``review defer`` with its audit trail."""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from tests.support.review import NODE, commit_file, make_review_repo, review_text, git
from tests.support.extracted.review_cli import _ready
from tests.support.same.run_651387813ee4 import _run
from tests.support.extracted.review_rca import ROSTER, _block_round, _status

from specy_road.roadmap_load import load_roadmap
from specy_road.review_defer_rules import answer_item
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.rework_rca import governing_rca
from tests.support.extracted.review_defer import (
    BUDGET,
    ROSTER4,
    _Tty,
    _forge_closed_deferral,
    _item,
    _record,
    _review,
    _two_fail_round,
    _untouched,
    _write_rca,
    bound_ledger,
    human,
)

SCHEMA = Path(__file__).resolve().parents[1] / "specy_road" / "schemas" / "rca-record.schema.json"
















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


@pytest.mark.slow
def test_budget_unset_reports_nothing_new(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    for n in (1, 2):
        _block_round(repo, n)
    code, st = _status(repo, capsys)
    assert (code, st["state"]) == (1, "blocked") and "fix_round_budget" not in st
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    assert "fix_round" not in capsys.readouterr().out


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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








def _crlf_review(repo: Path, model: str) -> None:
    """``model`` blocks HEAD on A1 with the boundary finding 'CRLF input still warns'."""
    notes = repo.parent / f"notes-{model}.md"
    text = (review_text(git(repo, "rev-parse", "HEAD"), model=model, verdict="block", a1="fail")
            .replace("boundary: []", "boundary:\n  - CRLF input still warns"))
    front, _body = text.rsplit("---\n", 1)
    notes.write_text(front + "---\n" + f"# {model} notes\n", encoding="utf-8")
    assert _run("review", "record", "M1.1", "--model", model, "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0


def _edit_yaml(path: Path, edit) -> None:
    data = yaml.safe_load(path.read_text())
    edit(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _unrelated(repo: Path, d: Path, ledger: Path) -> None:
    _edit_yaml(ledger, lambda doc: doc["entries"].append({**doc["entries"][0], "id": "D99", "why_now": "w",
                                                         "answer": "Use blue for the button."}))
    _edit_yaml(d / "DEFERRAL-2.yaml", lambda m: m.update(decision="D99"))


def _rewrite(repo: Path, d: Path, item: dict) -> None:
    """RCA-2 and its marker rewritten to ``item``, same finding text; the decision left as recorded."""
    _write_rca(repo, _record(2, [item]))
    _edit_yaml(d / "DEFERRAL-2.yaml", lambda m: m["deferred"][0].update(reviewer=item["reviewer"],
                                                                         commit=item["commit"]))


UNBOUND = {   # each leaves the named reviewer's block counted at HEAD (and the marker not in effect)
    "unrelated_decision": ("opus", _unrelated),
    "decision_on_another_node": ("opus", lambda r, d, l: _edit_yaml(
        l, lambda doc: doc["entries"][0].update(node="M9.9"))),
    "open_decision": ("opus", lambda r, d, l: _edit_yaml(l, lambda doc: doc["entries"][0].update(status="open"))),
    "missing_rca": ("opus", lambda r, d, l: (d / "RCA-2.md").unlink()),
    "rca_of_another_round": ("opus", lambda r, d, l: _edit_yaml(d / "DEFERRAL-2.yaml", lambda m: m.update(round=3))),
    "rca_other_findings": ("opus", lambda r, d, l: _write_rca(r, _record(2, [_item(
        git(r, "rev-parse", "HEAD"), input_class="CRLF in headers")]))),
    "marker_altered": ("opus", lambda r, d, l: _edit_yaml(
        d / "DEFERRAL-2.yaml", lambda m: m["deferred"][0].update(input_class="CRLF in headers"))),
    "replayed_to_another_reviewer": ("sonnet", lambda r, d, l: _rewrite(
        r, d, _item(git(r, "rev-parse", "HEAD"), reviewer="sonnet"))),
    "replayed_to_another_commit": ("opus", lambda r, d, l: _rewrite(
        r, d, _item(git(r, "rev-parse", "HEAD~1")))),
}


@pytest.mark.slow
@pytest.mark.parametrize("case", sorted(UNBOUND))
def test_a_marker_not_bound_to_its_decision_and_rca_resolves_nothing(tmp_path: Path, capsys, human,
                                                                     case: str) -> None:
    """Only the marker ``review defer`` wrote, for the RCA and decision it recorded, is in effect."""
    repo = make_review_repo(tmp_path, orchestration=ROSTER4 + BUDGET)
    _two_fail_round(repo, 1, correctness=False)   # opus: the same CRLF finding in both rounds
    _two_fail_round(repo, 2, correctness=False)
    _crlf_review(repo, "sonnet")   # sonnet blocks round 2 with the same finding text
    head = git(repo, "rev-parse", "HEAD")
    rca = _write_rca(repo, _record(2, [_item(head[:12])]))
    os.utime(rca, ns=(time.time_ns() + 10**10,) * 2)   # filed after every review
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 0
    gate = evaluate_gate(repo, NODE, head)
    assert [b.model for b in gate.blocks] == ["sonnet"]
    assert _status(repo, capsys)[1]["fix_round_budget"]["state"] == "spent_defer_applied_no_executor"
    assert governing_rca(repo, "M1.1", [b.review for b in gate.blocks]).name == "RCA-2.md"
    model, tamper = UNBOUND[case]
    tamper(repo, reviews_dir(repo, "M1.1"), repo / "roadmap" / "decisions.yaml")
    gate = evaluate_gate(repo, NODE, head)
    assert model in [b.model for b in gate.blocks]
    b = _status(repo, capsys)[1].get("fix_round_budget") or {}
    assert not str(b.get("state")).startswith("spent_defer_applied"), b
    assert governing_rca(repo, "M1.1", [b.review for b in gate.blocks]) is None


# Every public name each old module defined before the rename or fold, by its new home. A name
# that moved into a CLI entry point is not served (a package module never imports one): see
# test_old_path_does_not_serve_names_that_moved_into_the_cli.
@pytest.mark.parametrize(("old", "new", "names"), [
    ("review_defer", "review_defer_cli", "add_parser applicable_record cmd_review_defer"),
    ("review_deferral", "review_defer_rules", "CATEGORIES DEFERRAL_PREFIX Evidence MARKER_SCHEMA "
     "Marker answer_item apply_deferrals deferral_evidence deferral_in_effect load_markers "
     "marker_path normalise_input_class qualify_deferral rca_deferral round_of write_marker"),
    ("review_strong", "review_gate", "applicable_items human_closes_strong item_label "
     "strong_problem touch_zones unmet_strong zones_meet"),
    ("review_resumed_delta", "review_gate", "FRESH_SESSION RESUMED_KEY fresh_only_note "
     "fresh_session_problem resumed_delta_on"),
    ("review_eligible", "review_gate", "Identity reviews_to_judge writers"),
    ("review_ready_merge", "review_gate_ready", "add_ready_parser cmd_ready trial_merge_warning"),
    ("changelog_check", "review_gate_ready", "missing_entry_warning"),
    ("review_bookkeeping", "review_override", "CARRY_NOTE count_at_later_commit heads_problem "
     "only_planning_or_review_bookkeeping_since policy_line review_commit"),
    ("review_gate_agreement", "review_policy_pin", "GATE_FIX GATE_KEY gate_config_mismatch "
     "report_gate_mismatch"),
    ("review_policy_ref", "review_policy_pin", "WORKFLOW_REL committed_yaml integration_name "
     "policy_source review_required trusted_integration_ref"),
])
def test_renamed_module_old_path_warns_and_serves_the_same_names(monkeypatch, old, new, names):
    """A renamed or folded module's old import path serves its public names until its removal
    (the release after 0.3.1), and says so on import."""
    monkeypatch.delitem(sys.modules, f"specy_road.{old}", raising=False)
    with pytest.warns(DeprecationWarning, match="removed in the release after 0.3.1"):
        module = importlib.import_module(f"specy_road.{old}")
    target = importlib.import_module(f"specy_road.{new}")
    for name in names.split():
        assert getattr(module, name) is getattr(target, name)


def test_old_path_does_not_serve_names_that_moved_into_the_cli(monkeypatch) -> None:
    """``review_eligible``'s two CLI names live only in the ``review`` CLI entry point."""
    monkeypatch.delitem(sys.modules, "specy_road.review_eligible", raising=False)
    with pytest.warns(DeprecationWarning):
        module = importlib.import_module("specy_road.review_eligible")
    cli = importlib.import_module("specy_road.bundled_scripts.review_cli")
    for name in ("eligibility_lines", "reviewer_eligibility"):
        assert not hasattr(module, name) and callable(getattr(cli, name))
