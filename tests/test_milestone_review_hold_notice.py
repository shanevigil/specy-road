"""A milestone held by ``policy.milestone_full_review`` says so in validate, why-blocked and list-nodes (M13.4).

The only symptom of a hold was ``export --check`` / ``digest --check`` drift:
validate was silent and ``list-nodes`` gave no reason.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from specy_road.bundled_scripts import roadmap_query_cli as rq
from specy_road.bundled_scripts.roadmap_crud_ops import cmd_list
from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.finish_ancestor_rollup import milestone_review_hold_notice
from tests.test_milestone_full_review import POLICY_OFF, set_node_status, make_milestone_repo

WAYS_OUT = [
    "  1. Review it: specy-road review-packet M2; each reviewer: specy-road review record M2 --model <id> "
    "--verdict approve|block --file <notes.md>; then specy-road mark-implementation-reviewed M2",
    "  2. Record it Complete: specy-road edit-node M2 --set status=Complete",
    "  3. Turn the hold off: set policy.milestone_full_review: false in roadmap/orchestration.yaml",
]
HEAD = ("milestone review: notice — M2 is held at In Progress: every leaf is Complete but "
        "its full review is not approved at refs/heads/dev (")


def _notice_lines(out: str) -> list[str]:
    lines = out.splitlines()
    i = next(i for i, ln in enumerate(lines) if ln.startswith("milestone review: notice — M2"))
    return lines[i:i + 4]


def _list(root: Path, capsys, as_json: bool = False) -> str:
    cmd_list(argparse.Namespace(repo_root=str(root), status=None, as_json=as_json))
    return capsys.readouterr().out


def _why(root: Path, *extra: str) -> None:
    with pytest.raises(SystemExit):
        rq.main(["why-blocked", "M2", *extra, "--repo-root", str(root)])


def test_validate_prints_the_hold_reason_and_three_ways_out(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path)   # both leaves Complete on dev, no approvals
    capsys.readouterr()
    validate_at(root)
    out = capsys.readouterr().out
    assert out.count("milestone review: notice") == 1
    head, *ways = _notice_lines(out)
    assert head.startswith(HEAD) and head.endswith("(policy.milestone_full_review). Ways out:")
    assert ways == WAYS_OUT


def test_why_blocked_prints_the_same_notice(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path)
    capsys.readouterr()
    _why(root)
    head, *ways = _notice_lines(capsys.readouterr().out)
    assert head.startswith(HEAD) and ways == WAYS_OUT
    _why(root, "--json")
    assert json.loads(capsys.readouterr().out)["review_hold"].startswith(
        "its full review is not approved at refs/heads/dev")


def test_list_nodes_marks_the_held_rollup_and_json_carries_the_reason(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path)
    capsys.readouterr()
    rows = {ln.split()[0]: ln for ln in _list(root, capsys).splitlines()[1:]}
    assert "In Progress (review hold)" in rows["M2"]
    assert "review hold" not in rows["M2.1"]
    data = {r["id"]: r for r in json.loads(_list(root, capsys, as_json=True))}
    assert data["M2"]["review_hold"].startswith("its full review is not approved at refs/heads/dev")
    assert "review_hold" not in data["M2.1"]


def test_no_notice_when_the_policy_is_off_or_the_milestone_is_recorded_complete(tmp_path: Path, capsys) -> None:
    off = make_milestone_repo(tmp_path / "off", orchestration=POLICY_OFF)
    capsys.readouterr()
    validate_at(off)
    assert "milestone review: notice" not in capsys.readouterr().out
    assert "review hold" not in _list(off, capsys)
    closed = make_milestone_repo(tmp_path / "closed")
    set_node_status(closed, "M2", "Complete")   # way out 2
    capsys.readouterr()
    validate_at(closed)
    assert "milestone review: notice" not in capsys.readouterr().out
    _why(closed, "--json")
    assert json.loads(capsys.readouterr().out)["review_hold"] is None


def test_an_unresolvable_hold_is_one_line() -> None:
    text = milestone_review_hold_notice("M2", "its full review cannot be evaluated (no integration branch)")
    assert text == ("milestone review: notice — M2: its full review cannot be evaluated (no integration branch) "
                    "(policy.milestone_full_review); its rollup follows its leaves")
