"""The landed generated files must match a fresh render of the merged graph.

``roadmap.md`` and ``roadmap-context.md`` are generated and committed, and the
toolkit tells people to gate CI on ``export --check`` and ``digest --check``.
A landing merge that leaves either stale hands CI a failure the developer never
saw -- the v0.2.2 class of bug -- so these tests assert the post-merge tree is
exactly what a fresh render produces.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts.export_roadmap_md import export_markdown
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.finish_land_integration import land_merge_feature_into_integration
from specy_road.registry_yaml import registry_path, write_registry
from tests.helpers import DOGFOOD

CODENAME = "contracts-bootstrap"
BRANCH = f"feature/rm-{CODENAME}"


def _git(repo: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=repo)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)


def _chunk_path(repo: Path) -> Path:
    return repo / "roadmap" / "phases" / "M0.json"


def _set_dependencies(repo: Path, node_id: str, deps: list[str] | None) -> None:
    path = _chunk_path(repo)
    doc = json.loads(path.read_text(encoding="utf-8"))
    for node in doc["nodes"]:
        if node["id"] == node_id:
            if deps:
                node["dependencies"] = deps
            else:
                node.pop("dependencies", None)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _regenerate(repo: Path) -> None:
    """What the feature branch's bookkeeping commit does before landing."""
    (repo / "roadmap.md").write_text(
        export_markdown(load_roadmap(repo)["nodes"]), encoding="utf-8"
    )
    (repo / DEFAULT_OUTPUT).write_text(render_digest(repo), encoding="utf-8")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A dogfood-shaped repo on `master`, with a bare origin, one claim held."""
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    bare = tmp_path / "remote.git"
    subprocess.check_call(["git", "init", "--bare", "-q", str(bare)])
    subprocess.check_call(["git", "init", "-q", "-b", "master", str(dest)])
    _git(dest, "config", "user.email", "t@e.com")
    _git(dest, "config", "user.name", "T")
    _git(dest, "remote", "add", "origin", str(bare))
    write_registry(
        registry_path(dest),
        {
            "version": 1,
            "entries": [
                {
                    "codename": CODENAME,
                    "node_id": "M0.1",
                    "branch": BRANCH,
                    "started": "2026-09-01",
                }
            ],
        },
    )
    # An edge that exists on the integration branch, so removing it on the
    # feature branch produces a real dep_removed event in git history.
    _set_dependencies(dest, "M0.3", ["M0.1"])
    _regenerate(dest)
    _commit(dest, "init")
    _git(dest, "push", "-q", "-u", "origin", "master")
    return dest


def _finish_on_feature_branch(repo: Path) -> None:
    """The bookkeeping commit: drop the edge, deregister, regenerate."""
    _git(repo, "checkout", "-q", "-b", BRANCH)
    _set_dependencies(repo, "M0.3", None)
    write_registry(registry_path(repo), {"version": 1, "entries": []})
    _regenerate(repo)
    _commit(repo, f"chore(rm-{CODENAME}): complete, deregister")


def test_the_landed_generated_files_match_a_fresh_render(repo: Path) -> None:
    """i.e. `export --check` and `digest --check` pass on the integration branch.

    The digest's "Dependencies that were removed" section comes from a
    ``--first-parent`` walk of HEAD, so it is only computable once the merge
    commit exists. Rendering it before that point lands a digest missing the
    line and reintroduces CI drift.
    """
    _finish_on_feature_branch(repo)
    ok, err = land_merge_feature_into_integration(
        repo, remote="origin", integration_branch="master", feature_branch=BRANCH
    )
    assert ok, err
    _git(repo, "checkout", "-q", "master")

    assert (repo / DEFAULT_OUTPUT).read_text(encoding="utf-8") == render_digest(repo)
    assert (repo / "roadmap.md").read_text(encoding="utf-8") == export_markdown(
        load_roadmap(repo)["nodes"]
    )


def test_the_dropped_dependency_is_recorded_after_landing(repo: Path) -> None:
    """The merge commit makes the feature branch's history reachable."""
    _finish_on_feature_branch(repo)
    ok, err = land_merge_feature_into_integration(
        repo, remote="origin", integration_branch="master", feature_branch=BRANCH
    )
    assert ok, err
    _git(repo, "checkout", "-q", "master")
    assert "Dependencies that were removed" in (
        repo / DEFAULT_OUTPUT
    ).read_text(encoding="utf-8")


def test_a_stale_generated_file_on_the_feature_branch_is_overwritten(
    repo: Path,
) -> None:
    _git(repo, "checkout", "-q", "-b", BRANCH)
    write_registry(registry_path(repo), {"version": 1, "entries": []})
    (repo / "roadmap.md").write_text("STALE\n", encoding="utf-8")
    (repo / DEFAULT_OUTPUT).write_text("STALE\n", encoding="utf-8")
    _commit(repo, f"chore(rm-{CODENAME}): complete, deregister")

    ok, err = land_merge_feature_into_integration(
        repo, remote="origin", integration_branch="master", feature_branch=BRANCH
    )
    assert ok, err
    _git(repo, "checkout", "-q", "master")
    assert "STALE" not in (repo / "roadmap.md").read_text(encoding="utf-8")
    assert "STALE" not in (repo / DEFAULT_OUTPUT).read_text(encoding="utf-8")
