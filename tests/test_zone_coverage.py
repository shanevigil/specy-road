"""Plan-time warnings when acceptance names paths outside a leaf's touch zones."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from specy_road import orchestrate_plan as op
from specy_road.bundled_scripts import orchestrate_cli
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.bundled_scripts.grind_session import run_session
from specy_road.bundled_scripts.session_plan_render import render_session_plan_text
from specy_road.bundled_scripts.session_plan_git import gather_session_plan
from specy_road.zone_coverage import BEST_EFFORT_HINT, NEW_OUTSIDE, uncovered_acceptance_paths
from tests.review_repo_helpers import git
from tests.test_orchestrate_plan import ROSTER, plan_repo

_TRACKED = frozenset({"src/a.py", "docs/readme.md", "docs/outside.md", "docs/api/schema.json", "docs/contracts/api.yaml"})


def _labels(acceptance: str, *, zones: list[str], tracked: set[str] = set(_TRACKED)) -> list[str]:
    node = {"acceptance": [acceptance], "touch_zones": zones}
    return uncovered_acceptance_paths(Path("/tmp"), node, tracked=tracked)


# One row per A1 path-rule clause (roadmap acceptance line 1, planner rule 2026-11-05).
@pytest.mark.parametrize(
    ("acceptance", "zones", "tracked", "want"),
    [
        # Backtick span with / → always candidate; nonexistent → new file outside zones
        pytest.param("Add `brand/newdir`", ["src/"], _TRACKED, {NEW_OUTSIDE}, id="a1-backtick-slash-new"),
        pytest.param("Add `docs/newdir`", ["src/"], _TRACKED, {NEW_OUTSIDE}, id="a1-backtick-slash-new-under-tracked-tree"),
        pytest.param(
            "Update `input/output`",
            ["src/"],
            _TRACKED,
            {NEW_OUTSIDE},
            id="a1-backtick-slash-even-prose-shaped",
        ),
        # Backtick span with known suffix → candidate; nonexistent → new
        pytest.param("Ship `NOTES.txt`", ["src/"], _TRACKED, {NEW_OUTSIDE}, id="a1-backtick-suffix-new"),
        # Bare token: tracked top-level directory name (docs/)
        pytest.param("See docs/ next", ["src/"], _TRACKED, {"docs"}, id="a1-bare-top-level-dir-slash-existing"),
        pytest.param("Extend docs/contracts", ["src/"], _TRACKED, {"docs/contracts"}, id="a1-bare-under-top-level-existing"),
        pytest.param("Edit docs/existing.md", ["src/"], _TRACKED | {"docs/existing.md"}, {"docs/existing.md"}, id="a1-bare-path-under-top-level-existing"),
        # Bare token: ends in known suffix
        pytest.param("Ship NOTES.txt today", ["src/"], _TRACKED, {NEW_OUTSIDE}, id="a1-bare-suffix-new"),
        pytest.param("Ship (NOTES.txt) today", ["src/"], _TRACKED, {NEW_OUTSIDE}, id="a1-bare-suffix-strips-parens"),
        # Existing path in zone → no warning
        pytest.param("Update `src/a.py`", ["src/"], _TRACKED, set(), id="a1-in-zone-silent"),
        pytest.param(
            "Touch docs/api/schema.json",
            ["docs/"],
            _TRACKED,
            set(),
            id="a1-bare-file-in-zone-silent",
        ),
        # One covered + one uncovered path (pin from A1)
        pytest.param(
            "Change `docs/outside.md` and `src/in_zone.py`",
            ["src/"],
            _TRACKED | {"src/in_zone.py"},
            {"docs/outside.md"},
            id="a1-one-covered-one-uncovered",
        ),
        pytest.param("Refresh `docs/` tree", ["src/"], _TRACKED, {"docs"}, id="a1-backtick-dir-existing"),
        # Ignored prose (not candidates)
        pytest.param("Compare input/output for the CLI", ["src/"], _TRACKED, set(), id="a1-ignore-prose-slash"),
        pytest.param("Use read/write mode", ["src/"], _TRACKED, set(), id="a1-ignore-read-write"),
        pytest.param("Coordinate M12/M13 handoff", ["src/"], _TRACKED, set(), id="a1-ignore-milestone-ids"),
        pytest.param(
            "See https://example.com/foo/bar for details",
            ["src/"],
            _TRACKED,
            set(),
            id="a1-ignore-url",
        ),
    ],
)
def test_a1_path_rule_table(
    acceptance: str,
    zones: list[str],
    tracked: set[str],
    want: set[str],
) -> None:
    got = set(_labels(acceptance, zones=zones, tracked=tracked))
    assert got == want


def _warn_suffix(*parts: str) -> str:
    body = ", ".join(parts)
    return f"M1.1: acceptance names paths outside touch zones ({BEST_EFFORT_HINT}): {body}"


def _leaf_repo(tmp_path: Path) -> Path:
    repo = plan_repo(tmp_path, roster=ROSTER)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    data = json.loads(chunk.read_text(encoding="utf-8"))
    data["nodes"][0]["touch_zones"] = ["src/"]
    data["nodes"][0]["acceptance"] = ["Change `docs/outside.md` and `src/in_zone.py`"]
    chunk.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "in_zone.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / "outside.md").write_text("# x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "paths")
    return repo


def test_orchestrate_and_grind_warn_once_per_leaf(tmp_path: Path, capsys) -> None:
    """A1: orchestrate plan and grind-session --plan warn once per leaf."""
    repo = _leaf_repo(tmp_path)
    plan, err = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    assert err is None and plan is not None
    msg = _warn_suffix("docs/outside.md")
    assert plan.batches[0][0].warnings == [msg]
    _nodes, _reg, session = gather_session_plan(repo, None)
    assert session.zone_coverage[0]["message"] == msg
    assert f"! {msg}" in render_session_plan_text(session)
    print("\n".join(orchestrate_cli.render(plan)))
    assert f"! {msg}" in capsys.readouterr().out
    run_session(parse_grind_session_args(["--plan", "--json", "--repo-root", str(repo)]))
    json_plan = json.loads(capsys.readouterr().out.splitlines()[0])
    assert json_plan["zone_coverage"][0]["message"] == msg
