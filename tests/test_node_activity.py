"""Last-worked-on is derived from git history, never recorded.

The design rule these tests protect: no file is written, so the feature has no
cold start on an existing repo and cannot dirty the working tree. The toolkit
asserts a clean tree in six places (do-next-available-task and
abort-task-pickup among them), so a sidecar written mid-flow would break the
grind loop — that is the regression this replaced.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road.node_activity import (
    SOURCE_CHUNK,
    SOURCE_PLANNING,
    clear_cache,
    compute_node_activity,
    last_commit_dates,
    node_activity,
)
from tests.helpers import DOGFOOD

M01_KEY = "44ef4a9d-923f-545c-8187-eaabc7ca86ba"


@pytest.fixture(autouse=True)
def _isolate_cache() -> None:
    clear_cache()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _git(repo: Path, *args: str, date: str = "2024-06-01T12:00:00+00:00") -> str:
    import os

    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
        }
    )
    r = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=env
    )
    return r.stdout.strip()


@pytest.fixture()
def committed(repo: Path) -> Path:
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "roadmap")
    return repo


def _nodes(root: Path) -> list[dict]:
    from roadmap_load import load_roadmap

    return load_roadmap(root)["nodes"]


# --- the point of the redesign ----------------------------------------------


def test_it_writes_nothing_at_all(committed: Path) -> None:
    """No sidecar means no cold start and no dirty working tree."""
    before = _git(committed, "status", "--porcelain")
    activity = node_activity(committed, _nodes(committed))

    assert activity  # it did produce answers
    assert _git(committed, "status", "--porcelain") == before == ""
    assert not (committed / "roadmap" / "activity.json").exists()


def test_an_untouched_existing_repo_is_populated_immediately(
    committed: Path,
) -> None:
    """The whole reason for deriving: nothing to seed, no command to run."""
    activity = node_activity(committed, _nodes(committed))

    keys = {n["node_key"] for n in _nodes(committed)}
    assert keys and keys <= set(activity)
    assert activity[M01_KEY]["at"].startswith("2024-06-01")


# --- derivation rules --------------------------------------------------------


def test_the_planning_sheet_is_the_primary_signal(committed: Path) -> None:
    activity = node_activity(committed, _nodes(committed))
    assert activity[M01_KEY]["source"] == SOURCE_PLANNING


def test_it_reports_the_most_recent_touch(committed: Path) -> None:
    nodes = _nodes(committed)
    sheet = committed / next(
        n["planning_dir"] for n in nodes if n["node_key"] == M01_KEY
    )
    first = node_activity(committed, nodes)[M01_KEY]["at"]

    sheet.write_text(sheet.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
    _git(committed, "add", "-A", date="2025-09-09T00:00:00+00:00")
    _git(committed, "commit", "-q", "-m", "edit", date="2025-09-09T00:00:00+00:00")
    clear_cache()

    latest = node_activity(committed, nodes)[M01_KEY]["at"]
    assert latest.startswith("2025-09-09")
    assert latest != first


def test_a_sibling_edit_does_not_make_a_node_look_freshly_worked(
    committed: Path,
) -> None:
    """Chunk dates are a fallback only.

    A chunk holds many nodes. Blending its date into every node would mean one
    node's status change made all its siblings look worked, destroying exactly
    the staleness signal the column exists to give.
    """
    nodes = _nodes(committed)
    before = node_activity(committed, nodes)[M01_KEY]["at"]

    # Change a DIFFERENT node in the same chunk as M0.1.
    chunk = committed / "roadmap" / "phases" / "M0.json"
    doc = json.loads(chunk.read_text(encoding="utf-8"))
    sibling = next(n for n in doc["nodes"] if n["node_key"] != M01_KEY)
    sibling["notes"] = "touched by a sibling edit"
    chunk.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _git(committed, "add", "-A", date="2025-12-12T00:00:00+00:00")
    _git(committed, "commit", "-q", "-m", "sibling", date="2025-12-12T00:00:00+00:00")
    clear_cache()

    assert node_activity(committed, nodes)[M01_KEY]["at"] == before


def test_a_node_whose_sheet_was_never_committed_falls_back_to_its_chunk(
    repo: Path,
) -> None:
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "roadmap")
    _git(repo, "commit", "-q", "-m", "chunks only")
    clear_cache()

    activity = node_activity(repo, _nodes(repo))
    assert activity[M01_KEY]["source"] == SOURCE_CHUNK


def test_a_merge_carrying_someone_elses_edit_is_not_a_touch(
    committed: Path,
) -> None:
    """Otherwise every node looks freshly worked after an integration merge."""
    nodes = _nodes(committed)
    sheet = committed / next(
        n["planning_dir"] for n in nodes if n["node_key"] == M01_KEY
    )

    _git(committed, "checkout", "-q", "-b", "side")
    sheet.write_text(sheet.read_text(encoding="utf-8") + "\nside\n", encoding="utf-8")
    _git(committed, "add", "-A", date="2025-03-01T00:00:00+00:00")
    _git(committed, "commit", "-q", "-m", "side", date="2025-03-01T00:00:00+00:00")
    _git(committed, "checkout", "-q", "main")
    _git(
        committed,
        "merge",
        "-q",
        "--no-ff",
        "--no-edit",
        "-m",
        "merge side",
        "side",
        date="2026-08-08T00:00:00+00:00",
    )
    clear_cache()

    # The real edit counts; the merge that carried it does not add a later touch.
    assert node_activity(committed, nodes)[M01_KEY]["at"].startswith("2025-03-01")


# --- robustness --------------------------------------------------------------


def test_outside_a_git_repo_it_is_empty_not_an_error(repo: Path) -> None:
    assert node_activity(repo, _nodes(repo)) == {}


def test_no_scopes_means_no_git_call(committed: Path) -> None:
    assert last_commit_dates(committed, []) == {}


def test_the_batched_walk_agrees_with_per_path_lookups(committed: Path) -> None:
    """One walk replaces one lookup per node; it must not change an answer.

    Per-path lookups are linear in node count: ~31s on a 400-node roadmap
    against ~0.17s batched, which is what makes deriving on demand viable.
    """
    dates = last_commit_dates(committed, ["planning"])
    assert dates
    for rel, when in dates.items():
        expected = _git(committed, "log", "-1", "--format=%aI", "--", rel)
        assert when == expected, rel


# --- caching -----------------------------------------------------------------


def test_results_are_memoized_until_head_moves(
    committed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeat GUI polls must not re-walk history on every request."""
    nodes = _nodes(committed)
    node_activity(committed, nodes)

    calls: list[int] = []
    real = compute_node_activity
    monkeypatch.setattr(
        "specy_road.node_activity.compute_node_activity",
        lambda r, n: (calls.append(1), real(r, n))[1],
    )
    node_activity(committed, nodes)
    assert calls == []  # served from cache

    (committed / "planning" / "README.md").write_text("x\n", encoding="utf-8")
    _git(committed, "add", "-A", date="2026-01-01T00:00:00+00:00")
    _git(committed, "commit", "-q", "-m", "move head", date="2026-01-01T00:00:00+00:00")

    node_activity(committed, nodes)
    assert calls == [1]  # HEAD moved, so it recomputed
