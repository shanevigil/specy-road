"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.helpers import DOGFOOD
from pathlib import Path
import pytest
import shutil

@pytest.fixture()
def dogfood_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dest = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dest)
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dest))
    return dest
