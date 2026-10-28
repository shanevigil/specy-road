"""Tests for roadmap validation logic and script."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, REPO, script_subprocess_env

from specy_road import __version__
from specy_road.bundled_scripts import validate_roadmap as vr
from specy_road.bundled_scripts.roadmap_load import annotate_rollup_status, load_roadmap
from specy_road.bundled_scripts.validate_roadmap_checks import (
    run_validation,
    touch_zone_overlap,
    validate_dependency_ids,
    validate_node_keys,
    validate_parents,
    warn_stale_parent_status,
)


def test_validate_script_is_quiet_when_no_parent_status_drifted() -> None:
    """The dogfood fixture's parents agree with their rollups, so nothing is reported."""
    r = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_roadmap.py"),
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "rolls up to" not in (r.stderr or "")
    # The fixture's touch zones name real directories, so nothing is reported.
    assert "matches nothing" not in (r.stderr or "")


def test_warn_stale_parent_status_reports_drift_without_failing(capsys) -> None:
    """Rollup is authoritative, so drift is a warning — but it must not be silent.

    rc2 dropped this warning while dependency satisfaction still read own status,
    which turned a stale parent into an unexplained stall.
    """
    nodes = annotate_rollup_status(
        [
            {
                "id": "M1",
                "node_key": "50000000-0000-4000-8000-000000000001",
                "parent_id": None,
                "type": "phase",
                "title": "P",
                "status": "Not Started",
            },
            {
                "id": "M1.1",
                "node_key": "50000000-0000-4000-8000-000000000002",
                "parent_id": "M1",
                "type": "task",
                "title": "T",
                "status": "Complete",
            },
        ]
    )
    warn_stale_parent_status(nodes)
    err = capsys.readouterr().err
    assert "M1 has status 'Not Started' but rolls up to 'Complete'" in err
    assert "specy-road edit-node M1 --set status=Complete" in err


@pytest.mark.parametrize(
    ("parent", "leaf", "warned"),
    [
        ("Complete", "Complete", False),
        # rc1: an honest In Progress parent was told to go back to Not Started.
        ("In Progress", "Not Started", False),
        ("Not Started", "In Progress", False),
        ("Complete", "In Progress", True),
        ("In Progress", "Complete", True),
    ],
)
def test_warn_stale_parent_status_only_on_a_complete_disagreement(
    capsys, parent: str, leaf: str, warned: bool
) -> None:
    nodes = annotate_rollup_status(
        [
            {
                "id": "M1",
                "node_key": "50000000-0000-4000-8000-000000000003",
                "parent_id": None,
                "type": "phase",
                "title": "P",
                "status": parent,
            },
            {
                "id": "M1.1",
                "node_key": "50000000-0000-4000-8000-000000000004",
                "parent_id": "M1",
                "type": "task",
                "title": "T",
                "status": leaf,
            },
        ]
    )
    warn_stale_parent_status(nodes)
    err = capsys.readouterr().err
    assert (f"specy-road edit-node M1 --set status={leaf}" in err) is warned
    assert bool(err) is warned


def test_cycle_check_detects_cycle() -> None:
    k1 = "10000000-0000-4000-8000-000000000001"
    k2 = "20000000-0000-4000-8000-000000000002"
    nodes = [
        {"id": "M1", "node_key": k1, "dependencies": [k2]},
        {"id": "M2", "node_key": k2, "dependencies": [k1]},
    ]
    with pytest.raises(SystemExit):
        vr.cycle_check(nodes)


def test_validate_codenames_duplicate() -> None:
    nodes = [
        {"id": "M1", "codename": "foo"},
        {"id": "M2", "codename": "foo"},
    ]
    with pytest.raises(SystemExit):
        vr.validate_codenames(nodes)


def test_validate_unique_titles_duplicate() -> None:
    nodes = [
        {"id": "M1", "title": "  Shared name  "},
        {"id": "M2", "title": "Shared name"},
    ]
    with pytest.raises(SystemExit):
        vr.validate_unique_titles(nodes)


def test_validate_unique_titles_ok_when_empty_or_distinct() -> None:
    nodes = [
        {"id": "M1", "title": "  "},
        {"id": "M2", "title": "Only one real title"},
    ]
    vr.validate_unique_titles(nodes)


def test_validate_unique_title_slugs_duplicate_different_titles() -> None:
    """Kebab slug from title_to_codename must be unique (spacing vs hyphen)."""
    nodes = [
        {"id": "M1", "title": "Hello World"},
        {"id": "M2", "title": "hello-world"},
    ]
    with pytest.raises(SystemExit):
        vr.validate_unique_title_slugs(nodes)


def test_validate_required_planning_dirs_phase() -> None:
    nodes = [
        {
            "id": "M1",
            "node_key": "10000000-0000-4000-8000-000000000001",
            "type": "phase",
        },
    ]
    with pytest.raises(SystemExit):
        vr.validate_required_planning_dirs(nodes)


def test_validate_required_planning_dirs_task() -> None:
    nodes = [
        {
            "id": "M1.1",
            "node_key": "10000000-0000-4000-8000-000000000001",
            "type": "task",
        },
    ]
    with pytest.raises(SystemExit):
        vr.validate_required_planning_dirs(nodes)


def test_validate_required_planning_dirs_ok_when_set() -> None:
    nodes = [
        {
            "id": "M1",
            "node_key": "10000000-0000-4000-8000-000000000001",
            "type": "phase",
            "planning_dir": (
                "planning/M1_unnamed_10000000-0000-4000-8000-000000000001.md"
            ),
        },
    ]
    vr.validate_required_planning_dirs(nodes)


