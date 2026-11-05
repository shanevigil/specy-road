"""Shared documentation zones (``planning/``, ``shared/``) do not serialize
``grind-session --plan`` batches or trip the registry overlap warning (M15.12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts.session_plan import compute_session_plan
from specy_road.bundled_scripts.session_plan_render import (
    render_session_plan_text,
    session_plan_to_dict,
    zone_overlaps,
)
from specy_road.bundled_scripts.validate_registry_overlap import (
    AuthoringOverlapScope,
    touch_zone_overlap,
    warn_registry_touch_zone_overlap,
)
from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.shared_zones import (
    DEFAULT_SHARED_ZONES,
    ignored_shared_zones,
    resolve_shared_zones,
    zones_overlap,
)

_SHARED = ["planning/", "shared/"]


def _leaf(n: int, zones: list[str]) -> dict:
    return {
        "id": f"M1.{n}", "node_key": f"10000000-0000-4000-8000-{n:012d}",
        "type": "task", "title": f"M1.{n}", "status": "Not Started",
        "codename": f"cn-{n}", "dependencies": [], "parent_id": None,
        "sibling_order": n, "touch_zones": zones,
    }


def _plan(zone_lists: list[list[str]], **kw):
    nodes = [_leaf(i + 1, z) for i, z in enumerate(zone_lists)]
    return compute_session_plan(nodes, {"version": 1, "entries": []}, **kw)


def _thirty() -> list[list[str]]:
    return [_SHARED + [f"src/mod{i}.py"] for i in range(30)]


def test_thirty_leaves_sharing_only_doc_zones_form_one_batch() -> None:
    plan = _plan(_thirty())
    assert plan.parallel_batches == [[f"M1.{i}" for i in range(1, 31)]]
    assert zone_overlaps(plan) == []
    data = session_plan_to_dict(plan)
    assert data["shared_zones_ignored"] == ["planning/", "shared/"]
    text = render_session_plan_text(plan)
    assert text.count("Shared zones ignored for overlap") == 1
    assert "`planning/`, `shared/`" in text
    assert "waits for" not in text


def test_same_planning_sheet_keeps_two_leaves_apart() -> None:
    sheet = "planning/M1_same-sheet.md"
    plan = _plan([_SHARED + ["src/a.py", sheet], _SHARED + ["src/b.py", sheet], _SHARED + ["src/c.py"]])
    assert plan.parallel_batches == [["M1.1", "M1.3"], ["M1.2"]]
    assert zone_overlaps(plan) == [{"node_id": "M1.2", "waits_for": "M1.1", "zones": [sheet, sheet]}]


def test_code_overlap_still_splits_alongside_shared_zones() -> None:
    plan = _plan([_SHARED + ["src/"], _SHARED + ["src/x.py"]])
    assert plan.parallel_batches == [["M1.1"], ["M1.2"]]


def test_empty_shared_zone_set_restores_the_plain_rule() -> None:
    plan = _plan(_thirty()[:3], shared_zones=())
    assert plan.parallel_batches == [["M1.1"], ["M1.2"], ["M1.3"]]
    assert session_plan_to_dict(plan)["shared_zones_ignored"] == []
    assert "Shared zones ignored" not in render_session_plan_text(plan)


_GW = "version: 1\nintegration_branch: dev\nremote: origin\n"


def _repo(tmp_path: Path, extra: str = "") -> Path:
    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(_GW + extra, encoding="utf-8")
    return tmp_path


def test_shared_zones_config_default_override_and_schema(tmp_path: Path) -> None:
    assert resolve_shared_zones(tmp_path) == ("planning/", "shared/")  # no config file
    assert resolve_shared_zones(_repo(tmp_path / "a")) == ("planning/", "shared/")
    assert resolve_shared_zones(_repo(tmp_path / "b", "grind:\n  shared_zones: []\n")) == ()
    assert resolve_shared_zones(_repo(tmp_path / "c", "grind:\n  shared_zones: [docs/]\n")) == ("docs/",)
    _, err = load_git_workflow_config(_repo(tmp_path / "d", "grind:\n  shared_zones: docs/\n"))
    assert err and "shared_zones" in err
    _, err = load_git_workflow_config(_repo(tmp_path / "e", "grind:\n  sharedzones: [docs/]\n"))
    assert err and "grind" in err


def _entries() -> list[dict]:
    return [{"codename": f"cn-{i}", "touch_zones": _SHARED + [f"src/mod{i}.py"]} for i in range(30)]


def test_registry_warning_ignores_shared_zones(capsys) -> None:
    touch_zone_overlap(_entries())
    assert capsys.readouterr().err == ""


def test_registry_warning_keeps_same_planning_sheet(capsys) -> None:
    sheet = "planning/M1_same-sheet.md"
    entries = [
        {"codename": "a", "touch_zones": _SHARED + ["src/a.py", sheet]},
        {"codename": "b", "touch_zones": _SHARED + ["src/b.py", sheet]},
    ]
    touch_zone_overlap(entries)
    err = capsys.readouterr().err
    assert err.count("possible overlap") == 1
    assert f"'{sheet}' vs '{sheet}' (a vs b)" in err


def test_registry_scoped_warning_ignores_shared_zones(capsys) -> None:
    touch_zone_overlap(_entries(), scope_label="new", scope_touch_zones=_SHARED + ["src/new.py"])
    assert capsys.readouterr().err == ""


def test_validate_reads_the_configured_shared_zones(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path, "grind:\n  shared_zones: []\n")
    warn_registry_touch_zone_overlap(_entries(), no_overlap_warn=False, overlap_scope=None, repo_root=repo)
    assert "shared zone 'planning/'" in capsys.readouterr().err


_ALIASED = [
    {"node_id": "M1.1", "codename": "a", "touch_zones": _SHARED + ["planning/same.md", "src/1.py"]},
    {"node_id": "M1.2", "codename": "b", "touch_zones": _SHARED + ["./planning/same.md", "src/2.py"]},
]


def test_same_file_spelled_two_ways_warns_scoped_and_unscoped_and_splits(capsys) -> None:
    warn_registry_touch_zone_overlap(_ALIASED, no_overlap_warn=False, overlap_scope=None)
    err = capsys.readouterr().err
    assert err.count("possible overlap") == 1
    assert "'planning/same.md' vs './planning/same.md' (a vs b)" in err
    scope = AuthoringOverlapScope("b", "M1.2", _ALIASED[1]["touch_zones"])
    warn_registry_touch_zone_overlap(_ALIASED, no_overlap_warn=False, overlap_scope=scope)
    err = capsys.readouterr().err
    assert err.count("possible overlap") == 1
    assert "(b vs a)" in err
    plan = _plan([e["touch_zones"] for e in _ALIASED])
    assert plan.parallel_batches == [["M1.1"], ["M1.2"]]


def test_registry_broad_zone_spelled_two_ways_is_summarized_once(capsys) -> None:
    touch_zone_overlap([
        {"codename": "a", "touch_zones": ["src/", "src/a.py"]},
        {"codename": "b", "touch_zones": ["./src/", "src/b.py"]},
    ])
    err = capsys.readouterr().err
    assert err.count("possible overlap") == 1
    assert "shared zone 'src/' (claims: a, b)" in err


# (zone of leaf a, zone of leaf b, overlap?) with the default shared zones planning/, shared/.
_PAIRS = [
    ("src/a.py", "./src/a.py", True),
    ("src/a.py", "src/a.py", True),
    ("src/", "src", True),
    ("src/", "./src/", True),
    ("src/", "src/a.py", True),
    ("./src/", "src/a/b.py", True),
    ("src/a/../b.py", "src/b.py", True),
    ("src//b.py", "src/b.py", True),
    (" src/b.py ", "src/b.py", True),
    ("src/a.py", "src/b.py", False),
    ("src-old/x.py", "src/", False),
    ("planning/", "planning/x.md", False),
    ("./planning/", "planning/x.md", False),
    ("planning", "planning/x.md", False),
    ("planning/", "planning/", False),
    ("shared/", "./shared//", False),
    ("planning/x.md", "./planning/x.md", True),
    ("planning/x.md", "planning//x.md", True),
    ("planning/a/../x.md", "planning/x.md", True),
    ("planning/x.md", "planning/y.md", False),
    ("shared/api/", "shared/api/x.md", True),
    ("shared/api/", "shared/web/", False),
]


@pytest.mark.parametrize(("a", "b", "overlap"), _PAIRS)
def test_plan_and_validate_apply_one_overlap_rule(a: str, b: str, overlap: bool, capsys) -> None:
    plan = _plan([[a], [b]])
    assert (plan.parallel_batches == [["M1.1"], ["M1.2"]]) is overlap
    assert (plan.parallel_batches == [["M1.1", "M1.2"]]) is not overlap
    entries = [{"node_id": "M1.1", "codename": "a", "touch_zones": [a]},
               {"node_id": "M1.2", "codename": "b", "touch_zones": [b]}]
    warn_registry_touch_zone_overlap(entries, no_overlap_warn=False, overlap_scope=None)
    assert ("possible overlap" in capsys.readouterr().err) is overlap
    scope = AuthoringOverlapScope("b", "M1.2", [b])
    warn_registry_touch_zone_overlap(entries, no_overlap_warn=False, overlap_scope=scope)
    assert ("possible overlap" in capsys.readouterr().err) is overlap


@pytest.mark.parametrize("configured", [
    ("notes/team/", "./notes/team/"),
    ("notes/team/", "notes//team/", " notes/team "),
    ("notes/team/", "notes/x/../team/"),
])
def test_aliased_shared_zone_is_reported_once_in_text_and_json(configured, tmp_path: Path) -> None:
    yaml_list = ", ".join(f"'{z}'" for z in configured)
    repo = _repo(tmp_path, f"grind:\n  shared_zones: [{yaml_list}]\n")
    assert resolve_shared_zones(repo) == ("notes/team/",)
    zone_lists = [["notes/team/", "src/a.py"], ["./notes/team/", "src/b.py"]]
    for shared in (configured, resolve_shared_zones(repo)):
        plan = _plan(zone_lists, shared_zones=shared)
        assert plan.parallel_batches == [["M1.1", "M1.2"]]
        assert session_plan_to_dict(plan, fields=("shared_zones_ignored",)) == {
            "shared_zones_ignored": ["notes/team/"]
        }
        text = render_session_plan_text(plan)
        assert text.count("Shared zones ignored for overlap") == 1
        assert "overlap (leaves meet only there): `notes/team/`; two" in text


def test_zones_overlap_iterable_shared_matches_tuple() -> None:
    """Non-shared file under a shared directory: ``iter(shared)`` must match a tuple."""
    a, b = "planning/x.md", "planning/"
    assert zones_overlap(a, b, DEFAULT_SHARED_ZONES) is False
    assert zones_overlap(a, b, iter(DEFAULT_SHARED_ZONES)) is False


def test_ignored_shared_zones_iterable_leaf_ids_matches_list() -> None:
    zones = {
        "a": ["planning/", "shared/"],
        "b": ["planning/x.md", "shared/api.md"],
    }
    expected = ["planning/", "shared/"]
    assert ignored_shared_zones(zones, ["a", "b"], DEFAULT_SHARED_ZONES) == expected
    assert ignored_shared_zones(zones, iter(["a", "b"]), DEFAULT_SHARED_ZONES) == expected
