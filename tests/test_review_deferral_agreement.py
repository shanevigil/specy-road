"""M12.1 fix round 4: ``review defer`` and the gate apply one qualification rule; markers are checked at the boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import NODE, git, make_review_repo
from tests.test_review_defer import (BUDGET, ROSTER, _block_round, _item, _record, _run, _two_fail_round,
                                     _write_rca, human)  # noqa: F401 — human is a fixture

from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate

LEDGER = {"version": 1, "entries": [{
    "id": "D9", "node": "M1.1", "kind": "decision", "summary": "s", "why_now": "w",
    "options": [{"label": "a", "effect": "b"}], "recommendation": "a", "recommendation_reason": "r",
    "default_if_unanswered": "a", "asked": "2026-11-04", "status": "closed", "answer": "x", "closed": "2026-11-04"}]}


def _case(repo: Path, case: str) -> tuple[int, list[dict]]:
    """Build one agreement case; ``(round the source record covers, its items)``."""
    _block_round(repo, 1)   # opus blocks A1 with no findings; A2 passes
    if case == "later_round":
        _write_rca(repo, _record(1, None, action="escalate_human"))
        _two_fail_round(repo, 2, correctness=False)
        return 1, [_item(git(repo, "rev-parse", "HEAD"))]
    if case == "earlier_class":   # R1: RCA-1 already named the class
        _write_rca(repo, _record(1, None, action="escalate_human", disposition_class="crlf  LINE endings"))
    _two_fail_round(repo, 2, correctness=case in ("protected_block", "correctness_item"))
    head = git(repo, "rev-parse", "HEAD")
    items = {
        "eligible": [_item(head)],
        "earlier_class": [_item(head)],
        "crossed_category": [_item(head, category="regression")],
        "unbound_text": [_item(head, finding="round 2/opus: something else")],
        "uncovered_failed_id": [_item(head, acceptance_id="A2")],
        "absent_reviewer": [_item(head, reviewer="sol")],
        "duplicate": [_item(head), _item(head[:9])],
        "protected_block": [_item(head), _item(head, finding="round 2/opus: A2 regressed", category="correctness",
                                                acceptance_id="A1", input_class="a2")],
        "correctness_item": [_item(head, acceptance_id="A2"),
                             _item(head, finding="round 2/opus: A2 regressed", category="correctness",
                                   acceptance_id="A2", input_class="a2")],
    }[case]
    return 2, items


CASES = ["eligible", "earlier_class", "later_round", "crossed_category", "unbound_text", "uncovered_failed_id",
         "absent_reviewer", "duplicate", "protected_block", "correctness_item"]


@pytest.mark.parametrize("case", CASES)
def test_review_defer_and_the_gate_agree(tmp_path: Path, capsys, human, case: str) -> None:
    """The agreement table: each item set is accepted by both, or refused by both."""
    applied = make_review_repo(tmp_path / "defer", orchestration=ROSTER + BUDGET)
    covers, items = _case(applied, case)
    rca = _write_rca(applied, _record(covers, items))
    defer_ok = _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(applied)) == 0

    forged = make_review_repo(tmp_path / "gate", orchestration=ROSTER + BUDGET)
    covers, items = _case(forged, case)
    _write_rca(forged, _record(covers, items))
    (forged / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump(LEDGER))
    commits = {x["commit"]: git(forged, "rev-parse", x["commit"]) for x in items if x["reviewer"] == "opus"}
    (reviews_dir(forged, "M1.1") / f"DEFERRAL-{covers}.yaml").write_text(yaml.safe_dump({
        "node_id": "M1.1", "rca": f"RCA-{covers}.md", "round": covers, "decision": "D9",
        "deferred": [{k: x[k] for k in ("reviewer", "finding", "category", "acceptance_id", "input_class")}
                     | {"commit": commits.get(x["commit"], x["commit"])} for x in items]}))
    head = git(forged, "rev-parse", "HEAD")
    gate_ok = "opus" not in [b.model for b in evaluate_gate(forged, NODE, head).blocks]
    assert (defer_ok, gate_ok) == ((case == "eligible"),) * 2, capsys.readouterr().err


MALFORMED = {
    "string_items": "node_id: M1.1\nrca: RCA-2.md\nround: 2\ndecision: D9\ndeferred: [incomplete write]\n",
    "not_a_mapping": "- a\n- b\n",
    "missing_keys": "node_id: M1.1\n",
    "wrong_types": "node_id: M1.1\nrca: RCA-2.md\nround: two\ndecision: D9\ndeferred: {a: b}\n",
    "bad_yaml": "deferred: [\n",
    "bad_item_fields": ("node_id: M1.1\nrca: RCA-2.md\nround: 2\ndecision: D9\n"
                        "deferred: [{reviewer: opus, commit: zz, finding: f, category: style, acceptance_id: B1, "
                        "input_class: c}]\n"),
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_a_malformed_marker_resolves_nothing_and_status_stays_usable(tmp_path: Path, capsys, name: str) -> None:
    """R4: with max_fix_rounds unset, a bad marker never raises; status names it on one line."""
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block_round(repo, 1)
    (repo / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump(LEDGER))
    (reviews_dir(repo, "M1.1") / "DEFERRAL-2.yaml").write_text(MALFORMED[name])
    head = git(repo, "rev-parse", "HEAD")
    assert [b.model for b in evaluate_gate(repo, NODE, head).blocks] == ["opus"]
    capsys.readouterr()
    assert _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo)) == 1
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert st["state"] == "blocked" and "fix_round_budget" not in st
    lines = [p for p in st["problems"] if "DEFERRAL-2.yaml" in p]
    assert len(lines) == 1 and "resolves nothing" in lines[0]
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    assert "DEFERRAL-2.yaml" in capsys.readouterr().out
