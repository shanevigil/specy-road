"""M12.1 fix round 4: every row of the fix-round next-step state machine, through ``handoff status``.

Each test reaches one row, checks ``--json`` and the text line, and runs the printed command, which must not
exit 1. ``test_every_state_row_is_tested`` keeps this file in step with :data:`review_next_step.STATES`.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo, review_text
from tests.test_review_cli import _ready
from tests.test_review_defer import (BUDGET, ROSTER, _block_round, _item, _record, _review, _run, _two_fail_round,
                                     _write_rca, human)  # noqa: F401 — human is a fixture
from tests.test_review_defer_rounds import _runs

from specy_road.review_next_step import STATES

SONNET = "  - {id: sonnet, family: anthropic, roles: [reviewer]}\n"
EXECUTOR = "  - {id: composer, family: cursor, roles: [executor]}\n"


def _row(repo: Path, capsys, state: str, step: str) -> dict:
    """``handoff status`` (JSON and text) reports ``state``; its printed command runs."""
    capsys.readouterr()
    code = _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    b = st.get("fix_round_budget") or {"state": "budget_unset", "step": "none", "next": None, "spent": False}
    assert (b["state"], b["step"]) == (state, step), b
    assert code == 1 or st["state"] == "approved"
    assert (st["state"] == "fix_round_budget_spent") == b["spent"]
    _run("handoff", "status", "M1.1", "--repo-root", str(repo))
    text = capsys.readouterr().out
    if b["spent"]:
        assert f"next: `{b['next']}`" in text and b["next_why"] in text
    if step == "none":
        assert b["next"] is None
    elif shlex.split(b["next"])[1:3] == ["review", "defer"]:   # human-only: a terminal, as a person runs it
        assert _run(*shlex.split(b["next"])[1:], "--repo-root", str(repo)) == 0
    else:
        assert _runs(repo, b["next"]) == 0, b["next"]
    if step == "blocked":
        assert b["next"].startswith("specy-road decisions add M1.1") and b["next_why"].startswith("blocked: ")
    return b


def _spent(tmp_path: Path, roster: str = ROSTER) -> tuple[Path, str]:
    repo = make_review_repo(tmp_path, orchestration=roster + BUDGET)
    _block_round(repo, 1)
    _two_fail_round(repo, 2, correctness=False)
    return repo, git(repo, "rev-parse", "HEAD")


def test_budget_unset(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block_round(repo, 1)
    _block_round(repo, 2)
    _row(repo, capsys, "budget_unset", "none")


def test_within_budget(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER + BUDGET)
    _block_round(repo, 1)
    _row(repo, capsys, "within_budget", "none")


def test_spent_no_blocks(tmp_path: Path, capsys) -> None:
    repo, _ = _spent(tmp_path)
    head = commit_file(repo, "src/fix.py", "fix\n", "fix")
    notes = repo.parent / "approve.md"
    notes.write_text(review_text(head, model="opus"))
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes), "--repo-root", str(repo)) == 0
    _row(repo, capsys, "spent_no_blocks", "none")


def test_spent_no_rca(tmp_path: Path, capsys) -> None:
    b = _row(_spent(tmp_path)[0], capsys, "spent_no_rca", "command")
    assert b["next"].endswith("--model sol")


def test_spent_no_rca_no_analyst(tmp_path: Path, capsys) -> None:
    """R2: sol is the only independent reviewer and is unavailable, so no RCA prompt is named."""
    roster = ROSTER.replace("{id: sol, family: openai, roles: [reviewer]}",
                            "{id: sol, family: openai, roles: [reviewer], available: false}")
    assert "available: false" in roster
    b = _row(_spent(tmp_path, roster)[0], capsys, "spent_no_rca_no_analyst", "blocked")
    assert "sol" not in b["next"].split("--why")[0]


def test_spent_defer_unapplied_then_applied_rows(tmp_path: Path, capsys, human) -> None:
    """R3: after one reviewer's deferral, the budget stays spent while another block counts."""
    repo, head = _spent(tmp_path, ROSTER + SONNET)
    _review(repo, "sonnet")
    rca = _write_rca(repo, _record(2, [_item(head)]))
    b = _row(repo, capsys, "spent_defer_unapplied", "command")   # runs `review defer` as a person would
    assert b["next"] == f"specy-road review defer M1.1 --rca {rca}"
    b = _row(repo, capsys, "spent_defer_applied_no_executor", "blocked")
    assert "review defer" not in b["next"] and b["spent"]


def test_spent_defer_applied(tmp_path: Path, capsys, human) -> None:
    repo, head = _spent(tmp_path, ROSTER + SONNET + EXECUTOR)
    _review(repo, "sonnet")
    _ready(repo)
    rca = _write_rca(repo, _record(2, [_item(head)]))
    assert _run("review", "defer", "M1.1", "--rca", str(rca), "--repo-root", str(repo)) == 0
    b = _row(repo, capsys, "spent_defer_applied", "command")
    assert b["next"] == "specy-road prompt M1.1 --role executor --model composer"


def test_spent_defer_refused(tmp_path: Path, capsys) -> None:
    repo, head = _spent(tmp_path)
    _write_rca(repo, _record(2, [_item(head, category="regression")]))
    b = _row(repo, capsys, "spent_defer_refused", "blocked")
    assert "would refuse it" in b["next_why"]


def test_spent_rca_executor(tmp_path: Path, capsys) -> None:
    repo, _ = _spent(tmp_path, ROSTER + EXECUTOR)
    _ready(repo)
    _write_rca(repo, _record(2, None, action="continue_with_class_fix"))
    _row(repo, capsys, "spent_rca_executor", "command")


def test_spent_rca_packet_then_reviewer(tmp_path: Path, capsys) -> None:
    repo, _ = _spent(tmp_path)
    _write_rca(repo, _record(2, None, action="change_or_reprompt_reviewer"))
    assert _row(repo, capsys, "spent_rca_packet", "command")["next"] == "specy-road review-packet M1.1"
    assert _row(repo, capsys, "spent_rca_reviewer", "command")["next"].endswith("--role reviewer --model opus")


@pytest.mark.parametrize("action", ["escalate_human", "continue_with_class_fix"])   # no executor for the latter
def test_spent_rca_human(tmp_path: Path, capsys, action: str) -> None:
    repo, _ = _spent(tmp_path)
    _write_rca(repo, _record(2, None, action=action))
    _row(repo, capsys, "spent_rca_human", "blocked")


def test_every_state_row_is_tested() -> None:
    """Every row of the table is reached by a test above (a new row needs one)."""
    names = [s.name for s in STATES]
    assert len(names) == len(set(names))
    tested = {n for n in names if f"\"{n}\"" in Path(__file__).read_text()}
    assert tested == set(names), set(names) - tested
