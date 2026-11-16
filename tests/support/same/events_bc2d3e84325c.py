"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

import json

def events(capsys):
    """Shared test helper."""
    out = capsys.readouterr().out.strip().splitlines()
    return [json.loads(line) for line in out if line.strip()]
