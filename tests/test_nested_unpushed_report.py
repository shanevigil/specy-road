"""M11.32: ``doctor`` and ``grind-session --plan`` list nested-repo branches whose commits no remote has.

The fixture is the M11.22 project (``tests/test_nested_repo_worktrees``) with
two nested repositories: ``lib``, pushed to its own bare ``origin``, and
``svc``, whose remote is removed. ``lib`` holds one branch per case: ahead of
its upstream, no upstream, an upstream deleted on the remote, no upstream but
nothing to push, and a clean pushed ``main``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.pickup_repo_helpers import make_pickup_project
from tests.review_repo_helpers import commit_file, git
from tests.test_nested_repo_worktrees import add_nested_repo

from specy_road.bundled_scripts import doctor
from specy_road.bundled_scripts import grind_session as gs
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.nested_repos import describe_unpushed, unpushed_branches

EXPECTED = [
    {"repo": "lib", "branch": "dropped", "commits": 1, "state": "no upstream", "upstream": None},
    {"repo": "lib", "branch": "topic", "commits": 2, "state": "ahead", "upstream": "origin/topic"},
    {"repo": "lib", "branch": "wip", "commits": 1, "state": "no upstream", "upstream": None},
    {"repo": "svc", "branch": "main", "commits": 1, "state": "no remote", "upstream": None},
]
LINES = [
    "lib: dropped has 1 commit(s) on no remote branch (no upstream)",
    "lib: topic has 2 commit(s) ahead of origin/topic",
    "lib: wip has 1 commit(s) on no remote branch (no upstream)",
    "svc: main has 1 commit(s) in a repository with no remote",
]


@pytest.fixture
def clean_project(tmp_path: Path) -> Path:
    root = make_pickup_project(tmp_path)
    add_nested_repo(root, "lib", "main")
    return root


@pytest.fixture
def project(clean_project: Path) -> Path:
    lib = clean_project / "lib"
    git(lib, "checkout", "-q", "-b", "topic")
    git(lib, "push", "-q", "-u", "origin", "topic")
    commit_file(lib, "a.py", "a\n", "a")
    commit_file(lib, "b.py", "b\n", "b")
    git(lib, "checkout", "-q", "-b", "dropped", "main")
    commit_file(lib, "d.py", "d\n", "d")
    git(lib, "push", "-q", "-u", "origin", "dropped")
    git(lib, "push", "-q", "origin", "--delete", "dropped")   # its upstream is now gone
    git(lib, "branch", "fresh", "main")                       # no upstream, nothing to push
    git(lib, "checkout", "-q", "-b", "wip", "main")           # sorts last: its empty upstream ends the output
    commit_file(lib, "w.py", "w\n", "w")
    svc = add_nested_repo(clean_project, "svc", "main")
    git(svc, "remote", "remove", "origin")
    return clean_project


def _plan(root: Path, capsys, *flags: str) -> str:
    assert gs.run_session(parse_grind_session_args(["--plan", *flags, "--repo-root", str(root)])) == 0
    return capsys.readouterr().out


def test_each_unpushed_branch_is_named_with_its_count(project: Path) -> None:
    found = unpushed_branches(project)
    assert found == EXPECTED
    assert [describe_unpushed(u) for u in found] == LINES


def test_a_clean_nested_repo_reports_nothing(clean_project: Path) -> None:
    assert unpushed_branches(clean_project) == []


def test_a_configured_path_that_is_not_a_repository_is_skipped(project: Path) -> None:
    (project / "roadmap" / "git-workflow.yaml").write_text(
        (project / "roadmap" / "git-workflow.yaml").read_text() + "  - gone\n", encoding="utf-8")
    assert unpushed_branches(project) == EXPECTED


def test_doctor_lists_them_without_failing(project: Path, capsys) -> None:
    with pytest.raises(SystemExit) as e:
        doctor.main(["--repo-root", str(project)])
    out = capsys.readouterr().out
    assert not e.value.code
    assert "Nested repos with commits no remote has" in out
    for line in LINES:
        assert f"  {line}\n" in out
    assert "fresh" not in out and "lib: main" not in out


def test_doctor_is_silent_about_a_clean_nested_repo(clean_project: Path, capsys) -> None:
    with pytest.raises(SystemExit):
        doctor.main(["--repo-root", str(clean_project)])
    assert "Nested repos" not in capsys.readouterr().out


def test_plan_text_and_json_list_them(project: Path, capsys) -> None:
    text = _plan(project, capsys)
    assert "## Nested repos: commits no remote has" in text
    for line in LINES:
        assert f"- {line}" in text
    payload = json.loads(_plan(project, capsys, "--json").strip().splitlines()[0])
    assert payload["nested_unpushed"] == EXPECTED
    picked = json.loads(_plan(project, capsys, "--json", "--fields", "nested_unpushed"))
    assert picked == {"nested_unpushed": EXPECTED}


def test_plan_has_no_section_for_a_clean_nested_repo(clean_project: Path, capsys) -> None:
    assert "Nested repos" not in _plan(clean_project, capsys)
    assert json.loads(_plan(clean_project, capsys, "--json").strip().splitlines()[0])["nested_unpushed"] == []
