"""Public scenarios for archive --auto, restore errors, scaffold and update.

Archive goes through ``archive_cli.main``. Scaffold goes through
``scaffold_planning.main`` (it reads ``sys.argv``). Update goes through
``update_specy_road.main``, which is where the fast-forward and the dirty-tree
refusal run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.archive_index import load_archive_index
from specy_road.bundled_scripts import archive_cli, scaffold_planning, update_specy_road
from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from tests.move_node_helpers import NK_B1, base_fixture


def _close_leaf(root: Path, node_id: str, closed_at: str) -> None:
    """Mark one leaf Complete with a rollup timestamp old enough for --auto."""
    chunk = root / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    for item in nodes:
        if item["id"] == node_id:
            item["status"] = "Complete"
            item["milestone_execution"] = {
                "state": "closed",
                "rollup_branch": f"rollup/{node_id}",
                "integration_branch": "main",
                "remote": "origin",
                "closed_at": closed_at,
            }
    write_json_chunk(chunk, nodes)


def _exit(main, argv: list[str]) -> int:
    try:
        main(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    return 0


def _archive(root: Path, *args: str) -> int:
    return _exit(archive_cli.main, [*args, "--repo-root", str(root)])


def _live_ids(root: Path) -> set[str]:
    return {node["id"] for node in load_roadmap(root)["nodes"]}


def test_archive_auto_with_nothing_old_enough_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base_fixture(tmp_path)

    code = _archive(tmp_path, "archive", "--auto", "--older-than-days", "1")

    assert code == 0
    assert "nothing to archive" in capsys.readouterr().out
    assert not (tmp_path / "roadmap" / "archive").exists()
    assert "M2.1" in _live_ids(tmp_path)


def test_archive_auto_archives_a_leaf_complete_past_the_threshold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base_fixture(tmp_path)
    _close_leaf(tmp_path, "M2.1", "2020-01-01T00:00:00+00:00")

    code = _archive(tmp_path, "archive", "--auto", "--older-than-days", "1")

    out = capsys.readouterr().out
    assert code == 0, out
    assert "archived M2.1" in out
    assert "M2.1" not in _live_ids(tmp_path)
    records = load_archive_index(tmp_path)["records"]
    assert len(records) == 1
    assert records[0]["root_node_id"] == "M2.1"
    assert NK_B1 in records[0]["node_keys"]


def test_restore_of_an_unknown_id_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base_fixture(tmp_path)
    before = _live_ids(tmp_path)

    code = _archive(tmp_path, "restore-archive", "no-such-archive")

    err = capsys.readouterr().err
    assert code == 1
    assert "no archive with id" in err
    assert "list-archives" in err
    assert _live_ids(tmp_path) == before


def test_restore_dry_run_of_an_unknown_id_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base_fixture(tmp_path)

    code = _archive(tmp_path, "restore-archive", "no-such-archive", "--dry-run")

    err = capsys.readouterr().err
    assert code == 1
    assert "no archive with id" in err
    assert "list-archives" not in err


def test_restore_of_a_record_whose_chunk_is_missing_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base_fixture(tmp_path)
    _close_leaf(tmp_path, "M2.1", "2020-01-01T00:00:00+00:00")
    assert _archive(tmp_path, "archive", "--auto", "--older-than-days", "1") == 0
    capsys.readouterr()
    record = load_archive_index(tmp_path)["records"][0]
    (tmp_path / record["chunk"]).unlink()
    live = _live_ids(tmp_path)

    code = _archive(tmp_path, "restore-archive", record["archive_id"])

    err = capsys.readouterr().err
    assert code == 1
    assert "missing" in err
    assert _live_ids(tmp_path) == live
    assert load_archive_index(tmp_path)["records"][0]["archive_id"] == record["archive_id"]


def _scaffold(root: Path, *args: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``scaffold-planning``'s ``main`` reads ``sys.argv``; there is no ``argv`` parameter."""
    monkeypatch.setattr(sys, "argv", ["scaffold-planning", *args, "--repo-root", str(root)])
    scaffold_planning.main()


def test_scaffold_planning_writes_a_missing_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_fixture(tmp_path)
    sheet = tmp_path / "planning" / f"M2.1_beta-work_{NK_B1}.md"
    sheet.unlink()

    _scaffold(tmp_path, "M2.1", monkeypatch=monkeypatch)

    assert sheet.is_file()
    text = sheet.read_text(encoding="utf-8")
    assert "M2.1" not in text
    node = next(item for item in load_roadmap(tmp_path)["nodes"] if item["node_key"] == NK_B1)
    assert node["planning_dir"] == f"planning/M2.1_beta-work_{NK_B1}.md"


def test_scaffold_planning_force_overwrites_an_existing_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_fixture(tmp_path)
    sheet = tmp_path / "planning" / f"M2.1_beta-work_{NK_B1}.md"
    sheet.write_text("KEEP\n", encoding="utf-8")

    _scaffold(tmp_path, "M2.1", monkeypatch=monkeypatch)
    assert sheet.read_text(encoding="utf-8") == "KEEP\n"

    _scaffold(tmp_path, "M2.1", "--force", monkeypatch=monkeypatch)

    assert "KEEP" not in sheet.read_text(encoding="utf-8")
    assert "Intent" in sheet.read_text(encoding="utf-8")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def clone_behind_origin(tmp_path: Path) -> Path:
    """A clone whose ``main`` is one commit behind a local bare ``origin``."""
    bare = tmp_path / "upstream.git"
    _git(tmp_path, "init", "--bare", str(bare))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(bare), str(seed))
    (seed / "README.md").write_text("v1\n", encoding="utf-8")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-m", "v1")
    _git(seed, "branch", "-M", "main")
    _git(seed, "push", "-u", "origin", "main")
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(bare), str(work))
    (seed / "README.md").write_text("v2\n", encoding="utf-8")
    _git(seed, "commit", "-am", "v2")
    _git(seed, "push", "origin", "main")
    return work


def test_update_fast_forwards_a_clean_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(update_specy_road, "is_canonical_specy_road_remote", lambda _url: True)
    work = clone_behind_origin(tmp_path)

    update_specy_road.main(["--path", str(work)])

    assert (work / "README.md").read_text(encoding="utf-8") == "v2\n"
    assert "fast-forwarded" in capsys.readouterr().out


def test_update_refuses_a_dirty_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(update_specy_road, "is_canonical_specy_road_remote", lambda _url: True)
    work = clone_behind_origin(tmp_path)
    (work / "README.md").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        update_specy_road.main(["--path", str(work)])

    assert exc.value.code == 1
    assert "working tree is not clean" in capsys.readouterr().err
    assert (work / "README.md").read_text(encoding="utf-8") == "dirty\n"
