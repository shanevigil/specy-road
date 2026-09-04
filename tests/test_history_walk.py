"""Replaying a real git history into roadmap events.

Builds an actual repository commit by commit so the walk is exercised against
git's real output, not a fixture of it. The cases that matter are the ones a
hand-rolled parser gets wrong: a renumbered node keeping one story, a merged
branch arriving as one step, and archiving reading as "archived" rather than
"deleted".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road.history_events import (
    ARCHIVED,
    CREATED,
    DEP_ADDED,
    DEP_REMOVED,
    REMOVED,
    RENUMBERED,
    SHEET_EDIT,
    STATUS,
)
from specy_road.history_walk import walk
from tests.helpers import DOGFOOD

_ENV = {
    "GIT_AUTHOR_NAME": "pat",
    "GIT_AUTHOR_EMAIL": "pat@example.com",
    "GIT_COMMITTER_NAME": "pat",
    "GIT_COMMITTER_EMAIL": "pat@example.com",
}

# Fixture identities. M0.1 and M0.3 start Complete; M2 and M0.2 start Not
# Started. M0.2 lives in M1.json, not M0.json — which is why edit_node has
# to find a node rather than assume a chunk.
M01_KEY = "44ef4a9d-923f-545c-8187-eaabc7ca86ba"
M02_KEY = "e7fcdb23-5d23-5bbf-a9b5-aaa0140ff208"
M2_KEY = "4c1d98f2-2bdc-4a7d-81b9-c6f7e96e95f0"
M03_KEY = "cd44fef1-715a-5b8d-b03f-1752a61a47cc"


def git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update(_ENV)
    r = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=env
    )
    return r.stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """The dogfood fixture as a real git repo with one baseline commit."""
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    git(dest, "init", "-q", "-b", "main")
    commit(dest, "baseline roadmap")
    return dest


def write_chunk(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def edit_node(repo: Path, node_id: str, **fields: object) -> None:
    """Update a node wherever it lives — the fixture spreads them over chunks."""
    for path in sorted((repo / "roadmap" / "phases").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if any(n["id"] == node_id for n in doc["nodes"]):
            for node in doc["nodes"]:
                if node["id"] == node_id:
                    node.update(fields)
            write_chunk(path, doc)
            return
    raise AssertionError(f"no node {node_id} in the fixture")


def kinds_for(events: list[dict], key: str) -> set[str]:
    return {e["kind"] for e in events if e["node_key"] == key}


def at_head(repo: Path, events: list[dict]) -> list[dict]:
    """Events from the newest commit only, ignoring the baseline import."""
    head = git(repo, "rev-parse", "HEAD")
    return [e for e in events if e["commit"] == head]


def test_the_baseline_commit_creates_every_node(repo: Path) -> None:
    events, last = walk(repo)

    created = [e for e in events if e["kind"] == CREATED]
    assert {e["id"] for e in created} == {"M0", "M0.1", "M0.2", "M0.3", "M1", "M2"}
    assert last == git(repo, "rev-parse", "HEAD")
    assert all(e["author"] == "pat" for e in created)
    assert all(e["at"] for e in created)


def test_a_status_change_is_one_event_on_the_changed_node(repo: Path) -> None:
    edit_node(repo, "M2", status="In Progress")
    sha = commit(repo, "start M2")

    changes = [e for e in walk(repo)[0] if e["kind"] == STATUS]

    assert len(changes) == 1
    assert changes[0]["node_key"] == M2_KEY
    assert (changes[0]["from"], changes[0]["to"]) == ("Not Started", "In Progress")
    assert changes[0]["commit"] == sha


def test_renumbering_keeps_one_continuous_story(repo: Path) -> None:
    """The node_key survives, so this is a rename and not a death plus a birth."""
    edit_node(repo, "M0.1", id="M0.9")
    commit(repo, "renumber M0.1 -> M0.9")

    events, _ = walk(repo)

    assert kinds_for(events, M01_KEY) == {CREATED, SHEET_EDIT, RENUMBERED}
    assert REMOVED not in kinds_for(events, M01_KEY)
    renumber = [e for e in events if e["kind"] == RENUMBERED][0]
    assert (renumber["from"], renumber["to"]) == ("M0.1", "M0.9")


def test_a_dependency_added_later_is_its_own_event(repo: Path) -> None:
    """M0.2 lives in M1.json — the walk must merge every include, not one chunk."""
    edit_node(repo, "M0.2", dependencies=[M03_KEY, M01_KEY])  # M0.3 was already there
    commit(repo, "M0.2 now also depends on M0.1")

    events = at_head(repo, walk(repo)[0])

    added = [e for e in events if e["kind"] == DEP_ADDED]
    assert [e["to"] for e in added] == [M01_KEY]
    assert added[0]["node_key"] == M02_KEY and added[0]["id"] == "M0.2"
    assert [e for e in events if e["kind"] == DEP_REMOVED] == []


def test_a_planning_sheet_edit_is_attributed_from_its_filename(repo: Path) -> None:
    """No blob is read for this — the node_key is in the path."""
    sheet = next((repo / "planning").glob(f"M0.1_*_{M01_KEY}.md"))
    sheet.write_text(sheet.read_text(encoding="utf-8") + "\nrevised\n", encoding="utf-8")
    commit(repo, "revise the M0.1 sheet")

    edits = [e for e in at_head(repo, walk(repo)[0]) if e["kind"] == SHEET_EDIT]

    assert len(edits) == 1
    assert edits[0]["node_key"] == M01_KEY
    assert edits[0]["id"] == "M0.1"


def test_archiving_reads_as_archived_not_as_deleted(repo: Path) -> None:
    from specy_road.archive_ops import archive_node

    archive_node(repo, "M0.1")  # already Complete in the fixture
    commit(repo, "archive M0.1")

    events, _ = walk(repo)
    trail = kinds_for(events, M01_KEY)

    assert ARCHIVED in trail
    assert REMOVED not in trail
    archived = [e for e in events if e["kind"] == ARCHIVED][0]
    assert archived["root_node_id"] == "M0.1"
    assert archived["archive_id"].startswith("M0.1-")


def test_archive_then_restore_leaves_no_phantom_creation(repo: Path) -> None:
    from specy_road.archive_ops import archive_node
    from specy_road.archive_restore import restore_archive

    record = archive_node(repo, "M0.1")
    commit(repo, "archive M0.1")
    restore_archive(repo, record["archive_id"])
    commit(repo, "restore M0.1")

    events = walk(repo)[0]
    creations = [e for e in events if e["kind"] == CREATED and e["node_key"] == M01_KEY]

    assert len(creations) == 1  # only the original import
    assert REMOVED not in kinds_for(events, M01_KEY)


def test_a_hard_delete_is_still_reported_as_removed(repo: Path) -> None:
    """Reconciliation must not swallow genuine deletions."""
    path = repo / "roadmap" / "phases" / "M0.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["nodes"] = [n for n in doc["nodes"] if n["id"] != "M0.3"]
    write_chunk(path, doc)
    commit(repo, "drop M0.3 outright")

    removed = [e for e in walk(repo)[0] if e["kind"] == REMOVED]

    assert [e["id"] for e in removed] == ["M0.3"]


def test_a_merged_branch_arrives_as_one_mainline_step(repo: Path) -> None:
    """--first-parent: no interleaving, no flip-flop events."""
    git(repo, "checkout", "-q", "-b", "feature/rm-x")
    edit_node(repo, "M2", status="In Progress")
    commit(repo, "wip")
    edit_node(repo, "M2", status="Complete")
    commit(repo, "done")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "feature/rm-x", "-m", "merge feature")

    changes = [e for e in walk(repo)[0] if e["kind"] == STATUS]

    # The intermediate "In Progress" never existed on main, so it is not history
    # main can tell. One step: Not Started -> Complete.
    assert len(changes) == 1
    assert (changes[0]["from"], changes[0]["to"]) == ("Not Started", "Complete")


def test_incremental_walk_matches_a_full_walk(repo: Path) -> None:
    """Seeding from ls-tree at `since` must reproduce the same later events."""
    baseline = git(repo, "rev-parse", "HEAD")
    edit_node(repo, "M0.1", status="In Progress")
    commit(repo, "start M0.1")
    edit_node(repo, "M0.2", dependencies=[M01_KEY])
    commit(repo, "link M0.2")

    full, full_last = walk(repo)
    partial, partial_last = walk(repo, since=baseline)

    baseline_commits = {e["commit"] for e in full if e["kind"] == CREATED}
    assert partial == [e for e in full if e["commit"] not in baseline_commits]
    assert partial_last == full_last


def test_a_directory_that_is_not_a_repo_yields_nothing(tmp_path: Path) -> None:
    events, last = walk(tmp_path)
    assert events == [] and last is None
