"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from specy_road.history_index import clear_memo
import pytest

@pytest.fixture(autouse=True)
def _no_memo() -> None:
    clear_memo()
