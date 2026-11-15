"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

import pytest
from specy_road.bundled_scripts import review_cli

def _run(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code
