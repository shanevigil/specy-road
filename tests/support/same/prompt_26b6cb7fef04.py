"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path

SLUG = "how-do-we-expand-payments"

def prompt(repo: Path, pass_name: str = "r1") -> str:
    """Shared test helper."""
    return (repo / "work" / f"brainstorm-{SLUG}-{pass_name}-prompt.md").read_text(encoding="utf-8")
