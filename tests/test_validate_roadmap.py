"""Tests for roadmap validation logic and script."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, REPO, script_subprocess_env

import validate_roadmap as vr
from roadmap_load import load_roadmap
from validate_roadmap_checks import (
    run_validation,
    touch_zone_overlap,
    validate_dependency_ids,
    validate_node_keys,
    validate_parents,
)


def test_warn_phase_status_when_all_descendants_complete_emits(capsys) -> None:
    k1 = "10000000-0000-4000-8000-000000000001"
    k2 = "20000000-0000-4000-8000-000000000002"
    nodes = [
        {
            "id": "M1",
            "node_key": k1,
            "type": "phase",
            "title": "P",
            "status": "In Progress",
            "planning_dir": "planning/M1_x.md",
            "parent_id": None,
        },
        {
            "id": "M1.1",
            "node_key": k2,
            "type": "milestone",
            "title": "M",
            "status": "Complete",
            "planning_dir": "planning/M1.1_y.md",
            "parent_id": "M1",
        },
    ]
    vr.warn_phase_status_when_all_descendants_complete(nodes, no_phase_status_warn=False)
    err = capsys.readouterr().err
    assert "phase 'M1'" in err
    assert "every descendant" in err


def test_warn_phase_status_suppressed_with_flag(capsys) -> None:
    k1 = "10000000-0000-4000-8000-000000000001"
    k2 = "20000000-0000-4000-8000-000000000002"
    nodes = [
        {
            "id": "M1",
            "node_key": k1,
            "type": "phase",
            "title": "P",
            "status": "In Progress",
            "planning_dir": "planning/M1_x.md",
            "parent_id": None,
        },
        {
            "id": "M1.1",
            "node_key": k2,
            "type": "milestone",
            "title": "M",
            "status": "Complete",
            "planning_dir": "planning/M1.1_y.md",
            "parent_id": "M1",
        },
    ]
    vr.warn_phase_status_when_all_descendants_complete(nodes, no_phase_status_warn=True)
    assert capsys.readouterr().err == ""


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
        "validate_roadmap_checks.require_implementation_review_before_finish",
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
        "validate_roadmap_checks.require_implementation_review_before_finish",
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
