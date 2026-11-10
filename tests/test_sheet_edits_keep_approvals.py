"""M11.16: planning or review bookkeeping after approval does not stale reviews."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import (
    NODE, commit_file, git, git_root_relative, make_layout_finish_repo, make_review_repo, review_text,
)
from tests.test_review_cli import ONE_AI, _status

from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate


def _review(repo: Path) -> str:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    commit = git(repo, "rev-parse", "HEAD")
    (d / "REVIEW-human.md").write_text(review_text(commit, model="human"))
    return commit


def _gate(repo: Path):
    return evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))


def test_sheet_only_delta_keeps_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    commit_file(repo, NODE["planning_dir"], _with_tier(), "tier")
    _review(repo)
    assert _gate(repo).passed
    commit_file(repo, NODE["planning_dir"], _with_tier("Updated."), "sheet")
    g = _gate(repo)
    assert g.passed and g.bookkeeping_carry
    assert not g.stale
    assert "still count" in g.summary()


def test_summary_only_delta_keeps_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    commit_file(repo, NODE["planning_dir"], _with_tier(), "tier")
    _review(repo)
    commit_file(
        repo,
        "work/implementation-summary-M1.1.md",
        "# Summary\n\nDone.\n",
        "summary",
    )
    g = _gate(repo)
    assert g.passed and g.bookkeeping_carry
    assert not g.stale


def test_mixed_delta_stales_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _review(repo)
    commit_file(repo, NODE["planning_dir"], "# M1.1 Thing\n\n## Intent\n\nAlso.\n\n## References\n", "sheet")
    commit_file(repo, "src/b.py", "x\n", "code")
    g = _gate(repo)
    assert not g.passed
    assert len(g.stale) == 1
    assert not g.bookkeeping_carry


def test_ours_merge_stales_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _review(repo)
    git(repo, "checkout", "-q", "-b", "other")
    commit_file(repo, "other.txt", "x\n", "other")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "-s", "ours", "--no-edit", "other")
    g = _gate(repo)
    assert not g.passed
    assert len(g.stale) == 1
    assert not g.bookkeeping_carry


def test_unresolved_commit_leaves_approval_stale(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _review(repo)
    g = evaluate_gate(repo, NODE, None)
    assert not g.passed
    assert len(g.stale) == 1
    assert not g.bookkeeping_carry
    assert "still count" not in g.summary()


def test_nested_sheet_carry_and_git_root_namesake_stales(tmp_path: Path) -> None:
    git_top, project = make_layout_finish_repo(tmp_path / "keep", "nested")
    rel = git_root_relative(git_top, project, NODE["planning_dir"])
    commit_file(git_top, rel, _with_tier(), "tier")
    _review(project)
    commit_file(git_top, rel, _with_tier("Updated."), "in-project sheet")
    g = evaluate_gate(project, NODE, git(git_top, "rev-parse", "HEAD"))
    assert g.passed and g.bookkeeping_carry
    assert not g.stale

    for i, rel in enumerate((NODE["planning_dir"], "work/implementation-summary-M1.1.md")):
        git_top, project = make_layout_finish_repo(tmp_path / f"stale-{i}", "nested")
        _review(project)
        commit_file(git_top, rel, "git-root namesake\n", "git-root namesake")
        g = evaluate_gate(project, NODE, git(git_top, "rev-parse", "HEAD"))
        assert not g.passed
        assert len(g.stale) == 1
        assert not g.bookkeeping_carry


def test_handoff_status_reports_bookkeeping_carry(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    commit_file(repo, NODE["planning_dir"], _with_tier(), "tier")
    _review(repo)
    commit_file(repo, NODE["planning_dir"], _with_tier("Notes."), "sheet")
    st = _status(repo, capsys)
    assert st["policy_met"]
    assert "still count" in st["policy"]


def _rel(git_top: Path, project: Path, path: str) -> str:
    return git_root_relative(git_top, project, path)


def _with_tier(body: str = "Do the thing.", tier: str = "trust boundary: the gate") -> str:
    return f"# M1.1 Thing\n\n## Tier\n\n{tier}\n\n## Intent\n\n{body}\n\n## References\n"


def _prepare(tmp_path: Path, *, tier: bool) -> tuple[Path, Path]:
    """Nested project with a second node, and a tier on this leaf's sheet unless ``tier`` is false."""
    git_top, project = make_layout_finish_repo(tmp_path, "nested")
    rel = _rel(git_top, project, "roadmap/phases/M1.json")
    doc = json.loads((git_top / rel).read_text())
    other = {**NODE, "id": "M1.2", "node_key": "22222222-2222-5222-8222-222222222222", "codename": "other",
             "title": "Other", "sibling_order": 2, "acceptance": ["other"], "planning_dir": "planning/M1.2_other.md"}
    doc["nodes"].append(other)
    commit_file(git_top, rel, json.dumps(doc), "other node")
    if tier:
        commit_file(git_top, _rel(git_top, project, NODE["planning_dir"]), _with_tier(), "tier")
    _review(project)
    return git_top, project


