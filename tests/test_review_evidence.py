"""Review evidence: READY verifier results are checked, and approvals can be required to re-run.

From the "SRE for AI" triage (docs/design-notes/sre-for-ai-triage.md): a claim
the executor declared is reported as such, and a reviewer's "tested" rung can be
made mandatory by policy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.orchestration_config import parse_orchestration_text
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.review_target import resolve_target

ONE_AI = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
"""


def _run(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _ready(repo: Path, verify: str) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "READY-exec.md").write_text(
        f"---\nnode_id: M1.1\nagent: exec\nbranch: feature/rm-thing\ncommit: {git(repo, 'rev-parse', 'HEAD')}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n{verify}---\n"
    )


def _status(repo: Path, capsys) -> dict:
    capsys.readouterr()
    code = _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert code == (0 if st["policy_met"] else 1), st["state"]
    return st


FAILED = "verify:\n  - {cmd: 'false', exit: 1, tail: boom}\n  - {cmd: pytest, exit: 0}\n"
PASSED = "verify:\n  - {cmd: pytest, exit: 0, tail: '9 passed'}\n"


# --- S1: verifier evidence ------------------------------------------------------

def test_status_lists_a_failing_verifier(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, FAILED)
    st = _status(repo, capsys)
    assert "READY-exec.md (executor-reported): verifier `false` exited 1" in st["problems"]
    assert not any("pytest" in p for p in st["problems"])


def test_status_lists_missing_verifier_evidence(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, "")
    st = _status(repo, capsys)
    assert "READY-exec.md (executor-reported): no verifier evidence recorded (verify is empty)" in st["problems"]


def test_a_failing_verifier_does_not_change_state(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, FAILED)
    assert _status(repo, capsys)["state"] == "in-review"


def test_packet_marks_failing_and_missing_verifiers(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, FAILED)
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "### `false` → exit 1  **← verifier failed**" in text
    assert "### `pytest` → exit 0\n" in text
    _ready(repo, "")
    assert "**No verifier evidence recorded.**" in rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])


def test_passing_verifiers_add_no_problem(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, PASSED)
    assert not any(p.startswith("READY-") for p in _status(repo, capsys)["problems"])
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "verifier failed" not in text and "No verifier evidence" not in text


# --- S3: policy.reviewer_reruns_required -----------------------------------------

RERUNS_ON = ONE_AI + "policy:\n  reviewer_reruns_required: true\n"
NO_RERUN = "does not count — approved without re-running a command (policy.reviewer_reruns_required)"


def _review(repo: Path, model: str = "opus", rerun: list[str] | None = None, verdict: str = "approve") -> str:
    text = review_text(git(repo, "rev-parse", "HEAD"), model=model, verdict=verdict)
    if rerun:
        text = text.replace("commands_rerun: []", "commands_rerun: " + json.dumps(rerun))
    return text


def _gate(repo: Path, text: str, model: str = "opus"):
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(text)
    t = resolve_target(repo, "M1.1")
    return evaluate_gate(repo, t.node, t.commit, branch=(t.entry or {}).get("branch"))


def test_reruns_required_rejects_an_approval_without_a_rerun(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=RERUNS_ON)
    gate = _gate(repo, _review(repo))
    assert not gate.passed and not gate.approvals
    assert f"REVIEW-opus.md: {NO_RERUN}" in gate.problems()


def test_reruns_required_counts_an_approval_with_a_rerun(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=RERUNS_ON)
    assert _gate(repo, _review(repo, rerun=["pytest"])).passed


def test_reruns_off_counts_as_before(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _gate(repo, _review(repo)).passed


def test_reruns_required_exempts_the_interactive_human_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=RERUNS_ON)
    assert _gate(repo, _review(repo, model="human"), model="human").passed


def test_review_record_refuses_an_approval_without_a_rerun(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=RERUNS_ON)
    notes = repo.parent / "notes.md"
    notes.write_text(_review(repo))
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes), "--repo-root", str(repo)) == 1
    assert "approved without re-running a command" in capsys.readouterr().err
    notes.write_text(_review(repo, rerun=["pytest"]))
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes), "--repo-root", str(repo)) == 0


def test_validate_checks_the_reruns_key_type() -> None:
    assert parse_orchestration_text(RERUNS_ON)[1] is None
    _data, err = parse_orchestration_text(ONE_AI + "policy:\n  reviewer_reruns_required: 'yes'\n")
    assert err and "reviewer_reruns_required" in err


