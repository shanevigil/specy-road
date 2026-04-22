"""Smoke tests for reconcile-milestone-status script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import REPO, script_subprocess_env


@pytest.mark.parametrize("extra", [[], ["--fallback-head-delivery"]])
def test_reconcile_dry_run_on_dogfood(extra: list[str]) -> None:
    dog = REPO / "tests" / "fixtures" / "specy_road_dogfood"
    script = (
        REPO / "specy_road" / "bundled_scripts" / "reconcile_milestone_status.py"
    )
    r = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(dog), *extra],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )
    assert r.returncode == 0, r.stderr
    assert "Nothing to reconcile" in r.stdout or r.stdout.strip() != ""
