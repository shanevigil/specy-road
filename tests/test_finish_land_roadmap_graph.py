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

from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from tests.helpers import script_subprocess_env
from tests.review_repo_helpers import NODE, commit_file, git
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
