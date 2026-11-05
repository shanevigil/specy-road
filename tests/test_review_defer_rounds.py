"""M12.1 fix-round regressions for ``review defer`` and the gate (reviewer gpt-6.1-sol, rounds 1 and 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_cli import _ready
from tests.test_review_defer import (BUDGET, ROSTER, ROSTER4, _block_round, _forge_closed_deferral, _item,
                                     _record, _review, _run, _status, _two_fail_round, _untouched,
                                     _write_rca, human)  # noqa: F401 — human is a fixture

from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate


def test_r1_a_partial_deferral_neither_applies_nor_hides_the_rest_of_the_block(tmp_path: Path, capsys,
                                                                               human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)   # A2 passes here
    _two_fail_round(repo, 2, correctness=True)
    head = git(repo, "rev-parse", "HEAD")
    rca = _write_rca(repo, _record(2, [_item(head)]))   # defers only the boundary A1 finding
    capsys.readouterr()
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "the block has a correctness finding and fails A2, which round 1 marked pass" in err
    assert "correctness finding 'A2 regressed' is not deferred" in err
    _untouched(repo)
    # a marker written by hand for the boundary finding alone does not hide the correctness finding either
    (repo / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump({"version": 1, "entries": [{
        "id": "D1", "node": "M1.1", "kind": "decision", "summary": "s", "why_now": "w",
        "options": [{"label": "a", "effect": "b"}], "recommendation": "a", "recommendation_reason": "r",
        "default_if_unanswered": "a", "asked": "2026-11-04", "status": "closed", "answer": "x",
        "closed": "2026-11-04"}]}))
    (reviews_dir(repo, "M1.1") / "DEFERRAL-2.yaml").write_text(yaml.safe_dump({
        "node_id": "M1.1", "rca": "RCA-2.md", "round": 2, "decision": "D1",
        "deferred": [{"reviewer": "opus", "commit": head, "category": "boundary", "acceptance_id": "A1"}]}))
    assert [b.model for b in evaluate_gate(repo, NODE, head).blocks] == ["opus"]


def test_r1_a_deferral_covering_every_finding_of_the_block_resolves_it(tmp_path: Path, human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    _two_fail_round(repo, 2, correctness=False)
    head = git(repo, "rev-parse", "HEAD")
    rca = _write_rca(repo, _record(2, [_item(head)]))
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 0
    assert evaluate_gate(repo, NODE, head).blocks == []


def test_r2_no_marker_means_the_ledger_is_never_read(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block_round(repo, 1)
    (repo / "roadmap" / "decisions.yaml").write_text("entries: [\n")
    head = git(repo, "rev-parse", "HEAD")
    assert [b.model for b in evaluate_gate(repo, NODE, head).blocks] == ["opus"]
    code, st = _status(repo, capsys)
    assert (code, st["state"]) == (1, "blocked") and "fix_round_budget" not in st


def test_r3_a_later_record_is_not_earlier_evidence(tmp_path: Path, capsys, human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _two_fail_round(repo, 1, correctness=False)
    first = git(repo, "rev-parse", "HEAD")
    rca1 = _write_rca(repo, _record(1, [_item(first)]))   # proposes CRLF first; left unapplied
    _block_round(repo, 2)
    _write_rca(repo, _record(2, None, action="escalate_human", disposition_class="crlf  LINE endings"))
    capsys.readouterr()
    assert _run("review", "defer", "M1.1", "--rca", str(rca1), "--repo-root", str(repo)) == 0, \
        capsys.readouterr().err
    marker = yaml.safe_load((reviews_dir(repo, "M1.1") / "DEFERRAL-1.yaml").read_text())
    assert marker["round"] == 1


@pytest.mark.parametrize("action,expected", [
    ("continue_with_class_fix", "specy-road prompt M1.1 --role executor --model composer"),
    ("change_or_reprompt_reviewer", "specy-road review-packet M1.1"),   # no packet yet; the prompt needs one
    ("escalate_human", "specy-road decisions add M1.1 --kind decision --summary"),
])
def test_r4_a_non_defer_rca_names_a_runnable_step_for_its_action(tmp_path: Path, capsys, monkeypatch,
                                                                   action: str, expected: str) -> None:
    import shlex
    import subprocess

    repo = make_review_repo(tmp_path, orchestration=ROSTER + "  - {id: composer, family: cursor, roles: [executor]}\n" + BUDGET)
    _block_round(repo, 1)
    _block_round(repo, 2)
    _ready(repo)   # the executor the step re-prompts: composer
    _write_rca(repo, _record(2, None, action=action))
    code, st = _status(repo, capsys)
    b = st["fix_round_budget"]
    assert (code, st["state"]) == (1, "fix_round_budget_spent")
    assert b["next"].startswith(expected) and "(" not in shlex.split(b["next"])[-1]
    assert f"RCA-2.md recommends {action}: defer the new class" in b["next_why"]
    argv = shlex.split(b["next"])   # parses as shell words, and the CLI accepts them
    assert argv[0] == "specy-road"
    if argv[1] == "decisions":
        r = subprocess.run(_cli(argv[1:], repo), capture_output=True, text=True, env=_this_checkout())
        assert r.returncode == 0, r.stderr
        entry = yaml.safe_load((repo / "roadmap" / "decisions.yaml").read_text())["entries"][0]
        assert (entry["status"], entry["recommendation"]) == ("open", "apply")


def test_r5_an_empty_second_title_fails_before_any_node_is_written(tmp_path: Path, capsys, human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER4 + BUDGET)
    _block_round(repo, 1)
    _block_round(repo, 2)
    _review(repo, "sonnet")
    head = git(repo, "rev-parse", "HEAD")
    rca = _write_rca(repo, _record(2, [_item(head), _item(head, reviewer="sonnet", follow_up_title="   ")]))
    capsys.readouterr()
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 1
    assert "follow_up_title is empty once whitespace is collapsed" in capsys.readouterr().err
    _untouched(repo)
    assert not list((repo / "planning").glob("M0*"))


def test_r5_a_failed_roadmap_write_is_rolled_back(tmp_path: Path, capsys, human, monkeypatch) -> None:
    from specy_road.bundled_scripts import review_defer

    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    _two_fail_round(repo, 2, correctness=False)   # opus: boundary 'CRLF input still warns', A1 fails
    rca = _write_rca(repo, _record(2, [_item(git(repo, "rev-parse", "HEAD"))]))
    before = {p: p.read_bytes() for p in (repo / "roadmap").rglob("*") if p.is_file()}

    def boom(*_a, **_k):
        raise ValueError("ledger write failed")
    monkeypatch.setattr(review_defer, "close_entry", boom)   # after the follow-up leaf and the open entry
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 1
    assert "could not apply RCA-2.md; nothing was written: ledger write failed" in capsys.readouterr().err
    assert {p: p.read_bytes() for p in (repo / "roadmap").rglob("*") if p.is_file()} == before
    assert not list(reviews_dir(repo, "M1.1").glob("DEFERRAL-*"))


@pytest.mark.parametrize("swap", ["crossed_categories", "acceptance_ids_swapped"])
def test_round2_r1_items_bind_to_original_findings(tmp_path: Path, capsys, human, swap: str) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)   # A2 passes here
    _two_fail_round(repo, 2, correctness=True)   # boundary 'CRLF input still warns' + correctness 'A2 regressed'
    head = git(repo, "rev-parse", "HEAD")
    if swap == "crossed_categories":   # each finding listed under the other's category
        items = [_item(head, category="correctness", acceptance_id="A1"),
                 _item(head, finding="round 2/opus: A2 regressed", category="boundary", acceptance_id="A2",
                       input_class="regression on A2")]
    else:   # categories right, but the correctness finding claims A1 and the boundary one A2
        items = [_item(head, acceptance_id="A2"),
                 _item(head, finding="round 2/opus: A2 regressed", category="correctness", acceptance_id="A1",
                       input_class="regression on A2")]
    rca = _write_rca(repo, _record(2, items))
    capsys.readouterr()
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 1
    assert "never deferred" in capsys.readouterr().err
    _untouched(repo)
    _forge_closed_deferral(repo, [{**x, "commit": head} for x in items])
    assert [b.model for b in evaluate_gate(repo, NODE, head).blocks] == ["opus"]


def test_round2_r2_a_marker_write_failure_rolls_back_everything(tmp_path: Path, capsys, human) -> None:
    import os

    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    _two_fail_round(repo, 2, correctness=False)
    rca = _write_rca(repo, _record(2, [_item(git(repo, "rev-parse", "HEAD"))]))
    d = reviews_dir(repo, "M1.1")
    before = {p: p.read_bytes() for p in (repo / "roadmap").rglob("*") if p.is_file()}
    sheets = sorted((repo / "planning").rglob("*"))
    d.chmod(0o555)   # readable, not writable: the marker write fails after the roadmap writes
    try:
        capsys.readouterr()
        assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 1
    finally:
        d.chmod(0o755)
    assert "could not apply RCA-2.md; nothing was written" in capsys.readouterr().err
    assert {p: p.read_bytes() for p in (repo / "roadmap").rglob("*") if p.is_file()} == before
    assert sorted((repo / "planning").rglob("*")) == sheets
    _untouched(repo)


def test_round2_r3_an_item_round_comes_from_its_blocking_commit(tmp_path: Path, capsys, human) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _two_fail_round(repo, 1, correctness=False)
    rca1 = _write_rca(repo, _record(1, None, action="escalate_human"))
    _two_fail_round(repo, 2, correctness=False)
    _write_rca(repo, _record(2, None, action="escalate_human", disposition_class="empty final message"))
    _two_fail_round(repo, 3, correctness=False)
    head = git(repo, "rev-parse", "HEAD")
    item = _item(head, input_class="Empty Final  Message")
    rca1.write_text("---\n" + yaml.safe_dump(_record(1, [item]), sort_keys=False) + "---\nreasoning\n")
    capsys.readouterr()
    assert _run("review", "defer", "M1.1", "--rca", str(rca1), "--repo-root", str(repo)) == 1
    assert "that commit is round 3, later than round 1 the record covers" in capsys.readouterr().err
    _write_rca(repo, _record(1, None, action="escalate_human"))   # RCA-1 back to naming no class
    rca3 = _write_rca(repo, _record(3, [item]))   # covers round 3, so RCA-2 is earlier evidence
    assert _run("review", "defer", "M1.1", "--rca", str(rca3), "--repo-root", str(repo)) == 1
    assert "input class 'Empty Final  Message' was already named in RCA-2.md" in capsys.readouterr().err
    _untouched(repo)


def test_round2_probe_the_gate_applies_the_correctness_rule_to_a_hand_written_marker(tmp_path: Path) -> None:
    """A correctness item on an id an earlier round passed never resolves a block, whoever wrote the marker."""
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)   # A2 passes here
    commit_file(repo, "src/c.py", "c\n", "c")
    head = git(repo, "rev-parse", "HEAD")
    notes = repo.parent / "notes.md"   # fails only A1; one boundary and one correctness finding
    notes.write_text(review_text(head, model="opus", verdict="block", a1="fail")
                     .replace("boundary: []", "boundary:\n  - CRLF input still warns")
                     .replace("correctness: []", "correctness:\n  - A2 regressed"))
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0
    boundary = _item(head)   # binds the boundary finding and names the failed A1
    _forge_closed_deferral(repo, [boundary, _item(head, finding="round 2/opus: A2 regressed", category="correctness",
                                                  acceptance_id="A2", input_class="a2")])
    assert [b.model for b in evaluate_gate(repo, NODE, head).blocks] == ["opus"]
    _forge_closed_deferral(repo, [boundary, _item(head, finding="round 2/opus: A2 regressed", category="correctness",
                                                  acceptance_id="A1", input_class="a2")])
    assert evaluate_gate(repo, NODE, head).blocks == []   # the same findings, the correctness one on A1, resolve


def _runs(repo: Path, command: str) -> int:
    """Run a status ``next`` command exactly as printed (plus ``--repo-root``)."""
    import shlex
    import subprocess

    argv = shlex.split(command)
    assert argv[0] == "specy-road", command
    return subprocess.run(_cli(argv[1:], repo), capture_output=True, text=True, cwd=repo,
                          env=_this_checkout()).returncode


def _cli(args: list[str], repo: Path) -> list[str]:
    """``specy-road <args>`` from this checkout's package, not whichever ``specy-road`` is first on PATH."""
    import sys

    return [sys.executable, "-c", "import sys; from specy_road.cli import main; main(sys.argv[1:])",
            *args, "--repo-root", str(repo)]


