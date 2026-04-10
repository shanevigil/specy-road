"""Tests for scripts/roadmap_gui_lib (PM GUI settings)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import roadmap_gui_lib as m


def test_apply_llm_env_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_MODEL", raising=False)
    m.apply_llm_env_from_settings(
        {
            "backend": "anthropic",
            "anthropic_api_key": "sk-ant-test",
            "anthropic_model": "claude-3-haiku-20240307",
        },
    )
    assert os.environ["SPECY_ROAD_ANTHROPIC_API_KEY"] == "sk-ant-test"
    assert os.environ["SPECY_ROAD_ANTHROPIC_MODEL"] == "claude-3-haiku-20240307"


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


def test_save_settings_obfuscates_anthropic_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(m, "SETTINGS_DIR", tmp_path / ".specy-road")
    monkeypatch.setattr(m, "SETTINGS_PATH", tmp_path / ".specy-road" / "gui-settings.json")
    data = m.default_settings()
    data["llm"]["anthropic_api_key"] = "secret-ant"
    m.save_settings(data)
    raw = json.loads(m.SETTINGS_PATH.read_text(encoding="utf-8"))
    stored = raw["llm"]["anthropic_api_key"]
    assert isinstance(stored, str)
    assert stored.startswith("__b64__:")
    assert "secret-ant" not in stored