def _set_field(git_top: Path, project: Path, node_id: str, field: str, value: object) -> None:
    rel = _rel(git_top, project, "roadmap/phases/M1.json")
    doc = json.loads((git_top / rel).read_text())
    for node in doc["nodes"]:
        if node["id"] == node_id:
            node[field] = value
    commit_file(git_top, rel, json.dumps(doc), field)


def _on_dev(git_top: Path, rel: str, text: str) -> None:
    git(git_top, "checkout", "-q", "dev")
    commit_file(git_top, rel, text, "dev moves")
    git(git_top, "checkout", "-q", "feature/rm-thing")


def _merge(git_top: Path, *args: str) -> int:
    completed = subprocess.run(["git", "-C", str(git_top), "merge", *args], capture_output=True, text=True)
    return completed.returncode


def _other_node(git_top: Path, project: Path) -> None:
    _set_field(git_top, project, "M1.2", "acceptance", ["changed"])


def _registry(git_top: Path, project: Path) -> None:
    rel = _rel(git_top, project, "roadmap/registry.yaml")
    commit_file(git_top, rel, (git_top / rel).read_text() + "# row\n", "registry")


def _summary(git_top: Path, project: Path) -> None:
    commit_file(git_top, _rel(git_top, project, "work/implementation-summary-M1.1.md"), "# Summary\n\nDone.\n", "summary")


def _review_note(git_top: Path, project: Path) -> None:
    rel = _rel(git_top, project, "work/reviews/M1.1/note.md")
    path = git_top / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("a note\n", encoding="utf-8")
    git(git_top, "add", "-f", rel)
    git(git_top, "commit", "-qm", "review note")


def _own_sheet(git_top: Path, project: Path) -> None:
    rel = _rel(git_top, project, NODE["planning_dir"])
    commit_file(git_top, rel, (git_top / rel).read_text().replace("Do the thing.", "Updated body."), "sheet")


def _this_acceptance(git_top: Path, project: Path) -> None:
    # Keep two criteria so the filed review's A1/A2 keys still match; the text is what changes.
    _set_field(git_top, project, "M1.1", "acceptance", ["changed", "still two"])


def _this_zones(git_top: Path, project: Path) -> None:
    _set_field(git_top, project, "M1.1", "touch_zones", ["docs"])


def _tier_value(git_top: Path, project: Path) -> None:
    rel = _rel(git_top, project, NODE["planning_dir"])
    commit_file(git_top, rel, (git_top / rel).read_text().replace("trust boundary:", "plain:", 1), "tier")


def _policy_workflow(git_top: Path, project: Path) -> None:
    rel = _rel(git_top, project, "roadmap/git-workflow.yaml")
    commit_file(git_top, rel, (git_top / rel).read_text() + "# policy\n", "policy")


def _policy_orchestration(git_top: Path, project: Path) -> None:
    commit_file(git_top, _rel(git_top, project, "roadmap/orchestration.yaml"), "version: 1\n# policy\n", "policy")


def _namesake(git_top: Path, _project: Path) -> None:
    commit_file(git_top, "roadmap/stray.md", "outside the project\n", "namesake")


