"""Roadmap graph conflicts at landing: resolved when inherited, refused when authored.

finish-this-task runs end to end in merge mode with a bare ``origin``. The
integration branch changes a roadmap chunk after the leaf branch merged it in,
so the landing merge conflicts there. Inherited-only content lands as the
integration branch's version with finish's completion applied again; an edit
the branch authored in a conflicted file is refused with the file named.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from specy_road.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from tests.helpers import REPO, script_subprocess_env
from tests.review_repo_helpers import (
    NODE, commit_file, git, git_root_relative, make_layout_finish_repo,
    prepare_layout_merge_mode_remote,
)
from tests.test_finish_merge_mode import merge_mode_finish_repo


def _cli(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the public ``specy-road`` CLI in ``repo``."""
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(repo)],
        cwd=repo, capture_output=True, text=True, check=False, env=script_subprocess_env(),
    )


def _assert_generated_files_current(repo: Path) -> None:
    """``export --check`` and ``digest --check`` pass on the landed integration branch."""
    git(repo, "checkout", "-q", "dev")
    git(repo, "reset", "-q", "--hard", "origin/dev")
    for command in ("export", "digest"):
        check = _cli(repo, command, "--check")
        assert check.returncode == 0, check.stdout + check.stderr


def _chunk_commit(repo: Path, message: str, **fields) -> None:
    """Rewrite M1.1 in ``roadmap/phases/M1.json`` with ``fields`` set, and commit it."""
    chunk = repo / "roadmap" / "phases" / "M1.json"
    nodes = load_json_chunk(chunk)
    nodes[0].update(fields)
    write_json_chunk(chunk, nodes)
    commit_file(repo, "roadmap/phases/M1.json", chunk.read_text(encoding="utf-8"), message)


def _merge_dev_resolving_by_hand(repo: Path) -> None:
    """Merge ``dev`` into the branch and change the chunk in the merge commit itself."""
    git(repo, "merge", "-q", "--no-commit", "dev")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    nodes = load_json_chunk(chunk)
    nodes[0]["title"] = "Thing, retitled in the merge"
    write_json_chunk(chunk, nodes)
    git(repo, "add", "roadmap/phases/M1.json")
    git(repo, "commit", "-q", "--no-edit")


@pytest.mark.parametrize(
    "branch_edit", [None, "commit", "merge", "manifest"],
    ids=["inherited-only", "own-commit", "own-merge-resolution", "own-edit-not-conflicting"],
)
def test_a_roadmap_chunk_conflict_lands_only_when_the_branch_inherited_it(
    tmp_path: Path, monkeypatch, branch_edit: str | None
) -> None:
    """The integration branch moves the finishing node after the branch merged it in.

    finish's bookkeeping flips the node's status on the line next to the moved
    field, so the landing merge conflicts in the chunk. With nothing but
    inherited content and that flip in the chunk -- an authored edit to another
    graph file does not count -- the chunk lands as the integration branch's
    version with the node Complete and the claim released. With an edit of the
    branch's own in the chunk, by commit or in a merge's resolution, finish
    refuses, names the chunk and leaves the branch as it was.
    """
    repo, bare = merge_mode_finish_repo(tmp_path, monkeypatch)
    git(repo, "checkout", "-q", "dev")
    _chunk_commit(repo, "integration edits the goal", goal="Do the thing well.")
    git(repo, "checkout", "-q", "feature/rm-thing")
    if branch_edit == "merge":
        _merge_dev_resolving_by_hand(repo)
    else:
        git(repo, "merge", "-q", "--no-edit", "dev")   # the branch inherits that edit
    if branch_edit == "commit":
        _chunk_commit(repo, "the branch retitles its node", title="Thing, retitled")
    manifest = json.dumps({"version": 1, "includes": ["phases/M1.json"]}, indent=2) + "\n"
    if branch_edit == "manifest":
        commit_file(repo, "roadmap/manifest.json", manifest, "the branch reformats the manifest")
    git(repo, "checkout", "-q", "dev")
    _chunk_commit(repo, "integration moves the node", sibling_order=2)
    git(repo, "push", "-q", "origin", "dev")
    git(repo, "checkout", "-q", "feature/rm-thing")
    pre = git(repo, "rev-parse", "HEAD")
    dev_before = git(bare, "rev-parse", "dev")

    result = _cli(repo, "finish-this-task")

    if branch_edit in ("commit", "merge"):
        assert result.returncode == 1, result.stdout
        errors = [ln for ln in result.stderr.splitlines() if ln.startswith("error:")]
        assert len(errors) == 1 and "roadmap/phases/M1.json" in errors[0], result.stderr
        assert "git merge dev" in errors[0], result.stderr
        assert git(bare, "rev-parse", "dev") == dev_before
        assert git(repo, "rev-parse", "HEAD") == pre   # no bookkeeping commit left
        assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
        return
    assert result.returncode == 0, result.stdout + result.stderr
    landed = json.loads(git(bare, "show", "dev:roadmap/phases/M1.json"))["nodes"][0]
    assert (landed["status"], landed["sibling_order"], landed["goal"]) == (
        "Complete", 2, "Do the thing well.",
    )
    registry = yaml.safe_load(git(bare, "show", "dev:roadmap/registry.yaml"))
    assert not any(e.get("codename") == "thing" for e in registry.get("entries") or [])
    if branch_edit == "manifest":   # the branch's own edit outside the conflict lands as it was
        assert git(bare, "show", "dev:roadmap/manifest.json") + "\n" == manifest
    _assert_generated_files_current(repo)


