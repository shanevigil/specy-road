"""Tests for remote registry overlay (git show on remote-tracking feature refs)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.helpers import BUNDLED_SCRIPTS

if str(BUNDLED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(BUNDLED_SCRIPTS))
import pm_gui_git_remote_verify as _pm_git  # noqa: E402

from specy_road.registry_remote_overlay import (
    merge_registry_with_remote_overlay,
    read_registry_at_ref,
    registry_remote_overlay_enabled,
    remote_feature_refs_fingerprint_addendum,
    roadmap_fingerprint_with_remote_refs,
    list_remote_feature_rm_refs,
)
import specy_road.registry_remote_overlay as _registry_overlay  # noqa: E402
from roadmap_gui_lib import roadmap_fingerprint


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _write_gw(repo: Path) -> None:
    p = repo / "roadmap" / "git-workflow.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n",
        encoding="utf-8",
    )


def _minimal_registry(
    entries: list[dict],
) -> str:
    return yaml.dump(
        {"version": 1, "entries": entries},
        default_flow_style=False,
        allow_unicode=True,
    )


@pytest.fixture()
def overlay_repo(tmp_path: Path) -> Path:
    """Git repo: main has empty registry; feature/rm-x has a claim; remote ref simulated."""
    repo = tmp_path / "ov"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "t@example.com")
    _run_git(repo, "config", "user.name", "T")
    roadmap = repo / "roadmap"
    roadmap.mkdir(parents=True, exist_ok=True)
    _write_gw(repo)
    (roadmap / "manifest.json").write_text('{"version":1,"includes":[]}\n', encoding="utf-8")
    (roadmap / "registry.yaml").write_text(
        _minimal_registry([]),
        encoding="utf-8",
    )
    _run_git(repo, "add", "roadmap")
    _run_git(repo, "commit", "-m", "init")
    _run_git(repo, "branch", "-M", "main")

    _run_git(repo, "checkout", "-b", "feature/rm-ovtest")
    entry = {
        "codename": "ovtest",
        "node_id": "M9.9",
        "branch": "feature/rm-ovtest",
        "touch_zones": ["src/"],
    }
    (roadmap / "registry.yaml").write_text(
        _minimal_registry([entry]),
        encoding="utf-8",
    )
    _run_git(repo, "add", "roadmap/registry.yaml")
    _run_git(repo, "commit", "-m", "claim")

    tip = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _run_git(repo, "checkout", "main")
    _run_git(repo, "update-ref", f"refs/remotes/origin/feature/rm-ovtest", tip)
    return repo


def test_list_remote_feature_rm_refs(overlay_repo: Path) -> None:
    refs = list_remote_feature_rm_refs(overlay_repo, "origin")
    assert f"refs/remotes/origin/feature/rm-ovtest" in refs


def test_read_registry_at_ref(overlay_repo: Path) -> None:
    doc = read_registry_at_ref(
        overlay_repo,
        "refs/remotes/origin/feature/rm-ovtest",
        5.0,
    )
    assert doc is not None
    assert any(e.get("node_id") == "M9.9" for e in (doc.get("entries") or []))


def test_merge_fills_gap_from_remote(overlay_repo: Path) -> None:
    head = {"version": 1, "entries": []}
    merged, meta = merge_registry_with_remote_overlay(head, overlay_repo, "origin")
    assert meta["merged_remote_entries"] == 1
    assert meta["remote_refs_scanned"] >= 1
    by_id = {e["node_id"]: e for e in merged.get("entries", [])}
    assert "M9.9" in by_id
    assert by_id["M9.9"]["codename"] == "ovtest"


def test_merge_head_wins_same_node_id(overlay_repo: Path) -> None:
    head = {
        "version": 1,
        "entries": [
            {
                "codename": "head",
                "node_id": "M9.9",
                "branch": "feature/rm-head",
                "touch_zones": ["x"],
            }
        ],
    }
    merged, meta = merge_registry_with_remote_overlay(head, overlay_repo, "origin")
    assert meta["merged_remote_entries"] == 0
    by_id = {e["node_id"]: e for e in merged.get("entries", [])}
    assert by_id["M9.9"]["codename"] == "head"


def test_registry_remote_overlay_enabled_env_and_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", raising=False)
    root = tmp_path / "norepo"
    root.mkdir()
    assert registry_remote_overlay_enabled(root) is False
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", "1")
    assert registry_remote_overlay_enabled(root) is True
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", "0")
    assert registry_remote_overlay_enabled(root) is False


def test_registry_remote_overlay_requires_git_remote_test_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Without env=1, overlay stays off until pm_gui + Test Git + repo/token."""
    monkeypatch.delenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", raising=False)
    root = tmp_path / "r"
    root.mkdir()
    # Isolate from developer ~/.specy-road/gui-settings.json (module binds import at load time).
    monkeypatch.setattr(
        _registry_overlay,
        "effective_settings_for_repo",
        lambda _repo: {
            "llm": {},
            "git_remote": {"repo": "", "token": ""},
            "pm_gui": {"registry_remote_overlay": False},
        },
    )
    monkeypatch.setattr(_pm_git, "get_git_remote_tested_ok", lambda _r: False)
    assert registry_remote_overlay_enabled(root) is False
    monkeypatch.setattr(_pm_git, "get_git_remote_tested_ok", lambda _r: True)
    assert registry_remote_overlay_enabled(root) is False


def test_fingerprint_addendum_zero_when_overlay_off(
    monkeypatch: pytest.MonkeyPatch,
    overlay_repo: Path,
) -> None:
    monkeypatch.delenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", raising=False)
    assert remote_feature_refs_fingerprint_addendum(overlay_repo) == 0


def test_fingerprint_addendum_nonzero_when_overlay_on(
    monkeypatch: pytest.MonkeyPatch,
    overlay_repo: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", "1")
    assert remote_feature_refs_fingerprint_addendum(overlay_repo) != 0


def test_roadmap_fingerprint_combined(
    monkeypatch: pytest.MonkeyPatch,
    overlay_repo: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", "1")
    base = roadmap_fingerprint(overlay_repo)
    combined = roadmap_fingerprint_with_remote_refs(overlay_repo, base)
    assert combined != base
