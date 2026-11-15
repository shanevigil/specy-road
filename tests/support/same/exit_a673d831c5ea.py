"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

import pytest

def exit_fn(fn, argv: list[str]) -> int:
    """Shared test helper."""
    with pytest.raises(SystemExit) as e:
        fn(argv)
        raise SystemExit(0)
    return e.value.code or 0
