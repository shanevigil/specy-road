"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import pytest

def run_cli(argv: list[str], root: Path) -> int:
    from specy_road.bundled_scripts.digest_cli import main

    with pytest.raises(SystemExit) as exit_info:
        main([*argv, "--repo-root", str(root)])
    return int(exit_info.value.code or 0)

def headings(text: str) -> list[str]:
    return [ln[3:] for ln in text.splitlines() if ln.startswith("## ")]
