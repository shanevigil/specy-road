"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

import pytest
from specy_road.bundled_scripts import session_cli

def cli(*args: str) -> int:
    """Shared test helper."""
    with pytest.raises(SystemExit) as e:
        session_cli.main(list(args))
    return e.value.code or 0
