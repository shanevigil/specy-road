"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.same.cli_02173e685269 import _cli
import json

def _status(repo: Path, capsys) -> dict:
    capsys.readouterr()
    _cli("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    return json.loads(capsys.readouterr().out)["nodes"][0]
