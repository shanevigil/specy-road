"""M9.8: a pre-existing verifier failure counts only when reproduced twice on the integration tip.

``dev`` (the integration branch) has ``roadmap/manifest.json`` but not
``src/a.py``, which only the feature branch adds; both paths are relative, so
each command also proves it ran at the project root of a checkout of ``dev``.
A command naming ``src/a.py`` fails on ``dev`` only because the leaf adds it,
so it is never evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import advance_dev, git, make_review_repo, review_text

from specy_road.bundled_scripts import review_cli
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.review_target import resolve_target

ONE_AI = "version: 1\nroster:\n  - {id: opus, family: anthropic, roles: [reviewer]}\n"
FAILS_ON_TIP = "test ! -f roadmap/manifest.json"
PASSES_ON_TIP = "test -f roadmap/manifest.json"


def _claimed_repo(tmp_path: Path, cmd: str) -> Path:
    """A READY with ``cmd`` failing, and an approval that claims it pre-existing."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / "READY-exec.md").write_text(
        f"---\nnode_id: M1.1\nagent: exec\nbranch: feature/rm-thing\ncommit: {git(repo, 'rev-parse', 'HEAD')}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n"
        f"verify:\n  - {{cmd: {json.dumps(cmd)}, exit: 1}}\n---\n"
    )
    text = review_text(git(repo, "rev-parse", "HEAD"), model="opus")
    (d / "REVIEW-opus.md").write_text(text.replace("commands_rerun: []\n",
                                                   f"commands_rerun: []\nverify_pre_existing: [{json.dumps(cmd)}]\n"))
    return repo


def _check(repo: Path) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "check-pre-existing", "M1.1", "--repo-root", str(repo)])
    return e.value.code


def _gate(repo: Path):
    t = resolve_target(repo, "M1.1")
    return evaluate_gate(repo, t.node, t.commit, branch=(t.entry or {}).get("branch"))


def _record(repo: Path) -> dict:
    return yaml.safe_load((reviews_dir(repo, "M1.1") / "PRE-EXISTING.md").read_text().split("---")[1])


def test_a_claim_on_a_command_that_passes_on_the_tip_is_rejected(tmp_path: Path, capsys) -> None:
    repo = _claimed_repo(tmp_path, PASSES_ON_TIP)
    assert _check(repo) == 1
    assert f"claim-rejected: {PASSES_ON_TIP}" in capsys.readouterr().out
    assert _record(repo)["commands"] == [{"cmd": PASSES_ON_TIP, "exits": [0, 0]}]
    assert _gate(repo).problems()[-1].endswith(f"verifier `{PASSES_ON_TIP}` exited 1 (rejected)")


def test_a_claim_that_fails_twice_on_the_tip_is_accepted(tmp_path: Path, capsys) -> None:
    repo = _claimed_repo(tmp_path, FAILS_ON_TIP)
    before = git(repo, "worktree", "list")
    assert _gate(repo).problems()[-1].endswith("(unverified)")
    assert _check(repo) == 0
    assert git(repo, "worktree", "list") == before
    assert _record(repo) == {"integration_commit": git(repo, "rev-parse", "dev"),
                             "commands": [{"cmd": FAILS_ON_TIP, "exits": [1, 1]}]}
    assert "claim-rejected" not in capsys.readouterr().out
    gate = _gate(repo)
    assert gate.passed, gate.problems()


@pytest.mark.parametrize("commands", [
    "1",
    f"[{{cmd: {json.dumps(FAILS_ON_TIP)}, exits: [1, '1']}}]",
    "[{cmd: 7, exits: [1, 1]}]",
])
def test_malformed_evidence_leaves_the_claim_unverified_until_rechecked(tmp_path: Path, commands: str) -> None:
    repo = _claimed_repo(tmp_path, FAILS_ON_TIP)
    (reviews_dir(repo, "M1.1") / "PRE-EXISTING.md").write_text(
        f"---\nintegration_commit: {git(repo, 'rev-parse', 'dev')}\ncommands: {commands}\n---\n")
    gate = _gate(repo)
    assert not gate.passed
    assert gate.problems()[-1].endswith(f"verifier `{FAILS_ON_TIP}` exited 1 (unverified)")
    assert _check(repo) == 0
    assert _record(repo)["commands"] == [{"cmd": FAILS_ON_TIP, "exits": [1, 1]}]
    assert _gate(repo).passed


def test_a_tip_that_moved_after_the_run_makes_the_claim_stale(tmp_path: Path) -> None:
    repo = _claimed_repo(tmp_path, FAILS_ON_TIP)
    assert _check(repo) == 0
    ran_on = git(repo, "rev-parse", "dev")
    advance_dev(repo, "other.txt", "x\n")
    gate = _gate(repo)
    assert not gate.passed
    assert gate.problems()[-1].endswith(f"exited 1 (stale: {ran_on[:12]})")


@pytest.mark.parametrize("cmd,why", [
    ("test -f src/a.py", "names src/a.py, which {tip} does not have"),   # a file the leaf adds
    ("python -m pytest -q src/a.py::test_x", "names src/a.py, which {tip} does not have"),
    ("no-such-command-specy-road", "exit 127 (command not found) is no evidence"),
    ("sh -c 'exit 4'", "exit 4 (pytest usage error or no such file) is no evidence"),
])
def test_a_failure_that_proves_nothing_about_the_tip_stays_unverified(tmp_path: Path, capsys, cmd: str,
                                                                      why: str) -> None:
    repo = _claimed_repo(tmp_path, cmd)
    why = why.format(tip=git(repo, "rev-parse", "dev")[:12])
    assert _check(repo) == 1
    assert f"claim-unverified: {cmd} ({why})" in capsys.readouterr().out
    assert _record(repo)["commands"][0]["unverified"] == why
    gate = _gate(repo)
    assert not gate.passed
    assert gate.problems()[-1].endswith(f"verifier `{cmd}` exited 1 (unverified: {why})")
