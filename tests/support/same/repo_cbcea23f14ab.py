"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import pytest
from tests.move_node_helpers import wide_fixture

@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    wide_fixture(tmp_path)
    return tmp_path
