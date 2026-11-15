"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from specy_road.bundled_scripts import brainstorm_cli
import contextlib
import io

def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main([*args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    return code, out.getvalue(), err.getvalue()
