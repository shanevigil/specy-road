"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

import pytest
from specy_road.bundled_scripts import refresh_profiles as rp

def run_main(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        rp.main(list(args))
        raise SystemExit(0)
    return e.value.code or 0