def _merge_same(git_top: Path, project: Path) -> None:
    _on_dev(git_top, _rel(git_top, project, "notes.txt"), "unrelated\n")
    assert _merge(git_top, "--no-ff", "-m", "merge dev", "dev") == 0


def _merge_code(git_top: Path, project: Path) -> None:
    _on_dev(git_top, _rel(git_top, project, "src/a.py"), "dev\n")
    assert _merge(git_top, "--no-ff", "-m", "merge dev", "dev") != 0
    rel = _rel(git_top, project, "src/a.py")
    (git_top / rel).write_text("merged\n")
    git(git_top, "add", rel)
    git(git_top, "commit", "-qm", "resolve")


def _ours_merge(git_top: Path, project: Path) -> None:
    _on_dev(git_top, _rel(git_top, project, "dropped.txt"), "drop me\n")
    assert _merge(git_top, "-s", "ours", "--no-ff", "-m", "ours", "dev") == 0


def _other_merge(git_top: Path, project: Path) -> None:
    git(git_top, "checkout", "-q", "-b", "side")
    commit_file(git_top, _rel(git_top, project, "side.txt"), "side\n", "side")
    git(git_top, "checkout", "-q", "feature/rm-thing")
    assert _merge(git_top, "--no-ff", "-m", "merge side", "side") == 0


def _bad_graph(git_top: Path, project: Path) -> None:
    rel = _rel(git_top, project, "roadmap/phases/M1.json")
    good = (git_top / rel).read_text()
    doc = json.loads(good)
    for node in doc["nodes"]:
        if node["id"] == "M1.1":
            del node["node_key"]
    commit_file(git_top, rel, json.dumps(doc), "drop key")
    (git_top / rel).write_text(good)


def _bad_sheet(git_top: Path, project: Path) -> None:
    git(git_top, "rm", "-q", _rel(git_top, project, NODE["planning_dir"]))
    git(git_top, "commit", "-qm", "drop sheet")


_CARRY = {"other-node", "registry", "summary", "own-sheet", "merge-same"}
_REASONS = {
    "this-acceptance": "acceptance changed",
    "this-zones": "touch zones changed",
    "tier": "tier changed",
    "bad-graph": "graph cannot be resolved",
    "bad-sheet": "planning sheet cannot be resolved",
    "no-tier": "no tier value",
    "no-tier-sheet": "no tier value",
    "no-tier-summary": "no tier value",
    "no-tier-reviews": "no tier value",
}
_ROWS = {
    "other-node": _other_node, "registry": _registry, "summary": _summary, "own-sheet": _own_sheet,
    "this-acceptance": _this_acceptance, "this-zones": _this_zones, "tier": _tier_value,
    "policy-workflow": _policy_workflow, "policy-orchestration": _policy_orchestration, "namesake": _namesake,
    "merge-same": _merge_same, "merge-code": _merge_code, "ours-merge": _ours_merge, "other-merge": _other_merge,
    "bad-graph": _bad_graph, "bad-sheet": _bad_sheet, "no-tier": _other_node,
    "no-tier-sheet": _own_sheet, "no-tier-summary": _summary, "no-tier-reviews": _review_note,
}


@pytest.mark.parametrize("row", list(_ROWS))
def test_wider_carry_on_a_nested_project(tmp_path: Path, capsys, row: str) -> None:
    """Each row of the M22.53 table, through ``handoff status``, on a project under a prefix."""
    git_top, project = _prepare(tmp_path, tier=not row.startswith("no-tier"))
    _ROWS[row](git_top, project)
    st = _status(project, capsys)
    if row in _CARRY:
        assert st["policy_met"] and st["state"] == "approved", st["policy"]
        if row == "registry":
            gate = _gate(project)
            assert gate.passed and gate.bookkeeping_carry and "still count" in gate.summary()
        else:
            assert "still count" in st["policy"]
        return
    assert not st["policy_met"], st["policy"]
    assert any("re-review" in problem for problem in st["problems"])
    if reason := _REASONS.get(row):
        assert reason in st["policy"], st["policy"]
