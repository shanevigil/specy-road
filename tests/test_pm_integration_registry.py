"""Tests for :mod:`specy_road.pm_integration_registry` (integration-branch registry + auto-FF describe)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.helpers import BUNDLED_SCRIPTS

if str(BUNDLED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(BUNDLED_SCRIPTS))
import roadmap_gui_settings as _rgs  # noqa: E402

from specy_road.pm_integration_registry import describe_integration_branch_auto_ff
from specy_road.registry_remote_overlay import merge_registry_with_remote_overlay


def _isolate_gui_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gui = tmp_path / ".specy-road"
    gui.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_rgs, "SETTINGS_DIR", gui)
    monkeypatch.setattr(_rgs, "SETTINGS_PATH", gui / "gui-settings.json")


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _write_gw(repo: Path) -> None:
    p = repo / "roadmap" / "git-workflow.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n",
        encoding="utf-8",
    )


def _minimal_registry(entries: list[dict]) -> str:
    return yaml.dump(
        {"version": 1, "entries": entries},
        default_flow_style=False,
        allow_unicode=True,
    )


@pytest.fixture()
def integration_only_registry_repo(tmp_path: Path) -> Path:
    """``main`` at HEAD has empty registry; ``refs/remotes/origin/main`` has a claim."""
    repo = tmp_path / "integ"
    repo.mkdir()
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.email", "t@example.com")
    _run_git(repo, "config", "user.name", "T")
    roadmap = repo / "roadmap"
    roadmap.mkdir(parents=True, exist_ok=True)
    _write_gw(repo)
    (roadmap / "manifest.json").write_text('{"version":1,"includes":[]}\n', encoding="utf-8")
    (roadmap / "registry.yaml").write_text(_minimal_registry([]), encoding="utf-8")
    _run_git(repo, "add", "roadmap")
    _run_git(repo, "commit", "-m", "init")
    entry = {
        "codename": "trunk",
        "node_id": "M1.0",
        "branch": "feature/rm-x",
        "touch_zones": ["a/"],
    }
    (roadmap / "registry.yaml").write_text(_minimal_registry([entry]), encoding="utf-8")
    _run_git(repo, "add", "roadmap/registry.yaml")
    _run_git(repo, "commit", "-m", "register on trunk")
    tip_remote = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _run_git(repo, "reset", "--hard", "HEAD~1")
    _run_git(repo, "update-ref", "refs/remotes/origin/main", tip_remote)
    return repo


def _init_integration_ff_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "ff"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    roadmap = repo / "roadmap"
    roadmap.mkdir(parents=True)
    _write_gw(repo)
    (roadmap / "manifest.json").write_text(
        '{"version":1,"includes":[]}\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "roadmap"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def test_merge_fills_gap_from_integration_branch_only(
    integration_only_registry_repo: Path,
) -> None:
    head = {"version": 1, "entries": []}
    merged, meta = merge_registry_with_remote_overlay(
        head,
        integration_only_registry_repo,
        "origin",
    )
    assert meta["merged_integration_branch_entries"] == 1
    assert meta["merged_remote_entries"] == 0
    assert meta["integration_branch_ref"] == "refs/remotes/origin/main"
    by_id = {e["node_id"]: e for e in merged.get("entries", [])}
    assert by_id["M1.0"]["codename"] == "trunk"


def test_describe_integration_branch_auto_ff_dirty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_gui_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    repo = _init_integration_ff_repo(tmp_path)
    (repo / "dirty.txt").write_text("z", encoding="utf-8")
    d = describe_integration_branch_auto_ff(repo)
    assert d is not None
    assert d["enabled"] is True
    assert d.get("skipped_reason") == "dirty_working_tree"


def test_describe_integration_branch_auto_ff_up_to_date(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_gui_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    repo = _init_integration_ff_repo(tmp_path)
    tip = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", tip],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    d = describe_integration_branch_auto_ff(repo)
    assert d is not None
    assert d["enabled"] is True
    assert d.get("sync_state") == "up_to_date"
