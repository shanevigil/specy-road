"""Tests for scripts/roadmap_gui_lib (PM GUI settings)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import roadmap_gui_lib as m
import roadmap_gui_settings as st


def test_apply_llm_env_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_MAX_TOKENS", raising=False)
    m.apply_llm_env_from_settings(
        {
            "backend": "anthropic",
            "anthropic_api_key": "sk-ant-test",
            "anthropic_model": "claude-3-haiku-20240307",
            "anthropic_max_output_tokens": "4096",
        },
    )
    assert os.environ["SPECY_ROAD_ANTHROPIC_API_KEY"] == "sk-ant-test"
    assert os.environ["SPECY_ROAD_ANTHROPIC_MODEL"] == "claude-3-haiku-20240307"
    assert os.environ["SPECY_ROAD_ANTHROPIC_MAX_TOKENS"] == "4096"


def test_apply_llm_env_anthropic_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_ANTHROPIC_API_KEY", "preset")
    m.apply_llm_env_from_settings(
        {
            "backend": "anthropic",
            "anthropic_api_key": "from_file",
            "anthropic_model": "",
        },
    )
    assert os.environ["SPECY_ROAD_ANTHROPIC_API_KEY"] == "preset"


def test_apply_llm_env_anthropic_model_refreshes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switching models in the GUI must not leave the first model in os.environ."""
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_MAX_TOKENS", raising=False)
    monkeypatch.setenv("SPECY_ROAD_ANTHROPIC_MODEL", "first-model")
    m.apply_llm_env_from_settings(
        {
            "backend": "anthropic",
            "anthropic_api_key": "k",
            "anthropic_model": "second-model",
            "anthropic_max_output_tokens": "8192",
        },
    )
    assert os.environ["SPECY_ROAD_ANTHROPIC_MODEL"] == "second-model"
    assert os.environ["SPECY_ROAD_ANTHROPIC_MAX_TOKENS"] == "8192"


def test_apply_llm_env_anthropic_max_output_tokens_refreshes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_MAX_TOKENS", raising=False)
    m.apply_llm_env_from_settings(
        {
            "backend": "anthropic",
            "anthropic_api_key": "k",
            "anthropic_model": "m",
            "anthropic_max_output_tokens": "1000",
        },
    )
    assert os.environ["SPECY_ROAD_ANTHROPIC_MAX_TOKENS"] == "1000"
    m.apply_llm_env_from_settings(
        {
            "backend": "anthropic",
            "anthropic_api_key": "k",
            "anthropic_model": "m",
            "anthropic_max_output_tokens": "2000",
        },
    )
    assert os.environ["SPECY_ROAD_ANTHROPIC_MAX_TOKENS"] == "2000"


def test_save_settings_obfuscates_anthropic_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(st, "SETTINGS_DIR", tmp_path / ".specy-road")
    monkeypatch.setattr(st, "SETTINGS_PATH", tmp_path / ".specy-road" / "gui-settings.json")
    data = m.default_settings()
    data["llm"]["anthropic_api_key"] = "secret-ant"
    m.save_settings(data)
    raw = json.loads(st.SETTINGS_PATH.read_text(encoding="utf-8"))
    stored = raw["global"]["llm"]["anthropic_api_key"]
    assert isinstance(stored, str)
    assert stored.startswith("__b64__:")
    assert "secret-ant" not in stored
    assert raw.get("version") == st.SETTINGS_FILE_VERSION


def test_v1_flat_file_migrates_to_v2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gui = tmp_path / ".specy-road" / "gui-settings.json"
    monkeypatch.setattr(st, "SETTINGS_DIR", tmp_path / ".specy-road")
    monkeypatch.setattr(st, "SETTINGS_PATH", gui)
    gui.parent.mkdir(parents=True)
    old = {
        "llm": {"backend": "openai", "openai_api_key": "from-v1"},
        "git_remote": {"repo": "o/r", "provider": "github"},
    }
    gui.write_text(json.dumps(old), encoding="utf-8")
    struct = st._read_settings_file_struct()
    assert struct["version"] == st.SETTINGS_FILE_VERSION
    assert struct["global"]["llm"]["openai_api_key"] == "from-v1"
    assert struct["global"]["git_remote"]["repo"] == "o/r"


def test_llm_inherit_off_is_blank_without_project_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Project-only LLM: no merge with global; empty overlay => blank fields."""
    gui = tmp_path / ".specy-road" / "gui-settings.json"
    monkeypatch.setattr(st, "SETTINGS_DIR", tmp_path / ".specy-road")
    monkeypatch.setattr(st, "SETTINGS_PATH", gui)
    m.save_settings(
        {
            "llm": {**m.default_settings()["llm"], "openai_api_key": "global-only"},
            "git_remote": m.default_settings()["git_remote"],
        },
    )
    repo = tmp_path / "proj"
    repo.mkdir()
    blank = st._blank_llm_base()
    m.save_settings_for_repo(
        repo,
        inherit_llm=False,
        inherit_git_remote=False,
        llm=blank,
        git_remote=m.default_settings()["git_remote"],
    )
    eff = m.effective_settings_for_repo(repo)["llm"]
    assert eff["openai_api_key"] == ""
    assert eff["openai_model"] == ""


def test_git_remote_is_per_repository_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Global git_remote in file must not apply to a checkout's effective settings."""
    gui = tmp_path / ".specy-road" / "gui-settings.json"
    monkeypatch.setattr(st, "SETTINGS_DIR", tmp_path / ".specy-road")
    monkeypatch.setattr(st, "SETTINGS_PATH", gui)
    m.save_settings(
        {
            "llm": m.default_settings()["llm"],
            "git_remote": {
                **m.default_settings()["git_remote"],
                "repo": "should-not-appear",
            },
        },
    )
    repo = tmp_path / "r"
    repo.mkdir()
    d = m.default_settings()
    m.save_settings_for_repo(
        repo,
        inherit_llm=True,
        inherit_git_remote=False,
        llm=d["llm"],
        git_remote={**d["git_remote"], "repo": "my/o"},
    )
    assert m.effective_settings_for_repo(repo)["git_remote"]["repo"] == "my/o"


def test_per_repo_llm_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gui = tmp_path / ".specy-road" / "gui-settings.json"
    monkeypatch.setattr(st, "SETTINGS_DIR", tmp_path / ".specy-road")
    monkeypatch.setattr(st, "SETTINGS_PATH", gui)
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    m.save_settings(
        {
            "llm": {**m.default_settings()["llm"], "openai_api_key": "global-key"},
            "git_remote": m.default_settings()["git_remote"],
        },
    )
    d = m.default_settings()
    m.save_settings_for_repo(
        repo_a,
        inherit_llm=False,
        inherit_git_remote=False,
        llm={**d["llm"], "openai_api_key": "key-a"},
        git_remote={**d["git_remote"]},
    )
    assert m.effective_settings_for_repo(repo_a)["llm"]["openai_api_key"] == "key-a"
    assert m.effective_settings_for_repo(repo_b)["llm"]["openai_api_key"] == "global-key"


def test_repo_settings_id_stable(tmp_path: Path) -> None:
    r = tmp_path / "myrepo"
    r.mkdir()
    assert m.repo_settings_id(r) == m.repo_settings_id(r)
