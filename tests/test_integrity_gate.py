"""M9.6: with policy.integrity_gate on, an undeclared test-integrity finding blocks the review gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts import do_next_prompt as dnp
from specy_road.bundled_scripts import finish_task, mark_implementation_reviewed as mir, review_cli
from specy_road.integrity_gate import integrity_gate_problems
from specy_road.orchestration_config import validate_orchestration_dict
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate

ROSTER = "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
GATE_ON = ROSTER + "policy: {integrity_gate: true}\n"
FINDING = "removed-test: tests/test_x.py::test_b"
SCHEMAS = Path(__file__).resolve().parents[1] / "specy_road" / "templates" / "project" / "schemas"


def _leaf_removes_a_test(tmp_path: Path, orchestration: str | None = GATE_ON) -> Path:
    """``dev`` gains two tests after the claim; the leaf merges them and deletes one."""
    repo = make_review_repo(tmp_path, orchestration=orchestration)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "tests/test_x.py", "def test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n", "tests")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")
    commit_file(repo, "tests/test_x.py", "def test_a():\n    assert 1\n", "drop test_b")
    return repo


def _declare(repo: Path, branch: str) -> None:
    """Commit ``planned_test_changes: [FINDING]`` on the node, on ``branch``; the repo ends on the leaf."""
    git(repo, "checkout", "-q", branch)
    chunk = json.dumps({"nodes": [{**NODE, "planned_test_changes": [FINDING]}]})
    commit_file(repo, "roadmap/phases/M1.json", chunk, "declare the test removal")
    git(repo, "checkout", "-q", "feature/rm-thing")


def _approve(repo: Path) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "REVIEW-human.md").write_text(review_text(git(repo, "rev-parse", "HEAD")))


def _gate(repo: Path, node: dict = NODE):
    return evaluate_gate(repo, node, git(repo, "rev-parse", "HEAD"))


def _exit(main, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        main(list(args))
        raise SystemExit(0)
    return e.value.code or 0


def test_undeclared_finding_blocks_an_approved_gate(tmp_path: Path) -> None:
    repo = _leaf_removes_a_test(tmp_path)
    _approve(repo)
    g = _gate(repo)
    assert not g.passed
    assert f"integrity (undeclared): {FINDING}" in "\n".join(g.problems())


def test_declaration_on_the_leaf_branch_does_not_clear_the_finding(tmp_path: Path) -> None:
    repo = _leaf_removes_a_test(tmp_path)
    _declare(repo, "feature/rm-thing")
    _approve(repo)
    g = _gate(repo, {**NODE, "planned_test_changes": [FINDING]})   # the leaf's own copy declares it
    assert not g.passed
    assert f"integrity (undeclared): {FINDING}" in "\n".join(g.problems())


def test_declaration_on_the_integration_branch_clears_the_finding(tmp_path: Path) -> None:
    repo = _leaf_removes_a_test(tmp_path)
    _declare(repo, "dev")
    _approve(repo)
    g = _gate(repo)
    assert g.passed, g.problems()


@pytest.mark.parametrize("orchestration", [None, ROSTER, ROSTER + "policy: {integrity_gate: false}\n"])
def test_gate_off_or_absent_ignores_findings(tmp_path: Path, orchestration: str | None) -> None:
    repo = _leaf_removes_a_test(tmp_path, orchestration)
    _approve(repo)
    assert _gate(repo).passed


def test_gate_switched_on_only_on_the_leaf_branch_is_not_read(tmp_path: Path) -> None:
    repo = _leaf_removes_a_test(tmp_path, ROSTER)
    commit_file(repo, "roadmap/orchestration.yaml", GATE_ON, "turn the integrity gate on here only")
    _approve(repo)
    assert _gate(repo).passed


def test_no_integration_ref_fails_closed(tmp_path: Path) -> None:
    repo = _leaf_removes_a_test(tmp_path)
    problems = integrity_gate_problems(repo, {"integrity_gate": True}, "M1.1", git(repo, "rev-parse", "HEAD"), None)
    assert problems and "no merge base" in problems[0]


def test_handoff_status_prints_undeclared_findings(tmp_path: Path, capsys) -> None:
    repo = _leaf_removes_a_test(tmp_path)
    _approve(repo)
    assert _exit(review_cli.main, "handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    assert f"- integrity (undeclared): {FINDING}" in capsys.readouterr().out


def _summarised(repo: Path) -> Path:
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n")
    _approve(repo)
    return repo


def test_mark_reviewed_yes_refuses(tmp_path: Path, capsys) -> None:
    repo = _summarised(_leaf_removes_a_test(tmp_path))
    assert _exit(mir.main, "--yes", "--repo-root", str(repo)) == 1
    captured = capsys.readouterr()
    assert "review gate is not met" in captured.err
    assert f"integrity (undeclared): {FINDING}" in captured.out
    reg = yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text())
    assert reg["entries"][0]["implementation_review"] == "pending"


def test_finish_refuses_once_the_integration_branch_turns_the_gate_on(tmp_path: Path, capsys) -> None:
    repo = _summarised(_leaf_removes_a_test(tmp_path, ROSTER))
    assert _exit(mir.main, "--yes", "--repo-root", str(repo)) == 0
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "roadmap/orchestration.yaml", GATE_ON, "integrity gate on")
    git(repo, "checkout", "-q", "feature/rm-thing")
    before = git(repo, "rev-parse", "HEAD")
    assert _exit(finish_task.main, "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "no longer holds at this commit" in err
    assert f"integrity (undeclared): {FINDING}" in err
    assert git(repo, "rev-parse", "HEAD") == before


def test_schemas_accept_the_new_fields() -> None:
    roadmap = json.loads((SCHEMAS / "roadmap.schema.json").read_text())
    Draft202012Validator(roadmap).validate({"version": 1, "nodes": [{**NODE, "planned_test_changes": [FINDING]}]})
    assert validate_orchestration_dict(yaml.safe_load(GATE_ON)) is None
    assert validate_orchestration_dict({**yaml.safe_load(ROSTER), "policy": {"integrity_gate": "yes"}})


@pytest.mark.parametrize("planned", [[], [FINDING]])
def test_pickup_prompt_lists_planned_test_changes(tmp_path: Path, planned: list[str]) -> None:
    brief = tmp_path / "work" / "brief-M1.1.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("# brief\n", encoding="utf-8")
    node = {**NODE, "planned_test_changes": planned}
    text = dnp.write_agent_prompt(node, [node], brief, repo_root=tmp_path, work_dir=tmp_path / "work").read_text()
    listed = text.split("## Planned test changes", 1)[1].split("## Instructions", 1)[0]
    assert (f"- `{FINDING}`" in listed) == bool(planned)
    assert ("_none_" in listed) == (not planned)
    assert "Any other is a `blocked_on` stop" in listed
    assert "amends `planned_test_changes` on the integration branch" in listed
