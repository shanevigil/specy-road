"""Review-loop escalation: `handoff status`/`review list` detect it, `prompt --role rca` analyses it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts import review_cli, role_prompt
from specy_road.review_files import PACKET_NAME, reviews_dir

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
"""


def _run(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _block_round(repo: Path, n: int, a1: str = "fail") -> None:
    """One more commit, blocked by opus."""
    commit_file(repo, f"src/r{n}.py", f"r = {n}\n", f"fix {n}")
    notes = repo.parent / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict="block", a1=a1)
                     .replace("notes\n", f"round {n}: the heading case still warns\n"))
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0


def _status(repo: Path, capsys) -> tuple[int, dict]:
    capsys.readouterr()
    code = _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    return code, json.loads(capsys.readouterr().out)["nodes"][0]


def test_three_rounds_blocking_on_one_id_escalate_status_and_list(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block_round(repo, 1)
    _block_round(repo, 2)
    code, st = _status(repo, capsys)
    assert (code, st["state"], st["escalation"]) == (1, "blocked", None)
    _block_round(repo, 3)
    code, st = _status(repo, capsys)
    assert (code, st["state"]) == (1, "escalated")
    assert st["escalation"]["rule"] == "same_acceptance" and st["escalation"]["acceptance_ids"] == ["A1"]
    assert st["escalation"]["round"] == 3
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    out = capsys.readouterr().out
    assert "M1.1: escalated" in out and "the last 3 review rounds all block on A1" in out
    assert "specy-road prompt M1.1 --role rca" in out
    assert _run("review", "list", "M1.1", "--repo-root", str(repo)) == 0
    assert "escalated: the last 3 review rounds all block on A1" in capsys.readouterr().out


def test_total_rounds_threshold_comes_from_policy(tmp_path: Path, capsys) -> None:
    policy = "policy: {escalate_same_acceptance_blocks: 3, escalate_review_rounds: 2}\n"
    repo = make_review_repo(tmp_path, orchestration=ROSTER + policy)
    _block_round(repo, 1, a1="pass")
    assert _status(repo, capsys)[1]["state"] == "blocked"
    _block_round(repo, 2, a1="pass")
    st = _status(repo, capsys)[1]
    assert st["state"] == "escalated" and st["escalation"]["rule"] == "review_rounds"
    assert "2 review rounds without converging" in st["escalation"]["describe"]


def _escalated_repo(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    for n in (1, 2, 3):
        _block_round(repo, n)
    return repo


def test_rca_prompt_carries_history_diffs_and_protocol(tmp_path: Path) -> None:
    repo = _escalated_repo(tmp_path)
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="rca", model="sol")
    assert err is None
    assert "# Root-cause analysis prompt: `M1.1` for `sol`" in text
    assert "does not report `escalated`" in text
    for cls in ("specification", "implementation", "test", "reviewer", "environment", "hard_problem"):
        assert f"`{cls}`" in text
    assert "bounded rewrite of the criterion" in text and "cheapest corrective action" in text
    assert f"`{reviews_dir(repo, 'M1.1') / 'RCA-3.md'}`" in text
    assert "trigger: {rule: same_acceptance, acceptance_ids: [A1], round: 3}" in text
    assert "- **A1:** a.py exists" in text   # the brief, with acceptance
    assert "### Round 1:" in text and "### Round 3:" in text
    assert "#### opus (anthropic): block, fails A1" in text and "> round 2: the heading case" in text
    assert "+r = 3" in text   # the diff round 3 answered


def test_rca_prompt_refuses_when_not_escalated_and_for_a_party(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block_round(repo, 1)
    err = role_prompt.build_prompt(repo, "M1.1", role="rca", model="sol")[2]
    assert "not escalated; no root-cause analysis is due" in err
    for n in (2, 3):
        _block_round(repo, n)
    err = role_prompt.build_prompt(repo, "M1.1", role="rca", model="opus")[2]
    assert "'opus' implemented or reviewed M1.1" in err


def _rca(repo: Path, *, primary: str = "specification", round_: int = 3, rewrite: bool = True) -> Path:
    data = {
        "node_id": "M1.1", "model": "sol", "date": "2026-10-29",
        "trigger": {"rule": "same_acceptance", "acceptance_ids": ["A1"], "round": round_},
        "classification": {"primary": primary, "confidence": 0.8},
        "evidence": [{"kind": "finding", "ref": "round 2/opus", "supports": "primary",
                      "note": "each round names a new input class"}],
        "recommended_action": {"type": "amend_criterion", "instructions": "bound A1",
                               "requires_human_approval": True},
    }
    if rewrite:
        data["criterion_rewrite"] = {
            "acceptance_id": "A1", "original_text": "a.py exists", "proposed_text": "src/a.py exists",
            "finding_disposition": [{"finding": "round 2/opus", "label": "out_of_scope_now"}]}
    path = reviews_dir(repo, "M1.1") / f"RCA-{round_}.md"
    path.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nreasoning\n")
    return path


def test_rca_record_validates_and_resolves_the_escalation(tmp_path: Path, capsys) -> None:
    repo = _escalated_repo(tmp_path)
    bad = _rca(repo, rewrite=False)
    st = _status(repo, capsys)[1]
    assert st["state"] == "escalated"
    assert any("RCA-3.md: invalid" in p and "criterion_rewrite" in p for p in st["problems"])
    bad.unlink()
    _rca(repo, round_=4)
    st = _status(repo, capsys)[1]
    assert st["state"] == "escalated" and any("the history has 3 round(s)" in p for p in st["problems"])
    (reviews_dir(repo, "M1.1") / "RCA-4.md").unlink()
    _rca(repo)
    code, st = _status(repo, capsys)
    assert (code, st["state"], st["escalation"]) == (1, "blocked", None)
    assert not any("RCA" in p for p in st["problems"])
    assert _run("review", "list", "M1.1", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "RCA-3.md: specification (0.8) by sol, through round 3 — amend_criterion" in out
    assert "escalated" not in out
    _block_round(repo, 4)
    assert _status(repo, capsys)[1]["state"] == "blocked"   # counting restarts after the analysis


def test_reviewer_prompt_says_the_loop_is_escalated_until_an_rca_exists(tmp_path: Path) -> None:
    repo = _escalated_repo(tmp_path)
    (reviews_dir(repo, "M1.1") / PACKET_NAME).write_text("# Review packet: `M1.1`\n")
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="sol")
    assert err is None and "## Loop escalated" in text and "all block on A1" in text
    _rca(repo)
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="sol")
    assert err is None and "## Loop escalated" not in text
