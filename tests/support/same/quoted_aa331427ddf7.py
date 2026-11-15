"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

import re

def _quoted(block: str) -> list[str]:
    return re.findall(r'"([^"]*)"', block)