PHASE = {
    "id": "M1", "node_key": "22222222-2222-5222-8222-222222222222", "codename": "phase-one",
    "title": "Phase one", "type": "phase", "parent_id": None, "sibling_order": 1,
    "status": "Not Started", "dependencies": [], "touch_zones": [],
    "planning_dir": "planning/M1_phase-one_22222222-2222-5222-8222-222222222222.md",
}


@pytest.mark.parametrize("leaf_status", ["In Progress", "Complete"])
def test_an_ancestor_chunk_conflict_lands_with_the_ancestor_recomputed(
    tmp_path: Path, monkeypatch, leaf_status: str
) -> None:
    """Only the ancestor's chunk conflicts; the leaf's chunk merges cleanly as Complete.

    finish's bookkeeping completes the leaf in its own chunk and its rolled-up
    ancestor in another. The integration branch then moves the ancestor, so
    only the ancestor's chunk conflicts and is restored from the integration
    branch -- with the ancestor's old status, while the leaf is Complete
    already. The ancestor must still land Complete -- also when the leaf was
    Complete before finish, so the bookkeeping commit never rewrote its chunk.
    """
    repo, bare = merge_mode_finish_repo(tmp_path, monkeypatch)
    git(repo, "checkout", "-q", "dev")
    phases = repo / "roadmap" / "phases"
    write_json_chunk(phases / "P.json", [PHASE])
    write_json_chunk(phases / "M1.json", [{**NODE, "parent_id": "M1", "status": leaf_status}])
    (repo / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/P.json", "phases/M1.json"]}),
        encoding="utf-8",
    )
    sheet = repo / PHASE["planning_dir"]
    sheet.write_text("# M1 Phase one\n\n## Intent\n\nGroup the thing.\n", encoding="utf-8")
    git(repo, "add", "roadmap", PHASE["planning_dir"])
    git(repo, "commit", "-qm", "integration nests the leaf under a phase in its own chunk")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")   # the branch inherits the new layout
    git(repo, "checkout", "-q", "dev")
    write_json_chunk(phases / "P.json", [{**PHASE, "sibling_order": 2}])
    commit_file(repo, "roadmap/phases/P.json", (phases / "P.json").read_text(), "move the phase")
    git(repo, "push", "-q", "origin", "dev")
    git(repo, "checkout", "-q", "feature/rm-thing")

    result = _cli(repo, "finish-this-task")

    assert result.returncode == 0, result.stdout + result.stderr
    # The conflict really was in the ancestor's chunk alone.
    assert "roadmap/phases/P.json" in result.stdout
    phase = json.loads(git(bare, "show", "dev:roadmap/phases/P.json"))["nodes"][0]
    leaf = json.loads(git(bare, "show", "dev:roadmap/phases/M1.json"))["nodes"][0]
    assert (phase["status"], phase["sibling_order"], leaf["status"]) == ("Complete", 2, "Complete")
    _assert_generated_files_current(repo)


OTHER = {
    "id": "M1.2", "node_key": "33333333-3333-5333-8333-333333333333", "codename": "other",
    "title": "Other", "type": "task", "parent_id": None, "sibling_order": 2,
    "status": "Not Started", "dependencies": [], "touch_zones": ["docs"],
    "goal": "Do the other thing.", "acceptance": ["noted"],
    "planning_dir": "planning/M1.2_other_33333333-3333-5333-8333-333333333333.md",
}


