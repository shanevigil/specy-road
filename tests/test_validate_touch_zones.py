"""Touch zones are checked against the working tree at authoring time.

A PM writes zones before the code exists, and nothing used to compare them with
what is on disk. Two zones in a real adopter repo named files that were never
created; the brief's "confirm touch zones" TODO caught them at implementation
time, which is late. These warnings catch them at `specy-road validate`.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.validate_touch_zones import (
    warn_touch_zones_match_nothing,
)


def _node(**over) -> dict:
    base = {"id": "M1.1", "status": "Not Started", "touch_zones": []}
    base.update(over)
    return base


def _warn(nodes: list[dict], root: Path, capsys) -> str:
    warn_touch_zones_match_nothing(nodes, root)
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
    assert "specy-road edit-node M1.1" in err


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
