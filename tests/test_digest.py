"""The current-state digest.

The digest exists to be believed — an agent reads it instead of crawling the
corpus — so the properties that matter are that it reports the *current* graph,
that it never invents a section it has no data for, and that `--check` catches
drift the way `export --check` does.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.history_index import clear_memo
from tests.test_history_walk import commit, edit_node, git, repo

__all__ = ["repo"]  # re-exported fixture


@pytest.fixture(autouse=True)
def _no_memo() -> None:
    clear_memo()


def run_cli(argv: list[str], root: Path) -> int:
    from specy_road.bundled_scripts.digest_cli import main

    with pytest.raises(SystemExit) as exit_info:
        main([*argv, "--repo-root", str(root)])
    return int(exit_info.value.code or 0)


def headings(text: str) -> list[str]:
    return [ln[3:] for ln in text.splitlines() if ln.startswith("## ")]


# --- content ----------------------------------------------------------------


def test_every_live_node_appears_with_its_rollup_status(repo: Path) -> None:
    text = render_digest(repo)

    for node_id in ("M0", "M0.1", "M0.2", "M0.3", "M1", "M2"):
        assert f"`{node_id}`" in text
    # M0.1 is Complete in the fixture; M0 rolls up as not complete.
    assert "`M0.1` Establish shared contracts and ADR skeleton" in text
    assert "**Complete**" in text


def test_the_outline_is_indented_by_depth(repo: Path) -> None:
    lines = [ln for ln in render_digest(repo).splitlines() if "`M0.1`" in ln]
    assert lines and lines[0].startswith("  - ")


def test_a_decided_node_is_reported_with_its_date_and_adr(repo: Path) -> None:
    edit_node(
        repo,
        "M0.2",
        decision={
            "status": "decided",
            "decided_date": "2026-03-01",
            "adr_ref": "docs/adr/0002-ci.md",
        },
    )

    text = render_digest(repo)

    assert "Decisions" in headings(text)
    assert "**Decided** 2026-03-01: `M0.2" in text
    assert "docs/adr/0002-ci.md" in text


def test_a_pending_decision_is_flagged_separately(repo: Path) -> None:
    edit_node(repo, "M0.2", decision={"status": "pending"})
    assert "**Pending**: `M0.2" in render_digest(repo)


def test_open_gates_are_listed_and_complete_ones_are_not(repo: Path) -> None:
    edit_node(repo, "M2", type="gate", status="Not Started")
    text = render_digest(repo)
    assert "Open gates" in headings(text)
    assert "`M2 testing`" in text.replace("  ", " ")

    edit_node(repo, "M2", type="gate", status="Complete")
    assert "Open gates" not in headings(render_digest(repo))


def test_removed_dependencies_are_reported_from_git_history(repo: Path) -> None:
    """The anti-rework signal: invisible in the current graph by definition."""
    m03_key = "cd44fef1-715a-5b8d-b03f-1752a61a47cc"
    edit_node(repo, "M0.2", dependencies=[])
    commit(repo, "M0.2 no longer depends on M0.3")
    clear_memo()

    text = render_digest(repo)

    assert "Dependencies that were removed" in headings(text)
    assert "`M0.2` stopped depending on `M0.3" in text
    assert m03_key not in text  # resolved to a readable label, not a raw key


def test_archived_work_is_reported_with_the_command_to_reach_it(repo: Path) -> None:
    from specy_road.archive_ops import archive_node

    record = archive_node(repo, "M0.1")  # already Complete in the fixture

    text = render_digest(repo)

    assert "Archived (not in the live roadmap)" in headings(text)
    assert f"specy-road show-archive {record['archive_id']}" in text
    assert "--scope archived" in text
    # and it is gone from the live outline
    assert "`M0.1` Establish" not in text


def test_active_claims_are_listed(repo: Path) -> None:
    (repo / "roadmap" / "registry.yaml").write_text(
        "version: 1\n"
        "entries:\n"
        "  - codename: roadmap-ci\n"
        "    node_id: M0.2\n"
        "    branch: feature/rm-roadmap-ci\n"
        "    started: 2026-05-04\n",
        encoding="utf-8",
    )

    text = render_digest(repo)

    assert "Claimed and in flight" in headings(text)
    assert "`M0.2` on `feature/rm-roadmap-ci` since 2026-05-04" in text


def test_sections_with_no_data_are_omitted_entirely(repo: Path) -> None:
    """A digest full of empty headings would waste the context it exists to save."""
    present = headings(render_digest(repo))

    assert "Live roadmap" in present
    assert "Decisions" not in present
    assert "Archived (not in the live roadmap)" not in present
    assert "Claimed and in flight" not in present


def test_it_always_points_at_search_for_the_detail(repo: Path) -> None:
    assert "specy-road search" in render_digest(repo)


# --- determinism and drift --------------------------------------------------


def test_two_renders_are_byte_identical(repo: Path) -> None:
    """--check is only meaningful if rendering is deterministic."""
    clear_memo()
    assert render_digest(repo) == render_digest(repo)


def test_it_carries_no_wall_clock_value(repo: Path) -> None:
    import datetime

    today = datetime.date.today().isoformat()
    text = render_digest(repo)
    # The fixture's commits are dated by git, not by now; nothing should stamp today.
    assert f"Generated {today}" not in text


def test_a_repo_without_git_still_renders(tmp_path: Path) -> None:
    from tests.helpers import DOGFOOD

    dest = tmp_path / "nogit"
    shutil.copytree(DOGFOOD, dest)

    text = render_digest(dest)

    assert "Live roadmap" in headings(text)
    assert "Dependencies that were removed" not in headings(text)


def test_a_corrupt_archive_ledger_does_not_break_the_digest(repo: Path) -> None:
    archive = repo / "roadmap" / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "index.json").write_text("{ not json", encoding="utf-8")

    assert "Live roadmap" in headings(render_digest(repo))


# --- CLI --------------------------------------------------------------------


def test_cli_writes_the_default_file(repo: Path, capsys) -> None:
    assert run_cli(["digest"], repo) == 0
    out = repo / DEFAULT_OUTPUT

    assert out.is_file()
    assert out.read_text(encoding="utf-8") == render_digest(repo)
    assert "Wrote" in capsys.readouterr().out


def test_cli_stdout_mode_writes_no_file(repo: Path, capsys) -> None:
    assert run_cli(["digest", "-o", "-"], repo) == 0

    assert not (repo / DEFAULT_OUTPUT).exists()
    assert "# Roadmap context" in capsys.readouterr().out


def test_check_passes_on_a_fresh_digest(repo: Path, capsys) -> None:
    run_cli(["digest"], repo)
    capsys.readouterr()

    assert run_cli(["digest", "--check"], repo) == 0
    assert "matches the roadmap" in capsys.readouterr().out


def test_check_fails_once_the_roadmap_moves(repo: Path, capsys) -> None:
    run_cli(["digest"], repo)
    edit_node(repo, "M0.2", status="In Progress")
    capsys.readouterr()

    assert run_cli(["digest", "--check"], repo) == 1
    assert "drift" in capsys.readouterr().err


def test_check_reports_a_missing_file_rather_than_writing_one(
    repo: Path, capsys
) -> None:
    assert run_cli(["digest", "--check"], repo) == 1
    assert not (repo / DEFAULT_OUTPUT).exists()
    assert "missing" in capsys.readouterr().err
