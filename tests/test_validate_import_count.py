"""``specy-road validate`` imports at most half the ``specy_road`` modules its M16 baseline did.

The count is taken as ``scripts/lean_metrics.py`` took the baseline in
``constraints/lean-baseline.json``: the same command and boot line, ``PYTHONPROFILEIMPORTTIME=1``,
and the distinct ``specy_road`` module names over the process's import rows. Each command imports
its own module and that module's dependencies only when it runs, so a check validate does not run
costs it nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from tests.helpers import REPO

BASELINE = json.loads((REPO / "constraints" / "lean-baseline.json").read_text(encoding="utf-8"))
RECORDED = BASELINE["metrics"]["validate_imports"]
CLI_BOOT = "import sys; from specy_road.cli import main; sys.argv[0] = 'specy-road'; main()"


def _specy_road_modules(argv: list[str]) -> set[str]:
    proc = subprocess.run(
        [sys.executable, "-c", CLI_BOOT, *argv],
        cwd=REPO,
        env={**os.environ, "PYTHONPROFILEIMPORTTIME": "1", "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    rows = [
        line.split("|")[-1].strip()
        for line in proc.stderr.splitlines()
        if line.startswith("import time:")
    ]
    return {name for name in rows if name.split(".")[0] == "specy_road"}


def test_validate_imports_at_most_half_the_baseline_modules() -> None:
    assert RECORDED["command"] == "specy-road validate --repo-root tests/fixtures/specy_road_dogfood"
    modules = _specy_road_modules(RECORDED["command"].split()[1:])
    limit = RECORDED["specy_road_modules"] // 2
    assert len(modules) <= limit, (
        f"validate imports {len(modules)} specy_road modules (limit {limit}, half the baseline):\n"
        + "\n".join(sorted(modules))
    )
