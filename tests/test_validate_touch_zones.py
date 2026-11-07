"""Touch zones are checked against the working tree at authoring time.

A PM writes zones before the code exists, and nothing used to compare them with
what is on disk. Two zones in a real adopter repo named files that were never
created; the brief's "confirm touch zones" TODO caught them at implementation
time, which is late. These warnings catch them at `specy-road validate`.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from specy_road.bundled_scripts.validate_touch_zones import (
    notice_stale_sheet_zones,
    warn_touch_zones_match_nothing,
)
from tests.move_node_helpers import NK_A1, base_fixture, run_cli


def _node(**over) -> dict:
    base = {"id": "M1.1", "status": "In Progress", "touch_zones": []}
    base.update(over)
    return base


def _warn(
    nodes: list[dict],
    project_root: Path,
    capsys,
    *,
    git_root: Path | None = None,
) -> str:
    warn_touch_zones_match_nothing(nodes, project_root, git_root=git_root)
    return capsys.readouterr().err


def test_a_zone_that_exists_is_quiet(tmp_path: Path, capsys) -> None:
    (tmp_path / "src").mkdir()

    assert _warn([_node(touch_zones=["src/"])], tmp_path, capsys) == ""


def test_a_zone_naming_a_real_file_is_quiet(tmp_path: Path, capsys) -> None:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "outline.py").write_text("x", encoding="utf-8")

    assert _warn([_node(touch_zones=["schemas/outline.py"])], tmp_path, capsys) == ""


def test_a_missing_path_is_reported_with_the_node_and_the_fix(
    tmp_path: Path, capsys
) -> None:
    err = _warn([_node(touch_zones=["schemas/prose.py"])], tmp_path, capsys)

    assert "M1.1" in err
    assert "schemas/prose.py" in err
    assert "specy-road edit-node" in err


def test_every_missing_zone_is_named_in_one_line(tmp_path: Path, capsys) -> None:
    (tmp_path / "src").mkdir()

    err = _warn(
        [_node(touch_zones=["src/", "schemas/outline.py", "schemas/prose.py"])],
        tmp_path,
        capsys,
    )

    assert err.count("warning") == 1
    assert "schemas/outline.py" in err
    assert "schemas/prose.py" in err
    assert "'src/'" not in err


def test_many_drifted_nodes_share_one_header_and_one_fix_line(
    tmp_path: Path, capsys
) -> None:
    """This runs inside every pickup and edit; it may not flood the terminal."""
    nodes = [_node(id=f"M1.{i}", touch_zones=[f"gone/{i}"]) for i in range(1, 6)]

    err = _warn(nodes, tmp_path, capsys)
    lines = [ln for ln in err.splitlines() if ln.strip()]

    assert err.count("warning") == 1
    assert err.count("specy-road edit-node") == 1
    # One header, one line per node, two lines of guidance — nothing per-node
    # repeated.
    assert len(lines) == len(nodes) + 3
    for i in range(1, 6):
        assert f"M1.{i}" in err


def test_a_glob_with_a_match_is_quiet(tmp_path: Path, capsys) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x", encoding="utf-8")

    assert _warn([_node(touch_zones=["src/*.py"])], tmp_path, capsys) == ""


def test_a_glob_with_no_match_is_reported(tmp_path: Path, capsys) -> None:
    (tmp_path / "src").mkdir()

    assert "src/*.py" in _warn([_node(touch_zones=["src/*.py"])], tmp_path, capsys)


def test_settled_nodes_are_left_alone(tmp_path: Path, capsys) -> None:
    """Completed work whose files were since renamed is not a mistake to fix."""
    nodes = [
        _node(id="M1.1", status="Complete", touch_zones=["gone/"]),
        _node(id="M1.2", status="Not Started", rollup_status="Complete",
              touch_zones=["gone/"]),
    ]

    assert _warn(nodes, tmp_path, capsys) == ""


def test_a_zone_outside_the_project_root_is_reported(tmp_path: Path, capsys) -> None:
    err = _warn([_node(touch_zones=["/etc/passwd", "../elsewhere"])], tmp_path, capsys)

    assert "/etc/passwd" in err
    assert "../elsewhere" in err


def test_nodes_without_zones_are_skipped(tmp_path: Path, capsys) -> None:
    assert _warn([_node(), _node(touch_zones=None)], tmp_path, capsys) == ""


def test_an_empty_zone_is_not_this_check_s_problem(tmp_path: Path, capsys) -> None:
    assert _warn([_node(touch_zones=["   ", ""])], tmp_path, capsys) == ""


def test_a_filesystem_error_never_becomes_a_traceback(tmp_path: Path, capsys, monkeypatch) -> None:
    """validate runs inside every pickup and node edit; advisory must stay advisory.

    The error is simulated: an over-long name used to raise ``ENAMETOOLONG``,
    but Python 3.15's ``Path.glob`` swallows it and simply matches nothing.
    """
    def _boom(self, *_a, **_k):
        raise OSError("simulated filesystem error")

    monkeypatch.setattr(Path, "glob", _boom)
    monkeypatch.setattr(Path, "exists", _boom)
    assert _warn([_node(touch_zones=["src/*.py", "docs"])], tmp_path, capsys) == ""


@pytest.mark.parametrize(
    "pattern",
    [
        "**/*.nomatch",          # walks everything, ignore rules and all
        "**/**/*.nomatch",       # each extra ** multiplies the walk
        "./**/**/**/*.nomatch",  # a "." prefix prunes nothing
        "*/**/**/*.nomatch",     # nor does a wildcard prefix
        "src/**/**/*.nomatch",   # concrete prefix, but still two **
    ],
)
def test_an_unbounded_glob_is_refused_rather_than_walked(
    tmp_path: Path, capsys, pattern: str
) -> None:
    """validate runs on every pickup and node edit; it may not hang there."""
    (tmp_path / "src").mkdir()
    for i in range(30):
        deep = tmp_path / f"d{i}" / "nested" / "deeper"
        deep.mkdir(parents=True)
        (deep / f"f{i}.txt").write_text("x", encoding="utf-8")

    started = time.monotonic()
    err = _warn([_node(touch_zones=[pattern])], tmp_path, capsys)

    assert err == ""
    assert time.monotonic() - started < 1.0


def test_a_glob_below_a_real_directory_is_still_checked(tmp_path: Path, capsys) -> None:
    """One ** under a concrete directory is bounded, so it is worth checking."""
    (tmp_path / "src").mkdir()

    assert "src/**/*.py" in _warn(
        [_node(touch_zones=["src/**/*.py"])], tmp_path, capsys
    )


def test_a_bounded_glob_that_matches_stays_quiet(tmp_path: Path, capsys) -> None:
    (tmp_path / "src" / "deep").mkdir(parents=True)
    (tmp_path / "src" / "deep" / "a.py").write_text("x", encoding="utf-8")

    assert _warn([_node(touch_zones=["src/**/*.py"])], tmp_path, capsys) == ""


def test_a_not_started_node_naming_files_it_will_create_is_quiet(tmp_path: Path, capsys) -> None:
    """Agents "fixed" this warning on unbuilt work by deleting the zones."""
    nodes = [_node(status="Not Started", touch_zones=["src/feature/new_module.py"])]

    assert _warn(nodes, tmp_path, capsys) == ""


def test_a_started_subtree_is_judged_by_its_rollup(tmp_path: Path, capsys) -> None:
    nodes = [_node(id="M2", status="Not Started", rollup_status="In Progress", touch_zones=["gone/"])]

    assert "M2" in _warn(nodes, tmp_path, capsys)


def test_the_hint_does_not_invite_removing_zones(tmp_path: Path, capsys) -> None:
    err = _warn([_node(touch_zones=["src/sync/engine.py"])], tmp_path, capsys)

    assert "do not remove zones just to silence this" in err
    assert "planning sheet" not in err


@pytest.fixture
def nested_project(tmp_path: Path) -> tuple[Path, Path]:
    """``(git_root, project_root)`` with the project at ``sr/`` and code beside it."""
    top = tmp_path / "checkout"
    project = top / "sr"
    project.mkdir(parents=True)
    (top / "specy_road").mkdir()
    (top / "specy_road" / "toolkit.py").write_text("# toolkit\n", encoding="utf-8")
    return top, project


def test_a_git_root_zone_outside_the_project_is_quiet(nested_project, capsys) -> None:
    top, project = nested_project

    assert _warn(
        [_node(touch_zones=["specy_road/toolkit.py"])],
        project,
        capsys,
        git_root=top,
    ) == ""


def test_a_misspelled_git_root_zone_still_warns(nested_project, capsys) -> None:
    top, project = nested_project

    err = _warn(
        [_node(touch_zones=["specy_road/typo.py"])],
        project,
        capsys,
        git_root=top,
    )

    assert "M1.1" in err
    assert "specy_road/typo.py" in err


def _git(top: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=top, check=True, capture_output=True,
    )


@pytest.mark.parametrize("staged", [False, True], ids=["unstaged", "staged"])
@pytest.mark.parametrize("status", ["Not Started", "In Progress", "Complete"])
def test_a_zone_naming_a_missing_planning_sheet_gets_a_stdout_notice(
    tmp_path: Path, status: str, staged: bool
) -> None:
    """Only an absent literal sheet path, in either form, is noticed; --strict ignores it."""
    top, project = tmp_path, tmp_path / "sr"
    base_fixture(project)
    current = f"planning/M1.1_alpha-work_{NK_A1}.md"
    gone = f"planning/M9.9_old-name_{NK_A1}.md"
    (project / gone).write_text("# old\n", encoding="utf-8")
    (project / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n"
        "require_implementation_review_before_finish: false\n",
        encoding="utf-8",
    )
    for doc in ("constitution/purpose.md", "constitution/principles.md", "docs/supply-chain-security.md"):
        (project / doc).parent.mkdir(exist_ok=True)
        (project / doc).write_text("# doc\n", encoding="utf-8")   # the AGENTS.md load order
    _git(top, "init", "-q", "-b", "main")
    assert run_cli(project, "refresh-stubs").returncode == 0  # no AGENTS.md warning under --strict
    _git(top, "add", "-A")
    _git(top, "commit", "-q", "-m", "init")
    if staged:
        _git(top, "rm", "-q", f"sr/{gone}")
    else:
        (project / gone).unlink()
    zones = [gone, f"sr/{gone}", current, f"sr/{current}", "planning/*.md", "sr/planning/*.md"]
    chunk = project / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    for n in nodes:
        if n["id"] == "M1.1":
            n.update(status=status, touch_zones=zones)
        elif n["id"] == "M1" and status == "Complete":
            n["status"] = status   # no stale-parent warning under --strict
    write_json_chunk(chunk, nodes)

    r = run_cli(project, "validate", "--strict")

    notices = [ln for ln in r.stdout.splitlines() if "names a planning sheet" in ln]
    assert notices == [
        f"roadmap: notice — M1.1: touch zone {z!r} names a planning sheet that does not exist; "
        f"M1.1's sheet is now {p + current!r} (specy-road edit-node M1.1 --set touch_zones=<paths>)"
        for z, p in ((gone, ""), (f"sr/{gone}", "sr/"))
    ]
    assert "planning sheet" not in r.stderr
    if status == "In Progress":   # keeps its existing stderr match-nothing warning
        assert "match nothing in the working tree" in r.stderr
    else:
        assert r.returncode == 0, r.stderr


def test_a_not_started_missing_non_sheet_zone_gets_no_new_notice(
    tmp_path: Path, capsys
) -> None:
    nodes = [_node(status="Not Started", touch_zones=["src/feature/new_module.py"])]

    warn_touch_zones_match_nothing(nodes, tmp_path)
    notice_stale_sheet_zones(nodes, tmp_path)

    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == ""