# --- M3.17: failing READY verifiers gate unless marked pre-existing ----------------


def _review_with_preexisting(repo: Path, *, pre: list[str], verdict: str = "approve") -> str:
    text = _review(repo, verdict=verdict)
    block = "verify_pre_existing: " + json.dumps(pre) + "\n"
    return text.replace("commands_rerun: []\n", "commands_rerun: []\n" + block)


def test_failing_verifier_blocks_even_when_reviews_pass(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, FAILED)
    assert _gate(repo, _review(repo)).passed is False
    st = _status(repo, capsys)
    assert not st["policy_met"]
    assert any("verifier `false` exited 1" in p for p in st["problems"])


def test_pre_existing_marker_on_approve_clears_verifier_block(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, FAILED)
    assert _gate(repo, _review_with_preexisting(repo, pre=["false"])).passed
    st = _status(repo, capsys)
    assert st["policy_met"]
    assert not any("verifier `false`" in p for p in st["problems"])


def test_pre_existing_marker_on_block_is_ignored(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, FAILED)
    text = _review_with_preexisting(repo, pre=["false"], verdict="block")
    gate = _gate(repo, text)
    assert not gate.passed
    assert gate.blocks
    assert any("verifier `false` exited 1" in p for p in gate.problems())


def test_no_ready_file_does_not_add_verifier_problems(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _gate(repo, _review(repo)).passed
    st = _status(repo, capsys)
    assert st["policy_met"]
    assert not any("verifier" in p for p in st["problems"])


def test_empty_verify_is_reported_but_does_not_block_with_an_approval(
    tmp_path: Path, capsys
) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, "")
    assert _gate(repo, _review(repo)).passed
    st = _status(repo, capsys)
    assert st["policy_met"]
    assert "READY-exec.md (executor-reported): no verifier evidence recorded (verify is empty)" in st["problems"]


# --- M9.4: executor blocked_on ---------------------------------------------------


BLOCKED_ON = (
    "blocked_on:\n"
    "  - {acceptance: A1, reason: would require weakening an existing test}\n"
    "  - {acceptance: A2, reason: baseline cap too low}\n"
)


def _ready_blocked(repo: Path) -> None:
    _ready(repo, PASSED + BLOCKED_ON)


def test_handoff_status_executor_blocked_lists_entries_and_exits_one(
    tmp_path: Path, capsys
) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready_blocked(repo)
    capsys.readouterr()
    code = _run("handoff", "status", "M1.1", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "executor_blocked" in out
    assert "A1: would require weakening an existing test" in out
    assert "A2: baseline cap too low" in out


def test_handoff_status_executor_blocked_json(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready_blocked(repo)
    capsys.readouterr()
    code = _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert code == 1
    assert st["state"] == "executor_blocked"
    assert st["executor_blocked"] == [
        "A1: would require weakening an existing test",
        "A2: baseline cap too low",
    ]


def test_executor_blocked_keeps_gate_unmet_even_with_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready_blocked(repo)
    gate = _gate(repo, _review(repo))
    assert not gate.passed
    assert any("blocked on A1" in p for p in gate.problems())
    assert any("blocked on A2" in p for p in gate.problems())


def test_a_stale_blocked_ready_does_not_block_a_later_commit(tmp_path: Path, capsys) -> None:
    """blocked_on binds to the READY commit: a later implementation commit is judged on its own."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready_blocked(repo)
    commit_file(repo, "src/b.py", "b = 1\n", "address the block")
    gate = _gate(repo, _review(repo))
    assert gate.passed, gate.problems()
    assert not any("blocked on" in p for p in gate.problems())
    st = _status(repo, capsys)
    assert st["state"] == "approved" and st["executor_blocked"] == []


def test_executor_blocked_outranks_a_reviewer_block_and_escalation(tmp_path: Path, capsys) -> None:
    """A3 holds even when a counted review blocks and the loop is escalated; both stay reported."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI + "policy: {escalate_review_rounds: 1}\n")
    notes = repo.parent / "notes.md"
    text = review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict="block", a1="fail")
    notes.write_text(text.replace("notes\n", "round 1: the heading case still warns\n"))
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0
    _ready_blocked(repo)
    st = _status(repo, capsys)
    assert st["state"] == "executor_blocked"
    assert st["executor_blocked"] == [
        "A1: would require weakening an existing test",
        "A2: baseline cap too low",
    ]
    assert st["escalation"] is not None
    assert [r["verdict"] for r in st["reviews"]] == ["block"]
