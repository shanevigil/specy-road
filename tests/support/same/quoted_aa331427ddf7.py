"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

import re

def quoted(block: str) -> list[str]:
    """Shared test helper."""
    return re.findall(r'"([^"]*)"', block)
