"""A nested project's touch zones match from either root (M9.11).

With the project at ``sr/`` under the git root, a leaf may name a project file
git-root-relative (``sr/schemas/``) like its code zones, or project-relative
(``schemas/``). The review packet and the finish check must agree either way.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts.review_packet import changed_paths_section
from specy_road.finish_implementation_check import implementation_gate_error, in_zones
from specy_road.review_target import ReviewTarget

OUTSIDE = "outside touch zones"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def nested(tmp_path: Path) -> tuple[Path, Path, str]:
    """``(git_root, project_root, base)`` with ``sr/schemas/s.json`` changed on a branch."""
    top = tmp_path / "checkout"
    (top / "sr").mkdir(parents=True)
    _git(top, "init", "-q", "-b", "main")
    _git(top, "config", "user.email", "t@example.com")
    _git(top, "config", "user.name", "Test")
    (top / "sr" / "seed.txt").write_text("seed", encoding="utf-8")
    _git(top, "add", "-A")
    _git(top, "commit", "-qm", "seed")
    base = _git(top, "rev-parse", "HEAD")
    _git(top, "checkout", "-qb", "feature/rm-nz")
    (top / "sr" / "schemas").mkdir()
    (top / "sr" / "schemas" / "s.json").write_text("{}", encoding="utf-8")
    _git(top, "add", "-A")
    _git(top, "commit", "-qm", "schema")
    return top, top / "sr", base


def _packet(project: Path, top: Path, base: str, zones: list[str]) -> tuple[list[str], str]:
    node = {"id": "M1", "touch_zones": zones}
    tip = _git(top, "rev-parse", "HEAD")
    target = ReviewTarget(node=node, nodes=[node], entry=None, ref="HEAD", commit=tip, base_ref=None, base=base)
    paths, lines = changed_paths_section(project, target)
    return paths, "\n".join(lines)


def _finish_error(project: Path, zones: list[str]) -> str | None:
    return implementation_gate_error(
        project, node_id="M1", zones=zones, remote="origin", integration_branch="main"
    )


@pytest.mark.parametrize("zone", ["sr/schemas/", "schemas/", "sr/schemas/s.json", "sr/schemas/*"])
def test_either_zone_form_is_in_zone_for_packet_and_finish(nested, zone):
    top, project, base = nested

    paths, text = _packet(project, top, base, [zone, "specy_road/"])

    assert paths == ["schemas/s.json"]
    assert OUTSIDE not in text
    assert _finish_error(project, [zone, "specy_road/"]) is None


def test_an_unmatched_zone_is_still_flagged_and_refused(nested):
    top, project, base = nested

    _paths, text = _packet(project, top, base, ["sr/docs/", "specy_road/"])

    assert "- `schemas/s.json`  **← outside touch zones**" in text
    error = _finish_error(project, ["sr/docs/", "specy_road/"])
    assert error is not None and "nothing was implemented for M1" in error


@pytest.mark.parametrize(
    "zone,path,prefix,expected",
    [
        ("sr/schemas", "sr/schemas/a.json", "sr/", True),
        ("schemas", "sr/schemas/a.json", "sr/", True),
        ("specy_road", "specy_road/x.py", "sr/", True),
        # Code outside the project has only its git-root name.
        ("sr/specy_road", "specy_road/x.py", "sr/", False),
        # A project-relative zone also reads a same-named tree beside the project,
        # as before: loose matching only costs a missed catch.
        ("schemas", "schemas/a.json", "sr/", True),
        ("sr/schemas", "sr/schemas/a.json", "", True),
        ("schemas", "sr/schemas/a.json", "", False),
    ],
)
def test_in_zones_reads_both_roots(zone, path, prefix, expected):
    assert in_zones([zone], path, prefix) is expected