# F-003/F-007: agentic_checklist / execution_subtask / contract_citation
# validators were removed (all leaves are agentic by design). Their tests
# used to live here and have been deleted together with the features.


def test_validate_script_exits_zero_on_repo() -> None:
    subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_roadmap.py"),
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        check=True,
    )


def test_validate_node_keys_rejects_empty() -> None:
    nodes = [{"id": "M1", "node_key": ""}]
    with pytest.raises(SystemExit):
        validate_node_keys(nodes)


def test_validate_node_keys_rejects_duplicate() -> None:
    nk = "10000000-0000-4000-8000-000000000001"
    nodes = [
        {"id": "M1", "node_key": nk},
        {"id": "M2", "node_key": nk},
    ]
    with pytest.raises(SystemExit):
        validate_node_keys(nodes)


def test_validate_parents_rejects_unknown_parent() -> None:
    nodes = [
        {
            "id": "M1",
            "node_key": "10000000-0000-4000-8000-000000000001",
            "parent_id": "NO_SUCH_PARENT",
        },
    ]
    with pytest.raises(SystemExit):
        validate_parents(nodes)


def test_validate_dependency_ids_rejects_missing_node_key() -> None:
    k1 = "10000000-0000-4000-8000-000000000001"
    k2 = "20000000-0000-4000-8000-000000000002"
    k_missing = "30000000-0000-4000-8000-000000000003"
    nodes = [
        {"id": "M1", "node_key": k1, "dependencies": [k_missing]},
        {"id": "M2", "node_key": k2, "dependencies": []},
    ]
    with pytest.raises(SystemExit):
        validate_dependency_ids(nodes)


def test_touch_zone_overlap_warns_on_same_path(capsys) -> None:
    entries = [
        {"codename": "a", "touch_zones": ["src/"]},
        {"codename": "b", "touch_zones": ["src/"]},
    ]
    touch_zone_overlap(entries)
    err = capsys.readouterr().err
    assert "overlap" in err.lower()


def test_validate_script_rejects_registry_unknown_node_id(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(DOGFOOD, root)
    (root / "roadmap" / "registry.yaml").write_text(
        "version: 1\n"
        "entries:\n"
        "  - codename: bad-entry\n"
        "    node_id: M999.1\n"
        "    branch: feature/rm-bad\n"
        "    touch_zones: [tests/]\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_roadmap.py"),
            "--repo-root",
            str(root),
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    combined = (r.stderr or "") + (r.stdout or "")
    assert "unknown node_id" in combined


def test_run_validation_requires_implementation_review_when_gate_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "specy_road.bundled_scripts.validate_roadmap_checks.review_required",
        lambda _r: True,
    )
    roadmap = load_roadmap(DOGFOOD)
    registry = {
        "version": 1,
        "entries": [
            {
                "codename": "roadmap-ci",
                "node_id": "M0.2",
                "branch": "feature/rm-roadmap-ci",
                "touch_zones": ["specy_road/bundled_scripts/"],
            }
        ],
    }
    with pytest.raises(SystemExit):
        run_validation(roadmap, registry, True, repo_root=DOGFOOD)


def test_run_validation_accepts_implementation_review_pending_when_gate_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "specy_road.bundled_scripts.validate_roadmap_checks.review_required",
        lambda _r: True,
    )
    roadmap = load_roadmap(DOGFOOD)
    registry = {
        "version": 1,
        "entries": [
            {
                "codename": "roadmap-ci",
                "node_id": "M0.2",
                "branch": "feature/rm-roadmap-ci",
                "touch_zones": ["specy_road/bundled_scripts/"],
                "implementation_review": "pending",
            }
        ],
    }
    run_validation(roadmap, registry, True, repo_root=DOGFOOD)


@pytest.mark.parametrize(
    ("manifest_pin", "requirements", "expected"),
    [
        ("0.2.3", "specy-road==0.1.0\n", ("0.2.3", ".specyrd/manifest.json")),
        (None, "requests>=2\nspecy-road[gui-next] == 0.2.3  # pinned\n", ("0.2.3", "requirements.txt")),
        (None, "specy-road>=0.2\n", None),
    ],
)
def test_the_declared_pin_comes_from_the_manifest_then_requirements(
    tmp_path: Path, manifest_pin: str | None, requirements: str, expected: tuple[str, str] | None
) -> None:
    if manifest_pin is not None:
        (tmp_path / ".specyrd").mkdir()
        (tmp_path / ".specyrd" / "manifest.json").write_text(json.dumps({"pin": manifest_pin}), encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(requirements, encoding="utf-8")

    assert vr.pinned_version(tmp_path) == expected


def test_validate_warns_once_when_the_running_version_is_not_the_pin(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "requirements.txt").write_text("specy-road==0.0.1\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("specy-road==0.0.2\n", encoding="utf-8")

    vr.warn_if_pin_differs(tmp_path)
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert f"pins specy-road 0.0.2 (requirements-dev.txt) but {__version__} is running" in err

    for req in ("requirements.txt", "requirements-dev.txt"):
        (tmp_path / req).write_text(f"specy-road=={__version__}\n", encoding="utf-8")
    vr.warn_if_pin_differs(tmp_path)
    assert capsys.readouterr().err == ""
