"""Finish, review-packet paths and merge re-runs in three repository layouts.

Regression 2 needed a nested project whose leaf also touches the git root
outside the project tree; regression 5 needed the same checks beyond the
embedded layout only. See ``docs/design-notes/regression-prevention.md``.
"""

from __future__ import annotations

import subprocess

import pytest

from specy_road.bundled_scripts import finish_task
from specy_road.bundled_scripts import review_packet as rp
from specy_road.finish_implementation_check import (
    implementation_gate_error,
    implementation_paths,
)
from specy_road.review_target import resolve_target
from specy_road.runtime_paths import project_prefix, rebase_to_project
from tests.helpers import REPO, sorted_diff_paths_project_relative
from tests.review_repo_helpers import (
    LAYOUT_FINISH_SHAPES,
    OUTSIDE_ROOT_FILE,
    git,
    git_root_relative,
    make_layout_finish_repo,
    prepare_layout_merge_mode_remote,
    touch_zones_for_layout,
)


def _paths_dropped_before_79eaff3(repo_root, *, zones, remote: str, integration_branch: str):
    """Pre-``79eaff3`` behaviour: paths outside the project never counted toward zones."""
    from specy_road.finish_implementation_check import base_ref, changed_paths as branch_paths, zone_matches

    ref = base_ref(repo_root, remote, integration_branch)
    if ref is None:
        return None
    paths = branch_paths(repo_root, ref)
    if paths is None:
        return None
    prefix = project_prefix(repo_root)
    project_paths = [p for p in (rebase_to_project(path, prefix) for path in paths) if p]
    return [p for p in project_paths if any(zone_matches(z, p) for z in zones)]


@pytest.fixture(params=LAYOUT_FINISH_SHAPES, ids=LAYOUT_FINISH_SHAPES)
def layout(tmp_path, request) -> tuple:
    shape = request.param
    git_top, project = make_layout_finish_repo(tmp_path / shape, shape)
    return git_top, project, shape


def test_layout_fixture_defines_three_shapes() -> None:
    assert set(LAYOUT_FINISH_SHAPES) == {"embedded", "nested", "nested_outside"}


def test_implementation_check_sees_work_in_each_layout(layout) -> None:
    _git_top, project, shape = layout
    zones = touch_zones_for_layout(shape)
    err = implementation_gate_error(
        project,
        node_id="M1.1",
        zones=zones,
        remote="origin",
        integration_branch="dev",
    )
    assert err is None, err


def test_nested_outside_would_fail_the_pre_79eaff3_implementation_paths(tmp_path) -> None:
    _git_top, project = make_layout_finish_repo(tmp_path, "nested_outside")
    zones = touch_zones_for_layout("nested_outside")
    assert _paths_dropped_before_79eaff3(
        project, zones=zones, remote="origin", integration_branch="dev"
    ) == []
    assert implementation_paths(
        project, zones=zones, remote="origin", integration_branch="dev"
    ) == [OUTSIDE_ROOT_FILE]


def test_review_packet_lists_every_changed_path(layout) -> None:
    git_top, project, _shape = layout
    base = git(git_top, "merge-base", "dev", "HEAD")
    expected = sorted_diff_paths_project_relative(project, base, "HEAD")
    target = resolve_target(project, "M1.1")
    paths, _lines = rp.changed_paths_section(project, target)
    assert paths == expected


def test_finish_merge_rerun_is_idempotent(layout, tmp_path, monkeypatch, capsys) -> None:
    git_top, project, shape = layout
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    bare = prepare_layout_merge_mode_remote(git_top, project, tmp_path)

    def finish() -> int:
        with pytest.raises(SystemExit) as exc:
            finish_task.main(["--repo-root", str(project)])
            raise SystemExit(0)
        return exc.value.code or 0

    assert finish() == 0
    capsys.readouterr()
    dev_after_first = git(bare, "rev-parse", "dev")
    reg_path = git_root_relative(git_top, project, "roadmap/registry.yaml")
    reg_after_first = subprocess.check_output(
        ["git", "-C", str(bare), "show", f"dev:{reg_path}"],
    )

    assert finish() == 0
    out = capsys.readouterr().out
    assert "already merged into dev on origin; nothing to do" in out
    assert git(bare, "rev-parse", "dev") == dev_after_first
    reg_after_second = subprocess.check_output(
        ["git", "-C", str(bare), "show", f"dev:{reg_path}"],
    )
    assert reg_after_second == reg_after_first
