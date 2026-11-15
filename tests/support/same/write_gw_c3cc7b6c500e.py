"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path

def _write_gw(repo: Path) -> None:
    p = repo / "roadmap" / "git-workflow.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n",
        encoding="utf-8",
    )
