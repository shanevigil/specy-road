"""Review evidence: READY verifier results are checked, and approvals can be required to re-run.

From the "SRE for AI" triage (docs/design-notes/sre-for-ai-triage.md): a claim
the executor declared is reported as such, and a reviewer's "tested" rung can be
made mandatory by policy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.review_files import reviews_dir

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
    assert _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo)) == 0
    return json.loads(capsys.readouterr().out)["nodes"][0]


FAILED = "verify:\n  - {cmd: 'false', exit: 1, tail: boom}\n  - {cmd: pytest, exit: 0}\n"
PASSED = "verify:\n  - {cmd: pytest, exit: 0, tail: '9 passed'}\n"


# --- S1: verifier evidence ------------------------------------------------------

def test_status_lists_a_failing_verifier(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, FAILED)
    st = _status(repo, capsys)
    assert "READY-exec.md: verifier `false` exited 1" in st["problems"]
    assert not any("pytest" in p for p in st["problems"])


def test_status_lists_missing_verifier_evidence(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo, "")
    st = _status(repo, capsys)
    assert "READY-exec.md: no verifier evidence recorded (verify is empty)" in st["problems"]


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
