"""Replay the grind table on another commit's package.

``python -m tests.parity.grind.replay REF``: the goldens must be what the code before the grind
modules moved printed. This extracts ``REF``'s tree (``git archive``) into a temporary directory,
lays this checkout's ``tests/parity/grind/`` (rows, fixture, test and committed goldens) over it,
and runs the table there without regeneration. Every command then runs on ``REF``'s package and is
compared with the goldens committed here. Exit status is pytest's. It is this table's own copy of
the state table's replay (``tests/parity/orchestration_state/replay.py``), which stays as it was.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from tests.helpers import REPO

ROWS_DIR = Path(__file__).resolve().parent
#: Laid over ``REF``'s tree with the goldens.
OVERLAY = ("__init__.py", "fixture.py", "rows.py", "test_grind_rows.py")


def replay(ref: str) -> int:
    """Run the grind table on ``ref``'s package against this checkout's goldens."""
    tree = subprocess.run(["git", "archive", ref], cwd=REPO, capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(tree)) as archive:
            archive.extractall(root, filter="data")
        dest = root / ROWS_DIR.relative_to(REPO)
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        for name in OVERLAY:
            shutil.copy2(ROWS_DIR / name, dest / name)
        shutil.copytree(ROWS_DIR / "golden", dest / "golden")
        argv = [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", "4",
            str(dest / "test_grind_rows.py"),
        ]
        env = {k: v for k, v in os.environ.items() if k != "SPECY_ROAD_PARITY_REGEN"}
        return subprocess.run(argv, cwd=root, env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(replay(sys.argv[1]))
