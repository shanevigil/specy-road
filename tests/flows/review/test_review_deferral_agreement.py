"""M12.1 fix round 4: ``review defer`` and the gate apply one qualification rule; markers are checked at the boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.support.review import NODE, make_review_repo, git
from tests.support.extracted.review_defer import (
    BUDGET,
    item,
    record,
    two_fail_round,
    write_rca,
    bound_ledger,
    human,
)
from tests.support.extracted.review_rca import ROSTER, block_round
from tests.support.same.run_651387813ee4 import run

from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate

#: A closed decision as ``review defer`` records one (for a malformed marker, it changes nothing).
LEDGER = bound_ledger("RCA-2.md", [{k: v for k, v in item("0" * 40).items()}])


def _case(repo: Path, case: str) -> tuple[int, list[dict]]:
    """Build one agreement case; ``(round the source record covers, its items)``."""
    block_round(repo, 1)   # opus blocks A1 with no findings; A2 passes
    if case == "later_round":
        write_rca(repo, record(1, None, action="escalate_human"))
        two_fail_round(repo, 2, correctness=False)
        return 1, [item(git(repo, "rev-parse", "HEAD"))]
    if case == "earlier_class":   # R1: RCA-1 already named the class
        write_rca(repo, record(1, None, action="escalate_human", disposition_class="crlf  LINE endings"))
    two_fail_round(repo, 2, correctness=case in ("protected_block", "correctness_item"))
    head = git(repo, "rev-parse", "HEAD")
    items = {
        "eligible": [item(head)],
        "earlier_class": [item(head)],
        "crossed_category": [item(head, category="regression")],
        "unbound_text": [item(head, finding="round 2/opus: something else")],
        "uncovered_failed_id": [item(head, acceptance_id="A2")],
        "absent_reviewer": [item(head, reviewer="sol")],
        "duplicate": [item(head), item(head[:9])],
        "protected_block": [item(head), item(head, finding="round 2/opus: A2 regressed", category="correctness",
                                                acceptance_id="A1", input_class="a2")],
        "correctness_item": [item(head, acceptance_id="A2"),
                             item(head, finding="round 2/opus: A2 regressed", category="correctness",
                                   acceptance_id="A2", input_class="a2")],
    }[case]
    return 2, items


CASES = ["eligible", "earlier_class", "later_round", "crossed_category", "unbound_text", "uncovered_failed_id",
         "absent_reviewer", "duplicate", "protected_block", "correctness_item"]


@pytest.mark.slow
@pytest.mark.parametrize("case", CASES)
def test_review_defer_and_the_gate_agree(tmp_path: Path, capsys, human, case: str) -> None:
    """The agreement table: each item set is accepted by both, or refused by both."""
    applied = make_review_repo(tmp_path / "defer", orchestration=ROSTER + BUDGET)
    covers, items = _case(applied, case)
    rca = write_rca(applied, record(covers, items))
    defer_ok = run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(applied)) == 0

    forged = make_review_repo(tmp_path / "gate", orchestration=ROSTER + BUDGET)
    covers, items = _case(forged, case)
    write_rca(forged, record(covers, items))
    commits = {x["commit"]: git(forged, "rev-parse", x["commit"]) for x in items if x["reviewer"] == "opus"}
    deferred = [{k: x[k] for k in ("reviewer", "finding", "category", "acceptance_id", "input_class")}
                | {"commit": commits.get(x["commit"], x["commit"])} for x in items]
    (forged / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump(bound_ledger(f"RCA-{covers}.md", deferred)))
    (reviews_dir(forged, "M1.1") / f"DEFERRAL-{covers}.yaml").write_text(yaml.safe_dump({
        "node_id": "M1.1", "rca": f"RCA-{covers}.md", "round": covers, "decision": "D9", "deferred": deferred}))
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


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_a_malformed_marker_resolves_nothing_and_status_stays_usable(tmp_path: Path, capsys, name: str) -> None:
    """R4: with max_fix_rounds unset, a bad marker never raises; status names it on one line."""
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    block_round(repo, 1)
    (repo / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump(LEDGER))
    (reviews_dir(repo, "M1.1") / "DEFERRAL-2.yaml").write_text(MALFORMED[name])
    head = git(repo, "rev-parse", "HEAD")
    assert [b.model for b in evaluate_gate(repo, NODE, head).blocks] == ["opus"]
    capsys.readouterr()
    assert run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo)) == 1
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert st["state"] == "blocked" and "fix_round_budget" not in st
    lines = [p for p in st["problems"] if "DEFERRAL-2.yaml" in p]
    assert len(lines) == 1 and "resolves nothing" in lines[0]
    assert run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    assert "DEFERRAL-2.yaml" in capsys.readouterr().out