def _nested_chunk_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    """Nested merge-mode repo whose chunk holds the finishing leaf and a sibling."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    git_top, project = make_layout_finish_repo(tmp_path, "nested")
    git(git_top, "checkout", "-q", "dev")
    chunk = project / "roadmap" / "phases" / "M1.json"
    write_json_chunk(chunk, [*load_json_chunk(chunk), json.loads(json.dumps(OTHER))])
    sheet = OTHER["planning_dir"]
    (project / sheet).write_text("# M1.2 Other\n\n## Intent\n\nThe other thing.\n", encoding="utf-8")
    git(git_top, "add", git_root_relative(git_top, project, "roadmap/phases/M1.json"),
        git_root_relative(git_top, project, sheet))
    git(git_top, "commit", "-qm", "add a sibling in the same chunk")
    git(git_top, "checkout", "-q", "feature/rm-thing")
    git(git_top, "merge", "-q", "--no-edit", "dev")
    return git_top, project, prepare_layout_merge_mode_remote(git_top, project, tmp_path)


def _diverge_chunk(git_top: Path, project: Path, case: str) -> None:
    """Integration edits the same chunk after the claim, then the feature branch is current."""
    chunk = project / "roadmap" / "phases" / "M1.json"
    nodes = json.loads(json.dumps(load_json_chunk(chunk)))
    if case == "removed":
        nodes = [n for n in nodes if n["id"] != "M1.1"]
    else:
        for node in nodes:
            if node["id"] == "M1.1":
                node["sibling_order"] = 4
            elif node["id"] == "M1.2" and case == "reapplied":
                node["touch_zones"] = ["docs", "notes"]
    git(git_top, "checkout", "-q", "dev")
    write_json_chunk(chunk, nodes)
    commit_file(
        git_top, git_root_relative(git_top, project, "roadmap/phases/M1.json"),
        chunk.read_text(encoding="utf-8"), "integration edits the same chunk",
    )
    git(git_top, "push", "-q", "origin", "dev")
    git(git_top, "checkout", "-q", "feature/rm-thing")


def _hide_claim_from_parent(git_top: Path, project: Path) -> None:
    """Commit the registry without the claim; the worktree still has the row, uncommitted."""
    rel = git_root_relative(git_top, project, "roadmap/registry.yaml")
    path = git_top / rel
    saved = path.read_text(encoding="utf-8")
    doc = yaml.safe_load(saved)
    doc["entries"] = [e for e in doc["entries"] if e.get("codename") != "thing"]
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    git(git_top, "add", rel)
    git(git_top, "commit", "-qm", "branch copy of the registry drops the claim")
    path.write_text(saved, encoding="utf-8")


@pytest.mark.parametrize("case", ["reapplied", "missing-row", "removed"])
def test_a_conflicted_chunk_keeps_the_leaf_complete_or_stops(
    tmp_path: Path, monkeypatch, case: str,
) -> None:
    """The integration side edits the finishing leaf's chunk after the claim.

    Nested project: sibling_order and another node's touch zones change, so the
    status line conflicts, and the landed chunk keeps Complete plus those
    integration fields. The same conflict with no registry row for the codename
    on the bookkeeping commit's parent stops before the merge commit. When that
    chunk no longer contains the leaf, the land keeps it absent and does not
    claim the status was applied.
    """
    git_top, project, bare = _nested_chunk_repo(tmp_path, monkeypatch)
    _diverge_chunk(git_top, project, case)
    dev_before = git(bare, "rev-parse", "dev")
    if case != "reapplied":
        _hide_claim_from_parent(git_top, project)
    result = _cli(project, "finish-this-task")
    if case == "missing-row":
        assert result.returncode != 0, result.stdout + result.stderr
        text = result.stdout + result.stderr
        assert "roadmap/phases/M1.json" in text and "thing" in text, text
        assert git(bare, "rev-parse", "dev") == dev_before
        return
    assert result.returncode == 0, result.stdout + result.stderr
    message = git(bare, "log", "-1", "--format=%B", "dev")
    nodes = json.loads(git(bare, "show", "dev:sr/roadmap/phases/M1.json"))["nodes"]
    if case == "removed":
        assert all(n.get("codename") != "thing" for n in nodes)
        assert "Complete status was applied again" not in message
        return
    leaf = next(n for n in nodes if n["id"] == "M1.1")
    other = next(n for n in nodes if n["id"] == "M1.2")
    assert (leaf["status"], leaf["sibling_order"], other["touch_zones"]) == (
        "Complete", 4, ["docs", "notes"],
    )
    assert "Complete status was applied again" in message
    _assert_generated_files_current(project)
