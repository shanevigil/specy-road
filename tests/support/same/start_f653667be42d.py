"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.same.cli_4bb09fdf3883 import _cli

def _start(repo: Path, *extra: str) -> tuple[int, str, str]:
    return _cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1", *extra)
