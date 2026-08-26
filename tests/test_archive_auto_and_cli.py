"""Auto-archive age threshold, the milestone lock, and the CLI surface."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.archive_ops import archive_node, auto_archive_candidates
from specy_road.archive_plan import plan_archive
from tests.helpers import REPO, DOGFOOD, script_subprocess_env


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _patch_node(repo: Path, chunk: str, node_id: str, **fields) -> None:
    p = repo / "roadmap" / "phases" / chunk
    doc = json.loads(p.read_text(encoding="utf-8"))
    for n in doc["nodes"]:
        if n["id"] == node_id:
            n.update(fields)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _closed_milestone(repo: Path, closed_at: str) -> None:
    """Give M0.1 a closed rollup so it carries a completion timestamp."""
    _patch_node(
        repo,
        "M0.json",
        "M0.1",
        milestone_execution={
            "state": "closed",
            "rollup_branch": "rollup/M0.1",
            "integration_branch": "main",
            "remote": "origin",
            "closed_at": closed_at,
        },
    )


def _cli(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(repo)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
        check=False,
    )


def test_auto_skips_work_completed_inside_the_window(repo: Path) -> None:
    _closed_milestone(repo, "2026-08-20T00:00:00+00:00")
    found = auto_archive_candidates(
        repo, older_than_days=90, now_iso="2026-08-26T00:00:00+00:00"
    )
    assert found == []


def test_auto_picks_up_work_past_the_threshold(repo: Path) -> None:
    _closed_milestone(repo, "2026-01-01T00:00:00+00:00")
    found = auto_archive_candidates(
        repo, older_than_days=90, now_iso="2026-08-26T00:00:00+00:00"
    )
    assert found == [("M0.1", "2026-01-01T00:00:00+00:00")]


def test_auto_ignores_incomplete_subtrees_whatever_their_age(repo: Path) -> None:
    """M0.2 is Not Started; a stale timestamp must not drag it into the archive."""
    _patch_node(
        repo,
        "M1.json",
        "M0.2",
        milestone_execution={
            "state": "closed",
            "rollup_branch": "rollup/M0.2",
            "integration_branch": "main",
            "remote": "origin",
            "closed_at": "2020-01-01T00:00:00+00:00",
        },
    )
    found = auto_archive_candidates(
        repo, older_than_days=1, now_iso="2026-08-26T00:00:00+00:00"
    )
    assert found == []


def test_auto_offers_only_the_top_of_a_nested_chain(repo: Path) -> None:
    """Archiving a phase takes its milestones with it.

    Offering both the phase and its child would double-count the work and then
    fail on the second archive, whose nodes are already gone.
    """
    _patch_node(repo, "M1.json", "M0.2", status="Complete")
    stamp = {
        "state": "closed",
        "rollup_branch": "rollup/x",
        "integration_branch": "main",
        "remote": "origin",
        "closed_at": "2026-01-01T00:00:00+00:00",
    }
    _patch_node(repo, "M0.json", "M0", milestone_execution=stamp)
    _patch_node(repo, "M0.json", "M0.1", milestone_execution=stamp)

    found = auto_archive_candidates(
        repo, older_than_days=30, now_iso="2026-08-26T00:00:00+00:00"
    )
    assert [nid for nid, _ in found] == ["M0"]


def test_auto_skips_what_is_already_archived(repo: Path) -> None:
    _closed_milestone(repo, "2026-01-01T00:00:00+00:00")
    archive_node(repo, "M0.1")
    found = auto_archive_candidates(
        repo, older_than_days=30, now_iso="2026-08-26T00:00:00+00:00"
    )
    assert found == []


def test_an_active_milestone_rollup_blocks_archiving(repo: Path) -> None:
    """Moving files out from under an in-flight rollup would strand its branch."""
    _patch_node(
        repo,
        "M0.json",
        "M0",
        milestone_execution={
            "state": "active",
            "rollup_branch": "rollup/M0",
            "integration_branch": "main",
            "remote": "origin",
        },
    )
    with pytest.raises(ValueError, match="milestone"):
        plan_archive(repo, "M0.1", force=True)


def test_cli_archive_dry_run_writes_nothing(repo: Path) -> None:
    r = _cli(repo, "archive", "M0.1", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "dry run" in r.stdout
    assert not (repo / "roadmap" / "archive").exists()


def test_cli_archive_list_show_restore_round_trip(repo: Path) -> None:
    assert _cli(repo, "archive", "M0.1").returncode == 0

    listed = _cli(repo, "list-archives")
    assert listed.returncode == 0
    assert "M0.1" in listed.stdout

    archive_id = json.loads(_cli(repo, "list-archives", "--json").stdout)["records"][0][
        "archive_id"
    ]
    shown = _cli(repo, "show-archive", archive_id)
    assert shown.returncode == 0
    assert "Establish shared contracts" in shown.stdout

    restored = _cli(repo, "restore-archive", archive_id)
    assert restored.returncode == 0, restored.stderr
    assert json.loads(_cli(repo, "list-archives", "--json").stdout)["records"] == []


def test_cli_reexports_roadmap_md(repo: Path) -> None:
    """A stale roadmap.md would fail `export --check` in the adopter's CI."""
    assert _cli(repo, "archive", "M0.1").returncode == 0
    assert _cli(repo, "export", "--check").returncode == 0


def test_cli_reports_an_unknown_archive_id(repo: Path) -> None:
    r = _cli(repo, "show-archive", "nope-00000000-20260101")
    assert r.returncode == 1
    assert "no archive with id" in r.stderr
