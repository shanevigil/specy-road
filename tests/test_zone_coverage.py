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


def _warn_suffix(*parts: str) -> str:
    body = ", ".join(parts)
    return f"M1.1: acceptance names paths outside touch zones ({BEST_EFFORT_HINT}): {body}"


def _leaf_repo(tmp_path: Path) -> Path:
    repo = plan_repo(tmp_path, roster=ROSTER)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    data = json.loads(chunk.read_text(encoding="utf-8"))
    data["nodes"][0]["touch_zones"] = ["src/"]
    data["nodes"][0]["acceptance"] = ["Update `src/in_zone.py` and `docs/outside.md`"]
    chunk.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "in_zone.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / "outside.md").write_text("# x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "paths")
    return repo


def _node(repo: Path) -> dict:
    return json.loads((repo / "roadmap" / "phases" / "M1.json").read_text(encoding="utf-8"))["nodes"][0]


def test_uncovered_acceptance_path_is_listed_and_covered_one_is_not(tmp_path: Path) -> None:
    repo = _leaf_repo(tmp_path)

    labels = uncovered_acceptance_paths(repo, _node(repo))

    assert labels == ["docs/outside.md"]


def test_nonexistent_backticked_path_with_suffix_is_new_file_outside_zones(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path, roster=ROSTER)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    data = json.loads(chunk.read_text(encoding="utf-8"))
    data["nodes"][0]["touch_zones"] = ["src/"]
    data["nodes"][0]["acceptance"] = ["Add `brand/new/module.py`"]
    chunk.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    git(repo, "add", chunk)
    git(repo, "commit", "-qm", "acceptance")

    assert uncovered_acceptance_paths(repo, _node(repo)) == [NEW_OUTSIDE]


@pytest.mark.parametrize(
    "phrase",
    [
        "Compare input/output for the CLI",
        "Use read/write mode",
        "Coordinate M12/M13 handoff",
        "See https://example.com/foo/bar for details",
    ],
)
def test_prose_slash_phrases_without_path_shape_are_ignored(phrase: str) -> None:
    node = {"acceptance": [phrase], "touch_zones": ["src/"]}
    tracked = {"src/a.py"}

    assert uncovered_acceptance_paths(Path("/tmp"), node, tracked=tracked) == []


@pytest.mark.parametrize(
    ("acceptance", "tracked", "zones", "want", "avoid"),
    [
        (
            "Update `input/output`",
            {"src/a.py"},
            ["src/"],
            set(),
            {NEW_OUTSIDE},
        ),
        (
            "Ship `CHANGELOG.md` beside the tree",
            {"src/a.py"},
            ["src/"],
            {NEW_OUTSIDE},
            {"CHANGELOG.md"},
        ),
        (
            "Edit docs/existing.md",
            {"docs/existing.md", "src/a.py"},
            ["src/"],
            {"docs/existing.md"},
            set(),
        ),
        (
            "See `docs` tree",
            {"docs/readme.md"},
            ["src/"],
            {"docs"},
            set(),
        ),
        (
            "Add docs/new.md in the next commit",
            {"docs/readme.md"},
            ["src/"],
            {NEW_OUTSIDE},
            {"docs/new.md"},
        ),
        (
            "Update `docs/api/schema.json`",
            {"docs/api/schema.json"},
            ["docs/"],
            set(),
            {NEW_OUTSIDE, "docs/api/schema.json"},
        ),
        (
            "Extend docs/contracts",
            {"docs/contracts/api.yaml"},
            ["src/"],
            {"docs/contracts"},
            set(),
        ),
    ],
)
def test_path_candidate_rule(
    acceptance: str,
    tracked: set[str],
    zones: list[str],
    want: set[str],
    avoid: set[str],
) -> None:
    node = {"acceptance": [acceptance], "touch_zones": zones}
    labels = set(uncovered_acceptance_paths(Path("/tmp"), node, tracked=tracked))
    assert want <= labels
    assert not labels & avoid


@pytest.mark.parametrize(
    ("token", "tracked", "zones", "want", "avoid"),
    [
        ("docs", {"docs/readme.md"}, ["src/"], {"docs"}, set()),
        ("docs/", {"docs/readme.md"}, ["src/"], {"docs"}, set()),
        ("docs/api", {"docs/api/schema.json"}, ["src/"], {"docs/api"}, {NEW_OUTSIDE}),
        ("docs/outside.md", {"docs/outside.md"}, ["src/"], {"docs/outside.md"}, set()),
        ("brand/new/module.py", set(), ["src/"], {NEW_OUTSIDE}, {"brand/new/module.py"}),
        (
            "src/new/file.py",
            {"src/old.py"},
            ["src/"],
            set(),
            {NEW_OUTSIDE, "src/new/file.py"},
        ),
    ],
)
def test_backticked_existence_classifies_tracked_dirs_files_and_new_paths(
    token: str,
    tracked: set[str],
    zones: list[str],
    want: set[str],
    avoid: set[str],
) -> None:
    node = {"acceptance": [f"Update `{token}`"], "touch_zones": zones}
    labels = set(uncovered_acceptance_paths(Path("/tmp"), node, tracked=tracked))
    assert want <= labels
    assert not labels & avoid


def test_mixed_acceptance_lists_dirs_files_and_new_outside_only_once(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path, roster=ROSTER)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    data = json.loads(chunk.read_text(encoding="utf-8"))
    data["nodes"][0]["touch_zones"] = ["src/"]
    data["nodes"][0]["acceptance"] = [
        "Touch `docs/`, `docs/outside.md`, `docs/api`, `src/brand_new.py`, and `brand/new/module.py`",
    ]
    chunk.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (repo / "docs" / "outside.md").parent.mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "outside.md").write_text("# x\n", encoding="utf-8")
    (repo / "docs" / "api").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "api" / "schema.json").write_text("{}\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "docs tree")

    labels = uncovered_acceptance_paths(repo, _node(repo))

    assert set(labels) == {"docs", "docs/outside.md", "docs/api", NEW_OUTSIDE}
    assert labels.count(NEW_OUTSIDE) == 1


def test_orchestrate_plan_warns_once_per_leaf(tmp_path: Path, capsys) -> None:
    repo = _leaf_repo(tmp_path)
    plan, err = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    assert err is None and plan is not None
    a = plan.batches[0][0]
    assert a.warnings == [_warn_suffix("docs/outside.md")]
    print("\n".join(orchestrate_cli.render(plan)))
    out = capsys.readouterr().out
    assert f"! {_warn_suffix('docs/outside.md')}" in out


def test_grind_session_plan_warns_once_per_leaf(tmp_path: Path) -> None:
    repo = _leaf_repo(tmp_path)
    _nodes, _reg, plan = gather_session_plan(repo, None)
    assert len(plan.zone_coverage) == 1
    assert plan.zone_coverage[0]["message"] == _warn_suffix("docs/outside.md")
    text = render_session_plan_text(plan)
    assert f"! {_warn_suffix('docs/outside.md')}" in text


def test_grind_session_plan_json_includes_zone_coverage(tmp_path: Path, capsys) -> None:
    repo = _leaf_repo(tmp_path)
    run_session(parse_grind_session_args(["--plan", "--json", "--repo-root", str(repo)]))
    plan = json.loads(capsys.readouterr().out.splitlines()[0])
    assert plan["zone_coverage"] == [{
        "node_id": "M1.1",
        "message": _warn_suffix("docs/outside.md"),
    }]