def _this_checkout() -> dict[str, str]:
    import os

    return {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}


def test_round3_every_next_step_runs_or_is_absent(tmp_path: Path, capsys, human) -> None:
    """The next-step audit: each budget state names a command that succeeds, or none at all."""
    executor = "  - {id: composer, family: cursor, roles: [executor]}\n"
    repo = make_review_repo(tmp_path, orchestration=ROSTER4 + executor + BUDGET)
    _block_round(repo, 1)
    _two_fail_round(repo, 2, correctness=False)
    _ready(repo)   # composer is the executor; sol and sonnet have not reviewed
    head = git(repo, "rev-parse", "HEAD")
    st = _status(repo, capsys)[1]   # 1. no RCA: a forced RCA by a rostered non-party
    assert st["state"] == "fix_round_budget_spent" and "--role rca --force" in st["fix_round_budget"]["next"]
    assert _runs(repo, st["fix_round_budget"]["next"]) == 0
    for action, role in (("continue_with_class_fix", "executor"), ("change_or_reprompt_reviewer", "reviewer"),
                         ("escalate_human", None)):   # 2. a covering non-defer RCA
        _write_rca(repo, _record(2, None, action=action))
        b = _status(repo, capsys)[1]["fix_round_budget"]
        assert (role is None) == b["next"].startswith("specy-road decisions add"), b["next"]
        if role == "reviewer":   # no packet yet: build it, and the reviewer prompt is next
            assert b["next"] == "specy-road review-packet M1.1" and _runs(repo, b["next"]) == 0
            b = _status(repo, capsys)[1]["fix_round_budget"]
            assert b["next"] == "specy-road prompt M1.1 --role reviewer --model opus"
        assert _runs(repo, b["next"]) == 0, b["next"]
    bad = _record(2, [_item(head, category="regression")])   # 3a. a defer RCA review defer would refuse
    _write_rca(repo, bad)
    b = _status(repo, capsys)[1]["fix_round_budget"]
    assert b["next"].startswith("specy-road decisions add") and "would refuse it" in b["next_why"]
    rca = _write_rca(repo, _record(2, [_item(head)]))   # 3b. an applicable defer RCA
    b = _status(repo, capsys)[1]["fix_round_budget"]
    assert b["next"] == f"specy-road review defer M1.1 --rca {rca}"
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 0
    code, st = _status(repo, capsys)   # 5. applied, no counted block left: the gate's own state
    assert st["state"] != "fix_round_budget_spent" and st["fix_round_budget"]["next"] is None
    assert evaluate_gate(repo, NODE, head).blocks == []


def test_round3_a_ready_agent_without_the_executor_role_is_not_named(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)   # composer is not rostered
    _block_round(repo, 1)
    _block_round(repo, 2)
    _ready(repo)
    _write_rca(repo, _record(2, None, action="continue_with_class_fix"))
    b = _status(repo, capsys)[1]["fix_round_budget"]
    assert b["next"].startswith("specy-road decisions add M1.1") and _runs(repo, b["next"]) == 0


def test_round3_no_independent_analyst_names_a_human_decision(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER.replace("  - {id: sol, family: openai, roles: [reviewer]}\n", "")
                            + BUDGET)   # opus reviews; no other non-human reviewer is rostered
    _block_round(repo, 1)
    _block_round(repo, 2)
    b = _status(repo, capsys)[1]["fix_round_budget"]
    assert "MODEL" not in b["next"] and "no available rostered reviewer that neither implemented" in b["next_why"]
    assert b["next"].startswith("specy-road decisions add M1.1") and _runs(repo, b["next"]) == 0
