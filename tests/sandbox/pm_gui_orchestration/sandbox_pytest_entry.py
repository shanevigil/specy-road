"""M17.9 entry for the sandbox's browser-test tool: one pytest test that runs browser_check.py.

The tool runs pytest on an explicit path and reads its JUnit XML. This file is not named ``test_*.py``,
so the repository's own suite never collects it; it runs only when passed by path. It finds the copied
bundle from its own location (the directory holding ``specy_road-*.whl``, ``wheelhouse/`` and
``tests/``), runs the browser check with the same interpreter as pytest, and fails unless every
checklist item passed. ``results.json`` and the screenshots land under the bundle's ``work/``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parents[2]


def test_every_checklist_item_passes() -> None:
    wheels = sorted(BUNDLE.glob("specy_road-*.whl"))
    assert len(wheels) == 1, f"want one specy_road wheel in {BUNDLE}, found {[w.name for w in wheels]}"
    run = subprocess.run(
        [sys.executable, str(HERE / "browser_check.py"), "--wheel", str(wheels[0]),
         "--wheelhouse", str(BUNDLE / "wheelhouse")],
        cwd=BUNDLE, capture_output=True, text=True, timeout=1700)
    print(run.stdout)
    print(run.stderr, file=sys.stderr)
    assert run.returncode == 0, f"browser_check exited {run.returncode}:\n{run.stdout[-3000:]}"
