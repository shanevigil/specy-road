"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

def _section(text: str, heading: str) -> str:
    body = text.split(f"## {heading}\n", 1)[1]
    return body.split("\n## ", 1)[0]
