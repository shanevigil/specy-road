"""Tier A: registry overlay gating + git remote Test Git flag (settings-backed)."""

from __future__ import annotations

from pathlib import Path

import pytest

import roadmap_gui_lib as m
import roadmap_gui_settings as st
import pm_gui_git_remote_verify as v
from specy_road.registry_remote_overlay import registry_remote_overlay_enabled


def _patch_gui_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gui_dir = tmp_path / ".specy-road"
    gui_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(st, "SETTINGS_DIR", gui_dir)
    monkeypatch.setattr(st, "SETTINGS_PATH", gui_dir / "gui-settings.json")
    return gui_dir


def _base_repo(tmp_path: Path) -> Path:
    r = tmp_path / "worktree"
    r.mkdir()
    return r


def test_registry_remote_overlay_enabled_true_when_gates_satisfied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", raising=False)
    _patch_gui_home(tmp_path, monkeypatch)
    repo = _base_repo(tmp_path)
    d = m.default_settings()
    gr = {**d["git_remote"], "repo": "org/repo", "token": "tok"}
    pm = {**d["pm_gui"], "registry_remote_overlay": True}
    m.save_settings_for_repo(
        repo,
        inherit_llm=True,
        inherit_git_remote=True,
        inherit_pm_gui=True,
        llm=d["llm"],
        git_remote=gr,
        pm_gui=pm,
    )
    v.set_git_remote_tested_ok(repo, True)
    assert v.get_git_remote_tested_ok(repo) is True
    assert registry_remote_overlay_enabled(repo) is True


@pytest.mark.parametrize(
    ("repo_slug", "token"),
    [
        ("org/repo", ""),
        ("", "sometoken"),
        ("  ", "tok"),
    ],
)
def test_registry_remote_overlay_enabled_false_without_repo_and_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repo_slug: str,
    token: str,
) -> None:
    monkeypatch.delenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", raising=False)
    _patch_gui_home(tmp_path, monkeypatch)
    repo = _base_repo(tmp_path)
    d = m.default_settings()
    gr = {**d["git_remote"], "repo": repo_slug, "token": token}
    pm = {**d["pm_gui"], "registry_remote_overlay": True}
    m.save_settings_for_repo(
        repo,
        inherit_llm=True,
        inherit_git_remote=True,
        inherit_pm_gui=True,
        llm=d["llm"],
        git_remote=gr,
        pm_gui=pm,
    )
    v.set_git_remote_tested_ok(repo, True)
    assert registry_remote_overlay_enabled(repo) is False


def test_git_remote_tested_ok_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_gui_home(tmp_path, monkeypatch)
    repo = _base_repo(tmp_path)
    assert v.get_git_remote_tested_ok(repo) is False
    v.set_git_remote_tested_ok(repo, True)
    assert v.get_git_remote_tested_ok(repo) is True
    v.set_git_remote_tested_ok(repo, False)
    assert v.get_git_remote_tested_ok(repo) is False


def test_save_settings_clears_git_remote_tested_ok_when_git_remote_identity_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_gui_home(tmp_path, monkeypatch)
    repo = _base_repo(tmp_path)
    d = m.default_settings()
    m.save_settings_for_repo(
        repo,
        inherit_llm=True,
        inherit_git_remote=True,
        inherit_pm_gui=True,
        llm=d["llm"],
        git_remote={**d["git_remote"], "repo": "a/b", "token": "t"},
        pm_gui=d["pm_gui"],
    )
    v.set_git_remote_tested_ok(repo, True)
    assert v.get_git_remote_tested_ok(repo) is True

    m.save_settings_for_repo(
        repo,
        inherit_llm=True,
        inherit_git_remote=True,
        inherit_pm_gui=True,
        llm=d["llm"],
        git_remote={**d["git_remote"], "repo": "c/d", "token": "t"},
        pm_gui=d["pm_gui"],
    )
    assert v.get_git_remote_tested_ok(repo) is False


def test_save_settings_preserves_git_remote_tested_ok_when_only_non_git_fields_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_gui_home(tmp_path, monkeypatch)
    repo = _base_repo(tmp_path)
    d = m.default_settings()
    gr = {**d["git_remote"], "repo": "a/b", "token": "t"}
    m.save_settings_for_repo(
        repo,
        inherit_llm=True,
        inherit_git_remote=True,
        inherit_pm_gui=True,
        llm=d["llm"],
        git_remote=gr,
        pm_gui=d["pm_gui"],
    )
    v.set_git_remote_tested_ok(repo, True)
    m.save_settings_for_repo(
        repo,
        inherit_llm=True,
        inherit_git_remote=True,
        inherit_pm_gui=True,
        llm={**d["llm"], "openai_model": "gpt-4o"},
        git_remote=gr,
        pm_gui=d["pm_gui"],
    )
    assert v.get_git_remote_tested_ok(repo) is True
