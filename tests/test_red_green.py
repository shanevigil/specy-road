"""M9.10: with policy.red_green on, the tests a leaf adds or changes must fail at the merge base and pass at head.

``dev`` holds a buggy ``src/calc.py`` (``add`` subtracts) and two tests. The leaf
fixes ``add``, adds ``mul`` and changes or adds four tests, one of each outcome
class: ``test_red`` (red then green), ``test_old`` (already passes at base),
``tests/test_mul.py::test_mul`` (its import errors at base) and ``test_kept``
(declared ``preserve`` on ``dev``). ``test_untouched`` is not under check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo

from specy_road.bundled_scripts import review_cli
from specy_road.integrity_gate import integrity_gate_problems
from specy_road.orchestration_config import validate_orchestration_dict
from specy_road import red_green
from specy_road.red_green import RED_GREEN_NAME, outcome_problems
from specy_road.review_files import render_front_matter, reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.review_target import resolve_target

ROSTER = "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
ON = ROSTER + "policy: {red_green: true}\n"
CALC = "tests/test_calc.py"
MUL = "tests/test_mul.py"
PRESERVE = f"preserve: {CALC}::test_kept"
BASE_TESTS = (
    "from src.calc import add\n\n\n"
    "def test_old():\n    assert add(0, 0) == 0\n\n\n"
    "def test_kept():\n    assert add(0, 0) == 0\n\n\n"
    "def test_untouched():\n    assert add(1, 0) == 1\n"
)
HEAD_TESTS = (
    "from src.calc import add\n\n\n"
    "def test_old():\n    assert add(2, 0) == 2\n\n\n"
    "def test_kept():\n    assert add(0, 0) == 0, 'zero'\n\n\n"
    "def test_untouched():\n    assert add(1, 0) == 1\n\n\n"
    "def test_red():\n    assert add(1, 2) == 3\n"
)
UNDER_CHECK = [f"{CALC}::test_kept", f"{CALC}::test_old", f"{CALC}::test_red", f"{MUL}::test_mul"]


def _leaf(tmp_path: Path, orchestration: str = ON) -> Path:
    repo = make_review_repo(tmp_path, orchestration=orchestration)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "src/calc.py", "def add(a, b):\n    return a - b\n", "buggy add")
    commit_file(repo, CALC, BASE_TESTS, "tests")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")
    git(repo, "checkout", "-q", "dev")
    chunk = json.dumps({"nodes": [{**NODE, "planned_test_changes": [PRESERVE]}]})
    commit_file(repo, "roadmap/phases/M1.json", chunk, "declare test_kept preserved")
    git(repo, "checkout", "-q", "feature/rm-thing")
    commit_file(repo, "src/calc.py",
                "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n", "fix add, add mul")
    commit_file(repo, CALC, HEAD_TESTS, "tests")
    commit_file(repo, MUL, "from src.calc import mul\n\n\ndef test_mul():\n    assert mul(2, 3) == 6\n", "mul test")
    return repo


def _run(repo: Path) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "red-green", "M1.1", "--repo-root", str(repo)])
    return e.value.code


def _record(repo: Path) -> dict:
    return yaml.safe_load((reviews_dir(repo, "M1.1") / RED_GREEN_NAME).read_text().split("---")[1])


def _red_green_problems(repo: Path) -> list[str]:
    t = resolve_target(repo, "M1.1")
    problems = evaluate_gate(repo, t.node, t.commit, branch=(t.entry or {}).get("branch")).problems()
    return [p for p in problems if p.startswith(("red-green", "not-red", "not-green"))]


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, int, str, str]:
    """One run of the command; ``(repo, exit, worktree list before, after)``."""
    repo = _leaf(tmp_path_factory.mktemp("rg"))
    before = git(repo, "worktree", "list")
    code = _run(repo)
    return repo, code, before, git(repo, "worktree", "list")


def test_tests_under_check_are_the_added_and_changed_test_functions(tmp_path: Path) -> None:
    repo = _leaf(tmp_path)
    t = resolve_target(repo, "M1.1")
    assert red_green.tests_under_check(repo, t.base, t.commit) == UNDER_CHECK


def test_record_has_one_outcome_per_test_at_base_and_head(ran) -> None:
    repo, code, before, after = ran
    assert code == 1
    assert after == before
    record = _record(repo)
    assert record["commit"] == git(repo, "rev-parse", "HEAD")
    assert record["base"] == git(repo, "merge-base", "dev", "HEAD")
    assert record["tests"] == [
        {"test": f"{CALC}::test_kept", "base": "pass", "head": "pass"},
        {"test": f"{CALC}::test_old", "base": "pass", "head": "pass"},
        {"test": f"{CALC}::test_red", "base": "fail", "head": "pass"},
        {"test": f"{MUL}::test_mul", "base": "error", "head": "pass"},
    ]


def test_gate_flags_tests_that_pass_or_error_at_base(ran) -> None:
    repo, *_ = ran
    assert _red_green_problems(repo) == [f"not-red: {CALC}::test_old", f"not-red: {MUL}::test_mul"]


def test_gate_flags_a_missing_record_and_ignores_evidence_with_the_policy_off(tmp_path: Path) -> None:
    repo = _leaf(tmp_path)
    assert _red_green_problems(repo) == ["red-green: missing"]
    off = _leaf(tmp_path / "off", ROSTER)
    assert _red_green_problems(off) == []


def test_gate_flags_a_stale_record(tmp_path: Path) -> None:
    repo = _leaf(tmp_path)
    old = git(repo, "rev-parse", "HEAD")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / RED_GREEN_NAME).write_text(f"---\ncommit: {old}\nbase: {old}\ntests: []\n---\n")
    commit_file(repo, "src/calc.py", "def add(a, b):\n    return b + a\n", "later work")
    assert _red_green_problems(repo) == [f"red-green: stale ({old[:12]})"]


@pytest.mark.parametrize(("side", "bad", "problem"), [
    ("base", [], "not-red"), ("base", {"x": 1}, "not-red"), ("head", [], "not-green"), ("head", {"x": 1}, "not-green"),
])
def test_gate_reports_a_non_string_outcome_as_a_per_test_problem(tmp_path: Path, side: str, bad, problem: str) -> None:
    repo = _leaf(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    rows = [{"test": t, "base": "pass" if t.endswith("test_kept") else "fail", "head": "pass"} for t in UNDER_CHECK]
    rows[2][side] = bad   # test_red
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / RED_GREEN_NAME).write_text(render_front_matter({"commit": head, "base": head, "tests": rows}))
    assert integrity_gate_problems(repo, {"red_green": True}, "M1.1", head, "dev") == [f"{problem}: {UNDER_CHECK[2]}"]


def test_preserve_must_pass_on_both_and_others_must_go_red_to_green() -> None:
    rows = [{"test": "t.py::a", "base": "fail", "head": "pass"}, {"test": "t.py::b", "base": "fail", "head": "pass"},
            {"test": "t.py::c", "base": "pass", "head": "fail"}]
    tests = ["t.py::a", "t.py::b", "t.py::c", "t.py::d"]
    assert outcome_problems(rows, tests, {"preserve: t.py::b"}) == [
        "not-green: t.py::b", "not-green: t.py::c", "not-green: t.py::d"]


def test_no_integration_ref_fails_closed(tmp_path: Path) -> None:
    repo = _leaf(tmp_path)
    problems = integrity_gate_problems(repo, {"red_green": True}, "M1.1", git(repo, "rev-parse", "HEAD"), None)
    assert problems == [f"red-green: no merge base between the integration branch (None) and "
                        f"{git(repo, 'rev-parse', 'HEAD')}"]


def test_schema_accepts_the_policy() -> None:
    assert validate_orchestration_dict(yaml.safe_load(ON)) is None
    assert validate_orchestration_dict({**yaml.safe_load(ROSTER), "policy": {"red_green": "yes"}})
