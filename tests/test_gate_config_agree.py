"""The two review-gate settings cannot silently disagree.

``roadmap/orchestration.yaml`` requiring reviewers while ``git-workflow.yaml``
leaves ``require_implementation_review_before_finish`` off means finish would
land a leaf with the gate unmet: validate and doctor report it as an error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from specy_road.bundled_scripts import doctor
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import validate_roadmap as vr
from specy_road.review_gate_agreement import GATE_KEY, gate_config_mismatch
from tests.helpers import REPO
from tests.review_repo_helpers import commit_file, git, make_review_repo

ORCHESTRATION = (REPO / "specy_road" / "templates" / "project" / "roadmap" / "orchestration.yaml").read_text()
GATE_OFF = f"version: 1\nintegration_branch: dev\nremote: origin\n{GATE_KEY}: false\n"
#: (git-workflow gate on, orchestration.yaml present, mismatch expected)
CASES = {
    "mismatch": (False, True, True),
    "both on": (True, True, False),
    "both off": (False, False, False),
}


def _repo(tmp_path: Path, *, gate: bool, orchestration: bool) -> Path:
    """A claimed leaf with the gate set on ``dev`` (pushed to a bare ``origin``), on the feature branch."""
    repo = make_review_repo(tmp_path, orchestration=ORCHESTRATION if orchestration else None)
    if not gate:   # make_review_repo turns it on
        git(repo, "checkout", "-q", "dev")
        commit_file(repo, "roadmap/git-workflow.yaml", GATE_OFF, "gate off")
        git(repo, "checkout", "-q", "feature/rm-thing")
        git(repo, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "--all")
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "dev")   # as clone does; fetch does it only from git 2.48
    return repo


def _exit(fn, *args) -> int:
    with pytest.raises(SystemExit) as e:
        fn(*args)
        raise SystemExit(0)
    return e.value.code or 0


@pytest.mark.parametrize("case", CASES)
def test_mismatch_only_when_reviewers_required_but_gate_off(tmp_path: Path, case: str) -> None:
    gate, orchestration, expected = CASES[case]
    msg = gate_config_mismatch(_repo(tmp_path, gate=gate, orchestration=orchestration))
    assert (msg is not None) == expected
    if expected:
        for needle in ("roadmap/orchestration.yaml", "reviewers_required", "roadmap/git-workflow.yaml",
                       f"Fix: set `{GATE_KEY}: true` in roadmap/git-workflow.yaml"):
            assert needle in msg


def test_gate_on_only_on_the_integration_branch_is_no_mismatch(tmp_path: Path) -> None:
    """Finish enforces the gate when the integration branch turns it on; a feature branch cannot lower it."""
    repo = _repo(tmp_path, gate=True, orchestration=True)
    commit_file(repo, "roadmap/git-workflow.yaml", GATE_OFF, "lower it")
    assert gate_config_mismatch(repo) is None


@pytest.mark.parametrize("case", CASES)
def test_validate_fails_on_the_mismatch(tmp_path: Path, monkeypatch, capsys, case: str) -> None:
    gate, orchestration, expected = CASES[case]
    repo = _repo(tmp_path, gate=gate, orchestration=orchestration)
    monkeypatch.setattr(sys, "argv", ["validate", "--repo-root", str(repo)])
    code = _exit(vr.main)
    err = capsys.readouterr().err
    assert (code, "roadmap: error — roadmap/orchestration.yaml requires" in err) == (int(expected), expected)


@pytest.mark.parametrize("case", CASES)
def test_doctor_reports_the_mismatch_as_an_error(tmp_path: Path, capsys, case: str) -> None:
    gate, orchestration, expected = CASES[case]
    repo = _repo(tmp_path, gate=gate, orchestration=orchestration)
    code = _exit(doctor.main, ["--repo-root", str(repo)])
    out = capsys.readouterr()
    assert "Nothing to tidy" in out.out   # the rest of the report still runs
    assert (code, "error: roadmap/orchestration.yaml requires 1 reviewer(s)" in out.err) == (int(expected), expected)


def test_mark_reviewed_says_the_gate_is_not_enforced_at_finish(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path, gate=False, orchestration=False)
    assert _exit(mir.main, ["--repo-root", str(repo)]) == 0
    out = capsys.readouterr()
    assert "review gate is not enforced at finish-this-task — nothing to do" in out.err
    assert f"set {GATE_KEY}: true" in out.out
