"""M14.10: a converging review loop defers same_family/review_rounds escalation; status shows the trend."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo, review_text
from tests.test_review_rca import ROSTER, _run, _status

from specy_road.orchestration_config import DEFAULT_POLICY
from specy_road.review_rca import Round, escalation
from specy_road.review_trend import converging

POLICY = {**DEFAULT_POLICY}   # escalate_same_acceptance_blocks 3, escalate_review_rounds 5


def _rec(n: int, fails: tuple[str, ...] = ()) -> SimpleNamespace:
    """A blocking record with ``n`` findings spread over the four categories."""
    cats = ["correctness", "regression", "boundary", "test_integrity"]
    findings = {c: [f"{c} {i}" for i in range(n) if i % 4 == k] for k, c in enumerate(cats)}
    acc = {"A1": "pass", "A2": "pass", **{a: "fail" for a in fails}}
    return SimpleNamespace(data={"model": "sol", "verdict": "block", "findings": findings, "acceptance": acc})


def _rounds(counts: list[int], fails_last: tuple[str, ...] = ()) -> list[Round]:
    return [Round(f"c{i}", [_rec(n, fails_last if i == len(counts) - 1 else ())]) for i, n in enumerate(counts)]


def test_falling_series_with_passing_acceptance_is_not_escalated() -> None:
    rounds = _rounds([13, 2, 2, 1, 0])
    for k in range(1, 6):
        assert escalation(rounds[:k], POLICY) is None, k
    assert converging(rounds, 3)


@pytest.mark.parametrize("counts", [[3, 3, 3], [2, 4, 1], [5, 5, 4, 6, 3]])
def test_flat_or_rising_series_still_escalates(counts: list[int]) -> None:
    esc = escalation(_rounds(counts), POLICY)
    assert esc is not None and esc.rule in ("same_family", "review_rounds")
    assert not converging(_rounds(counts), 3)


def test_a_failing_acceptance_in_the_latest_round_escalates() -> None:
    rounds = _rounds([5, 3, 1], fails_last=("A2",))
    assert not converging(rounds, 3)
    assert escalation(rounds, POLICY).rule == "same_family"


def test_policy_true_restores_escalation_while_converging() -> None:
    rounds = _rounds([13, 2, 2, 1, 0])
    on = {**POLICY, "escalate_when_converging": True}
    assert escalation(rounds[:3], on).rule == "same_family"
    assert escalation(rounds, on).rule == "same_family"
    assert escalation(rounds, {**on, "escalate_same_acceptance_blocks": 9}).rule == "review_rounds"


def test_same_acceptance_still_applies_while_counts_fall() -> None:
    rounds = [Round(f"c{i}", [_rec(n, ("A1",))]) for i, n in enumerate([5, 3, 1])]
    assert escalation(rounds, POLICY).rule == "same_acceptance"


def test_default_and_schema_carry_the_policy_key() -> None:
    assert DEFAULT_POLICY["escalate_when_converging"] is False
    schema = Path(__file__).resolve().parent.parent / "specy_road/templates/project/schemas/orchestration.schema.json"
    prop = json.loads(schema.read_text())["$defs"]["policy"]["properties"]["escalate_when_converging"]
    assert prop["type"] == "boolean" and "Default false" in prop["description"]


def _record(repo: Path, n: int, findings: int, a1: str) -> None:
    commit_file(repo, f"src/t{n}.py", f"t = {n}\n", f"fix {n}")
    notes = repo.parent / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict="block", a1=a1,
                                 findings={"correctness": [f"f{i}" for i in range(findings)], "regression": [],
                                           "boundary": [], "test_integrity": []}))
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0


def _replay(tmp_path: Path, policy: str = "") -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + policy)
    for n, (count, a1) in enumerate([(13, "fail"), (2, "pass"), (2, "pass"), (1, "pass"), (0, "pass")], 1):
        _record(repo, n, count, a1)
    return repo


def test_status_prints_the_trend_and_defers_a_converging_loop(tmp_path: Path, capsys) -> None:
    repo = _replay(tmp_path)
    code, st = _status(repo, capsys)
    assert (st["state"], st["escalation"]) == ("blocked", None)
    tr = st["findings_trend"]
    assert [r["findings"] for r in tr["rounds"]] == [13, 2, 2, 1, 0]
    assert [r["failing_acceptance"] for r in tr["rounds"]] == [["A1"], [], [], [], []]
    assert tr["converging"] and tr["escalation_deferred"]
    _run("handoff", "status", "M1.1", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert "findings by round: 13, 2, 2, 1, 0; acceptance all pass since round 2" in out
    assert "converging; escalation deferred" in out


def test_status_with_policy_true_escalates_the_same_replay(tmp_path: Path, capsys) -> None:
    repo = _replay(tmp_path, "policy: {escalate_when_converging: true}\n")
    code, st = _status(repo, capsys)
    assert (code, st["state"], st["escalation"]["rule"]) == (1, "escalated", "same_family")
    assert not st["findings_trend"]["escalation_deferred"]
    _run("handoff", "status", "M1.1", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert "findings by round: 13, 2, 2, 1, 0" in out and "escalation deferred" not in out
