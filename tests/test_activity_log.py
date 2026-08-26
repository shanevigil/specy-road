"""Last-worked-on: the sidecar, its write points, and the git backfill.

Activity is display metadata. The design rule these tests protect is that
recording it must never be the reason a pickup, review, finish or edit fails.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road.activity_backfill import backfill_activity, last_commit_iso
from specy_road.activity_log import (
    KIND_BACKFILLED,
    KIND_EDITED,
    KIND_FINISHED,
    activity_by_node_key,
    activity_path,
    load_activity,
    record_activity,
    set_activity,
    empty_activity,
    write_activity,
)
from tests.helpers import DOGFOOD

KEY = "44ef4a9d-923f-545c-8187-eaabc7ca86ba"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def test_no_log_means_no_activity(repo: Path) -> None:
    assert activity_by_node_key(repo) == {}
    assert load_activity(repo) == empty_activity()


def test_recording_creates_the_sidecar(repo: Path) -> None:
    record_activity(repo, KEY, KIND_FINISHED, "2026-03-01T00:00:00+00:00")

    assert activity_path(repo).is_file()
    assert activity_by_node_key(repo)[KEY] == {
        "at": "2026-03-01T00:00:00+00:00",
        "kind": KIND_FINISHED,
    }


def test_the_later_timestamp_wins_whatever_the_write_order(repo: Path) -> None:
    """Backfills and live writes interleave; a stale write must not clobber."""
    record_activity(repo, KEY, KIND_FINISHED, "2026-03-01T00:00:00+00:00")
    record_activity(repo, KEY, KIND_BACKFILLED, "2020-01-01T00:00:00+00:00")

    entry = activity_by_node_key(repo)[KEY]
    assert entry["at"] == "2026-03-01T00:00:00+00:00"
    assert entry["kind"] == KIND_FINISHED


def test_a_newer_write_replaces_an_older_one(repo: Path) -> None:
    record_activity(repo, KEY, KIND_EDITED, "2026-03-01T00:00:00+00:00")
    record_activity(repo, KEY, KIND_FINISHED, "2026-05-01T00:00:00+00:00")

    assert activity_by_node_key(repo)[KEY]["kind"] == KIND_FINISHED


def test_recording_never_raises_on_a_mangled_log(repo: Path) -> None:
    """A cosmetic sidecar must not be able to fail `finish-this-task`."""
    activity_path(repo).write_text("{not json", encoding="utf-8")

    record_activity(repo, KEY, KIND_FINISHED)  # must not raise
    assert activity_by_node_key(repo)[KEY]["kind"] == KIND_FINISHED


def test_recording_never_raises_on_a_bad_key(repo: Path) -> None:
    record_activity(repo, None, KIND_FINISHED)
    record_activity(repo, "", KIND_FINISHED)
    assert activity_by_node_key(repo) == {}


def test_a_mangled_log_reads_as_empty_rather_than_exploding(repo: Path) -> None:
    activity_path(repo).write_text('{"version": 1, "nodes": "nope"}', encoding="utf-8")
    assert load_activity(repo) == empty_activity()


def test_writes_are_schema_validated(repo: Path) -> None:
    doc = set_activity(empty_activity(), KEY, "not-a-real-kind")
    with pytest.raises(ValueError, match="activity log invalid"):
        write_activity(repo, doc)


def test_the_log_is_canonical_json(repo: Path) -> None:
    """Stable ordering keeps the sidecar's diffs readable in review."""
    record_activity(repo, KEY, KIND_FINISHED, "2026-03-01T00:00:00+00:00")
    text = activity_path(repo).read_text(encoding="utf-8")

    assert text.endswith("\n")
    assert json.loads(text)["version"] == 1


# --- write points -----------------------------------------------------------


def test_edit_node_records_activity(repo: Path) -> None:
    from roadmap_crud_ops import edit_node_set_pairs

    edit_node_set_pairs(repo, "M0.2", [("status", "Blocked")])

    entry = activity_by_node_key(repo)["e7fcdb23-5d23-5bbf-a9b5-aaa0140ff208"]
    assert entry["kind"] == KIND_EDITED


# --- backfill ---------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    import os

    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_AUTHOR_DATE": "2024-06-01T12:00:00+00:00",
            "GIT_COMMITTER_DATE": "2024-06-01T12:00:00+00:00",
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


def test_backfill_dates_nodes_from_their_planning_sheets(committed: Path) -> None:
    out = backfill_activity(committed)

    assert out["candidates"] > 0
    entry = activity_by_node_key(committed)[KEY]
    assert entry["kind"] == KIND_BACKFILLED
    assert entry["at"].startswith("2024-06-01")


def test_backfill_dry_run_writes_nothing(committed: Path) -> None:
    out = backfill_activity(committed, dry_run=True)

    assert out["candidates"] > 0
    assert out["applied"] == 0
    assert not activity_path(committed).exists()


def test_backfill_does_not_overwrite_observed_activity(committed: Path) -> None:
    record_activity(committed, KEY, KIND_FINISHED, "2026-05-01T00:00:00+00:00")
    backfill_activity(committed)

    entry = activity_by_node_key(committed)[KEY]
    assert entry["kind"] == KIND_FINISHED
    assert entry["at"] == "2026-05-01T00:00:00+00:00"


def test_backfill_outside_a_git_repo_is_a_no_op(repo: Path) -> None:
    out = backfill_activity(repo)
    assert out["candidates"] == 0


def test_last_commit_iso_returns_none_for_an_untracked_path(committed: Path) -> None:
    assert last_commit_iso(committed, "planning/does-not-exist.md") is None
