"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from specy_road import roadmap_gui_settings as _rgs
import pytest

def isolate_gui_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Shared test helper."""
    gui = tmp_path / ".specy-road"
    gui.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_rgs, "SETTINGS_DIR", gui)
    monkeypatch.setattr(_rgs, "SETTINGS_PATH", gui / "gui-settings.json")
